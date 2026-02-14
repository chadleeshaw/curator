"""
Bulk operations for periodicals - move, delete, regenerate thumbnails/OCR for multiple issues at once.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from core.constants.files import PDF_COVER_QUALITY_HIGH
from core.constants.ocr import PDF_COVER_DPI_OCR
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir
from core.utils.general import cleanup_empty_directories
from core.utils.metadata_builder import is_periodical_special_edition
from core.utils.pdf import extract_cover_from_pdf
from models.database import OCRJob, Periodical, PeriodicalTracking
from services.file_operations import reorganize_periodical_files
from services.ocr.queue import OCRQueueService
from services.ocr.service import OCRService
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


class BulkRegenerateRequest(BaseModel):
    """Request body for bulk regenerate thumbnail & OCR operation."""

    periodical_ids: List[int] = Field(..., min_length=1, description="List of periodical IDs to regenerate")


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

        # Use no_autoflush to prevent premature flushes when querying the next
        # periodical while previous ones have dirty file_path changes.
        with db.no_autoflush:
            for periodical_id in request.periodical_ids:
                magazine = db.query(Periodical).filter(Periodical.id == periodical_id).first()
                if not magazine:
                    failed_ids.append(periodical_id)
                    logger.warning(f"Periodical {periodical_id} not found during bulk move")
                    continue

                # Skip if already in the target tracking
                if magazine.tracking_id == request.target_tracking_id:
                    continue

                # Use a savepoint so a single failure doesn't roll back the whole batch
                savepoint = db.begin_nested()
                try:
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

                    # Flush this individual move so the DB sees the updated file_path
                    # before we process the next periodical
                    db.flush()
                    moved_count += 1

                except IntegrityError as e:
                    savepoint.rollback()
                    failed_ids.append(periodical_id)
                    logger.warning(f"Skipped periodical {periodical_id} due to conflict: {e}")
                except Exception as e:
                    savepoint.rollback()
                    failed_ids.append(periodical_id)
                    logger.error(f"Error moving periodical {periodical_id}: {e}")

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


@router.post("/periodicals/bulk/regenerate-thumbnail-ocr")
@handle_api_errors("Bulk regenerate thumbnail & OCR", logger)
async def bulk_regenerate_thumbnail_ocr(request: BulkRegenerateRequest) -> Dict[str, Any]:
    """
    Regenerate cover thumbnails and queue OCR for multiple issues.

    For each selected issue, extracts a fresh cover from the PDF (using the
    stored cover page or page 1), invalidates the cached thumbnail, and
    queues a high-priority OCR job.

    Args:
        request: BulkRegenerateRequest with periodical_ids
    """

    def operation(db):
        ocr_available = OCRService.is_available()

        regenerated_count = 0
        ocr_queued_count = 0
        skipped_count = 0
        failed_ids = []

        for periodical_id in request.periodical_ids:
            magazine = db.query(Periodical).filter(Periodical.id == periodical_id).first()
            if not magazine:
                failed_ids.append(periodical_id)
                logger.warning(f"Periodical {periodical_id} not found during bulk regenerate")
                continue

            if not magazine.file_path:
                failed_ids.append(periodical_id)
                logger.warning(f"Periodical {periodical_id} has no file path")
                continue

            try:
                pdf_path = _shared.resolve_file_path(magazine.file_path)
            except FileNotFoundError:
                failed_ids.append(periodical_id)
                logger.warning(f"File not found for periodical {periodical_id}: {magazine.file_path}")
                continue

            # Skip if custom cover was uploaded and the file still exists
            if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                if magazine.extra_metadata.get("cover_uploaded") and magazine.cover_path:
                    if Path(magazine.cover_path).exists():
                        logger.debug(f"Skipping periodical {periodical_id} — custom uploaded cover exists")
                        skipped_count += 1
                        continue
                    else:
                        logger.info(
                            f"Custom cover missing for periodical {periodical_id}, regenerating from PDF"
                        )

            # Determine cover directory
            if _shared._library_base_dir:
                cover_dir = _shared._library_base_dir / ".covers"
            else:
                cover_dir = pdf_path.parent.parent.parent / ".covers"

            # Use stored cover page or default to 1
            page_number = 1
            if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                page_number = magazine.extra_metadata.get("cover_page", 1)

            # Invalidate old thumbnail
            if magazine.cover_path:
                old_cover = Path(magazine.cover_path)
                old_thumbnail = old_cover.parent / f"{old_cover.stem}_thumb.jpg"
                if old_thumbnail.exists():
                    old_thumbnail.unlink()

            # Extract cover from PDF
            try:
                if ocr_available:
                    cover_path = extract_cover_from_pdf(
                        pdf_path,
                        cover_dir,
                        dpi=PDF_COVER_DPI_OCR,
                        quality=PDF_COVER_QUALITY_HIGH,
                        page_number=page_number,
                    )
                else:
                    cover_path = extract_cover_from_pdf(pdf_path, cover_dir, page_number=page_number)

                if cover_path:
                    magazine.cover_path = str(cover_path)
                    # Clear uploaded flag since we regenerated from PDF
                    if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                        magazine.extra_metadata.pop("cover_uploaded", None)
                    regenerated_count += 1
                else:
                    failed_ids.append(periodical_id)
                    logger.warning(f"Failed to extract cover for periodical {periodical_id}")
                    continue
            except Exception as e:
                failed_ids.append(periodical_id)
                logger.error(f"Error extracting cover for periodical {periodical_id}: {e}")
                continue

            # Queue OCR job
            if ocr_available:
                job = OCRQueueService.queue_ocr_job(
                    db=db,
                    periodical_id=periodical_id,
                    priority=OCRJob.PriorityEnum.HIGH.value,
                    language=magazine.language,
                )
                if job:
                    ocr_queued_count += 1

        db.commit()

        msg = f"Regenerated {regenerated_count} thumbnail(s)"
        if ocr_available:
            msg += f", queued {ocr_queued_count} OCR job(s)"
        else:
            msg += " (OCR not available)"
        if skipped_count:
            msg += f" ({skipped_count} skipped — custom covers)"
        if failed_ids:
            msg += f" ({len(failed_ids)} failed)"

        logger.info(msg)
        return success_response(
            msg,
            regenerated_count=regenerated_count,
            ocr_queued_count=ocr_queued_count,
            skipped_count=skipped_count,
            failed_ids=failed_ids,
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
