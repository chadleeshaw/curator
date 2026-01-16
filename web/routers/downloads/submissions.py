"""
Download submission endpoints
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from models.database import DownloadSubmission, MagazineTracking
from web.schemas import (
    APIError,
    DownloadAllIssuesRequest,
    DownloadSingleIssueRequest,
    DownloadSubmissionResponse,
)
from core.utils import run_in_thread

from . import _shared


@_shared.router.post(
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
        503: {
            "description": ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE,
            "model": APIError,
        },
    },
)
async def download_all_periodical_issues(
    request: DownloadAllIssuesRequest,
) -> Dict[str, Any]:
    """Search for and download all available issues of a tracked periodical"""
    try:
        if not _shared._download_manager:
            raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

        def _download():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == request.tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail="Tracking record not found")

                results = _shared._download_manager.download_all_periodical_issues(request.tracking_id, db_session)
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

        return await run_in_thread(_download)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error downloading all issues: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.post("/single-issue")
async def download_single_issue(
    request: DownloadSingleIssueRequest,
) -> DownloadSubmissionResponse:
    """Download a single issue"""
    try:
        if not _shared._download_manager:
            raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

        def _download():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == request.tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail="Tracking record not found")

                search_result = {
                    "title": request.title,
                    "url": request.url,
                    "provider": request.provider or "manual",
                    "publication_date": (
                        datetime.fromisoformat(request.publication_date) if request.publication_date else None
                    ),
                    "raw_metadata": {},
                }

                submission = _shared._download_manager.download_single_issue(
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

        return await run_in_thread(_download)
    except HTTPException:
        raise
    except Exception as e:
        _shared.logger.error(f"Error downloading single issue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
