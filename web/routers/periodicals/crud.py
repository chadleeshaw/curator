"""
CRUD operations for periodicals
"""

from pathlib import Path
from typing import Any, Dict

from sqlalchemy import cast, case, func, String

from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import generate_olid
from models.database import Periodical, PeriodicalTracking
from web.schemas import PeriodicalResponse
from web.utils.responses import success_response

from . import _shared

router = _shared.router
logger = _shared.logger


# Helper functions for list_periodicals query building


def _build_group_key_expression():
    """
    Build the group key expression used for grouping periodicals.

    Groups by tracking_id when present, otherwise uses periodical.id.
    This allows tracked items to be grouped together while keeping
    untracked items separate.

    Returns:
        SQLAlchemy case expression for grouping
    """
    return case(
        (Periodical.tracking_id.isnot(None), Periodical.tracking_id),
        else_=Periodical.id,
    )


def _build_date_subquery(db):
    """
    Build subquery to find the most recent issue date for each group.

    Args:
        db: Database session

    Returns:
        SQLAlchemy subquery with group_key, language, and max_date columns
    """
    return (
        db.query(
            _build_group_key_expression().label("group_key"),
            Periodical.language,
            func.max(Periodical.issue_date).label("max_date"),
        )
        .group_by("group_key", Periodical.language)
        .subquery()
    )


def _build_id_subquery(db, date_subquery):
    """
    Build subquery to find the highest ID among records with max_date.

    This acts as a tiebreaker when multiple issues have the same date.

    Args:
        db: Database session
        date_subquery: Subquery from _build_date_subquery

    Returns:
        SQLAlchemy subquery with group_key, language, and max_id columns
    """
    group_key_expr = _build_group_key_expression()
    return (
        db.query(
            group_key_expr.label("group_key"),
            Periodical.language,
            func.max(Periodical.id).label("max_id"),
        )
        .join(
            date_subquery,
            (group_key_expr == date_subquery.c.group_key)
            & (Periodical.language == date_subquery.c.language)
            & (Periodical.issue_date == date_subquery.c.max_date),
        )
        .group_by("group_key", Periodical.language)
        .subquery()
    )


def _build_count_subquery(db):
    """
    Build subquery to count total issues per group.

    Used when sorting by issue_count.

    Args:
        db: Database session

    Returns:
        SQLAlchemy subquery with group_key, language, and issue_count columns
    """
    return (
        db.query(
            _build_group_key_expression().label("group_key"),
            Periodical.language,
            func.count(Periodical.id).label("issue_count"),  # pylint: disable=not-callable
        )
        .group_by("group_key", Periodical.language)
        .subquery()
    )


