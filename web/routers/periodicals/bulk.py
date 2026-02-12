"""
Bulk operations for periodicals - move, delete multiple issues at once.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException
from pydantic import BaseModel, Field

from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir
from core.utils.general import cleanup_empty_directories, is_special_edition
from core.utils.metadata_builder import is_periodical_special_edition
from models.database import Periodical, PeriodicalTracking
from services.file_operations import reorganize_periodical_files
from web.utils.responses import success_response

from . import _shared

router = _shared.router
logger = _shared.logger


class BulkMoveRequest(BaseModel):
    """Request body for bulk move operation."""

    periodical_ids: List[int] = Field(..., min_length=1, description="List of periodical IDs to move")
    target_tracking_id: int = Field(..., description="Target tracking record ID")


class BulkDeleteRequest(BaseModel):
    """Request body for bulk delete operation."""

    periodical_ids: List[int] = Field(..., min_length=1, description="List of periodical IDs to delete")
    delete_files: bool = Field(default=False, description="Whether to delete files from disk")
    mark_as_bad: bool = Field(default=False, description="Mark issues as permanently failed")


@router.post("/periodicals/bulk/move-to-tracking")
@handle_api_errors("Bulk move issues to tracking", logger)
async def bulk_move_to_tracking(request: BulkMoveRequest) -> Dict[str, Any]:
    """
    Move multiple issues to a different tracking record.

    Args:
        request: BulkMoveRequest with periodical_ids and target_tracking_id
    """

    def operation(db):
        target_tracking = (
            db.query(PeriodicalTracking).filter(PeriodicalTracking.id == request.target_tracking_id).first()
        )
        if not target_tracking:
            raise HTTPException(status_code=404, detail="Target tracking record not found")

        library_base_dir = _shared._library_base_dir or get_library_dir(None)
        category_prefix = _shared._category_prefix

        moved_count = 0
        failed_ids = []
        dirs_to_cleanup = []

        for periodical_id in request.periodical_ids:
            magazine = db.query(Periodical).filter(Periodical.id == periodical_id).first()
            if not magazine:
                failed_ids.append(periodical_id)
                logger.warning(f"Periodical {periodical_id} not found during bulk move")
                continue

            # Skip if already in the target tracking
            if magazine.tracking_id == request.target_tracking_id:
                continue

            old_tracking_id = magazine.tracking_id
            magazine.tracking_id = request.target_tracking_id

            is_special = is_periodical_special_edition(magazine)

            if not is_special:
                old_pdf_path = Path(magazine.file_path)
                old_dir = old_pdf_path.parent

                result = reorganize_periodical_files(
                    magazine,
                    new_title=target_tracking.title,
                    library_base_dir=library_base_dir,
                    category_prefix=category_prefix,
                    update_db=True,
                )

                if result.success:
                    magazine.title = target_tracking.title
                else:
                    logger.error(f"Error reorganizing files for periodical {periodical_id}: {result.error}")
                    magazine.title = target_tracking.title

                if old_dir not in dirs_to_cleanup:
                    dirs_to_cleanup.append(old_dir)

            moved_count += 1

        db.commit()

        # Clean up empty directories after commit
        for old_dir in dirs_to_cleanup:
            if old_dir.exists():
                cleanup_empty_directories(old_dir, library_base_dir)

        msg = f"Moved {moved_count} issue(s) to '{target_tracking.title}'"
        if failed_ids:
            msg += f" ({len(failed_ids)} not found)"

        logger.info(msg)
        return success_response(
            msg,
            moved_count=moved_count,
            failed_ids=failed_ids,
            target_tracking_id=request.target_tracking_id,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.post("/periodicals/bulk/delete")
@handle_api_errors("Bulk delete issues", logger)
async def bulk_delete(request: BulkDeleteRequest) -> Dict[str, Any]:
    """
    Delete multiple issues at once.

    Args:
        request: BulkDeleteRequest with periodical_ids, delete_files flag, and mark_as_bad flag
    """

    def operation(db):
        library_base_dir = _shared._library_base_dir or get_library_dir(None)

        deleted_count = 0
        failed_ids = []
        dirs_to_cleanup = []

        for periodical_id in request.periodical_ids:
            magazine = db.query(Periodical).filter(Periodical.id == periodical_id).first()
            if not magazine:
                failed_ids.append(periodical_id)
                logger.warning(f"Periodical {periodical_id} not found during bulk delete")
                continue

            file_path = Path(magazine.file_path) if magazine.file_path else None
            cover_path = Path(magazine.cover_path) if magazine.cover_path else None

            if request.delete_files:
                # Delete the actual files
                if file_path and file_path.exists():
                    old_dir = file_path.parent
                    file_path.unlink()
                    if old_dir not in dirs_to_cleanup:
                        dirs_to_cleanup.append(old_dir)
                if cover_path and cover_path.exists():
                    cover_path.unlink()

            if request.mark_as_bad and magazine.tracking_id:
                # Mark as permanently failed in the download submissions table
                from models.database import DownloadSubmission

                submission = (
                    db.query(DownloadSubmission).filter(DownloadSubmission.periodical_id == periodical_id).first()
                )
                if submission:
                    submission.status = "permanently_failed"

            db.delete(magazine)
            deleted_count += 1

        db.commit()

        # Clean up empty directories after commit
        for old_dir in dirs_to_cleanup:
            if old_dir.exists():
                cleanup_empty_directories(old_dir, library_base_dir)

        msg = f"Deleted {deleted_count} issue(s)"
        if request.delete_files:
            msg += " and their files"
        if failed_ids:
            msg += f" ({len(failed_ids)} not found)"

        logger.info(msg)
        return success_response(
            msg,
            deleted_count=deleted_count,
            failed_ids=failed_ids,
        )

    return await with_db_session(_shared._session_factory, operation)
