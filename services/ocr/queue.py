"""Background OCR queue service for sequential processing."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

# Set environment variables before importing PaddleOCR-dependent modules
os.environ["USE_GPU"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from core import constants
from core.constants.date import NUMBER_TO_MONTH
from models.database import OCRJob, Magazine
from .service import OCRService

logger = logging.getLogger(__name__)


def _apply_scan_metadata_to_magazine(magazine: Magazine, scan_metadata: Dict[str, Any]) -> bool:
    """
    Apply scan/OCR metadata to magazine fields if not already present.
    Only fills in missing data, never overwrites existing metadata from filename parsing.

    Args:
        magazine: Magazine record to update
        scan_metadata: Metadata extracted from text scan or OCR

    Returns:
        True if any field was updated
    """
    if not scan_metadata:
        return False

    updated = False

    if not magazine.extra_metadata:
        magazine.extra_metadata = {}

    # Year - only if not already set
    if scan_metadata.get("year") and not magazine.extra_metadata.get("year"):
        magazine.extra_metadata["year"] = scan_metadata["year"]
        updated = True
        logger.debug(f"Applied year {scan_metadata['year']} from scan to {magazine.title}")

    # Month - only if not already set
    if scan_metadata.get("month") and not magazine.extra_metadata.get("month"):
        month_name = NUMBER_TO_MONTH.get(scan_metadata["month"], "")
        if month_name:
            magazine.extra_metadata["month"] = month_name
            updated = True
            logger.debug(f"Applied month {month_name} from scan to {magazine.title}")

    # Volume - only if not already set
    if scan_metadata.get("volume") and not magazine.extra_metadata.get("volume"):
        magazine.extra_metadata["volume"] = scan_metadata["volume"]
        updated = True
        logger.debug(f"Applied volume {scan_metadata['volume']} from scan to {magazine.title}")

    # Issue number - only if not already set
    if scan_metadata.get("issue_number") and not magazine.extra_metadata.get("issue_number"):
        magazine.extra_metadata["issue_number"] = scan_metadata["issue_number"]
        updated = True
        logger.debug(f"Applied issue number {scan_metadata['issue_number']} from scan to {magazine.title}")

    # Special edition - only if not already set
    if scan_metadata.get("special_edition") and not magazine.extra_metadata.get("special_edition"):
        magazine.extra_metadata["special_edition"] = scan_metadata["special_edition"]
        updated = True
        logger.debug(f"Applied special edition flag from scan to {magazine.title}")

    # Update issue_date if we found year and current date seems like a placeholder
    if updated and scan_metadata.get("year"):
        year = scan_metadata["year"]
        month = scan_metadata.get("month", 1)

        try:
            new_date = datetime(year, month, 1)
            # Only update if current issue_date appears to be a placeholder/default
            # (same as created_at or outside reasonable range)
            current_year = magazine.issue_date.year if magazine.issue_date else 1900
            # Check if current date is placeholder or invalid
            if current_year < 1900 or (  # noqa: W504
                magazine.created_at  # noqa: W504
                and abs((magazine.issue_date - magazine.created_at).total_seconds()) < 60
            ):
                magazine.issue_date = new_date
                logger.info(f"Updated issue_date to {new_date.strftime('%Y-%m')} for {magazine.title}")
        except ValueError as e:
            logger.warning(f"Invalid date from scan metadata (year={year}, month={month}): {e}")

    return updated


def _ocr_worker(cover_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Worker function that processes OCR synchronously.

    Args:
        cover_path: Path to cover image/PDF/EPUB
        language: Optional language hint for OCR

    Returns:
        Dictionary with OCR metadata
    """
    try:
        result = OCRService.analyze_cover(cover_path, language=language)
        return {"success": True, "metadata": result}
    except (RuntimeError, OSError, SystemError) as e:
        # Catch CPU instruction errors (SIGILL manifests as these)
        import traceback

        error_msg = f"OCR worker runtime error for {cover_path}: {e} (possible CPU instruction incompatibility)"
        error_trace = traceback.format_exc()
        logger.error(f"{error_msg}\n{error_trace}")
        return {
            "success": False,
            "error": f"Runtime error: {str(e)} (check CPU compatibility)",
        }
    except Exception as e:
        # Catch all other exceptions
        import traceback

        error_msg = f"OCR worker error for {cover_path}: {e}"
        error_trace = traceback.format_exc()
        logger.error(f"{error_msg}\n{error_trace}")
        return {"success": False, "error": str(e)}


