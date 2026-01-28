"""OCR queue management endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import sessionmaker

from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import OCRJob, Periodical
from services.ocr.queue import OCRQueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ocr", tags=["ocr"])

# Global dependencies
_session_factory: Optional[sessionmaker] = None


def set_dependencies(session_factory: sessionmaker) -> None:
    """Set router dependencies."""
    global _session_factory
    _session_factory = session_factory


@router.get("/queue")
@handle_api_errors("Get OCR queue", logger)
async def get_ocr_queue(status: Optional[str] = None):
    """
    Get OCR queue with optional status filter.

    Args:
        status: Optional filter (pending, processing, completed, failed)

    Returns:
        List of OCR jobs with magazine details
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        query = db.query(OCRJob).join(Periodical, OCRJob.periodical_id == Periodical.id)

        # Filter by status if provided
        if status:
            try:
                status_enum = OCRJob.StatusEnum[status.upper()]
                query = query.filter(OCRJob.status == status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        # Order by priority (highest first) and creation time
        jobs = query.order_by(OCRJob.priority.desc(), OCRJob.created_at).all()

        # Build response with magazine details
        result = []
        for job in jobs:
            magazine = (
                db.query(Periodical).filter(Periodical.id == job.periodical_id).first()
            )
            if not magazine:
                continue

            # Format issue date for display
            issue_display = ""
            if magazine.issue_date:
                issue_display = magazine.issue_date.strftime("%b %Y")

            result.append(
                {
                    "id": job.id,
                    "magazine_id": job.periodical_id,
                    "magazine_title": magazine.title,
                    "magazine_issue": issue_display,
                    "magazine_year": (
                        magazine.issue_date.year if magazine.issue_date else None
                    ),
                    "tracking_id": magazine.tracking_id,
                    "tracking_title": None,  # Will be populated below
                    "status": job.status.value,
                    "priority": job.priority,
                    "language": job.language,
                    "attempt_count": job.attempt_count,
                    "last_error": job.last_error,
                    "ocr_metadata": job.ocr_metadata,
                    "processing_time_seconds": job.processing_time_seconds,
                    "created_at": (
                        job.created_at.isoformat() if job.created_at else None
                    ),
                    "started_at": (
                        job.started_at.isoformat() if job.started_at else None
                    ),
                    "completed_at": (
                        job.completed_at.isoformat() if job.completed_at else None
                    ),
                }
            )

        # Get tracking titles for all jobs with tracking_id
        from models.database import PeriodicalTracking

        tracking_ids = {j["tracking_id"] for j in result if j["tracking_id"]}
        if tracking_ids:
            trackings = (
                db.query(PeriodicalTracking)
                .filter(PeriodicalTracking.id.in_(tracking_ids))
                .all()
            )
            tracking_map = {t.id: t.title for t in trackings}

            # Update tracking_title in results
            for job_data in result:
                if job_data["tracking_id"]:
                    job_data["tracking_title"] = tracking_map.get(
                        job_data["tracking_id"], job_data["magazine_title"]
                    )
                else:
                    job_data["tracking_title"] = job_data["magazine_title"]

        return {"jobs": result, "count": len(result)}

    return await with_db_session(_session_factory, operation)


@router.get("/queue/stats")
@handle_api_errors("Get OCR stats", logger)
async def get_ocr_stats():
    """
    Get OCR queue statistics.

    Returns:
        Status counts and queue information
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        stats = OCRQueueService.get_queue_status(db)
        return stats

    return await with_db_session(_session_factory, operation)


@router.post("/retry/{job_id}")
@handle_api_errors("Retry OCR job", logger)
async def retry_ocr_job(job_id: int):
    """
    Retry a failed OCR job.

    Args:
        job_id: OCR job ID to retry

    Returns:
        Updated job details
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail=ErrorMessages.OCR_JOB_NOT_FOUND)

        if job.status != OCRJob.StatusEnum.FAILED:
            raise HTTPException(
                status_code=400,
                detail=f"Can only retry failed jobs (current status: {job.status.value})",
            )

        # Reset job to pending
        job.status = OCRJob.StatusEnum.PENDING
        job.last_error = None
        job.started_at = None
        job.completed_at = None
        job.processing_time_seconds = None

        db.commit()
        db.refresh(job)

        logger.info(f"Reset OCR job {job_id} to pending for retry")

        return {
            "id": job.id,
            "status": job.status.value,
            "message": "Job queued for retry",
        }

    return await with_db_session(_session_factory, operation)


