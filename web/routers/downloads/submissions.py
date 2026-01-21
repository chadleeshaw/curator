"""
Download submission endpoints
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from models.database import DownloadSubmission, PeriodicalTracking
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
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def _download():
        db_session = _shared._session_factory()
        try:
            tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.tracking_id).first()
            if not tracking:
                raise ValueError(f"Tracking record not found: {request.tracking_id}")

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

    try:
        return await run_in_thread(_download)
    except ValueError as e:
        # Tracking record not found
        if "Tracking record not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _shared.logger.error(f"Error downloading all issues: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_shared.router.post("/single-issue")
async def download_single_issue(
    request: DownloadSingleIssueRequest,
) -> DownloadSubmissionResponse:
    """Download a single issue"""
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def _download():
        db_session = _shared._session_factory()
        try:
            tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.tracking_id).first()
            if not tracking:
                raise ValueError(f"Tracking record not found: {request.tracking_id}")

            search_result = {
                "title": request.title,
                "url": request.url,
                "provider": request.provider or "manual",
                "publication_date": (
                    datetime.fromisoformat(request.publication_date) if request.publication_date else None
                ),
                "raw_metadata": {},
            }

            submission = _shared._download_manager.download_single_issue(request.tracking_id, search_result, db_session)
            if not submission:
                # Check if there's a failed submission with error details
                failed_submission = (
                    db_session.query(DownloadSubmission)
                    .filter(
                        DownloadSubmission.tracking_id == request.tracking_id,
                        DownloadSubmission.result_title == request.title,
                        DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                    )
                    .order_by(DownloadSubmission.created_at.desc())
                    .first()
                )

                if failed_submission and failed_submission.last_error:
                    raise RuntimeError(f"Failed to submit download: {failed_submission.last_error}")

                # Check if it was skipped
                skipped_submission = (
                    db_session.query(DownloadSubmission)
                    .filter(
                        DownloadSubmission.tracking_id == request.tracking_id,
                        DownloadSubmission.result_title == request.title,
                        DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED,
                    )
                    .order_by(DownloadSubmission.created_at.desc())
                    .first()
                )

                if skipped_submission:
                    raise RuntimeError("Download was skipped (duplicate or blacklisted file)")

                # Generic fallback
                raise RuntimeError("Failed to submit download - check download client connection")

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

    try:
        return await run_in_thread(_download)
    except ValueError as e:
        # Tracking record not found
        if "Tracking record not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Failed to submit download
        _shared.logger.error(f"Error downloading single issue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        _shared.logger.error(f"Error downloading single issue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
