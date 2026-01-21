"""
Auto-metadata service for backfilling and syncing periodical metadata.

This service provides comprehensive metadata maintenance:
- Backfills derived_metadata for periodicals that don't have it
- Syncs issue_date from derived_metadata
- Queues missing OCR scans
- Queues missing text scans

Can be run manually or scheduled as a background task.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from sqlalchemy.orm import Session

from core.database import DatabaseManager
from core.utils.metadata_builder import (
    build_derived_metadata,
    build_file_scan,
    sync_issue_date_from_derived,
)
from core.parsers.parser import Parser
from models.database import Periodical, OCRJob
from services.text_scan_service import TextScanService
from services.ocr.queue import OCRQueueService

logger = logging.getLogger(__name__)


class AutoMetadataService:
    """Service for automatic metadata backfilling and syncing"""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize auto-metadata service

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.parser = Parser()
        self.ocr_service = OCRQueueService(db_manager)

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
            "derived_metadata_backfilled": 0,
            "issue_date_synced": 0,
            "ocr_queued": 0,
            "text_scan_queued": 0,
            "errors": 0,
        }

        # Get all periodicals
        periodicals = session.query(Periodical).all()
        stats["total_periodicals"] = len(periodicals)

        logger.info(f"Processing {len(periodicals)} periodicals...")

        for periodical in periodicals:
            try:
                # 1. Always regenerate file_scan and rebuild derived_metadata
                # This ensures stale data is refreshed (e.g., from old parser versions)
                if self._backfill_derived_metadata(periodical, session):
                    stats["derived_metadata_backfilled"] += 1

                # 2. Sync issue_date from derived_metadata
                if periodical.derived_metadata:
                    if self._sync_issue_date(periodical):
                        stats["issue_date_synced"] += 1

                # 3. Queue missing OCR scan
                if self._should_queue_ocr(periodical, session):
                    if self._queue_ocr_scan(periodical, session):
                        stats["ocr_queued"] += 1

                # 4. Queue missing text scan
                if self._should_queue_text_scan(periodical):
                    if self._queue_text_scan(periodical, session):
                        stats["text_scan_queued"] += 1

            except Exception as e:
                logger.error(f"Error processing periodical {periodical.id}: {e}")
                stats["errors"] += 1

        # Commit all changes
        session.commit()

        logger.info(f"Auto-metadata scan complete: {stats}")
        return stats

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

                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(periodical, "parsed_metadata")

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

            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(periodical, "derived_metadata")

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

        # Skip if no cover path
        if not periodical.cover_path:
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

                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(periodical, "parsed_metadata")
                flag_modified(periodical, "derived_metadata")

                logger.debug(f"Performed text scan for periodical {periodical.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to text scan {periodical.id}: {e}")

        return False


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
