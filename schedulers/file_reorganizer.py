"""Background task for reorganizing periodical files flagged with needs_reorganization."""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session, sessionmaker
from core.parsers import utc_now

logger = logging.getLogger(__name__)

# Maximum number of periodicals to reorganize per run
DEFAULT_BATCH_SIZE = 20


class FileReorganizer:
    """
    Background task that processes periodicals flagged for reorganization.

    When OCR, text scans, or imports discover new metadata (year, month, volume,
    issue_number), they set extra_metadata.needs_reorganization = True. This
    scheduler consumes that flag and moves files to their correct locations.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        library_base_dir: str,
        category_prefix: str = "_",
        organization_pattern: str = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        """
        Initialize the file reorganizer.

        Args:
            session_factory: SQLAlchemy session factory
            library_base_dir: Base directory for the library
            category_prefix: Prefix for category folders (e.g., "_")
            organization_pattern: Organization pattern for folder structure
            batch_size: Maximum periodicals to process per run
        """
        self.session_factory = session_factory
        self.library_base_dir = library_base_dir
        self.category_prefix = category_prefix
        self.organization_pattern = organization_pattern
        self.batch_size = batch_size

        # Stats for monitoring
        self.stats = {
            "total_runs": 0,
            "total_reorganized": 0,
            "total_skipped": 0,
            "total_errors": 0,
            "last_run_time": None,
        }

    def _find_flagged_periodicals(self, db: Session) -> list:
        """
        Find periodicals flagged for reorganization.

        Args:
            db: SQLAlchemy session

        Returns:
            List of Periodical records needing reorganization
        """
        from models.database import Periodical

        # JSON field query: find records where extra_metadata contains needs_reorganization = True
        # SQLite stores JSON as text, so we use JSON_EXTRACT
        from sqlalchemy import text

        flagged = (
            db.query(Periodical)
            .filter(
                text("json_extract(extra_metadata, '$.needs_reorganization') = 1"),
            )
            .limit(self.batch_size)
            .all()
        )

        return flagged

    def _resolve_organization_pattern(self, periodical: Any, db: Session) -> str:
        """
        Resolve the organization pattern for a periodical.

        Checks for a per-periodical pattern on the tracking record first,
        then falls back to the global organization pattern.

        Args:
            periodical: Periodical database record
            db: SQLAlchemy session

        Returns:
            Organization pattern string, or None for default
        """
        if periodical.tracking_id:
            try:
                from models.database import PeriodicalTracking

                tracking = db.query(PeriodicalTracking).filter_by(id=periodical.tracking_id).first()
                if tracking and tracking.organization_pattern:
                    logger.debug(
                        f"Using per-periodical organization pattern for '{periodical.title}': "
                        f"{tracking.organization_pattern}"
                    )
                    return tracking.organization_pattern
            except Exception:
                logger.debug(f"Failed to look up tracking record for periodical {periodical.id}")

        return self.organization_pattern

    def _reorganize_single(self, periodical: Any, db: Session) -> Dict[str, Any]:
        """
        Reorganize a single periodical's files.

        Uses the FileOrganizer's reorganization logic to move files to the
        correct location based on current metadata.

        Args:
            periodical: Periodical database record
            db: SQLAlchemy session

        Returns:
            Dictionary with result status
        """
        from core.constants import DEFAULT_CATEGORY
        from services.file_organizer import FileOrganizer

        organizer = FileOrganizer(self.library_base_dir, category_prefix=self.category_prefix)

        # Determine category
        category = (
            periodical.extra_metadata.get("category", DEFAULT_CATEGORY)
            if periodical.extra_metadata
            else DEFAULT_CATEGORY
        )
        category_with_prefix = f"{self.category_prefix}{category}"

        # Resolve organization pattern: per-periodical tracking pattern > global pattern
        pattern = self._resolve_organization_pattern(periodical, db)

        # Use the organizer's single-periodical reorganization
        old_directories = set()
        result = organizer._process_periodical_with_error_handling(
            periodical=periodical,
            db_session=db,
            category_with_prefix=category_with_prefix,
            pattern=pattern,
            dry_run=False,
            old_directories=old_directories,
            errors=[],
        )

        # Clean up empty directories left behind
        if old_directories:
            from pathlib import Path

            category_dir = Path(self.library_base_dir) / category_with_prefix
            organizer._safe_cleanup_library_directories(old_directories, category_dir)

        return result

    def _clear_flag(self, periodical: Any, db: Session, result: Dict[str, Any]) -> None:
        """
        Clear the needs_reorganization flag after processing.

        Records the reorganization result in extra_metadata for audit purposes.

        Args:
            periodical: Periodical database record
            db: SQLAlchemy session
            result: Result from reorganization attempt
        """
        from core.utils.db import mark_json_modified

        if not periodical.extra_metadata:
            periodical.extra_metadata = {}

        # Remove the flag
        periodical.extra_metadata.pop("needs_reorganization", None)

        # Record what happened
        periodical.extra_metadata["last_reorganization"] = {
            "timestamp": utc_now().isoformat(),
            "reason": periodical.extra_metadata.pop("reorganization_reason", "unknown"),
            "status": result.get("status", "unknown"),
        }

        mark_json_modified(periodical, "extra_metadata")
        db.commit()

    def run(self) -> Dict[str, Any]:
        """
        Process all periodicals flagged for reorganization.

        Returns:
            Dictionary with processing statistics
        """
        db = self.session_factory()
        try:
            flagged = self._find_flagged_periodicals(db)

            if not flagged:
                logger.debug("File reorganizer: No periodicals flagged for reorganization")
                return {"processed": 0, "reorganized": 0, "skipped": 0, "errors": 0}

            logger.info(f"File reorganizer: Found {len(flagged)} periodicals flagged for reorganization")

            reorganized = 0
            skipped = 0
            errors = 0

            for periodical in flagged:
                try:
                    reason = (
                        periodical.extra_metadata.get("reorganization_reason", "unknown")
                        if periodical.extra_metadata
                        else "unknown"
                    )
                    logger.debug(
                        f"File reorganizer: Processing '{periodical.title}' (id={periodical.id}, reason={reason})"
                    )

                    result = self._reorganize_single(periodical, db)

                    if result.get("status") == "reorganized":
                        reorganized += 1
                        logger.info(f"File reorganizer: Reorganized '{periodical.title}'")
                    else:
                        skipped += 1
                        skip_reason = result.get("reason", "unknown")
                        logger.debug(f"File reorganizer: Skipped '{periodical.title}' ({skip_reason})")

                    # Always clear the flag, whether reorganized or skipped
                    self._clear_flag(periodical, db, result)

                except Exception as e:
                    errors += 1
                    logger.error(
                        f"File reorganizer: Error processing '{periodical.title}' (id={periodical.id}): {e}",
                        exc_info=True,
                    )
                    # Still clear the flag to prevent infinite retry loops
                    try:
                        self._clear_flag(periodical, db, {"status": "error", "error": str(e)})
                    except Exception:
                        logger.error(f"File reorganizer: Failed to clear flag for {periodical.id}")

            # Update stats
            self.stats["total_runs"] += 1
            self.stats["total_reorganized"] += reorganized
            self.stats["total_skipped"] += skipped
            self.stats["total_errors"] += errors
            self.stats["last_run_time"] = utc_now().isoformat()

            stats = {
                "processed": len(flagged),
                "reorganized": reorganized,
                "skipped": skipped,
                "errors": errors,
            }

            if reorganized > 0 or errors > 0:
                logger.info(f"File reorganizer: {stats}")

            return stats

        finally:
            db.close()
