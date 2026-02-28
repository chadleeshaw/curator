"""
API endpoints for the Issue Discovery & Tracking system.

Provides endpoints for:
- Listing discovered issues with filters
- Viewing issue details
- Manually retrying permanently failed issues
- Viewing search statistics
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import sessionmaker

from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import DiscoveredIssue, DownloadStatus, PeriodicalTracking
from services import IssueDiscoveryService, SearchScheduler
from web.utils.responses import success_response
from web.routers.auth import get_verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discovered-issues", tags=["discovery"])

# Global dependencies
_session_factory: Optional[sessionmaker] = None
_issue_discovery_service: Optional[IssueDiscoveryService] = None
_search_scheduler: Optional[SearchScheduler] = None


def set_dependencies(
    session_factory: sessionmaker,
    issue_discovery_service: IssueDiscoveryService,
    search_scheduler: SearchScheduler,
) -> None:
    """Set router dependencies."""
    global _session_factory, _issue_discovery_service, _search_scheduler
    _session_factory = session_factory
    _issue_discovery_service = issue_discovery_service
    _search_scheduler = search_scheduler


@router.get("")
@handle_api_errors("List discovered issues", logger)
async def list_discovered_issues(
    tracking_id: Optional[int] = Query(None, description="Filter by tracking ID"),
    status: Optional[str] = Query(None, description="Filter by download status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort: str = Query("priority", description="Sort field: priority, first_seen, last_seen"),
    _username: str = Depends(get_verify_token),
) -> Dict[str, Any]:
    """
    List discovered issues with optional filters.

    Returns paginated list of discovered issues sorted by priority (default).

    Query Parameters:
    - tracking_id: Filter by specific periodical
    - status: Filter by download status (can be single or comma-separated: discovered, wanted, queued, downloading, completed, failed, permanently_failed, ignored)
    - limit: Max results (1-500, default 50)
    - offset: Skip results (for pagination)
    - sort: Sort by priority (default), first_seen, or last_seen
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        # Build query
        query = db.query(DiscoveredIssue)

        # Apply filters
        if tracking_id:
            query = query.filter(DiscoveredIssue.tracking_id == tracking_id)

        if status:
            # Validate status (can be single or comma-separated)
            valid_statuses = [
                DownloadStatus.DISCOVERED,
                DownloadStatus.WANTED,
                DownloadStatus.QUEUED,
                DownloadStatus.PENDING,
                DownloadStatus.DOWNLOADING,
                "completed",
                DownloadStatus.FAILED,
                DownloadStatus.PERMANENTLY_FAILED,
                DownloadStatus.IGNORED,
            ]

            # Handle comma-separated statuses
            statuses = [s.strip() for s in status.split(",")]

            # Validate all statuses
            for s in statuses:
                if s not in valid_statuses:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
                    )

            # Filter by status(es)
            if len(statuses) == 1:
                query = query.filter(DiscoveredIssue.download_status == statuses[0])
            else:
                query = query.filter(DiscoveredIssue.download_status.in_(statuses))

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting
        if sort == "first_seen":
            query = query.order_by(desc(DiscoveredIssue.first_seen))
        elif sort == "last_seen":
            query = query.order_by(desc(DiscoveredIssue.last_seen))
        else:  # priority (default)
            query = query.order_by(
                desc(DiscoveredIssue.download_priority),
                DiscoveredIssue.first_seen,
            )

        # Apply pagination
        issues = query.offset(offset).limit(limit).all()

        # Get tracking titles for all issues
        tracking_ids = {issue.tracking_id for issue in issues}
        trackings = db.query(PeriodicalTracking).filter(PeriodicalTracking.id.in_(tracking_ids)).all()
        tracking_map = {t.id: t.title for t in trackings}

        # Build response
        result = []
        for issue in issues:
            result.append(
                {
                    **issue.to_dict(),
                    "tracking_title": tracking_map.get(issue.tracking_id, "Unknown"),
                }
            )

        return {
            "issues": result,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }

    return await with_db_session(_session_factory, operation)


