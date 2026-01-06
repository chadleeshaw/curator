"""
Download management routes
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from models.database import DownloadSubmission, MagazineTracking
from web.schemas import (
    APIError,
    DownloadAllIssuesRequest,
    DownloadSingleIssueRequest,
    DownloadSubmissionResponse,
)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_download_manager = None
_download_client = None


def set_dependencies(session_factory, download_manager, download_client):
    """Set dependencies from main app"""
    global _session_factory, _download_manager, _download_client
    _session_factory = session_factory
    _download_manager = download_manager
    _download_client = download_client


@router.post(
    "/all-issues",
    summary="Download all issues of a periodical",
    description="Search providers and download all available issues of a tracked periodical.",
    responses={
        200: {
            "description": "Download submissions created",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "submitted": 5,
                        "duplicates": 2,
                        "failed": 0,
                    }
                }
            },
        },
        404: {"description": "Tracking record not found", "model": APIError},
        503: {"description": "Download manager not available", "model": APIError},
    },
)
async def download_all_periodical_issues(
    request: DownloadAllIssuesRequest,
) -> Dict[str, Any]:
    """Search for and download all available issues of a tracked periodical"""
    try:
        if not _download_manager:
            raise HTTPException(
                status_code=503, detail="Download manager not available"
            )

        db_session = _session_factory()
        try:
            tracking = (
                db_session.query(MagazineTracking)
                .filter(MagazineTracking.id == request.tracking_id)
                .first()
            )
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            results = _download_manager.download_all_periodical_issues(
                request.tracking_id, db_session
            )
            return {
                "success": True,
                "tracking_id": request.tracking_id,
                "magazine": tracking.title,
                "submitted": results["submitted"],
                "skipped": results["skipped"],
                "failed": results["failed"],
                "message": f"Started downloading issues: {results['submitted']} submitted, {results['skipped']} skipped",
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading all issues: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/single-issue")
async def download_single_issue(
    request: DownloadSingleIssueRequest,
) -> DownloadSubmissionResponse:
    """Download a single issue"""
    try:
        if not _download_manager:
            raise HTTPException(
                status_code=503, detail="Download manager not available"
            )

        db_session = _session_factory()
        try:
            tracking = (
                db_session.query(MagazineTracking)
                .filter(MagazineTracking.id == request.tracking_id)
                .first()
            )
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            search_result = {
                "title": request.title,
                "url": request.url,
                "provider": request.provider or "manual",
                "publication_date": (
                    datetime.fromisoformat(request.publication_date)
                    if request.publication_date
                    else None
                ),
                "raw_metadata": {},
            }

            submission = _download_manager.download_single_issue(
                request.tracking_id, search_result, db_session
            )
            if not submission:
                raise HTTPException(status_code=500, detail="Failed to submit download")

            return DownloadSubmissionResponse(
                submission_id=submission.id,
                job_id=submission.job_id,
                tracking_id=request.tracking_id,
                title=request.title,
                url=request.url,
                status=submission.status.value,
                message=f"Download submitted: {request.title}",
            )
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading single issue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{tracking_id}")
async def get_download_status_for_tracking(tracking_id: int) -> Dict[str, Any]:
    """Get download status for all submissions of a tracked periodical"""
    try:
        db_session = _session_factory()
        try:
            tracking = (
                db_session.query(MagazineTracking)
                .filter(MagazineTracking.id == tracking_id)
                .first()
            )
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            submissions = (
                db_session.query(DownloadSubmission)
                .filter(DownloadSubmission.tracking_id == tracking_id)
                .order_by(DownloadSubmission.created_at.desc())
                .all()
            )

            status_list = []
            for sub in submissions:
                client_status = None
                if _download_client and sub.job_id:
                    try:
                        client_status = _download_client.get_status(sub.job_id)
                    except Exception:
                        pass

                status_list.append(
                    {
                        "submission_id": sub.id,
                        "title": sub.result_title,
                        "status": sub.status.value,
                        "job_id": sub.job_id,
                        "progress": (
                            client_status.get("progress", 0) if client_status else 0
                        ),
                        "file_path": sub.file_path,
                        "created_at": (
                            sub.created_at.isoformat() if sub.created_at else None
                        ),
                    }
                )

            return {
                "success": True,
                "tracking_id": tracking_id,
                "magazine": tracking.title,
                "submissions": status_list,
                "count": len(status_list),
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/completed")
async def get_completed_downloads() -> Dict[str, Any]:
    """Get all completed downloads"""
    try:
        db_session = _session_factory()
        try:
            completed = (
                db_session.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED
                )
                .order_by(DownloadSubmission.updated_at.desc())
                .limit(100)
                .all()
            )

            return {
                "success": True,
                "downloads": [
                    {
                        "id": d.id,
                        "title": d.result_title,
                        "tracking_id": d.tracking_id,
                        "file_path": d.file_path,
                        "completed_at": (
                            d.updated_at.isoformat() if d.updated_at else None
                        ),
                    }
                    for d in completed
                ],
                "count": len(completed),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting completed downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/all")
async def get_download_queue(status: str = None) -> Dict[str, Any]:
    """Get all download submissions, optionally filtered by status"""
    try:
        db_session = _session_factory()
        try:
            query = db_session.query(DownloadSubmission)
            if status:
                query = query.filter(
                    DownloadSubmission.status
                    == DownloadSubmission.StatusEnum[status.upper()]
                )

            submissions = query.order_by(DownloadSubmission.created_at.desc()).all()

            return {
                "success": True,
                "queue": [
                    {
                        "id": s.id,
                        "tracking_id": s.tracking_id,
                        "title": s.result_title,
                        "status": s.status.value,
                        "job_id": s.job_id,
                        "error": s.last_error,
                        "attempts": s.attempt_count,
                        "created_at": (
                            s.created_at.isoformat() if s.created_at else None
                        ),
                    }
                    for s in submissions
                ],
                "count": len(submissions),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting download queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/retry/{submission_id}")
async def retry_download(submission_id: int) -> Dict[str, Any]:
    """Retry a failed download submission"""
    try:
        if not _download_manager:
            raise HTTPException(
                status_code=503, detail="Download manager not available"
            )

        db_session = _session_factory()
        try:
            submission = (
                db_session.query(DownloadSubmission)
                .filter(DownloadSubmission.id == submission_id)
                .first()
            )
            if not submission:
                raise HTTPException(status_code=404, detail="Submission not found")

            result = _download_manager.retry_submission(submission_id, db_session)
            return {
                "success": result["success"],
                "message": result.get("message", "Retry submitted"),
                "submission_id": submission_id,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queue/{submission_id}")
async def delete_from_queue(submission_id: int) -> Dict[str, Any]:
    """Remove a submission from the download queue"""
    try:
        db_session = _session_factory()
        try:
            submission = (
                db_session.query(DownloadSubmission)
                .filter(DownloadSubmission.id == submission_id)
                .first()
            )
            if not submission:
                raise HTTPException(status_code=404, detail="Submission not found")

            title = submission.result_title
            db_session.delete(submission)
            db_session.commit()

            return {"success": True, "message": f"Removed '{title}' from queue"}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting from queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/cleanup")
async def cleanup_old_submissions(
    days_old: int = 30, status_filter: str = None
) -> Dict[str, Any]:
    """Clean up old download submissions"""
    try:
        db_session = _session_factory()
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_old)

            query = db_session.query(DownloadSubmission).filter(
                DownloadSubmission.created_at < cutoff_date
            )
            if status_filter:
                query = query.filter(
                    DownloadSubmission.status
                    == DownloadSubmission.StatusEnum[status_filter.upper()]
                )

            count = query.count()
            query.delete()
            db_session.commit()

            return {
                "success": True,
                "deleted": count,
                "message": f"Cleaned up {count} old submissions",
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error cleaning up queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))
