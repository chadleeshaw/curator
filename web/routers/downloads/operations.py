"""
Download queue operation endpoints (retry, delete, cleanup)
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import DownloadSubmission

from . import _shared


@_shared.router.post("/queue/retry/{submission_id}")
@handle_api_errors("Retry download", _shared.logger)
async def retry_download(submission_id: int) -> Dict[str, Any]:
    """Retry a failed download submission"""
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def operation(db):
        submission = db.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail=ErrorMessages.SUBMISSION_NOT_FOUND)

        result = _shared._download_manager.retry_submission(submission_id, db)
        return {
            "success": result["success"],
            "message": result.get("message", "Retry submitted"),
            "submission_id": submission_id,
        }

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/pending")
@handle_api_errors("Clear pending downloads", _shared.logger)
async def clear_pending_downloads() -> Dict[str, Any]:
    """Clear all pending downloads from the queue"""

    def operation(db):
        # Get all pending downloads
        pending_query = db.query(DownloadSubmission).filter(
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
        db.commit()

        _shared.logger.info(f"Cleared {count} pending downloads from queue")

        return {
            "success": True,
            "deleted": count,
            "message": f"Cleared {count} pending download(s) from queue",
        }

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/queued")
@handle_api_errors("Clear queued downloads", _shared.logger)
async def clear_queued_downloads() -> Dict[str, Any]:
    """Clear all queued downloads from the queue"""

    def operation(db):
        # Get all queued downloads
        queued_query = db.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.QUEUED
        )

        count = queued_query.count()

        if count == 0:
            return {
                "success": True,
                "deleted": 0,
                "message": "No queued downloads to clear",
            }

        # Delete all queued downloads
        queued_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} queued downloads from queue")

        return {
            "success": True,
            "deleted": count,
            "message": f"Cleared {count} queued download(s) from queue",
        }

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/failed")
@handle_api_errors("Clear failed downloads", _shared.logger)
async def clear_failed_downloads() -> Dict[str, Any]:
    """Clear all failed downloads from the queue"""

    def operation(db):
        # Get all failed downloads
        failed_query = db.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED
        )

        count = failed_query.count()

        if count == 0:
            return {
                "success": True,
                "deleted": 0,
                "message": "No failed downloads to clear",
            }

        # Delete all failed downloads
        failed_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} failed downloads from queue")

        return {
            "success": True,
            "deleted": count,
            "message": f"Cleared {count} failed download(s) from queue",
        }

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/{submission_id}")
@handle_api_errors("Delete from queue", _shared.logger)
async def delete_from_queue(submission_id: int) -> Dict[str, Any]:
    """Remove a submission from the download queue"""

    def operation(db):
        submission = db.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail=ErrorMessages.SUBMISSION_NOT_FOUND)

        title = submission.result_title
        db.delete(submission)
        db.commit()

        return {"success": True, "message": f"Removed '{title}' from queue"}

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.post("/queue/cleanup")
@handle_api_errors("Cleanup old submissions", _shared.logger)
async def cleanup_old_submissions(days_old: int = 30, status_filter: str = None) -> Dict[str, Any]:
    """Clean up old download submissions"""

    def operation(db):
        cutoff_date = datetime.now(UTC) - timedelta(days=days_old)

        query = db.query(DownloadSubmission).filter(DownloadSubmission.created_at < cutoff_date)
        if status_filter:
            query = query.filter(DownloadSubmission.status == DownloadSubmission.StatusEnum[status_filter.upper()])

        count = query.count()
        query.delete()
        db.commit()

        return {
            "success": True,
            "deleted": count,
            "message": f"Cleaned up {count} old submissions",
        }

    return await with_db_session(_shared._session_factory, operation)