@router.get("/{issue_id}")
@handle_api_errors("Get discovered issue", logger)
async def get_discovered_issue(issue_id: int, _username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Get details for a specific discovered issue.

    Returns full details including tracking information and submission history.
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        issue = db.query(DiscoveredIssue).filter(DiscoveredIssue.id == issue_id).first()

        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Get tracking info
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == issue.tracking_id).first()

        # Get submission history if available
        submission_history = []
        if issue.submission_ids:
            from models.database import DownloadSubmission

            submissions = db.query(DownloadSubmission).filter(DownloadSubmission.id.in_(issue.submission_ids)).all()
            submission_history = [
                {
                    "id": s.id,
                    "job_id": s.job_id,
                    "status": s.status.value if s.status else None,
                    "attempt_count": s.attempt_count,
                    "last_error": s.last_error,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in submissions
            ]

        return {
            **issue.to_dict(),
            "tracking_title": tracking.title if tracking else "Unknown",
            "tracking_info": tracking.to_dict() if tracking else None,
            "submission_history": submission_history,
        }

    return await with_db_session(_session_factory, operation)


@router.post("/{issue_id}/retry")
@handle_api_errors("Retry discovered issue", logger)
async def retry_discovered_issue(
    issue_id: int,
    reset_attempts: bool = Query(True, description="Reset attempt count"),
    _username: str = Depends(get_verify_token),
) -> Dict[str, Any]:
    """
    Manually retry a permanently_failed issue (admin override).

    This resets the issue status from "permanently_failed" to "wanted" so it can be
    downloaded again. Useful when the original failure was temporary.

    Query Parameters:
    - reset_attempts: Whether to reset attempt_count to 0 (default: true)
    """
    if _session_factory is None or _issue_discovery_service is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    def operation(db):
        success = _issue_discovery_service.retry_permanently_failed(issue_id, db, reset_attempts)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Could not retry issue (not found or not marked as permanently_failed)",
            )

        # Get updated issue
        issue = db.query(DiscoveredIssue).filter(DiscoveredIssue.id == issue_id).first()

        return success_response(
            "Issue reset and marked as wanted",
            issue=issue.to_dict() if issue else None,
        )

    return await with_db_session(_session_factory, operation)


