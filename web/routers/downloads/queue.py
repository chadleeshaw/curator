"""
Download queue listing and monitoring endpoints
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException


from models.database import DownloadSubmission, PeriodicalTracking
from core.utils import run_in_thread

from . import _shared


@_shared.router.get("/queue")
async def get_download_queue_default(status: Optional[str] = None) -> Dict[str, Any]:
    """Get all download submissions (default endpoint), optionally filtered by status"""
    # Just call the /queue/all endpoint to avoid code duplication
    return await get_download_queue_all(status)


@_shared.router.get("/queue/all")
async def get_download_queue_all(status: Optional[str] = None) -> Dict[str, Any]:
    """Get all download submissions, optionally filtered by status"""
    try:

        def _query():
            db_session = _shared._session_factory()
            try:
                query = db_session.query(DownloadSubmission)
                if status:
                    query = query.filter(DownloadSubmission.status == DownloadSubmission.StatusEnum[status.upper()])

                submissions = query.order_by(DownloadSubmission.created_at.desc()).all()

                # Get tracking info for magazine names
                tracking_map = {}
                tracking_ids = {s.tracking_id for s in submissions if s.tracking_id}
                if tracking_ids:
                    trackings = (
                        db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id.in_(tracking_ids)).all()
                    )
                    tracking_map = {t.id: t.title for t in trackings}

                # Count by status
                status_counts = {
                    "queued": 0,
                    "pending": 0,
                    "downloading": 0,
                    "completed": 0,
                    "failed": 0,
                    "skipped": 0,
                }
                for s in submissions:
                    status_counts[s.status.value] = status_counts.get(s.status.value, 0) + 1

                return {
                    "success": True,
                    "queue": [
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
                            "created_at": (s.created_at.isoformat() if s.created_at else None),
                            "updated_at": (s.updated_at.isoformat() if s.updated_at else None),
                        }
                        for s in submissions
                    ],
                    "count": len(submissions),
                    "status_counts": status_counts,
                }
            finally:
                db_session.close()

        return await run_in_thread(_query)
    except Exception as e:
        _shared.logger.error(f"Error getting download queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.get("/queue/status")
async def get_download_queue_status() -> Dict[str, Any]:
    """Get download queue status including available slots"""
    try:

        def _query():
            db_session = _shared._session_factory()
            try:
                # Count active downloads (pending + downloading)
                active_downloads = (
                    db_session.query(DownloadSubmission)
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
                    "queued": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.QUEUED)
                    .count(),
                    "pending": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
                    .count(),
                    "downloading": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.DOWNLOADING)
                    .count(),
                    "completed": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED)
                    .count(),
                    "failed": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED)
                    .count(),
                    "skipped": db_session.query(DownloadSubmission)
                    .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED)
                    .count(),
                }

                return {
                    "success": True,
                    "max_concurrent": _shared._download_manager.max_downloads,
                    "active": active_downloads,
                    "available_slots": available_slots,
                    "status_counts": status_counts,
                }
            finally:
                db_session.close()

        return await run_in_thread(_query)
    except Exception as e:
        _shared.logger.error(f"Error getting download queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
