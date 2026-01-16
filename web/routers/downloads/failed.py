"""
Failed downloads management endpoints
"""

from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from models.database import DownloadSubmission, MagazineTracking
from web.schemas import APIError
from core.utils import run_in_thread

from . import _shared


@_shared.router.get(
    "/failed",
    summary="Get failed downloads",
    description="Retrieve downloads that have failed, optionally including files marked as bad (2+ failures).",
    responses={
        200: {
            "description": "List of failed downloads",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "failed_downloads": [],
                        "bad_files": [],
                        "total_failed": 0,
                        "total_bad": 0,
                    }
                }
            },
        },
    },
)
async def get_failed_downloads(include_bad: bool = True) -> Dict[str, Any]:
    """Get all failed downloads and bad files"""
    try:
        if not _shared._download_manager:
            raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

        def _query():
            db_session = _shared._session_factory()
            try:
                # Get failed downloads (not yet marked as bad)
                failed = _shared._download_manager.get_failed_downloads(db_session, include_bad_files=False)

                # Get bad files (failed 2+ times)
                bad_files = _shared._download_manager.get_bad_files(db_session) if include_bad else []

                # Get tracking info for magazine names
                tracking_map = {}
                all_items = list(failed) + list(bad_files)
                tracking_ids = {d.tracking_id for d in all_items if d.tracking_id}
                if tracking_ids:
                    trackings = db_session.query(MagazineTracking).filter(MagazineTracking.id.in_(tracking_ids)).all()
                    tracking_map = {t.id: t.title for t in trackings}

                return {
                    "success": True,
                    "failed_downloads": [
                        {
                            "id": d.id,
                            "title": d.result_title,
                            "tracking_id": d.tracking_id,
                            "magazine": tracking_map.get(d.tracking_id, "Unknown"),
                            "url": d.source_url,
                            "attempt_count": d.attempt_count or 0,
                            "last_error": d.last_error,
                            "failed_at": d.updated_at.isoformat() if d.updated_at else None,
                        }
                        for d in failed
                    ],
                    "bad_files": [
                        {
                            "id": d.id,
                            "title": d.result_title,
                            "tracking_id": d.tracking_id,
                            "magazine": tracking_map.get(d.tracking_id, "Unknown"),
                            "url": d.source_url,
                            "attempt_count": d.attempt_count,
                            "last_error": d.last_error,
                            "failed_at": d.updated_at.isoformat() if d.updated_at else None,
                        }
                        for d in bad_files
                    ],
                    "total_failed": len(failed),
                    "total_bad": len(bad_files),
                }
            finally:
                db_session.close()

        return await run_in_thread(_query)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error getting failed downloads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.delete(
    "/failed/{submission_id}",
    summary="Remove a failed download",
    description="Delete a failed download submission from the database.",
)
async def delete_failed_download(submission_id: int) -> Dict[str, Any]:
    """Delete a failed download submission"""
    try:

        def _delete():
            db_session = _shared._session_factory()
            try:
                submission = db_session.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()

                if not submission:
                    raise HTTPException(status_code=404, detail=ErrorMessages.SUBMISSION_NOT_FOUND)

                if submission.status != DownloadSubmission.StatusEnum.FAILED:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Submission is not failed (status: {submission.status.value})",
                    )

                title = submission.result_title
                db_session.delete(submission)
                db_session.commit()

                return {
                    "success": True,
                    "message": f"Deleted failed download: {title}",
                }
            finally:
                db_session.close()

        return await run_in_thread(_delete)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error deleting failed download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
