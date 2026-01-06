"""
Scheduled task for monitoring downloads and triggering processing.
Monitors download client progress and scans download folder for files to organize.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from models.database import DownloadSubmission
from processor.download_manager import DownloadManager
from processor.file_importer import FileImporter

logger = logging.getLogger(__name__)


class DownloadMonitorTask:
    """
    Monitor downloads and trigger processing on completion.

    This task performs two main functions:
    1. Monitors download client for completed downloads
    2. Scans download folder recursively for PDF/EPUB files and organizes them
    """

    def __init__(
        self,
        download_manager: DownloadManager,
        file_importer: FileImporter,
        session_factory: sessionmaker,
        downloads_dir: str,
        import_callback: Optional[Callable] = None,
    ):
        """
        Initialize download monitor task.

        Args:
            download_manager: DownloadManager instance
            file_importer: FileImporter instance for processing completed downloads
            session_factory: SQLAlchemy session factory
            downloads_dir: Path to downloads folder to scan
            import_callback: Optional callback to run after importing (e.g., for file processing)
        """
        self.download_manager = download_manager
        self.file_importer = file_importer
        self.session_factory = session_factory
        self.downloads_dir = Path(downloads_dir)
        self.import_callback = import_callback
        self.last_run_time = None
        self.next_run_time = None
        self.last_status = None

        # Statistics
        self.stats = {
            "total_runs": 0,
            "client_downloads_processed": 0,
            "client_downloads_failed": 0,
            "folder_files_imported": 0,
            "bad_files_detected": 0,
            "last_client_check": None,
            "last_folder_scan": None,
        }

    async def run(self):
        """
        Execute the download monitoring task.
        This should be called periodically by the scheduler.

        Performs:
        1. Updates status of pending download client submissions
        2. Processes completed download client submissions
        3. Scans download folder for new PDF/EPUB files and organizes them
        """
        session = self.session_factory()
        try:
            self.last_run_time = datetime.now()
            self.stats["total_runs"] += 1
            logger.debug(f"[DownloadMonitor] Monitor run #{self.stats['total_runs']} started")

            # Part 1: Monitor download client submissions
            logger.debug("[DownloadMonitor] Checking download client...")
            client_processed, client_failed = await self._monitor_download_client(session)
            self.stats["client_downloads_processed"] += client_processed
            self.stats["client_downloads_failed"] += client_failed
            self.stats["last_client_check"] = datetime.now()

            # Track bad files
            bad_files_count = len(self.download_manager.get_bad_files(session))
            self.stats["bad_files_detected"] = bad_files_count

            # Part 2: Scan downloads folder for files
            logger.debug("[DownloadMonitor] Scanning downloads folder...")
            folder_imported = await self._scan_downloads_folder(session)
            self.stats["folder_files_imported"] += folder_imported
            self.stats["last_folder_scan"] = datetime.now()

            logger.debug(
                f"[DownloadMonitor] Run completed - Client: {client_processed} processed, "
                f"Folder: {folder_imported} imported"
            )
            self.last_status = "success"

        except Exception as e:
            logger.error(f"Error in download monitor task: {e}", exc_info=True)
            self.last_status = "failed"
        finally:
            session.close()

    async def _monitor_download_client(self, session: Session) -> tuple[int, int]:
        """
        Monitor download client for pending and completed downloads.

        Args:
            session: Database session

        Returns:
            Tuple of (downloads processed, downloads failed)
        """
        processed_count = 0
        failed_count = 0

        try:
            # 1. Update status of all pending downloads
            logger.debug("[DownloadMonitor] Checking pending downloads...")
            failed_count = await self._update_pending_downloads(session)

            # Log failed downloads
            if failed_count > 0:
                logger.warning(f"[DownloadMonitor] {failed_count} downloads failed")

                # Check for bad files (failed 3+ times)
                bad_files = self.download_manager.get_bad_files(session)
                if bad_files:
                    logger.error(f"[DownloadMonitor] {len(bad_files)} files marked as bad (failed 3+ times):")
                    for bad in bad_files[:5]:  # Show first 5
                        logger.error(f"  - {bad.result_title}: {bad.last_error} " f"(attempts: {bad.attempt_count})")
                    if len(bad_files) > 5:
                        logger.error(f"  ... and {len(bad_files) - 5} more bad files")

            # 2. Process completed downloads
            logger.debug("[DownloadMonitor] Processing completed downloads...")
            processed_count = await self._process_completed_downloads(session)

        except Exception as e:
            logger.error(f"Error monitoring download client: {e}", exc_info=True)

        return processed_count, failed_count

    async def _scan_downloads_folder(self, session: Session) -> int:
        """
        Scan downloads folder recursively for PDF and EPUB files and import them.

        Args:
            session: Database session

        Returns:
            Number of files imported
        """
        imported_count = 0

        try:
            if not self.downloads_dir.exists():
                logger.debug(f"Downloads directory does not exist: {self.downloads_dir}")
                return 0

            # Check for PDFs and EPUBs recursively
            pdf_files = list(self.downloads_dir.glob("**/*.pdf"))
            epub_files = list(self.downloads_dir.glob("**/*.epub"))
            file_count = len(pdf_files) + len(epub_files)

            if file_count > 0:
                logger.info(
                    f"[DownloadMonitor] Found {file_count} files in downloads folder "
                    f"({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)"
                )
                results = self.file_importer.process_downloads(session)
                imported_count = results.get("imported", 0)

                if imported_count > 0:
                    logger.info(f"[DownloadMonitor] Successfully imported {imported_count} files from folder")

                if results.get("failed", 0) > 0:
                    logger.warning(
                        f"[DownloadMonitor] Failed to import {results['failed']} files. "
                        f"Errors: {results.get('errors', [])}"
                    )
            else:
                logger.debug("[DownloadMonitor] No files found in downloads folder")

        except Exception as e:
            logger.error(f"Error scanning downloads folder: {e}", exc_info=True)

        return imported_count

    async def _update_pending_downloads(self, session: Session) -> int:
        """
        Update status of all pending/downloading submissions from client.

        Args:
            session: Database session

        Returns:
            Number of downloads that failed
        """
        pending = self.download_manager.get_pending_downloads(session)

        if not pending:
            logger.debug("[DownloadMonitor] No pending downloads")
            return 0

        logger.debug(f"[DownloadMonitor] Checking {len(pending)} pending downloads")
        failed_count = 0

        for submission in pending:
            if not submission.job_id:
                logger.debug(f"[DownloadMonitor] Skipping submission {submission.id} - no job_id")
                continue

            try:
                logger.debug(f"[DownloadMonitor] Checking job {submission.job_id}")
                previous_status = submission.status
                result = self.download_manager.update_submission_status(submission.job_id, session)
                if result:
                    logger.debug(f"[DownloadMonitor] Status updated: {result.status.value}")
                    # Track if it transitioned to failed
                    if (
                        result.status == DownloadSubmission.StatusEnum.FAILED
                        and previous_status != DownloadSubmission.StatusEnum.FAILED
                    ):
                        failed_count += 1
            except Exception as e:
                logger.error(
                    f"Error updating status for job {submission.job_id}: {e}",
                    exc_info=True,
                )

        return failed_count

    async def _process_completed_downloads(self, session: Session) -> int:
        """
        Get completed downloads and process them via file importer.

        Args:
            session: Database session

        Returns:
            Number of downloads successfully processed
        """
        completed = self.download_manager.get_completed_downloads(session)

        if not completed:
            logger.debug("[DownloadMonitor] No completed downloads from client")
            return 0

        logger.info(f"[DownloadMonitor] Processing {len(completed)} completed downloads from client...")
        processed_count = 0

        for submission in completed:
            logger.debug(f"[DownloadMonitor] Processing submission {submission.id}: {submission.result_title}")

            if not submission.file_path:
                logger.warning(f"Submission {submission.id} has no file path")
                continue

            file_path = Path(submission.file_path)

            # Check if file exists locally
            if not file_path.exists():
                logger.warning(f"Downloaded file not found: {file_path}")
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = f"File not accessible: {submission.file_path}"
                session.commit()
                continue

            try:
                logger.debug(f"[DownloadMonitor] Importing file from client download: {file_path}")

                # Use file importer to process the file
                result = self.file_importer.import_pdf(file_path, session)

                if result:
                    logger.info(f"[DownloadMonitor] Successfully imported from client: {file_path.name}")
                    processed_count += 1

                    # Mark submission as processed
                    self.download_manager.mark_processed(submission.id, session)

                    # Call optional callback (e.g., for database updates)
                    if self.import_callback:
                        try:
                            await self.import_callback(file_path, result, submission, session)
                        except Exception as e:
                            logger.error(f"Error in import callback: {e}", exc_info=True)
                else:
                    logger.warning(f"Import failed for: {file_path}")
                    submission.status = DownloadSubmission.StatusEnum.FAILED
                    submission.last_error = "Import/processing failed"
                    session.commit()

            except Exception as e:
                logger.error(
                    f"Error processing completed download {submission.id}: {e}",
                    exc_info=True,
                )
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = str(e)
                session.commit()

        return processed_count
