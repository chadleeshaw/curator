"""
Tracking routes - Download tracking
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Query

from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils.general import (
    is_special_edition,
    generate_olid,
    cleanup_empty_directories,
)
from models.database import MagazineTracking
from models.database import SearchResult as DBSearchResult
from web.schemas import APIError, TrackingPreferencesRequest
from core.utils import run_in_thread
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
async def track_single_issue(
    tracking_id: int, edition_id: str, track: bool = Query(True)
) -> Dict[str, Any]:
    """Track or untrack a single issue/edition"""
    try:

        def _update():
            db_session = _shared._session_factory()
            try:
                tracking = (
                    db_session.query(MagazineTracking)
                    .filter(MagazineTracking.id == tracking_id)
                    .first()
                )
                if not tracking:
                    raise HTTPException(
                        status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND
                    )

                # Initialize selected_editions if None
                if tracking.selected_editions is None:
                    tracking.selected_editions = {}

                # Update the selected_editions dictionary
                tracking.selected_editions[edition_id] = track

                # Mark the column as modified for SQLAlchemy to detect the change
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(tracking, "selected_editions")

                db_session.commit()

                # Trigger immediate auto-download check if an edition was marked for tracking
                if track and _shared._auto_download_task_func:
                    import asyncio

                    try:
                        asyncio.create_task(_shared._auto_download_task_func())
                        logger.info(
                            f"Triggered immediate auto-download check after tracking edition {edition_id}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not trigger immediate auto-download: {e}"
                        )

                action = "marked for tracking" if track else "unmarked from tracking"
                logger.info(
                    f"Issue {edition_id} {action} for periodical '{tracking.title}'"
                )

                return {
                    "success": True,
                    "message": f"Issue {action}",
                    "tracking_id": tracking.id,
                    "edition_id": edition_id,
                    "tracked": track,
                    "total_selected": len(
                        [v for v in tracking.selected_editions.values() if v]
                    ),
                }
            finally:
                db_session.close()

        return await run_in_thread(_update)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Track single issue error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