class OCRQueueService:
    """Service for managing background OCR processing sequentially."""

    def __init__(self, max_workers: int = constants.OCR_MAX_WORKERS):
        """
        Initialize OCR queue service.

        Args:
            max_workers: Deprecated parameter (kept for compatibility)
        """
        # max_workers is now ignored since we process sequentially

    @staticmethod
    def queue_ocr_job(
        db: Session,
        magazine_id: int,
        priority: int = OCRJob.PriorityEnum.NORMAL.value,
        language: Optional[str] = None,
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
        existing = (
            db.query(OCRJob)
            .filter(
                OCRJob.magazine_id == magazine_id,
                OCRJob.status.in_([OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING]),
            )
            .first()
        )

        if existing:
            logger.debug(f"OCR job already queued for magazine {magazine_id}")
            return None

        # Create new job
        job = OCRJob(
            magazine_id=magazine_id,
            status=OCRJob.StatusEnum.PENDING,
            priority=priority,
            language=language,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(f"Queued OCR job {job.id} for magazine {magazine_id} (priority={priority})")
        return job

    def process_queue(self, db: Session, batch_size: int = 1, max_retries: int = 1) -> Dict[str, int]:
        """
        Process pending OCR jobs from the queue in batches.

        Args:
            db: Database session
            batch_size: Maximum number of jobs to process at once
            max_retries: Maximum number of retry attempts

        Returns:
            Dictionary with processing statistics
        """
        stats = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

        # Reset stuck jobs (processing for more than 30 minutes)
        from datetime import timedelta

        stuck_threshold = datetime.now(UTC) - timedelta(minutes=30)
        stuck_jobs = (
            db.query(OCRJob)
            .filter(
                OCRJob.status == OCRJob.StatusEnum.PROCESSING,
                OCRJob.started_at < stuck_threshold,
            )
            .all()
        )

        if stuck_jobs:
            logger.warning(f"Found {len(stuck_jobs)} stuck OCR jobs, resetting to PENDING")
            for job in stuck_jobs:
                job.status = OCRJob.StatusEnum.PENDING
                job.started_at = None
            db.commit()

        # Fetch pending jobs ordered by priority (highest first) and creation time
        pending_jobs = (
            db.query(OCRJob)
            .filter(
                OCRJob.status == OCRJob.StatusEnum.PENDING,
                OCRJob.attempt_count < max_retries,
            )
            .order_by(OCRJob.priority.desc(), OCRJob.created_at)
            .limit(batch_size)
            .all()
        )

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
                if pdf_path.suffix.lower() == ".pdf":
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
                            from core.constants.ocr import (
                                PDF_COVER_DPI_OCR,
                                OCR_IMAGE_MAX_DIMENSION,
                            )
                            from pdf2image import convert_from_path
                            from PIL import Image

                            images = convert_from_path(
                                str(pdf_path),
                                first_page=1,
                                last_page=1,
                                dpi=PDF_COVER_DPI_OCR,
                                fmt="png",
                            )

                            if images:
                                img = images[0]

                                # Resize if too large (using optimal max dimension)

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

            job_data.append(
                {
                    "job": job,
                    "magazine": magazine,
                    "cover_path": cover_path,
                    "language": job.language or magazine.language,
                    "png_generated": png_generated,
                }
            )

        db.commit()

        if not job_data:
            logger.info("No valid jobs to process")
            return stats

        # Process jobs sequentially
        for data in job_data:
            job = data["job"]
            magazine = data["magazine"]
            job_id = job.id
            magazine_id = magazine.id

            try:
                # Call the worker function directly (no multiprocessing)
                result = _ocr_worker(data["cover_path"], data["language"])

                # Refresh objects from DB to avoid stale state
                db.expire_all()
                job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                magazine = db.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not job or not magazine:
                    logger.error(f"Job or magazine not found after processing: job={job_id}, magazine={magazine_id}")
                    stats["failed"] += 1
                    stats["processed"] += 1
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
                        logger.info(
                            f"Stored text extraction metadata for {magazine.title} (method: {extraction_method})"
                        )
                    else:
                        magazine.extra_metadata["ocr_metadata"] = metadata
                        logger.info(f"Stored OCR metadata for {magazine.title} (method: {extraction_method})")

                    # Apply scan/OCR metadata to main magazine fields if missing
                    fields_updated = _apply_scan_metadata_to_magazine(magazine, metadata)
                    if fields_updated:
                        logger.info(f"Enhanced {magazine.title} with metadata from scan/OCR")

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
                    job.completed_at = datetime.now(UTC)

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
                # Processing exception
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"Error processing OCR job {job_id}: {e}", exc_info=True)

                # Try to update job status
                try:
                    db.expire_all()
                    job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                    if job:
                        job.status = OCRJob.StatusEnum.FAILED
                        job.last_error = f"{error_type}: {error_msg[:500]}"
                        job.completed_at = datetime.now(UTC)
                except Exception as update_error:
                    logger.error(f"Failed to update job status for {job_id}: {update_error}")
                stats["failed"] += 1

            stats["processed"] += 1
            db.commit()  # Commit after each job

        logger.info(
            f"OCR batch complete: {stats['processed']} processed, "
            f"{stats['succeeded']} succeeded, {stats['failed']} failed"
        )

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
        stuck_jobs = (
            db.query(OCRJob)
            .filter(
                OCRJob.status == OCRJob.StatusEnum.PROCESSING,
                OCRJob.started_at < stuck_threshold,
            )
            .all()
        )

        if stuck_jobs:
            logger.warning(f"Found {len(stuck_jobs)} stuck OCR jobs, resetting to PENDING")
            for job in stuck_jobs:
                job.status = OCRJob.StatusEnum.PENDING
                job.started_at = None
            db.commit()

        pending_count = db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PENDING).count()

        processing_count = db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PROCESSING).count()

        completed_count = db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.COMPLETED).count()

        failed_count = db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.FAILED).count()

        # Get oldest pending job
        oldest_pending = (
            db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PENDING).order_by(OCRJob.created_at).first()
        )

        return {
            "pending": pending_count,
            "processing": processing_count,
            "completed": completed_count,
            "failed": failed_count,
            "total": pending_count + processing_count + completed_count + failed_count,
            "oldest_pending_age_seconds": (
                int(
                    (
                        datetime.now(UTC)
                        - (
                            oldest_pending.created_at.replace(tzinfo=UTC)
                            if oldest_pending.created_at.tzinfo is None
                            else oldest_pending.created_at
                        )
                    ).total_seconds()
                )
                if oldest_pending
                else None
            ),
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

        deleted = (
            db.query(OCRJob)
            .filter(
                OCRJob.status.in_([OCRJob.StatusEnum.COMPLETED, OCRJob.StatusEnum.FAILED]),
                OCRJob.completed_at < cutoff,
            )
            .delete()
        )

        db.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old OCR jobs (older than {days} days)")

        return deleted

    def shutdown(self):
        """Shutdown method (no longer needed for sequential processing)."""


# Export all public items for wildcard imports
__all__ = ["OCRQueueService", "_apply_scan_metadata_to_magazine"]
