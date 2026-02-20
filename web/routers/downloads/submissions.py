"""
Download submission endpoints
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils.error_handling import handle_api_errors
from models.database import DownloadSubmission, PeriodicalTracking
from web.schemas import (
    APIError,
    DownloadAllIssuesRequest,
    DownloadBatchIssuesRequest,
    DownloadSingleIssueRequest,
    DownloadSubmissionResponse,
)
from core.utils.db import with_db_session
from web.utils.responses import success_response

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
@handle_api_errors("Download all periodical issues", _shared.logger)
async def download_all_periodical_issues(
    request: DownloadAllIssuesRequest,
) -> Dict[str, Any]:
    """Search for and download all available issues of a tracked periodical"""
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.tracking_id).first()
        if not tracking:
            raise HTTPException(
                status_code=404,
                detail=f"Tracking record not found: {request.tracking_id}",
            )

        results = _shared._download_manager.download_all_periodical_issues(request.tracking_id, db)
        submitted = results.get("submitted", 0)
        queued = results.get("queued", 0)
        skipped = results.get("skipped", 0)
        failed = results.get("failed", 0)
        return success_response(
            message=(f"Batch download: {submitted} submitted, {queued} queued, " f"{skipped} skipped, {failed} failed"),
            tracking_id=request.tracking_id,
            periodical=tracking.title,
            submitted=submitted,
            queued=queued,
            skipped=skipped,
            failed=failed,
            results=results,
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.post("/single-issue")
@handle_api_errors("Download single issue", _shared.logger)
async def download_single_issue(
    request: DownloadSingleIssueRequest,
) -> DownloadSubmissionResponse:
    """Download a single issue"""
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.tracking_id).first()
        if not tracking:
            raise HTTPException(
                status_code=404,
                detail=f"Tracking record not found: {request.tracking_id}",
            )

        search_result = {
            "title": request.title,
            "url": request.url,
            "provider": request.provider or "manual",
            "publication_date": (
                datetime.fromisoformat(request.publication_date) if request.publication_date else None
            ),
            "raw_metadata": {},
        }

        submission = _shared._download_manager.download_single_issue(request.tracking_id, search_result, db)
        if not submission:
            # Check if there's a failed submission with error details
            failed_submission = (
                db.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.tracking_id == request.tracking_id,
                    DownloadSubmission.result_title == request.title,
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                )
                .order_by(DownloadSubmission.created_at.desc())
                .first()
            )

            if failed_submission and failed_submission.last_error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to submit download: {failed_submission.last_error}",
                )

            # Check if it was skipped
            skipped_submission = (
                db.query(DownloadSubmission)
                .filter(
                    DownloadSubmission.tracking_id == request.tracking_id,
                    DownloadSubmission.result_title == request.title,
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED,
                )
                .order_by(DownloadSubmission.created_at.desc())
                .first()
            )

            if skipped_submission:
                raise HTTPException(
                    status_code=400,
                    detail="Download was skipped (duplicate or blacklisted file)",
                )

            # Generic fallback
            raise HTTPException(
                status_code=500,
                detail="Failed to submit download - check download client connection",
            )

        return DownloadSubmissionResponse(
            submission_id=submission.id,
            job_id=submission.job_id,
            tracking_id=request.tracking_id,
            title=request.title,
            url=request.url,
            status=submission.status.value,
            message=f"Download submitted: {request.title}",
        )

    return await with_db_session(_shared._session_factory, operation)


@_shared.router.post(
    "/batch-issues",
    summary="Download multiple issues in a single request",
    description="Submit multiple issues for download in one batch. "
    "Issues that exceed the concurrent download limit will be queued automatically.",
    responses={
        200: {
            "description": "Batch download results",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "submitted": 5,
                        "queued": 10,
                        "skipped": 2,
                        "failed": 1,
                        "results": [],
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
@handle_api_errors("Batch download issues", _shared.logger)
async def download_batch_issues(
    request: DownloadBatchIssuesRequest,
) -> Dict[str, Any]:
    """Download multiple issues in a single batch request"""
    if not _shared._download_manager:
        raise HTTPException(status_code=503, detail=ErrorMessages.DOWNLOAD_MANAGER_UNAVAILABLE)

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.tracking_id).first()
        if not tracking:
            raise HTTPException(
                status_code=404,
                detail=f"Tracking record not found: {request.tracking_id}",
            )

        submitted = 0
        queued = 0
        skipped = 0
        failed = 0
        results = []

        for issue in request.issues:
            search_result = {
                "title": issue.title,
                "url": issue.url,
                "provider": issue.provider or "manual",
                "publication_date": (
                    datetime.fromisoformat(issue.publication_date) if issue.publication_date else None
                ),
                "raw_metadata": {},
            }

            try:
                submission = _shared._download_manager.download_single_issue(request.tracking_id, search_result, db)

                if submission:
                    status = submission.status.value
                    if submission.status == DownloadSubmission.StatusEnum.PENDING:
                        submitted += 1
                    elif submission.status == DownloadSubmission.StatusEnum.QUEUED:
                        queued += 1
                    elif submission.status == DownloadSubmission.StatusEnum.SKIPPED:
                        skipped += 1
                    else:
                        failed += 1
                    results.append({"title": issue.title, "status": status})
                else:
                    # None means an error (already downloading, permanently failed, etc.)
                    failed += 1
                    results.append({"title": issue.title, "status": "failed"})

            except Exception as e:
                _shared.logger.error(f"Failed to submit {issue.title}: {e}")
                failed += 1
                results.append({"title": issue.title, "status": "failed", "error": str(e)})

        return success_response(
            message=(f"Batch download: {submitted} submitted, {queued} queued, " f"{skipped} skipped, {failed} failed"),
            tracking_id=request.tracking_id,
            magazine=tracking.title,
            submitted=submitted,
            queued=queued,
            skipped=skipped,
            failed=failed,
            results=results,
        )

    return await with_db_session(_shared._session_factory, operation)
