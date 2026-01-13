"""Background task for processing OCR queue."""

import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.orm import sessionmaker

from services.ocr_queue import OCRQueueService

logger = logging.getLogger(__name__)


class OCRProcessorTask:
    """Background task for processing queued OCR jobs."""

    def __init__(self, session_factory: sessionmaker, config_loader=None, max_workers: int = 3, batch_size: int = 10):
        """
        Initialize OCR processor task.

        Args:
            session_factory: SQLAlchemy session factory
            config_loader: ConfigLoader instance for checking OCR enabled setting
            max_workers: Number of concurrent OCR processes (default: 3)
            batch_size: Maximum number of jobs to process per run (default: 10)
        """
        self.session_factory = session_factory
        self.config_loader = config_loader
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.ocr_service = OCRQueueService(max_workers=max_workers)

        # Task tracking attributes (for API status)
        self.last_run_time = None
        self.next_run_time = None
        self.last_status = None
        self.stats = {
            "total_runs": 0,
            "jobs_processed": 0,
            "jobs_failed": 0,
            "last_process_time": None,
        }

        logger.info(f"OCR processor initialized with {max_workers} workers, batch size {batch_size}")

    async def run(self) -> Dict[str, Any]:
        """
        Process pending OCR jobs from the queue.

        Runs in a thread executor to avoid blocking the event loop during
        long-running operations (like model downloads).

        Returns:
            Dictionary with processing statistics
        """
        try:
            from datetime import datetime

            # Check if OCR is enabled in config
            if self.config_loader:
                import_config = self.config_loader.get_import()
                if not import_config.get("enable_ocr", True):
                    logger.debug("OCR is disabled in config, skipping OCR processing")
                    return {"skipped": True, "reason": "OCR disabled in config"}

            self.last_run_time = datetime.now()
            self.stats["total_runs"] += 1

            # Run the synchronous processing in a thread executor
            # This prevents blocking the event loop during model downloads or OCR processing
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._process_sync)

            # Update stats
            if "processed" in result:
                self.stats["jobs_processed"] += result["processed"]
            if "failed" in result:
                self.stats["jobs_failed"] += result["failed"]

            self.stats["last_process_time"] = datetime.now()
            self.last_status = "success"

            return result

        except Exception as e:
            logger.error(f"Error in OCR processor task: {e}", exc_info=True)
            self.last_status = "failed"
            return {"error": str(e)}

    def _process_sync(self) -> Dict[str, Any]:
        """
        Synchronous processing method that runs in thread executor.

        Returns:
            Dictionary with processing statistics
        """
        db = self.session_factory()
        try:
            # Process batch of jobs
            stats = self.ocr_service.process_queue(
                db=db,
                batch_size=self.batch_size,
                max_retries=3
            )

            # Clean up old completed jobs (weekly cleanup)
            if stats["processed"] > 0:
                # Only cleanup if we processed something (to avoid extra DB queries)
                cleaned = self.ocr_service.cleanup_old_jobs(db, days=7)
                if cleaned > 0:
                    stats["cleaned_up"] = cleaned

            return stats
        finally:
            db.close()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current OCR queue status.

        Returns:
            Dictionary with queue statistics
        """
        try:
            db = self.session_factory()
            status = self.ocr_service.get_queue_status(db)
            db.close()
            return status
        except Exception as e:
            logger.error(f"Error getting OCR queue status: {e}")
            return {"error": str(e)}

    def shutdown(self):
        """Shutdown the OCR processor gracefully."""
        logger.info("Shutting down OCR processor")
        self.ocr_service.shutdown()