@router.get("/stats/summary")
@handle_api_errors("Get discovery statistics", logger)
async def get_discovery_statistics(_username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Get overall statistics for the Issue Discovery & Tracking system.

    Returns counts by status, search statistics, and priority distribution.
    """
    if _session_factory is None or _search_scheduler is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    def operation(db):
        # Get counts by status
        status_counts = {}
        for status in [
            DownloadStatus.DISCOVERED,
            DownloadStatus.WANTED,
            DownloadStatus.QUEUED,
            DownloadStatus.PENDING,
            DownloadStatus.DOWNLOADING,
            "completed",
            DownloadStatus.FAILED,
            DownloadStatus.PERMANENTLY_FAILED,
            DownloadStatus.IGNORED,
        ]:
            count = db.query(DiscoveredIssue).filter(DiscoveredIssue.download_status == status).count()
            status_counts[status] = count

        # Get priority distribution
        high_priority = (
            db.query(DiscoveredIssue)
            .filter(
                and_(
                    DiscoveredIssue.download_status.in_([DownloadStatus.WANTED, DownloadStatus.FAILED]),
                    DiscoveredIssue.download_priority >= 70,
                )
            )
            .count()
        )

        medium_priority = (
            db.query(DiscoveredIssue)
            .filter(
                and_(
                    DiscoveredIssue.download_status.in_([DownloadStatus.WANTED, DownloadStatus.FAILED]),
                    DiscoveredIssue.download_priority >= 40,
                    DiscoveredIssue.download_priority < 70,
                )
            )
            .count()
        )

        low_priority = (
            db.query(DiscoveredIssue)
            .filter(
                and_(
                    DiscoveredIssue.download_status.in_([DownloadStatus.WANTED, DownloadStatus.FAILED]),
                    DiscoveredIssue.download_priority < 40,
                )
            )
            .count()
        )

        # Get search scheduler statistics
        search_stats = _search_scheduler.get_search_statistics(db)

        # Get top providers
        top_providers = (
            db.query(
                DiscoveredIssue.latest_provider,
                func.count(DiscoveredIssue.id).label("count"),  # pylint: disable=not-callable
            )
            .filter(DiscoveredIssue.latest_provider.isnot(None))
            .group_by(DiscoveredIssue.latest_provider)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        return {
            "status_counts": status_counts,
            "priority_distribution": {
                "high": high_priority,
                "medium": medium_priority,
                "low": low_priority,
            },
            "search_stats": search_stats,
            "top_providers": [{"provider": p[0], "count": p[1]} for p in top_providers],
        }

    return await with_db_session(_session_factory, operation)


@router.get("/stats/by-tracking")
@handle_api_errors("Get statistics by tracking", logger)
async def get_statistics_by_tracking(_username: str = Depends(get_verify_token)) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get discovery statistics grouped by tracked periodical.

    Returns issue counts and search statistics for each tracked periodical.
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        # Get all tracking records
        trackings = db.query(PeriodicalTracking).all()

        result = []
        for tracking in trackings:
            # Count issues by status for this tracking
            total = db.query(DiscoveredIssue).filter(DiscoveredIssue.tracking_id == tracking.id).count()

            wanted = (
                db.query(DiscoveredIssue)
                .filter(
                    and_(
                        DiscoveredIssue.tracking_id == tracking.id,
                        DiscoveredIssue.download_status == DownloadStatus.WANTED,
                    )
                )
                .count()
            )

            completed = (
                db.query(DiscoveredIssue)
                .filter(
                    and_(
                        DiscoveredIssue.tracking_id == tracking.id,
                        DiscoveredIssue.download_status == DownloadStatus.COMPLETED,
                    )
                )
                .count()
            )

            permanently_faileds = (
                db.query(DiscoveredIssue)
                .filter(
                    and_(
                        DiscoveredIssue.tracking_id == tracking.id,
                        DiscoveredIssue.download_status == DownloadStatus.PERMANENTLY_FAILED,
                    )
                )
                .count()
            )

            result.append(
                {
                    "tracking_id": tracking.id,
                    "title": tracking.title,
                    "language": tracking.language,
                    "total_discovered": total,
                    "wanted": wanted,
                    "completed": completed,
                    "permanently_faileds": permanently_faileds,
                    "last_searched": (tracking.last_searched.isoformat() if tracking.last_searched else None),
                    "search_interval_hours": tracking.search_interval_hours,
                    "searches_without_new_issues": tracking.searches_without_new_issues,
                    "total_issues_discovered": tracking.total_issues_discovered,
                }
            )

        return {"trackings": result}

    return await with_db_session(_session_factory, operation)


@router.post("/reset-all-search-intervals")
@handle_api_errors("Reset all search intervals", logger)
async def reset_all_search_intervals(_username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Reset all tracked periodicals to the normal search interval.

    This is useful after improving search filters or when periodicals have become
    overly slowed down due to consecutive empty searches.

    All periodicals will be reset to search every 2 hours (normal interval),
    and their "searches_without_new_issues" counter will be reset to 0.
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    if _search_scheduler is None:
        raise HTTPException(status_code=500, detail="Search scheduler not initialized")

    def operation(db):
        stats = _search_scheduler.reset_all_search_intervals(db)
        return success_response(
            f"Reset {stats['reset']} periodicals to normal search interval "
            f"({stats['already_normal']} were already at normal)",
            data={
                "reset_count": stats["reset"],
                "already_normal": stats["already_normal"],
                "normal_interval_hours": _search_scheduler.normal_interval_hours,
            },
        )

    return await with_db_session(_session_factory, operation)
