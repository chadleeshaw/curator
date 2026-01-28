"""
Download status query endpoints
"""

from typing import Any, Dict

from fastapi import HTTPException

from core.utils import run_in_thread
from core.utils.error_handling import handle_api_errors
from models.database import DownloadSubmission, PeriodicalTracking

from . import _shared


@_shared.router.get("/status/{tracking_id}")
@handle_api_errors("Get download status for tracking", _shared.logger)
async def get_download_status_for_tracking(tracking_id: int) -> Dict[str, Any]:
    """Get download status for all submissions of a tracked periodical"""

    def _query():
        db_session = _shared._session_factory()
        try:
            tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
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
                if _shared._download_client and sub.job_id:
                    try:
                        client_status = _shared._download_client.get_status(sub.job_id)
                    except Exception:
                        pass

                status_list.append(
                    {
                        "submission_id": sub.id,
                        "title": sub.result_title,
                        "status": sub.status.value,
                        "job_id": sub.job_id,
                        "progress": (client_status.get("progress", 0) if client_status else 0),
                        "file_path": sub.file_path,
                        "created_at": (sub.created_at.isoformat() if sub.created_at else None),
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

    return await run_in_thread(_query)


@_shared.router.get("/completed")
@handle_api_errors("Get completed downloads", _shared.logger)
async def get_completed_downloads() -> Dict[str, Any]:
    """Get all completed downloads"""

    def _query():
        db_session = _shared._session_factory()
        try:
            completed = (
                db_session.query(DownloadSubmission)
                .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED)
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
                        "completed_at": (d.updated_at.isoformat() if d.updated_at else None),
                    }
                    for d in completed
                ],
                "count": len(completed),
            }
        finally:
            db_session.close()

    return await run_in_thread(_query)
