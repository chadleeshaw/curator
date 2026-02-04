"""
Auto-metadata service for backfilling and syncing periodical metadata.

This service provides comprehensive metadata maintenance:
- Fixes incorrect file paths (e.g., from different environments)
- Backfills derived_metadata for periodicals that don't have it
- Syncs issue_date from derived_metadata
- Queues missing OCR scans
- Queues missing text scans

Can be run manually or scheduled as a background task.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from core.database import DatabaseManager
from core.utils.metadata_builder import (
    build_derived_metadata,
    build_file_scan,
    sync_issue_date_from_derived,
)
from core.utils.files import resolve_periodical_file_path
from core.parsers.parser import Parser
from models.database import Periodical, OCRJob
from services.text_scan_service import TextScanService
from services.ocr.queue import OCRQueueService

logger = logging.getLogger(__name__)


class AutoMetadataService:
    """Service for automatic metadata backfilling and syncing"""

    def __init__(
        self,
        db_manager: DatabaseManager,
        library_base_dir: Optional[str] = None,
        category_prefix: str = "_",
    ):
        """
        Initialize auto-metadata service

        Args:
            db_manager: Database manager instance
            library_base_dir: Optional library base directory for path resolution
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
        """
        self.db_manager = db_manager
        self.parser = Parser()
        self.ocr_service = OCRQueueService(db_manager)
        self.library_base_dir = Path(library_base_dir) if library_base_dir else None
        self.category_prefix = category_prefix

    def run_full_scan(self, session: Session) -> Dict[str, Any]:
        """
        Run full metadata scan on all periodicals.

        This performs:
        1. Backfills derived_metadata for periodicals without it
        2. Syncs issue_date from derived_metadata
        3. Queues missing OCR scans
        4. Queues missing text scans

        Args:
            session: Database session

        Returns:
            Dictionary with statistics
        """
        logger.info("Starting auto-metadata full scan...")

        stats = {
            "total_periodicals": 0,
            "paths_fixed": 0,
            "derived_metadata_backfilled": 0,
            "issue_date_synced": 0,
            "ocr_queued": 0,
            "text_scan_queued": 0,
            "metadata_cleaned": 0,
            "errors": 0,
        }

        # Get all periodicals
        periodicals = session.query(Periodical).all()
        stats["total_periodicals"] = len(periodicals)

        logger.info(f"Processing {len(periodicals)} periodicals...")

        for periodical in periodicals:
            # Capture ID before any operations that might fail
            periodical_id = periodical.id
            try:
                # 0. Fix file path if incorrect (e.g., from different Docker environment)
                if self._fix_file_path(periodical):
                    stats["paths_fixed"] += 1

                # 1. Clean up old/misplaced metadata fields
                if self._cleanup_metadata(periodical):
                    stats["metadata_cleaned"] += 1

                # 2. Always regenerate file_scan and rebuild derived_metadata
                # This ensures stale data is refreshed (e.g., from old parser versions)
                if self._backfill_derived_metadata(periodical, session):
                    stats["derived_metadata_backfilled"] += 1

                # 3. Sync issue_date from derived_metadata
                if periodical.derived_metadata:
                    if self._sync_issue_date(periodical):
                        stats["issue_date_synced"] += 1

                # 4. Queue missing OCR scan
                if self._should_queue_ocr(periodical, session):
                    if self._queue_ocr_scan(periodical, session):
                        stats["ocr_queued"] += 1

                # 5. Queue missing text scan
                if self._should_queue_text_scan(periodical):
                    if self._queue_text_scan(periodical, session):
                        stats["text_scan_queued"] += 1

                # Commit after each periodical to avoid long-running transactions
                session.commit()

            except Exception as e:
                # Rollback on error to continue processing other periodicals
                session.rollback()
                logger.error(f"Error processing periodical {periodical_id}: {e}")
                stats["errors"] += 1

        logger.info(f"Auto-metadata scan complete: {stats}")
        return stats

    def _fix_file_path(self, periodical: Periodical) -> bool:
        """
        Fix incorrect file path in database (e.g., from different Docker environment).

        This handles cases where:
        - Path is stored as absolute from Docker container (e.g., /app/local/data/...)
        - Path needs to be resolved relative to configured library_dir

        Args:
            periodical: Periodical to check and fix

        Returns:
            True if path was fixed, False otherwise
        """
        if not self.library_base_dir:
            return False

        stored_path = Path(periodical.file_path)

        # If path exists as-is, no fix needed
        if stored_path.exists():
            return False

        # Try to resolve the path using utility function
        try:
            resolved = resolve_periodical_file_path(
                stored_path=str(stored_path),
                library_base_dir=self.library_base_dir,
                category_prefix=self.category_prefix,
            )
            # Path was successfully resolved, update database
            periodical.file_path = str(resolved)
            logger.info(f"Fixed file path for periodical {periodical.id}: {stored_path} -> {resolved}")
            return True

        except FileNotFoundError:
            # Last resort: search by filename
            try:
                filename = stored_path.name
                for candidate in self.library_base_dir.rglob(filename):
                    if candidate.is_file():
                        periodical.file_path = str(candidate)
                        logger.warning(
                            f"Fixed file path by name search for periodical {periodical.id}: {stored_path} -> {candidate}"
                        )
                        return True
            except Exception as e:
                logger.warning(f"Failed to fix file path for periodical {periodical.id}: {e}")

        return False

    def _backfill_derived_metadata(self, periodical: Periodical, session: Session) -> bool:
        """
        Backfill derived_metadata from existing data.

        Tries to build derived_metadata from:
        1. Existing parsed_metadata (if available)
        2. Re-parsing filename (always regenerates file_scan to fix stale data)

        Args:
            periodical: Periodical to backfill
            session: Database session

        Returns:
            True if derived_metadata was created, False otherwise
        """
        # Check if parsed_metadata exists
        parsed_metadata = periodical.parsed_metadata or {}

        # Always regenerate file_scan from filename to ensure it's current
        # This fixes stale data from older parser versions
        if periodical.file_path:
            try:
                file_path = Path(periodical.file_path)
                if file_path.exists():
                    # Parse the file to get metadata
                    parsed = self.parser.parse_file(file_path)
                    file_scan = build_file_scan(parsed)

                    # Update parsed_metadata
                    if not periodical.parsed_metadata:
                        periodical.parsed_metadata = {}
                    periodical.parsed_metadata["file_scan"] = file_scan

                    from core.utils.db import mark_json_modified

                    mark_json_modified(periodical, "parsed_metadata")

                    logger.debug(f"Regenerated file_scan for periodical {periodical.id}")
            except Exception as e:
                logger.warning(f"Failed to regenerate file_scan for {periodical.id}: {e}")

        # Build derived_metadata from parsed_metadata
        # Always rebuild to incorporate any updated scan data
        parsed_metadata = periodical.parsed_metadata or {}
        if parsed_metadata.get("file_scan") or parsed_metadata.get("text_scan") or parsed_metadata.get("ocr_scan"):
            periodical.derived_metadata = build_derived_metadata(
                file_scan=parsed_metadata.get("file_scan"),
                text_scan=parsed_metadata.get("text_scan"),
                ocr_scan=parsed_metadata.get("ocr_scan"),
            )

            from core.utils.db import mark_json_modified

            mark_json_modified(periodical, "derived_metadata")

            logger.debug(f"Rebuilt derived_metadata for periodical {periodical.id}")
            return True

        return False

    def _sync_issue_date(self, periodical: Periodical) -> bool:
        """
        Sync issue_date from derived_metadata.

        Args:
            periodical: Periodical to sync

        Returns:
            True if issue_date was updated, False otherwise
        """
        new_issue_date = sync_issue_date_from_derived(periodical.derived_metadata)

        if new_issue_date and new_issue_date != periodical.issue_date:
            old_date = periodical.issue_date.strftime("%Y-%m") if periodical.issue_date else "None"
            periodical.issue_date = new_issue_date
            logger.debug(f"Synced issue_date for {periodical.id}: {old_date} -> {new_issue_date.strftime('%Y-%m')}")
            return True

        return False

    def _should_queue_ocr(self, periodical: Periodical, session: Session) -> bool:
        """
        Check if periodical should be queued for OCR.

        Args:
            periodical: Periodical to check
            session: Database session

        Returns:
            True if should queue OCR, False otherwise
        """
        # Skip if already has OCR scan
        if periodical.parsed_metadata and periodical.parsed_metadata.get("ocr_scan"):
            return False

        # Check if this periodical needs a date scan (flagged during import)
        # These get priority - we need to try harder to find their date/volume
        needs_date_scan = (
            periodical.extra_metadata
            and periodical.extra_metadata.get("needs_date_scan", False)
        )

        # Skip if text scan already found sufficient metadata
        # Text-based PDFs (True PDF, Text PDF) already have extractable text, no need for OCR
        # UNLESS we still need a date scan and text scan didn't find the date
        if periodical.parsed_metadata:
            text_scan = periodical.parsed_metadata.get("text_scan", {})
            if text_scan.get("has_sufficient_metadata", False):
                # If needs_date_scan, check if text scan actually found a date
                if needs_date_scan and not text_scan.get("year"):
                    logger.debug(
                        f"Periodical {periodical.id} needs date scan and text scan didn't find year - will queue OCR"
                    )
                else:
                    return False

        # Skip if no cover path (unless needs_date_scan - try anyway with file path)
        if not periodical.cover_path and not needs_date_scan:
            return False

        # Only queue PDFs for OCR (EPUBs and comics don't need OCR)
        if periodical.file_path:
            file_path = Path(periodical.file_path)
            if file_path.suffix.lower() != ".pdf":
                return False

        # Check if already in OCR queue
        existing_job = (
            session.query(OCRJob)
            .filter(
                OCRJob.periodical_id == periodical.id,
                OCRJob.status.in_(["pending", "in_progress"]),
            )
            .first()
        )

        return existing_job is None

    def _queue_ocr_scan(self, periodical: Periodical, session: Session) -> bool:
        """
        Queue periodical for OCR scan.

        Args:
            periodical: Periodical to queue
            session: Database session

        Returns:
            True if queued, False otherwise
        """
        try:
            # Create OCR job
            job = OCRJob(
                periodical_id=periodical.id,
                status=OCRJob.StatusEnum.PENDING,
                created_at=datetime.now(),
            )
            session.add(job)
            logger.debug(f"Queued OCR scan for periodical {periodical.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue OCR for {periodical.id}: {e}")
            return False

    def _should_queue_text_scan(self, periodical: Periodical) -> bool:
        """
        Check if periodical should be scanned for text.

        Args:
            periodical: Periodical to check

        Returns:
            True if should scan text, False otherwise
        """
        # Skip if already has text scan
        if periodical.parsed_metadata and periodical.parsed_metadata.get("text_scan"):
            return False

        # Only scan PDFs and EPUBs
        if not periodical.file_path:
            return False

        file_path = Path(periodical.file_path)
        if not file_path.exists():
            return False

        extension = file_path.suffix.lower()
        return extension in [".pdf", ".epub"]

    def _queue_text_scan(self, periodical: Periodical, session: Session) -> bool:
        """
        Perform text scan on periodical.

        Args:
            periodical: Periodical to scan
            session: Database session

        Returns:
            True if text scan performed, False otherwise
        """
        try:
            # Perform text scan
            scan_result = TextScanService.scan_document(periodical.file_path)

            if scan_result and scan_result.get("scanned"):
                # Store text scan results
                if not periodical.parsed_metadata:
                    periodical.parsed_metadata = {}
                periodical.parsed_metadata["text_scan"] = scan_result

                # Rebuild derived_metadata
                periodical.derived_metadata = build_derived_metadata(
                    file_scan=periodical.parsed_metadata.get("file_scan"),
                    text_scan=scan_result,
                    ocr_scan=periodical.parsed_metadata.get("ocr_scan"),
                )

                # Sync issue_date
                new_issue_date = sync_issue_date_from_derived(periodical.derived_metadata)
                if new_issue_date:
                    periodical.issue_date = new_issue_date

                from core.utils.db import mark_json_modified

                mark_json_modified(periodical, "parsed_metadata", "derived_metadata")

                logger.debug(f"Performed text scan for periodical {periodical.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to text scan {periodical.id}: {e}")

        return False

    def _cleanup_metadata(self, periodical: Periodical) -> bool:
        """
        Clean up old/misplaced metadata fields from extra_metadata and parsed_metadata.

        Removes:
        - From extra_metadata: duplicate metadata fields (year, month, country, etc.) and old fields
        - From extra_metadata: scan results that belong in parsed_metadata (text_scan, ocr_metadata)
        - Moves text_scan/ocr_metadata from extra_metadata to parsed_metadata if needed

        Args:
            periodical: Periodical to clean up

        Returns:
            True if cleanup was performed, False otherwise
        """
        cleaned = False
        extra = periodical.extra_metadata or {}
        parsed = periodical.parsed_metadata or {}

        # Fields that should be removed from extra_metadata (old/duplicate fields)
        fields_to_remove = [
            "confidence",
            "parse_source",
            "country",
            "special_edition",
            "full_title",
            "year",
            "month",
            "issue_number",
            "volume",
            "language",
        ]

        # Remove old/duplicate fields from extra_metadata
        for field in fields_to_remove:
            if field in extra:
                del extra[field]
                cleaned = True
                logger.debug(f"Removed duplicate field '{field}' from extra_metadata for periodical {periodical.id}")

        # Move scan results from extra_metadata to parsed_metadata
        # Old imports may have stored text_scan/ocr_metadata in extra_metadata
        if "text_scan" in extra:
            parsed["text_scan"] = extra["text_scan"]
            del extra["text_scan"]
            cleaned = True
            logger.debug(f"Moved text_scan from extra_metadata to parsed_metadata for periodical {periodical.id}")

        if "ocr_metadata" in extra:
            # Rename ocr_metadata to ocr_scan for consistency
            parsed["ocr_scan"] = extra["ocr_metadata"]
            del extra["ocr_metadata"]
            cleaned = True
            logger.debug(f"Moved ocr_metadata to parsed_metadata as ocr_scan for periodical {periodical.id}")

        # Save changes if any cleanup was done
        if cleaned:
            periodical.extra_metadata = extra
            periodical.parsed_metadata = parsed
            from core.utils.db import mark_json_modified

            mark_json_modified(periodical, "extra_metadata", "parsed_metadata")

        return cleaned


def run_auto_metadata_task(db_manager: DatabaseManager) -> Dict[str, Any]:
    """
    Run auto-metadata task (standalone function for task runner).

    Args:
        db_manager: Database manager instance

    Returns:
        Dictionary with statistics
    """
    service = AutoMetadataService(db_manager)
    session = db_manager.session_factory()

    try:
        return service.run_full_scan(session)
    finally:
        session.close()
