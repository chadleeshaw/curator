"""
CRUD operations for periodicals
"""

from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils.general import generate_olid
from core.utils import run_in_thread
from models.database import Periodical
from web.schemas import PeriodicalResponse

from . import _shared

router = _shared.router
logger = _shared.logger


@router.get("/periodicals")
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
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                # Validate sort_order
                is_descending = sort_order.lower() == "desc"

                # Group by tracking_id (when present) OR title+language (for untracked items)
                # This allows merged tracking records to show as one entry while preserving
                # separate entries for untracked items
                from sqlalchemy import func, case, String, cast
                from models.database import PeriodicalTracking

                # For grouping, use tracking.title when tracking_id exists, otherwise use magazine.title
                # This ensures merged items show under the primary tracking title
                # Subquery 1: Find the max issue_date for each group
                date_subquery = (
                    db_session.query(
                        case(
                            (
                                Periodical.tracking_id.isnot(None),
                                Periodical.tracking_id,
                            ),
                            else_=Periodical.id,
                        ).label("group_key"),
                        Periodical.language,
                        func.max(Periodical.issue_date).label("max_date"),
                    )
                    .group_by("group_key", Periodical.language)
                    .subquery()
                )

                # Subquery 2: Among rows with max_date, find the max id (tiebreaker for same date)
                id_subquery = (
                    db_session.query(
                        case(
                            (
                                Periodical.tracking_id.isnot(None),
                                Periodical.tracking_id,
                            ),
                            else_=Periodical.id,
                        ).label("group_key"),
                        Periodical.language,
                        func.max(Periodical.id).label("max_id"),
                    )
                    .join(
                        date_subquery,
                        (
                            case(
                                (
                                    Periodical.tracking_id.isnot(None),
                                    Periodical.tracking_id,
                                ),
                                else_=Periodical.id,
                            )
                            == date_subquery.c.group_key
                        )
                        & (Periodical.language == date_subquery.c.language)
                        & (Periodical.issue_date == date_subquery.c.max_date),
                    )
                    .group_by("group_key", Periodical.language)
                    .subquery()
                )

                # Join to get full magazine record for each group's latest issue
                query = db_session.query(Periodical).join(
                    id_subquery,
                    (
                        case(
                            (
                                Periodical.tracking_id.isnot(None),
                                Periodical.tracking_id,
                            ),
                            else_=Periodical.id,
                        )
                        == id_subquery.c.group_key
                    )
                    & (Periodical.language == id_subquery.c.language)
                    & (Periodical.id == id_subquery.c.max_id),
                )

                # Left join with tracking to get the primary title for display
                query = query.outerjoin(PeriodicalTracking, Periodical.tracking_id == PeriodicalTracking.id)

                # Calculate issue counts for sorting (if needed)
                if sort_by == "issue_count":
                    # Create subquery to count issues for each group
                    count_subquery = (
                        db_session.query(
                            case(
                                (
                                    Periodical.tracking_id.isnot(None),
                                    Periodical.tracking_id,
                                ),
                                else_=Periodical.id,
                            ).label("group_key"),
                            Periodical.language,
                            func.count(Periodical.id).label("issue_count"),  # pylint: disable=not-callable
                        )
                        .group_by("group_key", Periodical.language)
                        .subquery()
                    )

                    # Join the count subquery
                    query = query.outerjoin(
                        count_subquery,
                        (
                            case(
                                (
                                    Periodical.tracking_id.isnot(None),
                                    Periodical.tracking_id,
                                ),
                                else_=Periodical.id,
                            )
                            == count_subquery.c.group_key
                        )
                        & (Periodical.language == count_subquery.c.language),
                    )

                    # Sort by issue count
                    sort_expr = (
                        count_subquery.c.issue_count.desc() if is_descending else count_subquery.c.issue_count.asc()
                    )
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

                # Get total count of unique groups
                total_query = db_session.query(
                    func.count(  # pylint: disable=not-callable
                        func.distinct(  # pylint: disable=not-callable
                            case(
                                (
                                    Periodical.tracking_id.isnot(None),
                                    Periodical.tracking_id,
                                ),
                                else_=Periodical.id,
                            )
                            .concat("_")
                            .concat(func.coalesce(Periodical.language, "English"))
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
                                db_session.query(Periodical)
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
                                db_session.query(Periodical)
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
                        tracking = (
                            db_session.query(PeriodicalTracking)
                            .filter(PeriodicalTracking.id == mag.tracking_id)
                            .first()
                        )
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

                return {
                    "periodicals": [
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
                    "total": total_titles,
                    "skip": skip,
                    "limit": limit,
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"List periodicals error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/languages")
async def get_languages() -> Dict[str, Any]:
    """
    Get unique languages from library with periodical counts.

    Returns:
        List of languages with counts, sorted alphabetically
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                from sqlalchemy import func

                # Query for unique languages with counts
                # Use COALESCE to handle NULL languages as "English"
                language_counts = (
                    db_session.query(
                        func.coalesce(Periodical.language, "English").label("language"),
                        func.count(Periodical.id).label("count"),  # pylint: disable=not-callable
                    )
                    .group_by("language")
                    .order_by("language")
                    .all()
                )

                return {
                    "success": True,
                    "languages": [{"language": lang, "count": count} for lang, count in language_counts],
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Get languages error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}")
async def get_magazine(magazine_id: int) -> PeriodicalResponse:
    """Get magazine details"""
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Use to_dict() to get all fields from the Periodical model
                result = magazine.to_dict()

                # Add legacy 'metadata' field for backward compatibility (points to extra_metadata)
                result["metadata"] = magazine.extra_metadata

                return result
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Get magazine error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/periodicals/{magazine_id}")
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
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Store title and language for potential deletion of all issues
                title = magazine.title
                language = magazine.language

                # Determine which magazines to delete
                if delete_all_issues:
                    # Get all magazines with the same title and language
                    magazines_to_delete = (
                        db_session.query(Periodical)
                        .filter(Periodical.title == title, Periodical.language == language)
                        .all()
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
                    db_session.delete(mag)

                # Mark related discovered issues as permanently failed if requested
                if mark_as_bad:
                    from models.database import DiscoveredIssue

                    # Find discovered issues for the deleted magazine(s)
                    # Match by tracking_id (periodicals.tracking_id -> discovered_issues.tracking_id)
                    tracking_ids = [mag.tracking_id for mag in magazines_to_delete if mag.tracking_id]
                    if tracking_ids:
                        # Mark all related discovered issues as permanently_failed to prevent re-download
                        issues = (
                            db_session.query(DiscoveredIssue)
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

                db_session.commit()

                deleted_count = len(magazines_to_delete)

                # Remove tracking record if requested
                if remove_tracking:
                    from models.database import PeriodicalTracking

                    olid = generate_olid(title)
                    tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
                    if tracking:
                        db_session.delete(tracking)
                        db_session.commit()
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
                    return {
                        "success": True,
                        "message": message,
                    }
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
                    return {
                        "success": True,
                        "message": message,
                    }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete periodical error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge-database")
async def purge_database() -> Dict[str, Any]:
    """
    Purge all library entries and tracking records from the database.
    Files on disk will NOT be deleted.

    Returns:
        Success message with counts of deleted entries
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                from models.database import PeriodicalTracking, DownloadSubmission

                # Count entries before deletion
                magazine_count = db_session.query(Periodical).count()
                tracking_count = db_session.query(PeriodicalTracking).count()
                download_count = db_session.query(DownloadSubmission).count()

                # Delete all library entries
                db_session.query(Periodical).delete()

                # Delete all tracking records
                db_session.query(PeriodicalTracking).delete()

                # Delete all download submissions
                db_session.query(DownloadSubmission).delete()

                # Commit all deletions
                db_session.commit()

                logger.warning(
                    f"Database purged successfully. Removed {magazine_count} library entries, "
                    f"{tracking_count} tracking records, and {download_count} download submissions."
                )

                return {
                    "success": True,
                    "message": f"Database purged successfully. Removed {magazine_count} library entries, "
                    f"{tracking_count} tracking records, and {download_count} downloads. "
                    f"Files on disk remain untouched.",
                    "counts": {
                        "magazines": magazine_count,
                        "tracking": tracking_count,
                        "downloads": download_count,
                    },
                }

            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Purge database error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge-cache")
async def purge_cache() -> Dict[str, Any]:
    """
    Purge all cached search results from the database.
    This will force fresh searches from providers on next query.

    Returns:
        Success message with count of deleted cache entries
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                from models.database import SearchResult as DBSearchResult

                # Count cache entries before deletion
                cache_count = db_session.query(DBSearchResult).count()

                # Delete all search result cache entries
                db_session.query(DBSearchResult).delete()

                # Commit deletion
                db_session.commit()

                logger.info(f"Search cache purged successfully. Removed {cache_count} cached search results.")

                return {
                    "success": True,
                    "message": f"Search cache purged successfully. Removed {cache_count} cached search results.",
                    "count": cache_count,
                }

            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Purge cache error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the search result cache.

    Returns:
        Dictionary with cache statistics including total entries, oldest/newest entries
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                from models.database import SearchResult as DBSearchResult
                from sqlalchemy import func

                # Get total count
                total = db_session.query(DBSearchResult).count()

                # Get oldest and newest entries
                oldest = db_session.query(func.min(DBSearchResult.created_at)).scalar()
                newest = db_session.query(func.max(DBSearchResult.created_at)).scalar()

                # Get unique query count
                unique_queries = db_session.query(func.distinct(DBSearchResult.query)).count()

                # Get provider breakdown
                provider_counts = (
                    db_session.query(
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

            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Get cache stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/stats/count")
async def get_periodicals_count() -> Dict[str, int]:
    """
    Get total count of periodicals in the library.

    Returns:
        Dictionary with total count
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                total = db_session.query(Periodical).count()
                return {"total": total}
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except Exception as e:
        logger.error(f"Get periodicals count error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
