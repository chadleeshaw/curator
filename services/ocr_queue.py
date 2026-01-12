"""Background OCR queue service with process pool for concurrent processing."""

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from models.database import OCRJob, Magazine
from services.ocr_service import OCRService

logger = logging.getLogger(__name__)

# Global process pool - initialized once and reused
_process_pool: Optional[ProcessPoolExecutor] = None
_pool_size = 0


def _ocr_worker(cover_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Worker function that runs in a separate process.
    This function must be at module level to be picklable.

    Args:
        cover_path: Path to cover image/PDF/EPUB
        language: Optional language hint for OCR

    Returns:
        Dictionary with OCR metadata
    """
    # Each process gets its own OCRService instance
    try:
        result = OCRService.analyze_cover(cover_path, language=language)
        return {"success": True, "metadata": result}
    except Exception as e:
        # Catch all exceptions to prevent process crash
        import traceback
        error_msg = f"OCR worker error for {cover_path}: {e}"
        error_trace = traceback.format_exc()
        logger.error(f"{error_msg}\n{error_trace}")
        return {"success": False, "error": str(e)}


class OCRQueueService:
    """Service for managing background OCR processing with process pool."""

    def __init__(self, max_workers: int = 3):
        """
        Initialize OCR queue service.

        Args:
            max_workers: Number of concurrent OCR processes (default: 3)
        """
        self.max_workers = max_workers
        self._ensure_pool()

    def _ensure_pool(self, force_recreate: bool = False):
        """Ensure process pool is initialized and healthy."""
        global _process_pool, _pool_size

        # Recreate pool if forced or if pool is broken/None or size changed
        if force_recreate or _process_pool is None or _pool_size != self.max_workers:
            if _process_pool is not None:
                logger.info("Shutting down old process pool")
                try:
                    _process_pool.shutdown(wait=False)
                except Exception as e:
                    logger.warning(f"Error shutting down old pool: {e}")

            logger.info(f"Initializing OCR process pool with {self.max_workers} workers")
            _process_pool = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=None  # Use default (fork on Unix, spawn on Windows)
            )
            _pool_size = self.max_workers

    @staticmethod
    def queue_ocr_job(
        db: Session,
        magazine_id: int,
        priority: int = OCRJob.PriorityEnum.NORMAL.value,
        language: Optional[str] = None
    ) -> Optional[OCRJob]:
        """
        Queue an OCR job for background processing.

        Args:
            db: Database session
            magazine_id: Magazine ID to process
            priority: Job priority (LOW=1, NORMAL=5, HIGH=10)
            language: Optional language hint

        Returns:
            Created OCRJob or None if already exists
        """
        # Check if job already exists and is pending/processing
        existing = db.query(OCRJob).filter(
            OCRJob.magazine_id == magazine_id,
            OCRJob.status.in_([OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING])
        ).first()

        if existing:
            logger.debug(f"OCR job already queued for magazine {magazine_id}")
            return None

        # Create new job
        job = OCRJob(
            magazine_id=magazine_id,
            status=OCRJob.StatusEnum.PENDING,
            priority=priority,
            language=language
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(f"Queued OCR job {job.id} for magazine {magazine_id} (priority={priority})")
        return job

    def process_queue(self, db: Session, batch_size: int = 10, max_retries: int = 3) -> Dict[str, int]:
        """
        Process pending OCR jobs from the queue in batches.

        Args:
            db: Database session
            batch_size: Maximum number of jobs to process at once
            max_retries: Maximum number of retry attempts

        Returns:
            Dictionary with processing statistics
        """
        stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0
        }

        # Reset stuck jobs (processing for more than 30 minutes)
        from datetime import timedelta
        stuck_threshold = datetime.now(UTC) - timedelta(minutes=30)
        stuck_jobs = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PROCESSING,
            OCRJob.started_at < stuck_threshold
        ).all()

        if stuck_jobs:
            logger.warning(f"Found {len(stuck_jobs)} stuck OCR jobs, resetting to PENDING")
            for job in stuck_jobs:
                job.status = OCRJob.StatusEnum.PENDING
                job.started_at = None
            db.commit()

        # Fetch pending jobs ordered by priority (highest first) and creation time
        pending_jobs = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PENDING,
            OCRJob.attempt_count < max_retries
        ).order_by(
            OCRJob.priority.desc(),
            OCRJob.created_at
        ).limit(batch_size).all()

        if not pending_jobs:
            logger.debug("No pending OCR jobs to process")
            return stats

        logger.info(f"Processing {len(pending_jobs)} OCR jobs (batch_size={batch_size})")

        # Prepare jobs for processing
        job_data = []
        for job in pending_jobs:
            # Get magazine and cover path
            magazine = db.query(Magazine).filter(Magazine.id == job.magazine_id).first()

            if not magazine:
                logger.warning(f"Magazine {job.magazine_id} not found for OCR job {job.id}")
                job.status = OCRJob.StatusEnum.FAILED
                job.last_error = "Magazine not found"
                stats["failed"] += 1
                continue

            # Generate OCR PNG if it doesn't exist
            cover_path = None
            png_generated = False

            if magazine.file_path and Path(magazine.file_path).exists():
                pdf_path = Path(magazine.file_path)

                # Only process PDF files for OCR
                if pdf_path.suffix.lower() == '.pdf':
                    # Determine PNG path
                    if magazine.cover_path:
                        cover_dir = Path(magazine.cover_path).parent
                        ocr_covers_dir = cover_dir.parent / ".ocr_covers"
                    else:
                        # Fallback to data directory
                        ocr_covers_dir = pdf_path.parent.parent / ".ocr_covers"

                    ocr_covers_dir.mkdir(parents=True, exist_ok=True)
                    png_path = ocr_covers_dir / f"{magazine.id}_ocr.png"

                    # Generate PNG if it doesn't exist
                    if not png_path.exists():
                        logger.info(f"Generating OCR PNG for magazine {magazine.id}")
                        try:
                            from core.constants import PDF_COVER_DPI_OCR
                            from pdf2image import convert_from_path
                            from PIL import Image

                            images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_OCR, fmt='png')

                            if images:
                                img = images[0]

                                # Resize if too large (using optimal max dimension)
                                from core.constants import OCR_IMAGE_MAX_DIMENSION
                                if max(img.size) > OCR_IMAGE_MAX_DIMENSION:
                                    ratio = OCR_IMAGE_MAX_DIMENSION / max(img.size)
                                    new_size = tuple(int(dim * ratio) for dim in img.size)
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                    logger.debug(f"Resized OCR PNG from {images[0].size} to {new_size}")

                                img.save(str(png_path), "PNG")
                                png_generated = True
                                logger.debug(f"Generated OCR PNG: {png_path}")
                            else:
                                logger.warning(f"Failed to generate OCR PNG from {pdf_path}")
                        except Exception as e:
                            logger.error(f"Error generating OCR PNG for magazine {magazine.id}: {e}")

                    if png_path.exists():
                        cover_path = str(png_path)
                        logger.debug(f"Using OCR PNG: {png_path}")
                else:
                    logger.warning(f"Magazine {magazine.id} is not a PDF, skipping OCR")

            if not cover_path:
                logger.warning(f"Could not generate OCR PNG for magazine {magazine.id}")
                job.status = OCRJob.StatusEnum.FAILED
                job.last_error = "Could not generate OCR PNG"
                stats["failed"] += 1
                continue

            # Mark as processing
            job.status = OCRJob.StatusEnum.PROCESSING
            job.started_at = datetime.now(UTC)
            job.attempt_count += 1

            job_data.append({
                "job": job,
                "magazine": magazine,
                "cover_path": cover_path,
                "language": job.language or magazine.language,
                "png_generated": png_generated
            })

        db.commit()

        if not job_data:
            logger.info("No valid jobs to process")
            return stats

        # Process jobs concurrently using process pool
        futures = {}
        for data in job_data:
            try:
                future = _process_pool.submit(
                    _ocr_worker,
                    data["cover_path"],
                    data["language"]
                )
                futures[future] = data
            except Exception as e:
                # If pool is broken, recreate it and retry once
                if "BrokenProcessPool" in str(type(e).__name__) or "not usable" in str(e):
                    logger.warning(f"Process pool is broken, recreating: {e}")
                    self._ensure_pool(force_recreate=True)
                    try:
                        future = _process_pool.submit(
                            _ocr_worker,
                            data["cover_path"],
                            data["language"]
                        )
                        futures[future] = data
                    except Exception as retry_e:
                        logger.error(f"Failed to submit job after pool recreation: {retry_e}")
                        # Mark job as failed
                        job = data["job"]
                        job.status = OCRJob.StatusEnum.FAILED
                        job.last_error = f"Process pool error: {str(retry_e)[:500]}"
                        job.completed_at = datetime.now(UTC)
                        stats["failed"] += 1
                else:
                    logger.error(f"Failed to submit OCR job: {e}")
                    job = data["job"]
                    job.status = OCRJob.StatusEnum.FAILED
                    job.last_error = f"Submit error: {str(e)[:500]}"
                    job.completed_at = datetime.now(UTC)
                    stats["failed"] += 1

        db.commit()

        if not futures:
            logger.warning("No jobs were successfully submitted to process pool")
            return stats

        # Collect results as they complete
        for future in as_completed(futures):
            data = futures[future]
            job = data["job"]
            magazine = data["magazine"]
            job_id = job.id  # Store ID before any processing
            magazine_id = magazine.id

            try:
                result = future.result(timeout=120)  # 2 minute timeout per job

                # Refresh objects from DB to avoid stale state
                db.expire_all()
                job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                magazine = db.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not job or not magazine:
                    logger.error(f"Job or magazine not found after processing: job={job_id}, magazine={magazine_id}")
                    stats["failed"] += 1
                    continue

                # Ensure started_at is timezone-aware (SQLite stores naive datetimes)
                started_at = job.started_at.replace(tzinfo=UTC) if job.started_at.tzinfo is None else job.started_at
                processing_time = (datetime.now(UTC) - started_at).total_seconds()

                if result.get("success"):
                    # Success - store metadata
                    metadata = result["metadata"]
                    job.status = OCRJob.StatusEnum.COMPLETED
                    job.ocr_metadata = metadata
                    job.completed_at = datetime.now(UTC)
                    job.processing_time_seconds = int(processing_time)

                    # Update magazine with metadata - use different keys for text vs OCR
                    if not magazine.extra_metadata:
                        magazine.extra_metadata = {}

                    # Store in text_metadata if direct extraction, ocr_metadata if OCR was used
                    extraction_method = metadata.get("extraction_method", "ocr_image")
                    if extraction_method in ["pdf_text", "epub_text"]:
                        magazine.extra_metadata["text_metadata"] = metadata
                        logger.info(f"Stored text extraction metadata for {magazine.title} (method: {extraction_method})")
                    else:
                        magazine.extra_metadata["ocr_metadata"] = metadata
                        logger.info(f"Stored OCR metadata for {magazine.title} (method: {extraction_method})")

                    # Flag the JSON field as modified so SQLAlchemy persists it
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(magazine, "extra_metadata")

                    # Clean up OCR PNG file immediately after successful processing
                    try:
                        cover_dir = Path(magazine.cover_path).parent if magazine.cover_path else None
                        if cover_dir:
                            ocr_covers_dir = cover_dir.parent / ".ocr_covers"
                            png_path = ocr_covers_dir / f"{magazine.id}_ocr.png"
                            if png_path.exists():
                                png_path.unlink()
                                logger.debug(f"Cleaned up OCR PNG after successful processing: {png_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup OCR PNG for magazine {magazine_id}: {cleanup_error}")

                    logger.info(f"OCR job {job_id} completed in {processing_time:.1f}s for {magazine.title}")
                    stats["succeeded"] += 1
                else:
                    # Worker reported error
                    error_msg = result.get("error", "Unknown error")
                    job.status = OCRJob.StatusEnum.FAILED
                    job.last_error = error_msg[:512]  # Truncate if too long

                    # Clean up OCR PNG file after failed processing too
                    try:
                        cover_dir = Path(magazine.cover_path).parent if magazine.cover_path else None
                        if cover_dir:
                            ocr_covers_dir = cover_dir.parent / ".ocr_covers"
                            png_path = ocr_covers_dir / f"{magazine.id}_ocr.png"
                            if png_path.exists():
                                png_path.unlink()
                                logger.debug(f"Cleaned up OCR PNG after failed processing: {png_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup OCR PNG for magazine {magazine_id}: {cleanup_error}")

                    logger.error(f"OCR job {job_id} failed: {error_msg}")
                    stats["failed"] += 1

            except Exception as e:
                # Processing exception - use stored job_id
                logger.error(f"Error processing OCR job {job_id}: {e}")
                try:
                    # Try to update job status
                    db.expire_all()
                    job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                    if job:
                        job.status = OCRJob.StatusEnum.FAILED
                        job.last_error = str(e)[:512]
                except Exception as update_error:
                    logger.error(f"Failed to update job status for {job_id}: {update_error}")
                stats["failed"] += 1

            stats["processed"] += 1

        db.commit()

        logger.info(f"OCR batch complete: {stats['processed']} processed, "
                    f"{stats['succeeded']} succeeded, {stats['failed']} failed")

        return stats

    @staticmethod
    def get_queue_status(db: Session) -> Dict[str, Any]:
        """
        Get current queue status.

        Args:
            db: Database session

        Returns:
            Dictionary with queue statistics
        """
        # Reset stuck jobs (processing for more than 30 minutes)
        from datetime import timedelta
        stuck_threshold = datetime.now(UTC) - timedelta(minutes=30)
        stuck_jobs = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PROCESSING,
            OCRJob.started_at < stuck_threshold
        ).all()

        if stuck_jobs:
            logger.warning(f"Found {len(stuck_jobs)} stuck OCR jobs, resetting to PENDING")
            for job in stuck_jobs:
                job.status = OCRJob.StatusEnum.PENDING
                job.started_at = None
            db.commit()

        pending_count = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PENDING
        ).count()

        processing_count = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PROCESSING
        ).count()

        completed_count = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.COMPLETED
        ).count()

        failed_count = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.FAILED
        ).count()

        # Get oldest pending job
        oldest_pending = db.query(OCRJob).filter(
            OCRJob.status == OCRJob.StatusEnum.PENDING
        ).order_by(OCRJob.created_at).first()

        return {
            "pending": pending_count,
            "processing": processing_count,
            "completed": completed_count,
            "failed": failed_count,
            "total": pending_count + processing_count + completed_count + failed_count,
            "oldest_pending_age_seconds": (
                int((datetime.now(UTC) - (oldest_pending.created_at.replace(tzinfo=UTC) if oldest_pending.created_at.tzinfo is None else oldest_pending.created_at)).total_seconds())
                if oldest_pending else None
            )
        }

    @staticmethod
    def cleanup_old_jobs(db: Session, days: int = 7) -> int:
        """
        Clean up completed/failed jobs older than specified days.

        Args:
            db: Database session
            days: Number of days to keep (default: 7)

        Returns:
            Number of jobs deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)

        deleted = db.query(OCRJob).filter(
            OCRJob.status.in_([OCRJob.StatusEnum.COMPLETED, OCRJob.StatusEnum.FAILED]),
            OCRJob.completed_at < cutoff
        ).delete()

        db.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old OCR jobs (older than {days} days)")

        return deleted

    def shutdown(self):
        """Shutdown the process pool gracefully."""
        global _process_pool
        if _process_pool is not None:
            logger.info("Shutting down OCR process pool")
            try:
                # Don't wait for pending jobs, cancel them
                _process_pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.warning(f"Error during process pool shutdown: {e}")
            finally:
                _process_pool = None
