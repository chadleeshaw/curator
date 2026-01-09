"""
Scheduled task for monitoring downloads and triggering processing.
Monitors download client progress and scans download folder for files to organize.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from core.constants import DOWNLOAD_FILE_SEARCH_DEPTH
from models.database import DownloadSubmission, MagazineTracking
from services import DownloadManager
from services import FileImporter

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
        *,
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
        # Run synchronous database work in thread pool to avoid blocking event loop
        await asyncio.to_thread(self._run_sync)

    def _run_sync(self):
        """Synchronous implementation of the monitoring task."""
        session = self.session_factory()
        try:
            self.last_run_time = datetime.now()
            self.stats["total_runs"] += 1
            logger.debug(f"[DownloadMonitor] Monitor run #{self.stats['total_runs']} started")

            # Part 1: Monitor download client submissions
            logger.debug("[DownloadMonitor] Checking download client...")
            client_processed, client_failed = self._monitor_download_client(session)
            self.stats["client_downloads_processed"] += client_processed
            self.stats["client_downloads_failed"] += client_failed
            self.stats["last_client_check"] = datetime.now()

            # Track bad files
            bad_files_count = len(self.download_manager.get_bad_files(session))
            self.stats["bad_files_detected"] = bad_files_count

            # Part 2: Scan downloads folder for files
            logger.debug("[DownloadMonitor] Scanning downloads folder...")
            folder_imported = self._scan_downloads_folder(session)
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

    def _find_pdf_epub_files(self, directory: Path) -> list[Path]:
        """
        Find all PDF and EPUB files in a directory recursively.

        Args:
            directory: Directory to search

        Returns:
            List of Path objects for PDF/EPUB files found
        """
        files = []
        if directory.exists() and directory.is_dir():
            files.extend(directory.glob("**/*.pdf"))
            files.extend(directory.glob("**/*.epub"))
        return files

    def _find_file_in_downloads(self, file_path: str, max_depth: int = DOWNLOAD_FILE_SEARCH_DEPTH) -> Optional[Path]:
        """
        Find a file in the downloads folder, checking multiple possible locations.
        Searches recursively up to max_depth subdirectories.

        Args:
            file_path: File path from download client (may be absolute or relative)
            max_depth: Maximum directory depth to search (default from DOWNLOAD_FILE_SEARCH_DEPTH)

        Returns:
            Path object if file exists, None otherwise
        """
        if not file_path:
            return None

        file_path_obj = Path(file_path)
        filename = file_path_obj.name

        # First try as absolute path - if it's a file, return it
        if file_path_obj.is_absolute() and file_path_obj.exists():
            if file_path_obj.is_file():
                return file_path_obj
            # If it's a directory, search for PDF/EPUB files inside it
            if file_path_obj.is_dir():
                found_files = self._find_pdf_epub_files(file_path_obj)
                if found_files:
                    return found_files[0]

        # Search in downloads directory up to max_depth
        # Build glob patterns for each depth level
        for depth in range(max_depth + 1):
            if depth == 0:
                # Check root downloads dir
                candidate = self.downloads_dir / filename
                if candidate.exists():
                    if candidate.is_file():
                        return candidate
                    # If it's a directory, search for PDF/EPUB files inside it
                    if candidate.is_dir():
                        found_files = self._find_pdf_epub_files(candidate)
                        if found_files:
                            return found_files[0]
            else:
                # Check subdirectories at this depth
                pattern = "/".join(["*"] * depth) + f"/{filename}"
                for candidate in self.downloads_dir.glob(pattern):
                    if candidate.exists():
                        if candidate.is_file():
                            return candidate
                        # If it's a directory, search for PDF/EPUB files inside it
                        if candidate.is_dir():
                            found_files = self._find_pdf_epub_files(candidate)
                            if found_files:
                                return found_files[0]

        return None

    def _monitor_download_client(self, session: Session) -> tuple[int, int]:
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
            failed_count = self._update_pending_downloads(session)

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
            processed_count = self._process_completed_downloads(session)

        except Exception as e:
            logger.error(f"Error monitoring download client: {e}", exc_info=True)

        return processed_count, failed_count

    def _scan_downloads_folder(self, session: Session) -> int:
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
            all_files = self._find_pdf_epub_files(self.downloads_dir)
            pdf_files = [f for f in all_files if f.suffix.lower() == '.pdf']
            epub_files = [f for f in all_files if f.suffix.lower() == '.epub']
            file_count = len(all_files)

            if file_count > 0:
                logger.info(
                    f"[DownloadMonitor] Found {file_count} files in downloads folder "
                    f"({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)"
                )
                results = self.file_importer.process_downloads(session)
                data = results.get("data", {})
                imported_count = data.get("imported", 0)

                if imported_count > 0:
                    logger.info(f"[DownloadMonitor] Successfully imported {imported_count} files from folder")

                if data.get("failed", 0) > 0:
                    errors = results.get("errors", [])
                    error_messages = [e.get("message", str(e)) for e in errors] if errors else []
                    logger.warning(
                        f"[DownloadMonitor] Failed to import {data['failed']} files. "
                        f"Errors: {error_messages}"
                    )
            else:
                logger.debug("[DownloadMonitor] No files found in downloads folder")

        except Exception as e:
            logger.error(f"Error scanning downloads folder: {e}", exc_info=True)

        return imported_count

    def _update_pending_downloads(self, session: Session) -> int:
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

                    # Special handling when status is PENDING but client returned "unknown"
                    # This happens when job was deleted from client (e.g., due to delete_from_client_on_completion)
                    if (result.status == DownloadSubmission.StatusEnum.PENDING
                            and previous_status in [
                                DownloadSubmission.StatusEnum.DOWNLOADING,
                                DownloadSubmission.StatusEnum.COMPLETED
                            ]):
                        # Job might have been deleted from client after completion
                        # Check if file exists in downloads folder
                        found_path = self._find_file_in_downloads(result.file_path)
                        if found_path:
                            logger.info(
                                f"[DownloadMonitor] Job {submission.job_id} not found in client, but file exists at {found_path} - "
                                f"marking as completed (likely deleted from client after completion)"
                            )
                            result.status = DownloadSubmission.StatusEnum.COMPLETED
                            session.commit()

                    # Track if it transitioned to failed
                    if (
                        result.status == DownloadSubmission.StatusEnum.FAILED
                        and previous_status != DownloadSubmission.StatusEnum.FAILED
                    ):
                        failed_count += 1

                        # Check if we should delete from client after failure
                        if submission.tracking_id:
                            tracking = (
                                session.query(MagazineTracking)
                                .filter(MagazineTracking.id == submission.tracking_id)
                                .first()
                            )
                            if tracking and tracking.delete_from_client_on_completion:
                                try:
                                    if self.download_manager.download_client.delete(submission.job_id):
                                        logger.info(
                                            f"[DownloadMonitor] Deleted failed job {submission.job_id} "
                                            f"from download client"
                                        )
                                except Exception as e:
                                    logger.error(f"Error deleting from client: {e}")
            except Exception as e:
                logger.error(
                    f"Error updating status for job {submission.job_id}: {e}",
                    exc_info=True,
                )

        return failed_count

    def _process_completed_downloads(self, session: Session) -> int:
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

            # Map the client path to Curator's download directory
            # The client returns a path like "/downloads/Books/Magazine.Name" which is the client's view
            # We need to look for it in our configured downloads_dir
            file_path = self._find_file_in_downloads(submission.file_path)

            if not file_path:
                logger.warning(f"Downloaded file not found in downloads directory: {submission.file_path}")
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = f"File not found in downloads directory: {Path(submission.file_path).name}"
                session.commit()
                continue

            logger.debug(f"[DownloadMonitor] Found file at: {file_path}")

            try:
                logger.debug(f"[DownloadMonitor] Importing file from client download: {file_path}")

                # Use file importer to process the file
                result = self.file_importer.import_pdf(file_path, session)

                if result:
                    logger.info(f"[DownloadMonitor] Successfully imported from client: {file_path.name}")
                    processed_count += 1

                    # Mark submission as processed
                    self.download_manager.mark_processed(submission.id, session)

                    # Check if we should delete from client after successful completion
                    if submission.tracking_id:
                        tracking = (
                            session.query(MagazineTracking)
                            .filter(MagazineTracking.id == submission.tracking_id)
                            .first()
                        )
                        if tracking and tracking.delete_from_client_on_completion:
                            try:
                                if self.download_manager.download_client.delete(submission.job_id):
                                    logger.info(
                                        f"[DownloadMonitor] Deleted completed job {submission.job_id} "
                                        f"from download client"
                                    )
                            except Exception as e:
                                logger.error(f"Error deleting from client: {e}")

                    # Call optional callback (e.g., for database updates)
                    if self.import_callback:
                        try:
                            self.import_callback(file_path, result, submission, session)
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