@router.get("/periodicals")
@handle_api_errors("List periodicals", logger)
async def list_periodicals(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """
    List unique periodicals from library (grouped by title).
    Returns one entry per periodical title with the latest issue's metadata.

    Args:
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        sort_by: Sort field - "title", "category", "issue_date", "created_at", or "issue_count" (default: "title")
        sort_order: Sort direction - "asc" or "desc" (default: "asc")

    Returns:
        List of unique periodicals with their metadata
    """

    def operation(db):
        # Validate sort_order
        is_descending = sort_order.lower() == "desc"

        # Build subqueries for grouping and finding latest issue per group
        date_subquery = _build_date_subquery(db)
        id_subquery = _build_id_subquery(db, date_subquery)
        group_key_expr = _build_group_key_expression()

        # Join to get full magazine record for each group's latest issue
        query = db.query(Periodical).join(
            id_subquery,
            (group_key_expr == id_subquery.c.group_key)
            & (Periodical.language == id_subquery.c.language)
            & (Periodical.id == id_subquery.c.max_id),
        )

        # Left join with tracking to get the primary title for display
        query = query.outerjoin(PeriodicalTracking, Periodical.tracking_id == PeriodicalTracking.id)

        # Calculate issue counts for sorting (if needed)
        if sort_by == "issue_count":
            count_subquery = _build_count_subquery(db)

            # Join the count subquery
            query = query.outerjoin(
                count_subquery,
                (group_key_expr == count_subquery.c.group_key)
                & (Periodical.language == count_subquery.c.language),
            )

            # Sort by issue count
            sort_expr = count_subquery.c.issue_count.desc() if is_descending else count_subquery.c.issue_count.asc()
            query = query.order_by(
                sort_expr,
                func.coalesce(PeriodicalTracking.title, Periodical.title).asc(),
            )
        # Apply sorting - use tracking title when available
        elif sort_by == "category":
            # Sort by category from tracking if available, otherwise fall back to magazine category
            sort_expr = (
                func.coalesce(
                    PeriodicalTracking.category,
                    cast(Periodical.extra_metadata["category"], String),
                ).desc()
                if is_descending
                else func.coalesce(
                    PeriodicalTracking.category,
                    cast(Periodical.extra_metadata["category"], String),
                ).asc()
            )
            query = query.order_by(
                sort_expr,
                func.coalesce(PeriodicalTracking.title, Periodical.title).asc(),
            )
        elif sort_by == "issue_date":
            sort_expr = Periodical.issue_date.desc() if is_descending else Periodical.issue_date.asc()
            query = query.order_by(sort_expr)
        elif sort_by == "created_at":
            sort_expr = Periodical.created_at.desc() if is_descending else Periodical.created_at.asc()
            query = query.order_by(sort_expr)
        else:  # Default to title
            sort_expr = (
                func.coalesce(PeriodicalTracking.title, Periodical.title).desc()
                if is_descending
                else func.coalesce(PeriodicalTracking.title, Periodical.title).asc()
            )
            query = query.order_by(sort_expr)

        magazines = query.offset(skip).limit(limit).all()

        # Get total count of unique groups using helper
        group_key_expr = _build_group_key_expression()
        total_query = db.query(
            func.count(  # pylint: disable=not-callable
                func.distinct(  # pylint: disable=not-callable
                    group_key_expr.concat("_").concat(func.coalesce(Periodical.language, "English"))
                )
            )
        )
        total_titles = total_query.scalar()

        # Get issue counts for each group
        # For tracked items, count all issues with same tracking_id + language
        # For untracked items, count by title + language
        issue_counts = {}
        for mag in magazines:
            if mag.tracking_id:
                # Count all magazines with same tracking_id and language
                key = (mag.tracking_id, mag.language or "English")
                if key not in issue_counts:
                    count = (
                        db.query(Periodical)
                        .filter(
                            Periodical.tracking_id == mag.tracking_id,
                            Periodical.language == mag.language,
                        )
                        .count()
                    )
                    issue_counts[key] = count
            else:
                # Count by title and language for untracked items
                key = (mag.title, mag.language or "English", None)
                if key not in issue_counts:
                    count = (
                        db.query(Periodical)
                        .filter(
                            Periodical.title == mag.title,
                            Periodical.language == mag.language,
                            Periodical.tracking_id.is_(None),
                        )
                        .count()
                    )
                    issue_counts[key] = count

        # Fetch tracking record for each magazine to get display title
        tracking_titles = {}
        for mag in magazines:
            if mag.tracking_id and mag.tracking_id not in tracking_titles:
                tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == mag.tracking_id).first()
                if tracking:
                    tracking_titles[mag.tracking_id] = tracking.title

        # Helper function to get best title (tracking > derived_metadata > database column)
        def get_best_title(mag):
            # Priority 1: Tracking title (if linked to tracking)
            if mag.tracking_id and mag.tracking_id in tracking_titles:
                return tracking_titles[mag.tracking_id]

            # Priority 2: Title from derived_metadata (from best scan source)
            if mag.derived_metadata and mag.derived_metadata.get("title"):
                title_data = mag.derived_metadata["title"]
                if isinstance(title_data, dict) and title_data.get("value"):
                    return title_data["value"]

            # Priority 3: Database column (fallback)
            return mag.title

        return success_response(
            periodicals=[
                {
                    "id": m.id,
                    "title": get_best_title(m),
                    "language": m.language or "English",
                    "issue_date": (m.issue_date.date().isoformat() if m.issue_date else None),
                    "file_path": m.file_path,
                    "cover_path": m.cover_path,
                    "content_hash": m.content_hash,
                    "tracking_id": m.tracking_id,
                    "created_at": (m.created_at.isoformat() if m.created_at else None),
                    "updated_at": (m.updated_at.isoformat() if m.updated_at else None),
                    "metadata": m.extra_metadata,
                    "derived_metadata": m.derived_metadata,
                    "issue_count": issue_counts.get(
                        (
                            (m.tracking_id, m.language or "English")
                            if m.tracking_id
                            else (m.title, m.language or "English", None)
                        ),
                        1,
                    ),
                }
                for m in magazines
            ],
            total=total_titles,
            skip=skip,
            limit=limit,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/languages")
@handle_api_errors("Get languages", logger)
async def get_languages() -> Dict[str, Any]:
    """
    Get unique languages from library with periodical counts.

    Returns:
        List of languages with counts, sorted alphabetically
    """

    def operation(db):
        from sqlalchemy import func

        # Query for unique languages with counts
        # Use COALESCE to handle NULL languages as "English"
        language_counts = (
            db.query(
                func.coalesce(Periodical.language, "English").label("language"),
                func.count(Periodical.id).label("count"),  # pylint: disable=not-callable
            )
            .group_by("language")
            .order_by("language")
            .all()
        )

        return success_response(
            languages=[{"language": lang, "count": count} for lang, count in language_counts],
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/{magazine_id}")
@handle_api_errors("Get magazine", logger)
async def get_magazine(magazine_id: int) -> PeriodicalResponse:
    """Get magazine details"""

    def operation(db):
        magazine = _shared.get_periodical_or_404(db, magazine_id)

        # Use to_dict() to get all fields from the Periodical model
        result = magazine.to_dict()

        # Add legacy 'metadata' field for backward compatibility (points to extra_metadata)
        result["metadata"] = magazine.extra_metadata

        return result

    return await with_db_session(_shared._session_factory, operation)


@router.delete("/periodicals/{magazine_id}")
@handle_api_errors("Delete periodical", logger)
async def delete_periodical(
    magazine_id: int,
    delete_files: bool = False,
    remove_tracking: bool = False,
    delete_all_issues: bool = False,
    mark_as_bad: bool = False,
) -> Dict[str, Any]:
    """
    Delete a periodical from the library

    Args:
        magazine_id: ID of periodical to delete
        delete_files: If True, also delete the PDF and cover files from disk. If False, only remove from database.
        remove_tracking: If True, also remove the tracking record for this periodical.
        delete_all_issues: If True, delete all issues with the same title and language. If False, only delete the single issue.
        mark_as_bad: If True, mark related discovered issues as permanently_failed to prevent automatic re-download.
    """

    def operation(db):
        magazine = _shared.get_periodical_or_404(db, magazine_id)

        # Store title and language for potential deletion of all issues
        title = magazine.title
        language = magazine.language

        # Determine which magazines to delete
        if delete_all_issues:
            # Get all magazines with the same title and language
            magazines_to_delete = (
                db.query(Periodical).filter(Periodical.title == title, Periodical.language == language).all()
            )
        else:
            # Only delete the single specified magazine
            magazines_to_delete = [magazine]

        # Store file paths for potential deletion
        file_paths_to_delete = []
        for mag in magazines_to_delete:
            pdf_path = Path(mag.file_path)
            cover_path = Path(mag.cover_path) if mag.cover_path else None
            file_paths_to_delete.append((pdf_path, cover_path))

        # Delete database entries
        for mag in magazines_to_delete:
            db.delete(mag)

        # Mark related discovered issues as permanently failed if requested
        if mark_as_bad:
            from models.database import DiscoveredIssue

            # Find discovered issues for the deleted magazine(s)
            # Match by tracking_id (periodicals.tracking_id -> discovered_issues.tracking_id)
            tracking_ids = [mag.tracking_id for mag in magazines_to_delete if mag.tracking_id]
            if tracking_ids:
                # Mark all related discovered issues as permanently_failed to prevent re-download
                issues = (
                    db.query(DiscoveredIssue)
                    .filter(
                        DiscoveredIssue.tracking_id.in_(tracking_ids),
                        DiscoveredIssue.download_status.in_(["discovered", "wanted", "failed"]),
                    )
                    .all()
                )

                marked_count = 0
                for issue in issues:
                    issue.download_status = "permanently_failed"
                    issue.last_error = "Manually marked as bad file (user deleted from library)"
                    marked_count += 1

                if marked_count > 0:
                    logger.info(f"Marked {marked_count} discovered issue(s) as permanently failed for: {title}")

        db.commit()

        deleted_count = len(magazines_to_delete)

        # Remove tracking record if requested
        if remove_tracking:
            from models.database import PeriodicalTracking

            olid = generate_olid(title)
            tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
            if tracking:
                db.delete(tracking)
                db.commit()
                logger.info(f"Removed tracking record for: {title}")

        # Delete files from filesystem if requested
        if delete_files:
            files_deleted = 0
            for pdf_path, cover_path in file_paths_to_delete:
                try:
                    if pdf_path.exists():
                        pdf_path.unlink()
                        files_deleted += 1
                        logger.info(f"Deleted PDF file: {pdf_path}")
                except Exception as e:
                    logger.warning(f"Could not delete PDF file {pdf_path}: {e}")

                try:
                    if cover_path and cover_path.exists():
                        cover_path.unlink()
                        logger.info(f"Deleted cover file: {cover_path}")
                except Exception as e:
                    logger.warning(f"Could not delete cover file {cover_path}: {e}")

            logger.info(f"Deleted {deleted_count} issue(s) and files from disk: {title}")
            if deleted_count > 1:
                message = f"Deleted {deleted_count} issues of '{title}' and their files from disk"
            else:
                message = f"Deleted '{title}' and files from disk"
            if mark_as_bad:
                message += " (prevented auto-download)"
            if remove_tracking:
                message += " (tracking removed)"
            return success_response(message)
        else:
            logger.info(f"Deleted {deleted_count} issue(s) from library (files retained): {title}")
            if deleted_count > 1:
                message = f"Removed {deleted_count} issues of '{title}' from library (files retained on disk)"
            else:
                message = f"Removed '{title}' from library (files retained on disk)"
            if mark_as_bad:
                message += " (prevented auto-download)"
            if remove_tracking:
                message += " (tracking removed)"
            return success_response(message)

    return await with_db_session(_shared._session_factory, operation)


@router.post("/purge-database")
@handle_api_errors("Purge database", logger)
async def purge_database() -> Dict[str, Any]:
    """
    Purge all library entries and tracking records from the database.
    Files on disk will NOT be deleted.

    Returns:
        Success message with counts of deleted entries
    """

    def operation(db):
        from models.database import (
            PeriodicalTracking,
            DownloadSubmission,
            OCRJob,
            DiscoveredIssue,
        )

        # Count entries before deletion
        magazine_count = db.query(Periodical).count()
        tracking_count = db.query(PeriodicalTracking).count()
        download_count = db.query(DownloadSubmission).count()
        ocr_count = db.query(OCRJob).count()
        issue_count = db.query(DiscoveredIssue).count()

        # Delete all library entries (will cascade delete OCR jobs due to foreign key)
        db.query(Periodical).delete()

        # Delete all OCR jobs (in case any orphaned jobs exist)
        db.query(OCRJob).delete()

        # Delete all discovered issues (will cascade due to foreign key to tracking)
        db.query(DiscoveredIssue).delete()

        # Delete all tracking records
        db.query(PeriodicalTracking).delete()

        # Delete all download submissions
        db.query(DownloadSubmission).delete()

        # Commit all deletions
        db.commit()

        logger.warning(
            f"Database purged successfully. Removed {magazine_count} library entries, "
            f"{tracking_count} tracking records, {download_count} download submissions, "
            f"{ocr_count} OCR jobs, and {issue_count} discovered issues."
        )

        return success_response(
            message=f"Database purged successfully. Removed {magazine_count} library entries, "
            f"{tracking_count} tracking records, {download_count} downloads, "
            f"{ocr_count} OCR jobs, and {issue_count} discovered issues. "
            f"Files on disk remain untouched.",
            counts={
                "magazines": magazine_count,
                "tracking": tracking_count,
                "downloads": download_count,
                "ocr_jobs": ocr_count,
                "discovered_issues": issue_count,
            },
        )

    return await with_db_session(_shared._session_factory, operation)


@router.post("/purge-cache")
@handle_api_errors("Purge cache", logger)
async def purge_cache() -> Dict[str, Any]:
    """
    Purge all cached search results from the database.
    This will force fresh searches from providers on next query.

    Returns:
        Success message with count of deleted cache entries
    """

    def operation(db):
        from models.database import SearchResult as DBSearchResult

        # Count cache entries before deletion
        cache_count = db.query(DBSearchResult).count()

        # Delete all search result cache entries
        db.query(DBSearchResult).delete()

        # Commit deletion
        db.commit()

        logger.info(f"Search cache purged successfully. Removed {cache_count} cached search results.")

        return success_response(
            message=f"Search cache purged successfully. Removed {cache_count} cached search results.",
            count=cache_count,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.get("/cache/stats")
@handle_api_errors("Get cache stats", logger)
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the search result cache.

    Returns:
        Dictionary with cache statistics including total entries, oldest/newest entries
    """

    def operation(db):
        from models.database import SearchResult as DBSearchResult
        from sqlalchemy import func

        # Get total count
        total = db.query(DBSearchResult).count()

        # Get oldest and newest entries
        oldest = db.query(func.min(DBSearchResult.created_at)).scalar()
        newest = db.query(func.max(DBSearchResult.created_at)).scalar()

        # Get unique query count
        unique_queries = db.query(func.distinct(DBSearchResult.query)).count()

        # Get provider breakdown
        provider_counts = (
            db.query(
                DBSearchResult.provider,
                func.count(DBSearchResult.id),  # pylint: disable=not-callable
            )
            .group_by(DBSearchResult.provider)
            .all()
        )

        return {
            "total_entries": total,
            "unique_queries": unique_queries,
            "oldest_entry": oldest.isoformat() if oldest else None,
            "newest_entry": newest.isoformat() if newest else None,
            "providers": dict(provider_counts),
        }

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/stats/count")
@handle_api_errors("Get periodicals count", logger)
async def get_periodicals_count() -> Dict[str, int]:
    """
    Get total count of periodicals in the library.

    Returns:
        Dictionary with total count
    """
    return await with_db_session(_shared._session_factory, lambda db: {"total": db.query(Periodical).count()})
