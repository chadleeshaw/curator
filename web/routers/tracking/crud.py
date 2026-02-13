"""
Tracking routes - CRUD operations
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Query

from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import (
    generate_olid,
)
from models.database import Periodical, PeriodicalTracking, Stack, StackMembership
from services.file_operations import reorganize_periodical_files
from web.schemas import APIError
from web.utils.responses import success_response, error_response

from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


@router.post(
    "/periodicals/track",
    summary="Start tracking a periodical",
    description="Begin tracking a magazine, comic, or newspaper for automatic downloads.",
    responses={
        200: {
            "description": "Tracking started successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Started tracking Wired",
                        "tracking_id": 1,
                    }
                }
            },
        },
        400: {"description": "Invalid input", "model": APIError},
        500: {"description": "Failed to start tracking", "model": APIError},
    },
)
@handle_api_errors("Start tracking periodical", logger)
async def start_tracking_periodical(
    title: str = Query(...),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    language: Optional[str] = Query("English"),
) -> Dict[str, Any]:
    """Start tracking a periodical"""
    if not title or len(title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Title must be at least 2 characters")

    olid = generate_olid(title)

    def operation(db):
        existing = db.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
        if existing:
            return error_response(
                f"Already tracking '{title}'",
                tracking_id=existing.id,
            )

        tracking = PeriodicalTracking(
            olid=olid,
            title=title.strip(),
            category=category.strip() if category else None,
            language=language.strip() if language else "English",
            country=country.strip() if country else None,
            track_all_editions=False,
            selected_editions={},
            selected_years=[],
            last_metadata_update=datetime.now(UTC),
        )
        db.add(tracking)
        db.commit()

        # Reset skipped feed entries so they get re-evaluated against the new tracking
        if _shared._feed_sync_service:
            try:
                _shared._feed_sync_service.reset_skipped_entries()
            except Exception as e:
                logger.warning(f"Failed to reset skipped feed entries: {e}")

        logger.info(f"Started tracking periodical: {title}")
        return success_response(
            f"Started tracking '{title}'",
            tracking_id=tracking.id,
            olid=olid,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get(
    "/periodicals/tracked",
    summary="List tracked periodicals",
    description="Get a paginated list of all periodicals currently being tracked.",
    responses={
        200: {
            "description": "List retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "tracked": [{"id": 1, "title": "Wired", "publisher": "Condé Nast"}],
                        "total": 1,
                    }
                }
            },
        },
        500: {"description": "Failed to retrieve tracking list", "model": APIError},
    },
)
@handle_api_errors("List tracked periodicals", logger)
async def list_tracked_periodicals(skip: int = 0, limit: int = 50) -> Dict[str, Any]:
    """List all tracked periodicals"""

    def operation(db):
        tracked = db.query(PeriodicalTracking).offset(skip).limit(limit).all()
        total = db.query(PeriodicalTracking).count()

        return success_response(
            None,
            tracked=[
                {
                    "id": m.id,
                    "olid": m.olid,
                    "title": m.title,
                    "category": m.category,
                    "language": m.language,
                    "track_all_editions": m.track_all_editions,
                    "created_at": (m.created_at.isoformat() if m.created_at else None),
                }
                for m in tracked
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/tracking")
@handle_api_errors("List tracked magazines", logger)
async def list_tracked_magazines(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """List all currently tracked magazines"""

    def operation(db):
        is_descending = sort_order.lower() == "desc"
        query = db.query(PeriodicalTracking)

        if sort_by == "category":
            sort_expr = PeriodicalTracking.category.desc() if is_descending else PeriodicalTracking.category.asc()
            query = query.order_by(sort_expr, PeriodicalTracking.title.asc())
        elif sort_by == "tracking_mode":
            if is_descending:
                query = query.order_by(
                    PeriodicalTracking.track_all_editions.asc(),
                    PeriodicalTracking.track_new_only.asc(),
                )
            else:
                query = query.order_by(
                    PeriodicalTracking.track_all_editions.desc(),
                    PeriodicalTracking.track_new_only.desc(),
                )
        elif sort_by == "language":
            sort_expr = PeriodicalTracking.language.desc() if is_descending else PeriodicalTracking.language.asc()
            query = query.order_by(sort_expr, PeriodicalTracking.title.asc())
        elif sort_by == "created_at":
            sort_expr = PeriodicalTracking.created_at.desc() if is_descending else PeriodicalTracking.created_at.asc()
            query = query.order_by(sort_expr)
        elif sort_by == "latest_issue":
            sort_expr = (
                PeriodicalTracking.last_metadata_update.desc()
                if is_descending
                else PeriodicalTracking.last_metadata_update.asc()
            )
            # Put items with no issues (NULL last_metadata_update) at the end
            if is_descending:
                query = query.order_by(
                    PeriodicalTracking.last_metadata_update.is_(None),
                    sort_expr,
                )
            else:
                query = query.order_by(
                    PeriodicalTracking.last_metadata_update.isnot(None),
                    sort_expr,
                )
        elif sort_by == "library_count":
            # library_count is computed post-query; skip SQL ordering here
            pass
        else:
            sort_expr = PeriodicalTracking.title.desc() if is_descending else PeriodicalTracking.title.asc()
            query = query.order_by(sort_expr)

        tracked = query.offset(skip).limit(limit).all()
        total = db.query(PeriodicalTracking).count()

        # Compute library count and failed download count for each tracked periodical
        from models.database import (
            DiscoveredIssue,
            DownloadSubmission,
        )

        tracked_list = []
        for t in tracked:
            library_count = db.query(Periodical).filter(Periodical.tracking_id == t.id).count()

            # Count failed downloads from both sources for backward compatibility:
            # 1. New Issue Discovery system (canonical going forward)
            # 2. Legacy DownloadSubmission system (for historical failures)
            discovered_failed = (
                db.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == t.id,
                    DiscoveredIssue.download_status.in_(["failed", "permanently_failed"]),
                )
                .count()
            )

            legacy_failed = (
                db.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.tracking_id == t.id,
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                )
                .count()
            )

            # Show total of both systems (UI will query both)
            failed_count = discovered_failed + legacy_failed

            # Look up stack membership for this tracking item
            stack_info = {
                "stack_id": None,
                "stack_name": None,
                "stack_slug": None,
                "stack_description": None,
                "stack_categories": [],
            }
            stack_membership = db.query(StackMembership).filter(StackMembership.periodical_tracking_id == t.id).first()
            if stack_membership:
                stack = db.query(Stack).filter(Stack.id == stack_membership.stack_id).first()
                if stack:
                    stack_info = {
                        "stack_id": stack.id,
                        "stack_name": stack.name,
                        "stack_slug": stack.slug,
                        "stack_description": stack.description,
                        "stack_categories": stack.categories or [],
                    }

            tracked_list.append(
                {
                    "id": t.id,
                    "olid": t.olid,
                    "title": t.title,
                    "category": t.category,
                    "language": t.language,
                    "country": t.country,
                    "track_all_editions": t.track_all_editions,
                    "track_new_only": t.track_new_only,
                    "selected_count": (
                        len([v for v in t.selected_editions.values() if v]) if t.selected_editions else 0
                    ),
                    "total_known": t.total_editions_known,
                    "library_count": library_count,
                    "failed_count": failed_count,
                    "created_at": (t.created_at.isoformat() if t.created_at else None),
                    "last_issue_added": (t.last_metadata_update.isoformat() if t.last_metadata_update else None),
                    "stack_id": stack_info["stack_id"],
                    "stack_name": stack_info["stack_name"],
                    "stack_slug": stack_info["stack_slug"],
                    "stack_description": stack_info["stack_description"],
                    "stack_categories": stack_info["stack_categories"],
                }
            )

        # Post-query sort for library_count (computed field, not a SQL column)
        if sort_by == "library_count":
            tracked_list.sort(key=lambda x: x["library_count"], reverse=is_descending)

        return success_response(
            None,
            tracked_magazines=tracked_list,
            total=total,
            skip=skip,
            limit=limit,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/tracking/{tracking_id}")
@handle_api_errors("Get tracking details", logger)
async def get_tracking_details(tracking_id: int) -> Dict[str, Any]:
    """Get detailed tracking information for a specific magazine"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if not tracking:
            raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

        return success_response(
            None,
            tracking={
                "id": tracking.id,
                "olid": tracking.olid,
                "title": tracking.title,
                "category": tracking.category,
                "language": tracking.language,
                "country": tracking.country,
                "download_category": tracking.download_category,
                "first_publish_year": tracking.first_publish_year,
                "total_editions_known": tracking.total_editions_known,
                "track_all_editions": tracking.track_all_editions,
                "track_new_only": tracking.track_new_only,
                "delete_from_client_on_completion": tracking.delete_from_client_on_completion,
                "selected_editions": tracking.selected_editions,
                "selected_years": tracking.selected_years,
                "organization_pattern": tracking.organization_pattern,
                "search_aliases": tracking.search_aliases,
                "metadata": tracking.periodical_metadata,
                "last_metadata_update": (
                    tracking.last_metadata_update.isoformat() if tracking.last_metadata_update else None
                ),
                "created_at": (tracking.created_at.isoformat() if tracking.created_at else None),
            },
        )

    return await with_db_session(_shared._session_factory, operation)