@router.delete("/queue/failed")
@handle_api_errors("Clear failed OCR jobs", logger)
async def clear_failed_ocr_jobs():
    """
    Clear all failed OCR jobs from the queue.
    This is useful for cleaning up jobs that have repeatedly failed.

    Returns:
        Number of jobs cleared
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        # Delete all failed jobs
        failed_jobs = (
            db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.FAILED).all()
        )

        count = len(failed_jobs)

        for job in failed_jobs:
            db.delete(job)

        db.commit()

        logger.info(f"Cleared {count} failed OCR jobs from queue")

        return {"message": f"Cleared {count} failed OCR jobs", "count": count}

    return await with_db_session(_session_factory, operation)


@router.delete("/queue")
@handle_api_errors("Clear pending OCR jobs", logger)
async def clear_pending_ocr_jobs():
    """
    Clear all pending OCR jobs from the queue.
    This is useful when OCR is disabled to clean up the queue.

    Returns:
        Number of jobs cleared
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        # Delete all pending jobs
        pending_jobs = (
            db.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PENDING).all()
        )

        count = len(pending_jobs)

        for job in pending_jobs:
            db.delete(job)

        db.commit()

        logger.info(f"Cleared {count} pending OCR jobs from queue")

        return {"message": f"Cleared {count} pending OCR jobs", "count": count}

    return await with_db_session(_session_factory, operation)


@router.delete("/queue/{job_id}")
@handle_api_errors("Delete OCR job", logger)
async def delete_ocr_job(job_id: int):
    """
    Delete an OCR job from the queue.
    This will cancel processing jobs and remove pending/failed jobs.

    Args:
        job_id: OCR job ID to delete

    Returns:
        Success message
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail=ErrorMessages.OCR_JOB_NOT_FOUND)

        # Log appropriate message based on status
        action = (
            "cancelled" if job.status == OCRJob.StatusEnum.PROCESSING else "deleted"
        )

        db.delete(job)
        db.commit()

        logger.info(
            f"{action.capitalize()} OCR job {job_id} (status: {job.status.value})"
        )

        return {"message": f"Job {action} successfully"}

    return await with_db_session(_session_factory, operation)


@router.post("/queue/{magazine_id}")
@handle_api_errors("Queue magazine OCR", logger)
async def queue_magazine_ocr(
    magazine_id: int, priority: int = OCRJob.PriorityEnum.NORMAL.value
):
    """
    Manually queue OCR for a magazine.

    Args:
        magazine_id: Magazine ID to process
        priority: Job priority (1=LOW, 5=NORMAL, 10=HIGH)

    Returns:
        Created job details
    """
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def operation(db):
        # Verify magazine exists
        magazine = db.query(Periodical).filter(Periodical.id == magazine_id).first()
        if not magazine:
            raise HTTPException(status_code=404, detail="Magazine not found")

        # Queue the job
        job = OCRQueueService.queue_ocr_job(
            db=db,
            periodical_id=magazine_id,
            priority=priority,
            language=magazine.language,
        )

        if not job:
            # Job already exists
            existing = (
                db.query(OCRJob)
                .filter(
                    OCRJob.periodical_id == magazine_id,
                    OCRJob.status.in_(
                        [OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING]
                    ),
                )
                .first()
            )

            return {
                "message": "Job already queued",
                "job_id": existing.id if existing else None,
            }

        return {
            "id": job.id,
            "magazine_id": job.periodical_id,
            "status": job.status.value,
            "priority": job.priority,
            "message": "Job queued successfully",
        }

    return await with_db_session(_session_factory, operation)
