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
from web.utils.responses import success_response

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
        return success_response(
            message=result.get("message", "Retry submitted"),
            submission_id=submission_id,
            success=result["success"],
        )

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
            return success_response("No pending downloads to clear", deleted=0)

        # Delete all pending downloads
        pending_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} pending downloads from queue")

        return success_response(
            f"Cleared {count} pending download(s) from queue",
            deleted=count,
        )

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
            return success_response("No queued downloads to clear", deleted=0)

        # Delete all queued downloads
        queued_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} queued downloads from queue")

        return success_response(
            f"Cleared {count} queued download(s) from queue",
            deleted=count,
        )

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
            return success_response("No failed downloads to clear", deleted=0)

        # Delete all failed downloads
        failed_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} failed downloads from queue")

        return success_response(
            f"Cleared {count} failed download(s) from queue",
            deleted=count,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/completed")
@handle_api_errors("Clear completed downloads", _shared.logger)
async def clear_completed_downloads() -> Dict[str, Any]:
    """Clear all completed downloads from the queue"""

    def operation(db):
        completed_query = db.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED
        )

        count = completed_query.count()

        if count == 0:
            return success_response("No completed downloads to clear", deleted=0)

        completed_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} completed downloads from queue")

        return success_response(
            f"Cleared {count} completed download(s) from queue",
            deleted=count,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/downloading")
@handle_api_errors("Clear downloading downloads", _shared.logger)
async def clear_downloading_downloads() -> Dict[str, Any]:
    """Clear all downloading downloads from the queue"""

    def operation(db):
        downloading_query = db.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.DOWNLOADING
        )

        count = downloading_query.count()

        if count == 0:
            return success_response("No downloading downloads to clear", deleted=0)

        downloading_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} downloading downloads from queue")

        return success_response(
            f"Cleared {count} downloading download(s) from queue",
            deleted=count,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/skipped")
@handle_api_errors("Clear skipped downloads", _shared.logger)
async def clear_skipped_downloads() -> Dict[str, Any]:
    """Clear all skipped downloads from the queue"""

    def operation(db):
        skipped_query = db.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED
        )

        count = skipped_query.count()

        if count == 0:
            return success_response("No skipped downloads to clear", deleted=0)

        skipped_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} skipped downloads from queue")

        return success_response(
            f"Cleared {count} skipped download(s) from queue",
            deleted=count,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.delete("/queue/all")
@handle_api_errors("Clear all downloads", _shared.logger)
async def clear_all_downloads() -> Dict[str, Any]:
    """Clear all downloads from the queue"""

    def operation(db):
        all_query = db.query(DownloadSubmission)

        count = all_query.count()

        if count == 0:
            return success_response("No downloads to clear", deleted=0)

        all_query.delete()
        db.commit()

        _shared.logger.info(f"Cleared {count} downloads from queue")

        return success_response(
            f"Cleared {count} download(s) from queue",
            deleted=count,
        )

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

        return success_response(f"Removed '{title}' from queue")

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

        return success_response(
            f"Cleaned up {count} old submissions",
            deleted=count,
        )

    return await with_db_session(_shared._session_factory, operation)