def _reorganize_periodical_files(
    periodical, new_title: str, library_base_dir: Path, category_prefix: str = "_"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Reorganize periodical files to match new title structure.

    This is a wrapper around the shared reorganize_periodical_files utility.

    Args:
        periodical: Periodical database object
        new_title: New title to use for folder organization
        library_base_dir: Base directory for organized files
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Tuple of (new_pdf_path, new_cover_path) or (None, None) if failed
    """
    result = reorganize_periodical_files(
        periodical,
        new_title=new_title,
        library_base_dir=library_base_dir,
        category_prefix=category_prefix,
        update_db=True,
    )
    if result.success:
        return result.new_pdf_path, result.new_cover_path
    else:
        return None, None


@router.delete(
    "/periodicals/tracking/{tracking_id}",
    summary="Stop tracking a periodical",
    description="Remove a periodical from the tracking list. This does not delete downloaded files.",
    responses={
        200: {
            "description": "Tracking stopped successfully",
            "content": {"application/json": {"example": {"success": True, "message": "Stopped tracking 'Wired'"}}},
        },
        404: {"description": ErrorMessages.TRACKING_NOT_FOUND, "model": APIError},
        500: {"description": "Failed to delete tracking", "model": APIError},
    },
)
@handle_api_errors("Delete tracking", logger)
async def delete_tracking(tracking_id: int) -> Dict[str, Any]:
    """Delete a magazine tracking record"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if not tracking:
            raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

        title = tracking.title

        # Clean up stack memberships referencing this tracking
        membership_deleted = (
            db.query(StackMembership)
            .filter(StackMembership.periodical_tracking_id == tracking_id)
            .delete(synchronize_session="fetch")
        )
        if membership_deleted:
            logger.info(f"Removed {membership_deleted} stack membership(s) for tracking: {title}")

        db.delete(tracking)
        db.commit()

        logger.info(f"Deleted tracking for magazine: {title}")
        return success_response(f"Stopped tracking '{title}'")

    return await with_db_session(_shared._session_factory, operation)
