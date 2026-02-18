"""
Scheduled task for monitoring downloads and triggering processing.
Monitors download client progress and scans download folder for files to organize.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from core.constants.app import DOWNLOAD_FILE_SEARCH_DEPTH
from core.constants.app import MAX_IMPORT_RETRIES
from core.constants.files import INCOMPLETE_DOWNLOAD_PATTERNS
from core.parsers import utc_now
from core.utils import find_supported_files
from services.importer.sidecar import create_sidecar_file
from models.database import DownloadSubmission, PeriodicalTracking, DiscoveredIssue
from services import DownloadManager
from services import FileImporter

logger = logging.getLogger(__name__)


class DownloadMonitor:
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
        remote_path: Optional[str] = None,
        import_callback: Optional[Callable] = None,
    ):
        """
        Initialize download monitor.

        Args:
            download_manager: DownloadManager instance
            file_importer: FileImporter instance for processing completed downloads
            session_factory: SQLAlchemy session factory
            downloads_dir: Path to downloads folder to scan
            remote_path: Path prefix as seen by the download client (e.g., "/downloads/").
                When set, client paths starting with this prefix are remapped to downloads_dir.
                Useful when the client runs in a different container with different mount points.
            import_callback: Optional callback to run after importing (e.g., for file processing)
        """
        self.download_manager = download_manager
        self.file_importer = file_importer
        self.session_factory = session_factory
        self.downloads_dir = Path(downloads_dir)
        self.remote_path = remote_path.rstrip("/") + "/" if remote_path else None
        self.import_callback = import_callback
        self.last_run_time = None
        self.next_run_time = None
        self.last_status = None
        self.last_config_warning_time = None  # Rate limit config warning

        # Statistics
        self.stats = {
            "total_runs": 0,
            "client_downloads_processed": 0,
            "client_downloads_failed": 0,
            "folder_files_imported": 0,
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
            self.last_run_time = utc_now()
            self.stats["total_runs"] += 1
            logger.debug(f"[DownloadMonitor] Monitor run #{self.stats['total_runs']} started")

            # Part 1: Monitor download client submissions
            logger.debug("[DownloadMonitor] Checking download client...")
            client_processed, client_failed = self._monitor_download_client(session)
            self.stats["client_downloads_processed"] += client_processed
            self.stats["client_downloads_failed"] += client_failed
            self.stats["last_client_check"] = utc_now()

            # Part 1.5: Process queued downloads
            logger.debug("[DownloadMonitor] Processing download queue...")
            queue_result = self.download_manager.process_queue(session)
            logger.debug(
                f"[DownloadMonitor] Queue processing: {queue_result.get('submitted', 0)} submitted, "
                f"{queue_result.get('failed', 0)} failed, "
                f"{queue_result.get('active_count', 0)} active"
            )

            # Part 2: Scan downloads folder for files
            logger.debug("[DownloadMonitor] Scanning downloads folder...")
            folder_imported = self._scan_downloads_folder(session)
            self.stats["folder_files_imported"] += folder_imported
            self.stats["last_folder_scan"] = utc_now()

            # Part 3: Retry failed imports where the file still exists on disk
            logger.debug("[DownloadMonitor] Checking for retryable import failures...")
            import_retried = self._retry_failed_imports(session)
            if import_retried > 0:
                logger.info(f"[DownloadMonitor] Retried {import_retried} previously failed imports")

            # Warn if no files found but there are active downloads (potential config mismatch)
            # Rate limit to once every 30 minutes to avoid log spam
            # Use the active_count from queue processing above
            try:
                if folder_imported == 0 and queue_result.get("active_count", 0) > 0:
                    now = utc_now()
                    should_warn = (
                        self.last_config_warning_time is None
                        or (now - self.last_config_warning_time).total_seconds() > 1800  # 30 minutes
                    )

                    if should_warn:
                        logger.warning(
                            f"[DownloadMonitor] No files found in downloads folder ({self.downloads_dir}) "
                            f"but {queue_result.get('active_count', 0)} downloads are active. "
                            "Check CURATOR_DOWNLOAD_DIR environment variable or storage.download_dir config "
                            "matches your download client's output directory. "
                            "(This warning is rate-limited to once every 30 minutes)"
                        )
                        self.last_config_warning_time = now
                    else:
                        logger.debug(
                            f"[DownloadMonitor] Config warning suppressed (rate limited): "
                            f"No files in {self.downloads_dir} but {queue_result.get('active_count', 0)} active downloads"
                        )
            except NameError:
                # queue_result may not be defined if queue processing failed
                pass

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

    def _remap_client_path(self, file_path: str) -> str:
        """
        Remap a download client path to the local filesystem.

        When the download client runs in a different container, its paths
        (e.g., "/downloads/Books/file.pdf") don't match Curator's mount
        (e.g., "/app/local/downloads/Books/file.pdf"). This method replaces
        the client's remote_path prefix with the local downloads_dir.

        Args:
            file_path: File path as reported by the download client

        Returns:
            Remapped path string, or original if no remapping applies
        """
        if self.remote_path and file_path.startswith(self.remote_path):
            relative = file_path[len(self.remote_path) :]
            remapped = str(self.downloads_dir / relative)
            logger.debug(f"Remapped client path: {file_path} -> {remapped}")
            return remapped
        return file_path

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

        # Remap client path if remote_path is configured
        file_path = self._remap_client_path(file_path)

        file_path_obj = Path(file_path)
        filename = file_path_obj.name

        # First try as absolute path - if it's a file, return it
        if file_path_obj.is_absolute() and file_path_obj.exists():
            if file_path_obj.is_file():
                return file_path_obj
            # If it's a directory, search for PDF/EPUB files inside it
            if file_path_obj.is_dir():
                found_files = find_supported_files(file_path_obj, recursive=True)
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
                        found_files = find_supported_files(candidate, recursive=True)
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
                            found_files = find_supported_files(candidate, recursive=True)
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

            # 2. Process completed downloads
            logger.debug("[DownloadMonitor] Processing completed downloads...")
            processed_count = self._process_completed_downloads(session)

        except Exception as e:
            logger.error(f"Error monitoring download client: {e}", exc_info=True)

        return processed_count, failed_count

    def _scan_downloads_folder(self, session: Session) -> int:
        """
        Scan downloads folder recursively for periodical files and import them.

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

            # Check for PDFs, EPUBs, CBZs, and CBRs recursively
            all_files = find_supported_files(self.downloads_dir, recursive=True)

            # Filter out incomplete/temporary downloads (e.g., .part, _UNPACK_, .crdownload)
            all_files = [f for f in all_files if not any(pattern in f.name for pattern in INCOMPLETE_DOWNLOAD_PATTERNS)]

            # Strip trailing quotes from suffix (for files like 'Magazine.pdf')
            pdf_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".pdf"]
            epub_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".epub"]
            cbz_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbz"]
            cbr_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbr"]
            file_count = len(all_files)

            if file_count > 0:
                logger.info(
                    f"[DownloadMonitor] Found {file_count} files in downloads folder "
                    f"({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, "
                    f"{len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
                )
                results = self.file_importer.process_downloads(session)
                data = results.get("data", {})
                imported_count = data.get("imported", 0)

                if imported_count > 0:
                    logger.info(f"[DownloadMonitor] Successfully imported {imported_count} files from folder")
                    # Clean up any completed submissions from the download client
                    # that correspond to files we just imported via folder scan
                    self._cleanup_stale_completed_submissions(session)

                if data.get("failed", 0) > 0:
                    errors = results.get("errors", [])
                    error_messages = [e.get("message", str(e)) for e in errors] if errors else []
                    logger.warning(
                        f"[DownloadMonitor] Failed to import {data['failed']} files. " f"Errors: {error_messages}"
                    )
            else:
                logger.debug("[DownloadMonitor] No files found in downloads folder")

        except Exception as e:
            logger.error(f"Error scanning downloads folder: {e}", exc_info=True)

        return imported_count

    def _retry_failed_imports(self, session: Session) -> int:
        """
        Retry imports for FAILED submissions where the file still exists on disk.

        Picks up submissions that failed during import (not download failures)
        and re-attempts the import up to MAX_IMPORT_RETRIES times. This handles
        transient failures like disk full, temporary permission issues, or
        intermittent parsing errors.

        Args:
            session: Database session

        Returns:
            Number of imports successfully retried
        """
        retried_count = 0

        try:
            # Find FAILED submissions where the error indicates an import failure
            # and attempt_count is below the retry threshold
            failed_imports = (
                session.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                    DownloadSubmission.file_path.isnot(None),
                    DownloadSubmission.attempt_count < MAX_IMPORT_RETRIES,
                    DownloadSubmission.last_error.like("%Import%"),
                )
                .all()
            )

            if not failed_imports:
                return 0

            logger.debug(f"[DownloadMonitor] Found {len(failed_imports)} failed imports eligible for retry")

            for submission in failed_imports:
                file_path = self._find_file_in_downloads(submission.file_path)

                if not file_path:
                    # File no longer on disk — mark as permanently failed so it stops being retried
                    submission.attempt_count = MAX_IMPORT_RETRIES
                    submission.last_error = "Import file no longer exists on disk"
                    session.commit()
                    logger.debug(f"[DownloadMonitor] Import retry skipped: file gone for submission {submission.id}")
                    continue

                logger.info(
                    f"[DownloadMonitor] Retrying import for submission {submission.id}: "
                    f"{file_path.name} (attempt {submission.attempt_count + 1}/{MAX_IMPORT_RETRIES})"
                )

                submission.attempt_count += 1

                if self._process_single_file(file_path, submission, session):
                    retried_count += 1
                    self._sync_discovered_issue_status(submission, "completed", None, session)
                    self.download_manager.mark_processed(submission.id, session)

                    if self._should_delete_from_client(submission.tracking_id, session):
                        self._delete_from_client(submission.job_id, "completed (import retry)", submission.client_name)

                    logger.info(f"[DownloadMonitor] Import retry succeeded: {file_path.name}")
                else:
                    if submission.attempt_count >= MAX_IMPORT_RETRIES:
                        submission.last_error = (
                            f"Import/processing permanently failed after {MAX_IMPORT_RETRIES} attempts"
                        )
                        logger.warning(
                            f"[DownloadMonitor] Import retry exhausted for submission {submission.id}: "
                            f"{file_path.name} ({MAX_IMPORT_RETRIES} attempts)"
                        )
                    else:
                        submission.last_error = (
                            f"Import/processing failed (attempt {submission.attempt_count}/{MAX_IMPORT_RETRIES})"
                        )
                    session.commit()

        except Exception as e:
            logger.error(f"[DownloadMonitor] Error in import retry: {e}", exc_info=True)

        return retried_count

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
                logger.warning(
                    f"[DownloadMonitor] Marking submission {submission.id} as failed - " f"no job_id (stuck in pending)"
                )
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = "No job ID - download client never accepted this submission"
                submission.updated_at = utc_now()
                session.commit()
                failed_count += 1
                continue

            try:
                logger.debug(f"[DownloadMonitor] Checking job {submission.job_id}")
                previous_status = submission.status
                result = self.download_manager.update_submission_status(submission.job_id, session)
                if result:
                    logger.debug(f"[DownloadMonitor] Status updated: {result.status.value}")

                    # Special handling when status is PENDING but client returned "unknown"
                    # This happens when job was deleted from client (e.g., due to delete_from_client_on_completion)
                    if result.status == DownloadSubmission.StatusEnum.PENDING and previous_status in [
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                        DownloadSubmission.StatusEnum.COMPLETED,
                    ]:
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

                        # Delete failed downloads from client if tracking settings allow
                        if self._should_delete_from_client(submission.tracking_id, session):
                            self._delete_from_client(submission.job_id, "failed", submission.client_name)
            except Exception as e:
                logger.error(
                    f"Error updating status for job {submission.job_id}: {e}",
                    exc_info=True,
                )

        return failed_count

    def _handle_orphaned_submission(
        self, submission: DownloadSubmission, session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Handle a completed submission that has no file_path.

        These "orphaned" submissions occur when the download client marks a job as
        completed but doesn't provide a storage location (e.g., SABnzbd history purged).

        Args:
            submission: The orphaned submission
            session: Database session

        Returns:
            Updated submission if recovery succeeded, None if should skip processing
        """
        age_hours = (utc_now() - submission.updated_at).total_seconds() / 3600 if submission.updated_at else 0

        logger.warning(
            f"[DownloadMonitor] Orphaned completed submission detected:\n"
            f"  ID: {submission.id}\n"
            f"  Title: {submission.result_title}\n"
            f"  Job ID: {submission.job_id}\n"
            f"  Status: {submission.status.value}\n"
            f"  Created: {submission.created_at}\n"
            f"  Updated: {submission.updated_at} ({age_hours:.1f} hours ago)\n"
            f"  Attempt Count: {submission.attempt_count}\n"
            f"  Last Error: {submission.last_error}\n"
            f"  Reason: Download client marked job as completed but file_path is NULL.\n"
            f"  This typically happens when SABnzbd history was purged or storage field was empty."
        )

        # Auto-recovery: Mark as SKIPPED if older than 24 hours
        if age_hours > 24:
            logger.info(
                f"[DownloadMonitor] Marking submission {submission.id} as SKIPPED "
                f"(age: {age_hours:.1f} hours > 24 hours threshold)"
            )
            submission.status = DownloadSubmission.StatusEnum.SKIPPED
            submission.last_error = (
                f"Orphaned: Completed without file_path after {age_hours:.1f} hours. "
                "Likely SABnzbd history purged or storage field empty."
            )
            session.commit()
            return None

        # For recent submissions, attempt recovery from client
        logger.info(
            f"[DownloadMonitor] Attempting recovery for submission {submission.id} "
            f"(age: {age_hours:.1f} hours < 24 hours threshold)"
        )

        if not submission.job_id:
            return None

        try:
            logger.debug(f"[DownloadMonitor] Checking client for job {submission.job_id}")
            updated_submission = self.download_manager.update_submission_status(submission.job_id, session)

            if updated_submission and updated_submission.file_path:
                logger.info(f"[DownloadMonitor] Recovery successful! Found file_path: {updated_submission.file_path}")
                return updated_submission

            logger.warning(
                f"[DownloadMonitor] Recovery failed - client has no file_path for job {submission.job_id}. "
                f"Marking as FAILED for manual review."
            )
            submission.status = DownloadSubmission.StatusEnum.FAILED
            submission.last_error = (
                "Orphaned: Completed without file_path. Client returned no storage location. "
                "Job may have been deleted from client or storage was empty."
            )
            submission.attempt_count += 1
            session.commit()
            return None

        except Exception as e:
            logger.error(
                f"[DownloadMonitor] Error during recovery attempt for submission {submission.id}: {e}",
                exc_info=True,
            )
            submission.status = DownloadSubmission.StatusEnum.FAILED
            submission.last_error = f"Recovery attempt failed: {str(e)}"
            submission.attempt_count += 1
            session.commit()
            return None

    def _should_delete_from_client(self, tracking_id: Optional[int], session: Session) -> bool:
        """
        Determine if a completed/failed download should be deleted from the client.

        Args:
            tracking_id: ID of the associated tracking record
            session: Database session

        Returns:
            True if the download should be deleted from client
        """
        # Default: always delete
        if not tracking_id:
            return True

        tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if not tracking:
            return True

        return tracking.delete_from_client_on_completion

    def _delete_from_client(self, job_id: str, reason: str, client_name: Optional[str] = None) -> None:
        """
        Delete a job from the download client.

        Args:
            job_id: The download client job ID
            reason: Reason for deletion (for logging)
            client_name: Name of the client that handled the download (uses correct client)
        """
        try:
            # Use the correct client based on client_name, not just the default
            client = self.download_manager._get_client_by_name(client_name)
            if client.delete(job_id):
                logger.info(f"[DownloadMonitor] Deleted {reason} job {job_id} from {client.name}")
        except Exception as e:
            logger.error(f"Error deleting from client: {e}", exc_info=True)

    def _cleanup_stale_completed_submissions(self, session: Session) -> None:
        """
        Clean up completed download submissions whose files have already been imported.

        After folder-scan imports, some completed submissions may still be lingering
        in the download client because they were imported via folder scan rather than
        the client-based path. This finds those submissions and deletes them from the client.
        """
        try:
            # Find completed submissions that still have file_path set
            # (these weren't processed via the client path)
            stale_submissions = (
                session.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED,
                    DownloadSubmission.file_path.isnot(None),
                )
                .all()
            )

            if not stale_submissions:
                return

            for submission in stale_submissions:
                # Check if the file still exists in downloads - if gone, it was imported
                file_path = self._find_file_in_downloads(submission.file_path)
                if file_path is None:
                    logger.info(
                        f"[DownloadMonitor] Completed submission {submission.id} ({submission.result_title}) "
                        f"file no longer in downloads - marking processed and cleaning up client"
                    )
                    # Mark as processed
                    self.download_manager.mark_processed(submission.id, session)

                    # Sync DiscoveredIssue status
                    self._sync_discovered_issue_status(submission, "completed", None, session)

                    # Delete from client
                    if submission.job_id and self._should_delete_from_client(submission.tracking_id, session):
                        self._delete_from_client(submission.job_id, "completed (folder import)", submission.client_name)

        except Exception as e:
            logger.error(f"[DownloadMonitor] Error cleaning up stale submissions: {e}", exc_info=True)

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
                recovered = self._handle_orphaned_submission(submission, session)
                if recovered:
                    submission = recovered
                else:
                    continue

            # Check for comma-separated file paths (Internet Archive collection items)
            # IA collections store multiple extracted file paths as comma-separated string
            if "," in submission.file_path:
                file_paths_str = submission.file_path.split(",")
                logger.info(
                    f"[DownloadMonitor] Processing IA collection with {len(file_paths_str)} files "
                    f"for submission {submission.id}"
                )
                collection_success_count = 0

                for file_path_str in file_paths_str:
                    file_path_str = file_path_str.strip()
                    if not file_path_str:
                        continue

                    file_path = self._find_file_in_downloads(file_path_str)
                    if not file_path:
                        logger.warning(
                            f"[DownloadMonitor] Collection file not found: {file_path_str} "
                            f"(searched in: {self.downloads_dir})"
                        )
                        continue

                    # Process each collection file with tracking context
                    if self._process_single_file(file_path, submission, session):
                        collection_success_count += 1

                if collection_success_count > 0:
                    logger.info(
                        f"[DownloadMonitor] Successfully imported {collection_success_count}/{len(file_paths_str)} "
                        f"files from IA collection for submission {submission.id}"
                    )
                    processed_count += collection_success_count

                    # Sync status and mark processed after all collection files are done
                    self._sync_discovered_issue_status(submission, "completed", None, session)
                    self.download_manager.mark_processed(submission.id, session)

                    if self._should_delete_from_client(submission.tracking_id, session):
                        self._delete_from_client(submission.job_id, "completed", submission.client_name)
                else:
                    logger.warning(f"[DownloadMonitor] All collection files failed for submission {submission.id}")
                    submission.status = DownloadSubmission.StatusEnum.FAILED
                    submission.last_error = "All collection files failed to import"
                    session.commit()
                    self._sync_discovered_issue_status(submission, "failed", None, session)

                continue

            # Single file processing (non-collection)
            # Map the client path to Curator's download directory
            # The client returns a path like "/downloads/Books/Magazine.Name" which is the client's view
            # We need to look for it in our configured downloads_dir
            file_path = self._find_file_in_downloads(submission.file_path)

            if not file_path:
                logger.warning(
                    f"Downloaded file not found in downloads directory: {submission.file_path} "
                    f"(searched in: {self.downloads_dir}). "
                    f"Check CURATOR_DOWNLOAD_DIR environment variable matches your download client's output directory."
                )
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = f"File not found in downloads directory: {Path(submission.file_path).name} (searched: {self.downloads_dir})"
                session.commit()
                continue

            logger.debug(f"[DownloadMonitor] Found file at: {file_path}")

            if self._process_single_file(file_path, submission, session):
                processed_count += 1

                # Sync DiscoveredIssue status (NEW: Issue Discovery & Tracking)
                self._sync_discovered_issue_status(submission, "completed", None, session)

                # Mark submission as processed
                self.download_manager.mark_processed(submission.id, session)

                # Delete from client if tracking settings allow
                if self._should_delete_from_client(submission.tracking_id, session):
                    self._delete_from_client(submission.job_id, "completed", submission.client_name)
            else:
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = "Import/processing failed"
                session.commit()

                # Sync DiscoveredIssue status (NEW: Issue Discovery & Tracking)
                self._sync_discovered_issue_status(submission, "failed", None, session)

        return processed_count

    def _process_single_file(
        self,
        file_path: Path,
        submission: DownloadSubmission,
        session: Session,
    ) -> bool:
        """
        Process a single file: create sidecar and import.

        This handles both regular downloads and individual files from IA collections.
        Creates a sidecar file to preserve the tracking association, then imports the file.

        Args:
            file_path: Path to the file to process
            submission: The download submission record
            session: Database session

        Returns:
            True if import succeeded, False otherwise
        """
        # Create sidecar metadata file if we have tracking info
        # This preserves the tracking association even if the filename is ambiguous
        # Critical for IA collection items where filenames may not contain the periodical title
        if submission.tracking_id:
            try:
                tracking = session.query(PeriodicalTracking).filter_by(id=submission.tracking_id).first()
                if tracking:
                    create_sidecar_file(
                        file_path,
                        tracking_id=tracking.id,
                        tracking_title=tracking.title,
                        submission_id=submission.id,
                        category=tracking.category,
                        language=tracking.language,
                        country=tracking.country,
                    )
                    logger.debug(
                        f"[DownloadMonitor] Created sidecar for {file_path.name} -> "
                        f"tracking '{tracking.title}' (ID: {tracking.id})"
                    )
            except Exception as e:
                logger.warning(f"Failed to create sidecar file for {file_path.name}: {e}")

        try:
            logger.debug(f"[DownloadMonitor] Importing file from client download: {file_path}")

            # Use file importer to process the file, passing the tracking_id from the submission
            # This ensures the file is linked to the tracking that requested it
            result = self.file_importer.import_supported_files(file_path, session, tracking_id=submission.tracking_id)

            if result and result.get("periodical_id"):
                logger.info(f"[DownloadMonitor] Successfully imported from client: {file_path.name}")

                # Call optional callback (e.g., for database updates)
                if self.import_callback:
                    try:
                        self.import_callback(file_path, result, submission, session)
                    except Exception as e:
                        logger.error(f"Error in import callback: {e}", exc_info=True)

                return True
            else:
                logger.warning(f"Import failed for: {file_path}")
                return False

        except Exception as e:
            logger.error(
                f"Error processing file {file_path}: {e}",
                exc_info=True,
            )
            return False

    def _sync_discovered_issue_status(
        self,
        submission: DownloadSubmission,
        new_status: str,
        periodical_id: Optional[int],
        session: Session,
    ) -> None:
        """
        Sync DiscoveredIssue status based on DownloadSubmission changes.

        This bridges the old download system with the new Issue Discovery & Tracking system.

        Args:
            submission: DownloadSubmission that changed
            new_status: New status for DiscoveredIssue ("downloading", "completed", "failed", etc.)
            periodical_id: Magazine ID if successfully imported (for "completed" status)
            session: Database session
        """
        try:
            # Find the DiscoveredIssue linked to this submission
            discovered_issue = (
                session.query(DiscoveredIssue).filter(DiscoveredIssue.current_submission_id == submission.id).first()
            )

            if not discovered_issue:
                logger.debug(
                    f"No DiscoveredIssue found for submission {submission.id} - " f"this may be from the old system"
                )
                return

            logger.debug(
                f"Syncing DiscoveredIssue {discovered_issue.id} status: "
                f"{discovered_issue.download_status} -> {new_status}"
            )

            # Update status
            discovered_issue.download_status = new_status

            # Handle different status transitions
            if new_status == "completed" and periodical_id:
                # Successfully completed
                discovered_issue.periodical_id = periodical_id
                discovered_issue.download_priority = 0  # No longer needed
                discovered_issue.current_submission_id = None  # Clear active submission
                logger.info(f"Marked DiscoveredIssue as completed: {discovered_issue.title}")
                session.commit()

            elif new_status == "failed":
                # Failed download - use IssueDiscoveryService to handle retry logic
                from services import IssueDiscoveryService

                service = IssueDiscoveryService()
                error_message = submission.last_error or "Unknown error"
                final_status = service.handle_download_failure(discovered_issue.id, error_message, session)
                logger.info(
                    f"Handled download failure for DiscoveredIssue {discovered_issue.id}: "
                    f"final status = {final_status}"
                )
                # Don't commit here - service already commits

            elif new_status == "downloading":
                # Download is progressing
                discovered_issue.download_status = "downloading"
                session.commit()

            else:
                # Other status changes
                session.commit()

        except Exception as e:
            logger.error(
                f"Error syncing DiscoveredIssue status for submission {submission.id}: {e}",
                exc_info=True,
            )
