"""Background task for processing OCR queue."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

from sqlalchemy.orm import sessionmaker

from core import constants
from services.ocr.queue import OCRQueueService
from services.ocr.service import OCRService
from core.parsers import utc_now

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Background task for processing queued OCR jobs."""

    def __init__(
        self,
        session_factory: sessionmaker,
        config_loader=None,
        max_workers: int = constants.OCR_MAX_WORKERS,
        batch_size: int = constants.OCR_BATCH_SIZE,
    ):
        """
        Initialize OCR processor.

        Args:
            session_factory: SQLAlchemy session factory
            config_loader: ConfigLoader instance for checking OCR enabled setting
            max_workers: Number of concurrent OCR processes (default: OCR_MAX_WORKERS from constants)
            batch_size: Maximum number of jobs to process per run (default: OCR_BATCH_SIZE from constants)
        """
        self.session_factory = session_factory
        self.config_loader = config_loader
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.ocr_service = OCRQueueService(max_workers=max_workers)

        # Thread pool executor for CPU-intensive operations (PNG generation, OCR)
        # This prevents blocking the FastAPI event loop
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="OCRProcessor")

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

        Runs CPU-intensive operations (PNG generation, OCR) in a thread pool
        to avoid blocking the FastAPI event loop and freezing the web interface.

        Returns:
            Dictionary with processing statistics
        """
        try:
            # Check if OCR is available
            if not OCRService.is_available():
                logger.debug("OCR service not available, skipping OCR processing")
                return {"skipped": True, "reason": "OCR not available"}

            # Check if OCR is enabled in config
            if self.config_loader:
                import_config = self.config_loader.get_import()
                if not import_config.get("enable_ocr", True):
                    logger.debug("OCR is disabled in config, skipping OCR processing")
                    return {"skipped": True, "reason": "OCR disabled in config"}

            self.last_run_time = utc_now()
            self.stats["total_runs"] += 1

            # Run OCR processing in thread pool to avoid blocking the event loop
            # This prevents the web interface from freezing during PNG generation and OCR
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(self.executor, self._process_sync)

            # Update stats
            if "processed" in result:
                self.stats["jobs_processed"] += result["processed"]
            if "failed" in result:
                self.stats["jobs_failed"] += result["failed"]

            self.stats["last_process_time"] = utc_now()
            self.last_status = "success"

            return result

        except Exception as e:
            logger.error(f"Error in OCR processor task: {e}", exc_info=True)
            self.last_status = "failed"
            return {"error": str(e)}

    def _process_sync(self) -> Dict[str, Any]:
        """
        Synchronous OCR processing method.

        This runs in a separate thread via ThreadPoolExecutor to prevent blocking
        the FastAPI event loop during CPU-intensive PNG generation and OCR operations.

        Returns:
            Dictionary with processing statistics
        """
        db = self.session_factory()
        try:
            # Process batch of jobs
            # This includes CPU-intensive operations:
            # - PDF to PNG conversion (via pdf2image/poppler)
            # - OCR processing (via Tesseract)
            stats = self.ocr_service.process_queue(
                db=db,
                batch_size=self.batch_size,
                max_retries=constants.MAX_DOWNLOAD_RETRIES,
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

    def shutdown(self):
        """Shutdown the OCR processor gracefully."""
        logger.info("Shutting down OCR processor")
        self.ocr_service.shutdown()
        # Shutdown the thread pool executor
        self.executor.shutdown(wait=True)
        logger.info("OCR processor thread pool executor shutdown complete")
