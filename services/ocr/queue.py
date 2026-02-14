"""Background OCR queue service for sequential processing."""

import logging
import multiprocessing
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

# Set environment variables before importing PaddleOCR-dependent modules
os.environ["USE_GPU"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from core import constants
from core.config import ConfigLoader
from core.constants.app import DB_COMMIT_RETRY_DELAY, DB_LOCK_RETRY_MAX
from core.constants.ocr import PNG_GENERATION_TIMEOUT
from models.database import OCRJob, Periodical
from .service import OCRService

logger = logging.getLogger(__name__)

# Use 'spawn' context to avoid fork-safety issues in multithreaded processes
_mp_ctx = multiprocessing.get_context("spawn")

# Retry settings for SQLite lock contention
_COMMIT_MAX_RETRIES = DB_LOCK_RETRY_MAX
_COMMIT_BASE_DELAY = DB_COMMIT_RETRY_DELAY


def _safe_commit(db: Session, context: str = "") -> None:
    """
    Commit with retry logic for transient SQLite database locks.

    SQLite only allows one writer at a time. If the busy_timeout is exceeded,
    SQLAlchemy raises OperationalError ("database is locked"). This helper
    retries the commit with exponential back-off so that transient contention
    doesn't cause permanent failures.

    Args:
        db: Database session to commit
        context: Human-readable label for log messages
    """
    from sqlalchemy.exc import OperationalError

    for attempt in range(1, _COMMIT_MAX_RETRIES + 1):
        try:
            db.commit()
            return
        except OperationalError as exc:
            if "database is locked" in str(exc) and attempt < _COMMIT_MAX_RETRIES:
                delay = _COMMIT_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Database locked during {context or 'commit'} "
                    f"(attempt {attempt}/{_COMMIT_MAX_RETRIES}), retrying in {delay:.1f}s"
                )
                db.rollback()
                time.sleep(delay)
            else:
                raise


def _generate_png_in_process(pdf_path: str, png_path: str, dpi: int, max_dimension: int, result_queue) -> None:
    """
    Generate OCR PNG from PDF in a child process.

    Using a separate process allows us to hard-kill poppler if it hangs
    on a corrupted PDF (threads cannot be killed in Python).
    """
    try:
        from pdf2image import convert_from_path
        from PIL import Image

        images = convert_from_path(
            pdf_path,
            first_page=1,
            last_page=1,
            dpi=dpi,
            fmt="png",
        )

        if images:
            img = images[0]
            original_size = img.size

            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            img.save(png_path, "PNG")
            result_queue.put({"success": True, "original_size": original_size})
        else:
            result_queue.put({"success": False, "error": "No images extracted"})
    except Exception as e:
        result_queue.put({"success": False, "error": str(e)})


