"""
Scheduled task for monitoring downloads and triggering processing.
Monitors download progress and automatically processes completed downloads.
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
    """Monitor downloads and trigger processing on completion"""

    def __init__(
        self,
        download_manager: DownloadManager,
        file_importer: FileImporter,
        session_factory: sessionmaker,
        import_callback: Optional[Callable] = None,
    ):
        """
        Initialize download monitor task.

        Args:
            download_manager: DownloadManager instance
            file_importer: FileImporter instance for processing completed downloads
            session_factory: SQLAlchemy session factory
            import_callback: Optional callback to run after importing (e.g., for file processing)
        """
        self.download_manager = download_manager
        self.file_importer = file_importer
        self.session_factory = session_factory
        self.import_callback = import_callback
        self.last_run_time = None
        self.next_run_time = None
        self.last_status = None

    async def run(self):
        """
        Execute the download monitoring task.
        This should be called periodically by the scheduler.
        """
        session = self.session_factory()
        try:
            self.last_run_time = datetime.now()
            logger.debug("[DownloadMonitor] Monitor run started")

            # 1. Update status of all pending downloads
            logger.debug("[DownloadMonitor] Checking pending downloads...")
            await self._update_pending_downloads(session)

            # 2. Process completed downloads
            logger.debug("[DownloadMonitor] Processing completed downloads...")
            await self._process_completed_downloads(session)

            logger.debug("[DownloadMonitor] Monitor run completed")
            self.last_status = "success"

        except Exception as e:
            logger.error(f"Error in download monitor task: {e}", exc_info=True)
            self.last_status = "failed"
        finally:
            session.close()

    async def _update_pending_downloads(self, session: Session):
        """
        Update status of all pending/downloading submissions from client.

        Args:
            session: Database session
        """
        pending = self.download_manager.get_pending_downloads(session)

        if not pending:
            logger.debug("[DownloadMonitor] No pending downloads")
            return

        logger.debug(f"[DownloadMonitor] Checking {len(pending)} items")

        for submission in pending:
            if not submission.job_id:
                logger.debug(f"[DownloadMonitor] Skipping submission {submission.id} - no job_id")
                continue

            try:
                logger.debug(f"[DownloadMonitor] Checking job {submission.job_id}")
                result = self.download_manager.update_submission_status(
                    submission.job_id, session
                )
                if result:
                    logger.debug(f"[DownloadMonitor] Status updated: {result.status.value}")
            except Exception as e:
                logger.error(
                    f"Error updating status for job {submission.job_id}: {e}",
                    exc_info=True,
                )

    async def _process_completed_downloads(self, session: Session):
        """
        Get completed downloads and process them via file importer.

        Args:
            session: Database session
        """
        completed = self.download_manager.get_completed_downloads(session)

        if not completed:
            logger.debug("[DownloadMonitor] No completed downloads")
            return

        logger.debug(f"[DownloadMonitor] Processing {len(completed)} items...")

        for submission in completed:
            logger.info(f"[DownloadMonitor] Processing submission {submission.id}: {submission.result_title}")

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
                logger.info(f"Processing downloaded file: {file_path}")

                # Use file importer to process the file
                result = self.file_importer.import_pdf(file_path, session)

                if result:
                    logger.info(f"Successfully imported: {file_path.name}")

                    # Mark submission as processed
                    self.download_manager.mark_processed(submission.id, session)

                    # Call optional callback (e.g., for database updates)
                    if self.import_callback:
                        try:
                            await self.import_callback(
                                file_path, result, submission, session
                            )
                        except Exception as e:
                            logger.error(
                                f"Error in import callback: {e}", exc_info=True
                            )
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
