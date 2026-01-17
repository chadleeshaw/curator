"""
Download queue operation endpoints (retry, delete, cleanup)
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from models.database import DownloadSubmission
from core.utils import run_in_thread

from . import _shared


@_shared.router.post("/queue/retry/{submission_id}")
async def retry_download(submission_id: int) -> Dict[str, Any]:
    """Retry a failed download submission"""
    try:
        if not _shared._download_manager:
            raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

        def _retry():
            db_session = _shared._session_factory()
            try:
                submission = db_session.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()
                if not submission:
                    raise HTTPException(status_code=404, detail=ErrorMessages.SUBMISSION_NOT_FOUND)

                result = _shared._download_manager.retry_submission(submission_id, db_session)
                return {
                    "success": result["success"],
                    "message": result.get("message", "Retry submitted"),
                    "submission_id": submission_id,
                }
            finally:
                db_session.close()

        return await run_in_thread(_retry)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error retrying download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.delete("/queue/pending")
async def clear_pending_downloads() -> Dict[str, Any]:
    """Clear all pending downloads from the queue"""
    try:

        def _clear():
            db_session = _shared._session_factory()
            try:
                # Get all pending downloads
                pending_query = db_session.query(DownloadSubmission).filter(
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING
                )

                count = pending_query.count()

                if count == 0:
                    return {
                        "success": True,
                        "deleted": 0,
                        "message": "No pending downloads to clear",
                    }

                # Delete all pending downloads
                pending_query.delete()
                db_session.commit()

                _shared.logger.info(f"Cleared {count} pending downloads from queue")

                return {
                    "success": True,
                    "deleted": count,
                    "message": f"Cleared {count} pending download(s) from queue",
                }
            finally:
                db_session.close()

        return await run_in_thread(_clear)
    except Exception as e:
        _shared.logger.error(f"Error clearing pending downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.delete("/queue/{submission_id}")
async def delete_from_queue(submission_id: int) -> Dict[str, Any]:
    """Remove a submission from the download queue"""
    try:

        def _delete():
            db_session = _shared._session_factory()
            try:
                submission = db_session.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()
                if not submission:
                    raise HTTPException(status_code=404, detail=ErrorMessages.SUBMISSION_NOT_FOUND)

                title = submission.result_title
                db_session.delete(submission)
                db_session.commit()

                return {"success": True, "message": f"Removed '{title}' from queue"}
            finally:
                db_session.close()

        return await run_in_thread(_delete)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error deleting from queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.post("/queue/cleanup")
async def cleanup_old_submissions(days_old: int = 30, status_filter: str = None) -> Dict[str, Any]:
    """Clean up old download submissions"""
    try:

        def _cleanup():
            db_session = _shared._session_factory()
            try:
                cutoff_date = datetime.now(UTC) - timedelta(days=days_old)

                query = db_session.query(DownloadSubmission).filter(DownloadSubmission.created_at < cutoff_date)
                if status_filter:
                    query = query.filter(
                        DownloadSubmission.status == DownloadSubmission.StatusEnum[status_filter.upper()]
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

        return await run_in_thread(_cleanup)
    except Exception as e:
        _shared.logger.error(f"Error cleaning up queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))