def _apply_scan_metadata_to_magazine(
    magazine: Periodical,
    scan_metadata: Dict[str, Any],
    metadata_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Apply scan/OCR metadata to magazine using priority order + confidence thresholds.

    This function implements intelligent metadata aggregation:
    - Tries sources in priority order (default: ocr → text_scan → filename)
    - Checks confidence threshold for each source
    - First source meeting criteria wins for each field
    - Different fields can come from different sources

    Args:
        magazine: Magazine record to update
        scan_metadata: Metadata extracted from OCR or text scan
        metadata_config: Optional config with source_priority, confidence_thresholds, field_overrides
                        If None, uses defaults (backward compatible)

    Returns:
        True if any field was updated

    Examples:
        >>> # OCR finds year with high confidence, filename has issue number
        >>> result = _apply_scan_metadata_to_magazine(magazine, ocr_data, config)
        >>> # Result: year from OCR (85% conf), issue_number from filename
    """
    if not scan_metadata:
        return False

    updated = False

    if not magazine.extra_metadata:
        magazine.extra_metadata = {}

    # Get configuration with defaults
    if metadata_config is None:
        from core.constants.metadata import (
            DEFAULT_METADATA_SOURCE_PRIORITY,
            DEFAULT_METADATA_CONFIDENCE_THRESHOLDS,
            DEFAULT_FIELD_CONFIDENCE_OVERRIDES,
        )

        metadata_config = {
            "source_priority": DEFAULT_METADATA_SOURCE_PRIORITY,
            "confidence_thresholds": DEFAULT_METADATA_CONFIDENCE_THRESHOLDS,
            "field_overrides": DEFAULT_FIELD_CONFIDENCE_OVERRIDES,
        }

    source_priority = metadata_config.get("source_priority", ["ocr", "text_scan", "filename"])
    confidence_thresholds = metadata_config.get("confidence_thresholds", {"ocr": 70, "text_scan": 50, "filename": 0})
    field_overrides = metadata_config.get("field_overrides", {})

    # Gather metadata from all sources
    # Read existing values (from prior filename parsing) from derived_metadata
    filename_source = {}
    if magazine.derived_metadata:
        for key, val in magazine.derived_metadata.items():
            if isinstance(val, dict) and "value" in val:
                filename_source[key] = val["value"]
                # Propagate confidence if available
                if "confidence" in val:
                    conf = val["confidence"]
                    filename_source[f"{key}_confidence"] = conf * 100 if conf <= 1.0 else conf
            else:
                filename_source[key] = val

    sources = {
        "filename": filename_source,
        "text_scan": (magazine.parsed_metadata or {}).get("text_scan", {}),
        "ocr": scan_metadata or {},  # Current scan/OCR result
    }

    # All scan-derived fields belong in derived_metadata (structured with source/confidence)
    # (derived_fields set kept for documentation; all fields go to derived_metadata)

    # Fields to aggregate
    fields_to_process = ["year", "month", "volume", "issue_number", "special_edition"]

    # Process each field independently
    for field in fields_to_process:
        # Get field-specific threshold overrides
        field_config = field_overrides.get(field, {})

        # Try each source in priority order
        for source_name in source_priority:
            source_data = sources.get(source_name, {})
            value = source_data.get(field)

            if value is None:
                continue  # This source doesn't have this field

            # Normalize month to int for consistency with build_derived_metadata
            if field == "month" and isinstance(value, str):
                from core.constants.date import MONTH_TO_NUMBER

                value = MONTH_TO_NUMBER.get(value.lower())
                if value is None:
                    continue

            # Get confidence score (if available)
            confidence_key = f"{field}_confidence"
            confidence = source_data.get(confidence_key, 100)  # Default 100 if no confidence

            # Get threshold for this source/field combination
            threshold = field_config.get(source_name, confidence_thresholds.get(source_name, 0))

            # Check if confidence meets threshold
            if confidence is None or confidence >= threshold:
                # All scan-derived fields go to derived_metadata
                if not magazine.derived_metadata:
                    magazine.derived_metadata = {}
                norm_confidence = (
                    (confidence / 100.0) if isinstance(confidence, (int, float)) and confidence > 1.0 else confidence
                )
                current = magazine.derived_metadata.get(field)
                current_value = current.get("value") if isinstance(current, dict) else None
                if current_value != value:
                    magazine.derived_metadata[field] = {
                        "value": value,
                        "source": source_name,
                        "confidence": norm_confidence,
                    }
                    updated = True
                    logger.info(
                        f"Applied {field}={value} from {source_name} "
                        f"(confidence={confidence}%, threshold={threshold}%) to {magazine.title}"
                    )
                break  # Stop trying other sources for this field

            # Confidence didn't meet threshold
            logger.debug(f"Skipped {source_name} for {field}: confidence {confidence}% < threshold {threshold}%")

    # Update issue_date if we have year in derived_metadata
    year_entry = magazine.derived_metadata.get("year") if magazine.derived_metadata else None
    if updated and year_entry:
        year = year_entry["value"] if isinstance(year_entry, dict) else year_entry
        # Get month from derived_metadata (stored as int)
        month_entry = magazine.derived_metadata.get("month") if magazine.derived_metadata else None
        month = 1  # Default to January
        if month_entry:
            month_val = month_entry["value"] if isinstance(month_entry, dict) else month_entry
            if isinstance(month_val, int):
                month = month_val
            elif isinstance(month_val, str):
                from core.constants.date import MONTH_TO_NUMBER

                month = MONTH_TO_NUMBER.get(month_val.lower(), 1)

        try:
            new_date = datetime(int(year), month, 1, tzinfo=UTC)
            # Only update if current issue_date appears to be a placeholder/default
            current_year = magazine.issue_date.year if magazine.issue_date else 1900
            if current_year < 1900 or (  # noqa: W504
                magazine.created_at  # noqa: W504
                and abs((magazine.issue_date - magazine.created_at).total_seconds()) < 60
            ):
                magazine.issue_date = new_date
                logger.info(f"Updated issue_date to {new_date.strftime('%Y-%m')} for {magazine.title}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid date from metadata (year={year}, month={month}): {e}")

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
        import traceback

        error_str = str(e).lower()

        # Check for timeout errors from pytesseract
        if "timeout" in error_str or "timed out" in error_str:
            logger.warning(f"OCR timeout for {cover_path}: {e}")
            return {
                "success": False,
                "error": "OCR timeout: Operation took too long",
            }

        # Catch CPU instruction errors (SIGILL manifests as RuntimeError/OSError/SystemError)
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
        periodical_id: int,
        priority: int = OCRJob.PriorityEnum.NORMAL.value,
        language: Optional[str] = None,
    ) -> Optional[OCRJob]:
        """
        Queue an OCR job for background processing.

        Args:
            db: Database session
            periodical_id: Periodical ID to process
            priority: Job priority (LOW=1, NORMAL=5, HIGH=10)
            language: Optional language hint

        Returns:
            Created OCRJob or None if already exists
        """
        # Check if job already exists and is pending/processing
        existing = (
            db.query(OCRJob)
            .filter(
                OCRJob.periodical_id == periodical_id,
                OCRJob.status.in_([OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING]),
            )
            .first()
        )

        if existing:
            logger.debug(f"OCR job already queued for magazine {periodical_id}")
            return None

        # Create new job
        job = OCRJob(
            periodical_id=periodical_id,
            status=OCRJob.StatusEnum.PENDING,
            priority=priority,
            language=language,
        )
        db.add(job)
        _safe_commit(db, f"queue OCR job for magazine {periodical_id}")
        db.refresh(job)

        logger.info(f"Queued OCR job {job.id} for magazine {periodical_id} (priority={priority})")
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
            _safe_commit(db, "reset stuck OCR jobs")

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

        # Load metadata aggregation configuration
        config_loader = ConfigLoader()
        config_loader.get_metadata()

        # Prepare jobs for processing
        job_data = []
        for job in pending_jobs:
            # Get magazine and cover path
            magazine = db.query(Periodical).filter(Periodical.id == job.periodical_id).first()

            if not magazine:
                logger.warning(f"Magazine {job.periodical_id} not found for OCR job {job.id}")
                job.status = OCRJob.StatusEnum.FAILED
                job.last_error = "Magazine not found"
                _safe_commit(db, f"mark job {job.id} failed (magazine not found)")
                stats["failed"] += 1
                continue

            # Check if text_scan already has sufficient data (may have been run after job was queued)
            if magazine.parsed_metadata:
                # Skip if OCR was already done
                if magazine.parsed_metadata.get("ocr_scan"):
                    logger.info(f"Skipping OCR for {magazine.title} - already has ocr_scan")
                    job.status = OCRJob.StatusEnum.COMPLETED
                    job.completed_at = datetime.now(UTC)
                    job.last_error = "Skipped - already has ocr_scan"
                    _safe_commit(db, f"skip job {job.id} (already has ocr_scan)")
                    stats["skipped"] += 1
                    continue

                text_scan = magazine.parsed_metadata.get("text_scan", {})
                if text_scan.get("has_sufficient_metadata", False):
                    # Check needs_date_scan flag - if set and text_scan didn't find year, still need OCR
                    needs_date_scan = magazine.extra_metadata and magazine.extra_metadata.get("needs_date_scan", False)
                    if not needs_date_scan or text_scan.get("year"):
                        logger.info(f"Skipping OCR for {magazine.title} - text_scan already has sufficient metadata")
                        job.status = OCRJob.StatusEnum.COMPLETED
                        job.completed_at = datetime.now(UTC)
                        job.last_error = "Skipped - text_scan has sufficient metadata"
                        _safe_commit(db, f"skip job {job.id} (text_scan sufficient)")
                        stats["skipped"] += 1
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

                            # Run in a child process so we can hard-kill poppler
                            # if it hangs on a corrupted PDF
                            result_queue = _mp_ctx.Queue()
                            proc = _mp_ctx.Process(
                                target=_generate_png_in_process,
                                args=(str(pdf_path), str(png_path), PDF_COVER_DPI_OCR, OCR_IMAGE_MAX_DIMENSION, result_queue),
                                daemon=True,
                            )
                            proc.start()
                            proc.join(timeout=PNG_GENERATION_TIMEOUT)

                            if proc.is_alive():
                                proc.kill()
                                proc.join(timeout=2)
                                logger.warning(
                                    f"PNG generation timed out after {PNG_GENERATION_TIMEOUT}s "
                                    f"for magazine {magazine.id} - PDF may be corrupted"
                                )
                            elif not result_queue.empty():
                                result = result_queue.get_nowait()
                                if result.get("success"):
                                    png_generated = True
                                    logger.debug(f"Generated OCR PNG: {png_path}")
                                else:
                                    logger.warning(
                                        f"Failed to generate OCR PNG from {pdf_path}: {result.get('error')}"
                                    )
                            else:
                                logger.warning(f"PNG generation process exited without result for {pdf_path}")
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
                _safe_commit(db, f"mark job {job.id} failed (no OCR PNG)")
                stats["failed"] += 1
                continue

            # Mark as processing
            job.status = OCRJob.StatusEnum.PROCESSING
            job.started_at = datetime.now(UTC)
            job.attempt_count += 1
            _safe_commit(db, f"mark job {job.id} processing")

            job_data.append(
                {
                    "job": job,
                    "magazine": magazine,
                    "cover_path": cover_path,
                    "language": job.language or magazine.language,
                    "png_generated": png_generated,
                }
            )

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
                magazine = db.query(Periodical).filter(Periodical.id == magazine_id).first()

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

                    # Store OCR scan results in parsed_metadata
                    if not magazine.parsed_metadata:
                        magazine.parsed_metadata = {}

                    magazine.parsed_metadata["ocr_scan"] = metadata
                    extraction_method = metadata.get("extraction_method", "ocr_image")
                    logger.info(f"Stored OCR scan metadata for {magazine.title} (method: {extraction_method})")

                    # Rebuild derived_metadata with all scan results
                    from core.utils.metadata_builder import (
                        build_derived_metadata,
                        sync_issue_date_from_derived,
                    )

                    magazine.derived_metadata = build_derived_metadata(
                        file_scan=magazine.parsed_metadata.get("file_scan"),
                        text_scan=magazine.parsed_metadata.get("text_scan"),
                        ocr_scan=metadata,
                    )
                    logger.info(f"Enhanced {magazine.title} with metadata from OCR scan")

                    # Sync issue_date from derived_metadata (keeps column in sync with best data)
                    metadata_discovered = False
                    new_issue_date = sync_issue_date_from_derived(magazine.derived_metadata)
                    if new_issue_date:
                        magazine.issue_date = new_issue_date
                        metadata_discovered = True
                        logger.debug(f"Updated issue_date to {new_issue_date.strftime('%Y-%m')} from derived_metadata")

                    # Check if OCR found volume/issue (flag for reorganization)
                    if metadata.get("volume") or metadata.get("issue_number"):
                        metadata_discovered = True

                    # Flag for reorganization if we discovered new metadata
                    if metadata_discovered:
                        if not magazine.extra_metadata:
                            magazine.extra_metadata = {}
                        magazine.extra_metadata["needs_reorganization"] = True
                        magazine.extra_metadata["reorganization_reason"] = "metadata_discovered_by_ocr_queue"
                        logger.info(f"Flagged {magazine.title} for reorganization (metadata discovered by OCR)")

                    # Embed metadata into PDF file so it can be read on reimport without OCR
                    if magazine.file_path and Path(magazine.file_path).suffix.lower() == ".pdf":
                        try:
                            from core.utils.pdf_metadata import embed_metadata_in_pdf

                            embed_metadata_in_pdf(
                                pdf_path=magazine.file_path,
                                metadata=metadata,
                                title=magazine.title,
                            )
                        except Exception as embed_error:
                            logger.warning(f"Failed to embed metadata in PDF for {magazine.title}: {embed_error}")

                    # Flag the JSON fields as modified so SQLAlchemy persists them
                    from core.utils.db import mark_json_modified

                    mark_json_modified(magazine, "parsed_metadata", "derived_metadata", "extra_metadata")

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
            _safe_commit(db, f"OCR job {job_id} result")  # Commit after each job

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
            _safe_commit(db, "reset stuck OCR jobs in queue status")

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

        _safe_commit(db, "cleanup old OCR jobs")

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old OCR jobs (older than {days} days)")

        return deleted

    def shutdown(self):
        """Shutdown method (no longer needed for sequential processing)."""


# Export all public items for wildcard imports
__all__ = ["OCRQueueService", "_apply_scan_metadata_to_magazine"]
