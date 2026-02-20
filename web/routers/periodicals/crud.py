"""
CRUD operations for periodicals
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import cast, case, func, literal, String
from sqlalchemy.orm import Session

from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import generate_olid
from models.database import Periodical, PeriodicalTracking, Stack, StackMembership
from web.schemas import PeriodicalResponse
from web.utils.responses import success_response

from . import _shared

router = _shared.router
logger = _shared.logger


class PeriodicalQueryBuilder:
    """
    Constructs queries to find the latest periodical issue per tracking group.

    Uses string-prefixed group keys to prevent ID namespace collisions.
    """

    def __init__(self, db: Session):
        self.db = db
        self._date_subquery = None
        self._id_subquery = None
        self._count_subquery = None

    def _build_group_key_expression(self):
        """
        Groups tracked items together while keeping untracked items separate.
        Uses string prefixes ("t_" for tracked, "p_" for untracked) to prevent
        namespace collisions between tracking_id and periodical.id integers.
        """
        return case(
            (
                Periodical.tracking_id.isnot(None),
                literal("t_").concat(cast(Periodical.tracking_id, String)),
            ),
            else_=literal("p_").concat(cast(Periodical.id, String)),
        )

    def _build_language_expression(self):
        return func.coalesce(Periodical.language, "English")

    def _build_date_subquery(self):
        if self._date_subquery is None:
            group_key_expr = self._build_group_key_expression()
            lang_expr = self._build_language_expression()
            self._date_subquery = (
                self.db.query(
                    group_key_expr.label("group_key"),
                    lang_expr.label("language"),
                    func.max(Periodical.issue_date).label("max_date"),
                )
                .group_by(group_key_expr, lang_expr)
                .subquery()
            )
        return self._date_subquery

    def _build_id_subquery(self):
        """Build subquery to find highest ID among records with max_date (tiebreaker)."""
        if self._id_subquery is None:
            date_subquery = self._build_date_subquery()
            group_key_expr = self._build_group_key_expression()
            lang_expr = self._build_language_expression()
            self._id_subquery = (
                self.db.query(
                    group_key_expr.label("group_key"),
                    lang_expr.label("language"),
                    func.max(Periodical.id).label("max_id"),
                )
                .join(
                    date_subquery,
                    (group_key_expr == date_subquery.c.group_key)
                    & (lang_expr == date_subquery.c.language)
                    & (Periodical.issue_date == date_subquery.c.max_date),
                )
                .group_by(group_key_expr, lang_expr)
                .subquery()
            )
        return self._id_subquery

    def _build_count_subquery(self):
        if self._count_subquery is None:
            group_key_expr = self._build_group_key_expression()
            lang_expr = self._build_language_expression()
            self._count_subquery = (
                self.db.query(
                    group_key_expr.label("group_key"),
                    lang_expr.label("language"),
                    func.count(Periodical.id).label("issue_count"),  # pylint: disable=not-callable
                )
                .group_by(group_key_expr, lang_expr)
                .subquery()
            )
        return self._count_subquery

    def build_base_query(self):
        """Build query that selects the latest issue per group, joined with tracking for display titles."""
        id_subquery = self._build_id_subquery()
        group_key_expr = self._build_group_key_expression()
        lang_expr = self._build_language_expression()

        query = self.db.query(Periodical).join(
            id_subquery,
            (group_key_expr == id_subquery.c.group_key)
            & (lang_expr == id_subquery.c.language)
            & (Periodical.id == id_subquery.c.max_id),
        )

        # Left join with tracking to get the primary title for display
        return query.outerjoin(PeriodicalTracking, Periodical.tracking_id == PeriodicalTracking.id)

    def apply_sorting(self, query, sort_by: str, is_descending: bool):
        """
        Apply sorting to the query based on sort field and direction.

        Args:
            query: Base SQLAlchemy query
            sort_by: Field to sort by (title, category, issue_date, created_at, issue_count)
            is_descending: True for DESC, False for ASC

        Returns:
            Query with ORDER BY applied
        """
        if sort_by == "issue_count":
            return self._apply_issue_count_sort(query, is_descending)
        elif sort_by == "category":
            return self._apply_category_sort(query, is_descending)
        elif sort_by == "issue_date":
            return self._apply_simple_sort(query, Periodical.issue_date, is_descending)
        elif sort_by == "created_at":
            return self._apply_simple_sort(query, Periodical.created_at, is_descending)
        else:  # Default to title
            return self._apply_title_sort(query, is_descending)

    def _apply_issue_count_sort(self, query, is_descending: bool):
        """Apply sorting by issue count with title as secondary sort."""
        count_subquery = self._build_count_subquery()
        group_key_expr = self._build_group_key_expression()
        lang_expr = self._build_language_expression()

        query = query.outerjoin(
            count_subquery,
            (group_key_expr == count_subquery.c.group_key) & (lang_expr == count_subquery.c.language),
        )

        sort_expr = count_subquery.c.issue_count.desc() if is_descending else count_subquery.c.issue_count.asc()
        return query.order_by(
            sort_expr,
            func.coalesce(PeriodicalTracking.title, Periodical.title).asc(),
        )

    def _apply_category_sort(self, query, is_descending: bool):
        """Apply sorting by category with title as secondary sort."""
        category_expr = func.coalesce(
            PeriodicalTracking.category,
            cast(Periodical.extra_metadata["category"], String),
        )
        sort_expr = category_expr.desc() if is_descending else category_expr.asc()
        return query.order_by(
            sort_expr,
            func.coalesce(PeriodicalTracking.title, Periodical.title).asc(),
        )

    def _apply_title_sort(self, query, is_descending: bool):
        """Apply sorting by title (tracking title preferred over periodical title)."""
        title_expr = func.coalesce(PeriodicalTracking.title, Periodical.title)
        sort_expr = title_expr.desc() if is_descending else title_expr.asc()
        return query.order_by(sort_expr)

    def _apply_simple_sort(self, query, column, is_descending: bool):
        """Apply simple single-column sorting."""
        sort_expr = column.desc() if is_descending else column.asc()
        return query.order_by(sort_expr)

    def get_total_count(self) -> int:
        """Get total count of unique groups (for pagination)."""
        group_key_expr = self._build_group_key_expression()
        return self.db.query(
            func.count(  # pylint: disable=not-callable
                func.distinct(  # pylint: disable=not-callable
                    group_key_expr.concat("_").concat(func.coalesce(Periodical.language, "English"))
                )
            )
        ).scalar()

    def get_issue_counts(self, periodicals: List[Periodical]) -> Dict:
        """
        Get issue counts for each periodical in the list.

        For tracked items, counts all issues with same tracking_id + language.
        For untracked items, counts by title + language.

        Args:
            periodicals: List of Periodical objects

        Returns:
            Dictionary mapping (tracking_id, language) or (title, language, None) to count
        """
        issue_counts = {}
        for periodical in periodicals:
            if periodical.tracking_id:
                key = (periodical.tracking_id, periodical.language or "English")
                if key not in issue_counts:
                    issue_counts[key] = (
                        self.db.query(Periodical)
                        .filter(
                            Periodical.tracking_id == periodical.tracking_id,
                            Periodical.language == periodical.language,
                        )
                        .count()
                    )
            else:
                key = (periodical.title, periodical.language or "English", None)
                if key not in issue_counts:
                    issue_counts[key] = (
                        self.db.query(Periodical)
                        .filter(
                            Periodical.title == periodical.title,
                            Periodical.language == periodical.language,
                            Periodical.tracking_id.is_(None),
                        )
                        .count()
                    )
        return issue_counts

    def get_tracking_titles(self, periodicals: List[Periodical]) -> Dict[int, str]:
        """
        Fetch tracking titles for periodicals with tracking_id.

        Args:
            periodicals: List of Periodical objects

        Returns:
            Dictionary mapping tracking_id to title
        """
        tracking_titles = {}
        for periodical in periodicals:
            if periodical.tracking_id and periodical.tracking_id not in tracking_titles:
                tracking = (
                    self.db.query(PeriodicalTracking).filter(PeriodicalTracking.id == periodical.tracking_id).first()
                )
                if tracking:
                    tracking_titles[periodical.tracking_id] = tracking.title
        return tracking_titles

    def get_best_title(self, periodical: Periodical, tracking_titles: Dict[int, str]) -> str:
        """
        Get the best display title for a periodical.

        Priority: tracking title > derived_metadata title > database column

        Args:
            periodical: Periodical object
            tracking_titles: Dictionary of tracking_id to title

        Returns:
            Best available title string
        """
        # Priority 1: Tracking title (if linked to tracking)
        if periodical.tracking_id and periodical.tracking_id in tracking_titles:
            return tracking_titles[periodical.tracking_id]

        # Priority 2: Title from derived_metadata (from best scan source)
        if periodical.derived_metadata and periodical.derived_metadata.get("title"):
            title_data = periodical.derived_metadata["title"]
            if isinstance(title_data, dict) and title_data.get("value"):
                return title_data["value"]

        # Priority 3: Database column (fallback)
        return periodical.title

    def build_periodical_dict(
        self,
        periodical: Periodical,
        issue_counts: Dict,
        tracking_titles: Dict[int, str],
    ) -> Dict[str, Any]:
        """
        Build dictionary representation of a periodical for API response.

        Args:
            periodical: Periodical object
            issue_counts: Issue count dictionary from get_issue_counts()
            tracking_titles: Tracking titles from get_tracking_titles()

        Returns:
            Dictionary with periodical data
        """
        count_key = (
            (periodical.tracking_id, periodical.language or "English")
            if periodical.tracking_id
            else (periodical.title, periodical.language or "English", None)
        )

        # Look up stack membership
        stack_info = self._get_stack_info_for_periodical(periodical)

        return {
            "id": periodical.id,
            "title": self.get_best_title(periodical, tracking_titles),
            "language": periodical.language or "English",
            "issue_date": (periodical.issue_date.date().isoformat() if periodical.issue_date else None),
            "file_path": periodical.file_path,
            "cover_path": periodical.cover_path,
            "content_hash": periodical.content_hash,
            "tracking_id": periodical.tracking_id,
            "created_at": (periodical.created_at.isoformat() if periodical.created_at else None),
            "updated_at": (periodical.updated_at.isoformat() if periodical.updated_at else None),
            "metadata": periodical.extra_metadata,
            "derived_metadata": periodical.derived_metadata,
            "issue_count": issue_counts.get(count_key, 1),
            "stack_id": stack_info.get("stack_id"),
            "stack_name": stack_info.get("stack_name"),
            "stack_slug": stack_info.get("stack_slug"),
        }

    def _get_stack_info_for_periodical(self, periodical: Periodical) -> Dict[str, Any]:
        """
        Get stack information for a periodical.

        Checks both tracking-based and direct periodical memberships.

        Args:
            periodical: Periodical object

        Returns:
            Dictionary with stack_id, stack_name, stack_slug (or empty values)
        """
        membership = None
        if periodical.tracking_id:
            membership = (
                self.db.query(StackMembership)
                .filter(StackMembership.periodical_tracking_id == periodical.tracking_id)
                .first()
            )
        if not membership:
            membership = self.db.query(StackMembership).filter(StackMembership.periodical_id == periodical.id).first()

        if membership:
            stack = self.db.query(Stack).filter(Stack.id == membership.stack_id).first()
            if stack:
                return {
                    "stack_id": stack.id,
                    "stack_name": stack.name,
                    "stack_slug": stack.slug,
                }

        return {"stack_id": None, "stack_name": None, "stack_slug": None}


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
        builder = PeriodicalQueryBuilder(db)
        is_descending = sort_order.lower() == "desc"

        # Build and execute query
        query = builder.build_base_query()
        query = builder.apply_sorting(query, sort_by, is_descending)
        periodicals = query.offset(skip).limit(limit).all()

        # Gather metadata for response
        total = builder.get_total_count()
        issue_counts = builder.get_issue_counts(periodicals)
        tracking_titles = builder.get_tracking_titles(periodicals)

        return success_response(
            periodicals=[builder.build_periodical_dict(m, issue_counts, tracking_titles) for m in periodicals],
            total=total,
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
@handle_api_errors("Get periodical", logger)
async def get_periodical(magazine_id: int) -> PeriodicalResponse:
    """Get periodical details"""

    def operation(db):
        periodical = _shared.get_periodical_or_404(db, magazine_id)

        # Use to_dict() to get all fields from the Periodical model
        result = periodical.to_dict()

        # Add legacy 'metadata' field for backward compatibility (points to extra_metadata)
        result["metadata"] = periodical.extra_metadata

        return result

    return await with_db_session(_shared._session_factory, operation)


def _get_periodicals_to_delete(db: Session, periodical: Periodical, delete_all_issues: bool) -> List[Periodical]:
    """Get list of periodicals to delete based on deletion scope."""
    if delete_all_issues:
        return (
            db.query(Periodical)
            .filter(
                Periodical.title == periodical.title,
                Periodical.language == periodical.language,
            )
            .all()
        )
    return [periodical]


def _collect_file_paths(
    periodicals: List[Periodical],
) -> List[Tuple[Path, Optional[Path]]]:
    """Collect file paths from periodicals for potential deletion."""
    file_paths = []
    for periodical in periodicals:
        pdf_path = Path(periodical.file_path)
        cover_path = Path(periodical.cover_path) if periodical.cover_path else None
        file_paths.append((pdf_path, cover_path))
    return file_paths


def _delete_associated_ocr_jobs(db: Session, periodical_ids: List[int], title: str) -> None:
    """Delete OCR jobs associated with periodicals."""
    from models.database import OCRJob

    ocr_deleted = db.query(OCRJob).filter(OCRJob.periodical_id.in_(periodical_ids)).delete(synchronize_session="fetch")
    if ocr_deleted:
        logger.info(f"Deleted {ocr_deleted} OCR job(s) for periodical(s): {title}")


def _delete_periodical_stack_memberships(db: Session, periodical_ids: List[int], title: str) -> None:
    """Delete stack memberships for periodicals."""
    membership_deleted = (
        db.query(StackMembership)
        .filter(StackMembership.periodical_id.in_(periodical_ids))
        .delete(synchronize_session="fetch")
    )
    if membership_deleted:
        logger.info(f"Removed {membership_deleted} stack membership(s) for periodical(s): {title}")


def _mark_discovered_issues_as_failed(db: Session, periodicals: List[Periodical], title: str) -> None:
    """Mark related discovered issues as permanently failed to prevent re-download."""
    from models.database import DiscoveredIssue

    tracking_ids = [p.tracking_id for p in periodicals if p.tracking_id]
    if not tracking_ids:
        return

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


def _delete_tracking_record(db: Session, title: str) -> None:
    """Delete tracking record and associated stack memberships."""
    from models.database import PeriodicalTracking

    olid = generate_olid(title)
    tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
    if not tracking:
        return

    tracking_membership_deleted = (
        db.query(StackMembership)
        .filter(StackMembership.periodical_tracking_id == tracking.id)
        .delete(synchronize_session="fetch")
    )
    if tracking_membership_deleted:
        logger.info(f"Removed {tracking_membership_deleted} stack membership(s) for tracking: {title}")

    db.delete(tracking)
    db.commit()
    logger.info(f"Removed tracking record for: {title}")


def _delete_periodical_files(file_paths: List[Tuple[Path, Optional[Path]]]) -> None:
    """Delete periodical PDF and cover files from filesystem."""
    for pdf_path, cover_path in file_paths:
        try:
            if pdf_path.exists():
                pdf_path.unlink()
                logger.info(f"Deleted PDF file: {pdf_path}")
        except Exception as e:
            logger.warning(f"Could not delete PDF file {pdf_path}: {e}")

        try:
            if cover_path and cover_path.exists():
                cover_path.unlink()
                logger.info(f"Deleted cover file: {cover_path}")
        except Exception as e:
            logger.warning(f"Could not delete cover file {cover_path}: {e}")


def _build_deletion_message(
    title: str,
    deleted_count: int,
    files_deleted: bool,
    mark_as_bad: bool,
    remove_tracking: bool,
) -> str:
    """Build user-facing deletion success message."""
    if files_deleted:
        if deleted_count > 1:
            message = f"Deleted {deleted_count} issues of '{title}' and their files from disk"
        else:
            message = f"Deleted '{title}' and files from disk"
    else:
        if deleted_count > 1:
            message = f"Removed {deleted_count} issues of '{title}' from library (files retained on disk)"
        else:
            message = f"Removed '{title}' from library (files retained on disk)"

    if mark_as_bad:
        message += " (prevented auto-download)"
    if remove_tracking:
        message += " (tracking removed)"

    return message


@router.delete("/periodicals/{magazine_id}")
@handle_api_errors("Delete periodical", logger)
async def delete_periodical(
    magazine_id: int,
    delete_files: bool = False,
    remove_tracking: bool = False,
    delete_all_issues: bool = False,
    mark_as_bad: bool = False,
) -> Dict[str, Any]:
    """Delete a periodical from the library"""

    def delete_periodical_operation(db):
        periodical = _shared.get_periodical_or_404(db, magazine_id)
        title = periodical.title

        periodicals_to_delete = _get_periodicals_to_delete(db, periodical, delete_all_issues)
        file_paths = _collect_file_paths(periodicals_to_delete)
        periodical_ids = [p.id for p in periodicals_to_delete]

        _delete_associated_ocr_jobs(db, periodical_ids, title)
        _delete_periodical_stack_memberships(db, periodical_ids, title)

        for p in periodicals_to_delete:
            db.delete(p)

        if mark_as_bad:
            _mark_discovered_issues_as_failed(db, periodicals_to_delete, title)

        db.commit()

        if remove_tracking:
            _delete_tracking_record(db, title)

        if delete_files:
            _delete_periodical_files(file_paths)
            logger.info(f"Deleted {len(periodicals_to_delete)} issue(s) and files from disk: {title}")
        else:
            logger.info(f"Deleted {len(periodicals_to_delete)} issue(s) from library (files retained): {title}")

        message = _build_deletion_message(
            title,
            len(periodicals_to_delete),
            delete_files,
            mark_as_bad,
            remove_tracking,
        )
        return success_response(message)

    return await with_db_session(_shared._session_factory, delete_periodical_operation)


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

        # Delete all stack memberships and stacks
        membership_count = db.query(StackMembership).delete()
        stack_count = db.query(Stack).delete()

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
            f"{ocr_count} OCR jobs, {issue_count} discovered issues, "
            f"{stack_count} stacks, and {membership_count} stack memberships."
        )

        return success_response(
            message=f"Database purged successfully. Removed {magazine_count} library entries, "
            f"{tracking_count} tracking records, {download_count} downloads, "
            f"{ocr_count} OCR jobs, {issue_count} discovered issues, "
            f"and {stack_count} stacks. "
            f"Files on disk remain untouched.",
            counts={
                "magazines": magazine_count,
                "tracking": tracking_count,
                "downloads": download_count,
                "ocr_jobs": ocr_count,
                "discovered_issues": issue_count,
                "stacks": stack_count,
                "stack_memberships": membership_count,
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
