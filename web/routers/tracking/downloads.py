"""
Tracking routes - Download tracking
"""

from typing import Any, Dict

from fastapi import HTTPException, Query

from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.db import mark_json_modified
from core.utils.error_handling import handle_api_errors
from models.database import PeriodicalTracking
from web.schemas import APIError
from web.utils.responses import success_response

from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


@router.post(
    "/periodicals/tracking/{tracking_id}/editions/{edition_id}/track",
    summary="Track a single issue",
    description="Mark a specific edition/issue for tracking and automatic download.",
    responses={
        200: {
            "description": "Issue tracking updated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Issue marked for tracking",
                        "edition_id": "OL123456M",
                        "tracked": True,
                    }
                }
            },
        },
        404: {"description": ErrorMessages.TRACKING_NOT_FOUND, "model": APIError},
        500: {"description": "Failed to update tracking", "model": APIError},
    },
)
@handle_api_errors("Track single issue", logger)
async def track_single_issue(tracking_id: int, edition_id: str, track: bool = Query(True)) -> Dict[str, Any]:
    """Track or untrack a single issue/edition"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if not tracking:
            raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

        # Initialize selected_editions if None
        if tracking.selected_editions is None:
            tracking.selected_editions = {}

        # Update the selected_editions dictionary
        tracking.selected_editions[edition_id] = track

        # Mark the column as modified for SQLAlchemy to detect the change
        mark_json_modified(tracking, "selected_editions")

        db.commit()

        # Trigger immediate auto-download check if an edition was marked for tracking
        if track and _shared._auto_download_task_func:
            import asyncio

            try:
                asyncio.create_task(_shared._auto_download_task_func())
                logger.info(f"Triggered immediate auto-download check after tracking edition {edition_id}")
            except Exception as e:
                logger.warning(f"Could not trigger immediate auto-download: {e}")

        action = "marked for tracking" if track else "unmarked from tracking"
        logger.info(f"Issue {edition_id} {action} for periodical '{tracking.title}'")

        return success_response(
            f"Issue {action}",
            tracking_id=tracking.id,
            edition_id=edition_id,
            tracked=track,
            total_selected=len([v for v in tracking.selected_editions.values() if v]),
        )

    return await with_db_session(_shared._session_factory, operation)
