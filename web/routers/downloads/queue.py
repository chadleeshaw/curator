"""
Download queue listing and monitoring endpoints
"""

from typing import Any, Dict, Optional


from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import DownloadSubmission, PeriodicalTracking
from web.utils.responses import success_response

from . import _shared


@_shared.router.get("/queue")
async def get_download_queue_default(status: Optional[str] = None) -> Dict[str, Any]:
    """Get all download submissions (default endpoint), optionally filtered by status"""
    # Just call the /queue/all endpoint to avoid code duplication
    return await get_download_queue_all(status)


@_shared.router.get("/queue/all")
@handle_api_errors("Get download queue", _shared.logger)
async def get_download_queue_all(status: Optional[str] = None) -> Dict[str, Any]:
    """Get all download submissions, optionally filtered by status"""

    def operation(db):
        query = db.query(DownloadSubmission)
        if status:
            query = query.filter(DownloadSubmission.status == DownloadSubmission.StatusEnum[status.upper()])

        submissions = query.order_by(DownloadSubmission.created_at.desc()).all()

        # Get tracking info for magazine names
        tracking_map = {}
        tracking_ids = {s.tracking_id for s in submissions if s.tracking_id}
        if tracking_ids:
            trackings = db.query(PeriodicalTracking).filter(PeriodicalTracking.id.in_(tracking_ids)).all()
            tracking_map = {t.id: t.title for t in trackings}

        # Get download manager for real-time progress
        download_manager = _shared._download_manager

        # Count by status and build queue items with progress
        status_counts = {
            "queued": 0,
            "pending": 0,
            "downloading": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        queue_items = []
        for s in submissions:
            status_counts[s.status.value] = status_counts.get(s.status.value, 0) + 1

            # Get real-time progress for active downloads
            progress = None
            time_left = None
            size = None
            if s.status.value in ["downloading", "pending"] and s.job_id and download_manager:
                try:
                    client = download_manager._get_client_by_name(s.client_name)
                    if client:
                        client_status = client.get_status(s.job_id)
                        progress = client_status.get("progress")
                        time_left = client_status.get("time_left")
                        size = client_status.get("size")
                except Exception as e:
                    _shared.logger.debug(f"Could not get progress for job {s.job_id}: {e}")

            queue_items.append(
                {
                    "submission_id": s.id,
                    "tracking_id": s.tracking_id,
                    "title": s.result_title,
                    "magazine": tracking_map.get(s.tracking_id, "Unknown"),
                    "url": s.source_url or "",
                    "status": s.status.value,
                    "job_id": s.job_id,
                    "error": s.last_error,
                    "extra_status": s.extra_status,
                    "attempts": s.attempt_count,
                    "progress": progress,
                    "time_left": time_left,
                    "size": size,
                    "created_at": (s.created_at.isoformat() if s.created_at else None),
                    "updated_at": (s.updated_at.isoformat() if s.updated_at else None),
                }
            )

        return success_response(
            queue=queue_items,
            count=len(submissions),
            status_counts=status_counts,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.get("/queue/status")
@handle_api_errors("Get download queue status", _shared.logger)
async def get_download_queue_status() -> Dict[str, Any]:
    """Get download queue status including available slots"""

    def operation(db):
        # Count active downloads (pending + downloading)
        active_downloads = (
            db.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                    ]
                )
            )
            .count()
        )

        # Calculate available slots
        available_slots = max(0, _shared._download_manager.max_downloads - active_downloads)

        # Count all statuses
        status_counts = {
            "queued": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.QUEUED)
            .count(),
            "pending": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
            .count(),
            "downloading": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.DOWNLOADING)
            .count(),
            "completed": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED)
            .count(),
            "failed": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED)
            .count(),
            "skipped": db.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED)
            .count(),
        }

        return success_response(
            max_concurrent=_shared._download_manager.max_downloads,
            active=active_downloads,
            available_slots=available_slots,
            status_counts=status_counts,
        )

    return await with_db_session(_shared._session_factory, operation)
