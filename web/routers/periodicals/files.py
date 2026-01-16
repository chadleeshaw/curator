"""
File operations for periodicals
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException
from fastapi.responses import FileResponse

from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils.general import is_special_edition, cleanup_empty_directories
from core.utils import run_in_thread
from models.database import Magazine

from . import _shared

router = _shared.router
logger = _shared.logger


@router.get("/periodicals/{magazine_id}/pdf")
async def get_pdf(magazine_id: int):
    """Get magazine PDF file"""
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                pdf_path = Path(magazine.file_path)
                if not pdf_path.exists():
                    raise HTTPException(status_code=404, detail="PDF file not found")

                return pdf_path
            finally:
                db_session.close()

        pdf_path = await run_in_thread(_db_operation)
        return FileResponse(pdf_path, media_type="application/pdf")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get PDF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/periodicals/{magazine_id}/move-to-tracking")
async def move_issue_to_tracking(magazine_id: int, target_tracking_id: int) -> Dict[str, Any]:
    """
    Move a single issue to a different tracking record.
    Useful for correcting misplaced issues.

    Args:
        magazine_id: ID of the issue to move
        target_tracking_id: ID of the tracking record to move the issue to
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                from models.database import MagazineTracking

                # Get the magazine to move
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Get the target tracking record
                target_tracking = (
                    db_session.query(MagazineTracking).filter(MagazineTracking.id == target_tracking_id).first()
                )
                if not target_tracking:
                    raise HTTPException(status_code=404, detail="Target tracking record not found")

                old_title = magazine.title
                old_tracking_id = magazine.tracking_id

                # Get organize directory from config or use default
                organize_base_dir = Path("./local/data").resolve()
                category_prefix = "_"

                # Update the magazine's tracking_id
                magazine.tracking_id = target_tracking_id

                # Check if this is a special edition
                is_special = False
                if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                    is_special = magazine.extra_metadata.get("special_edition") is not None
                if not is_special:
                    is_special = is_special_edition(magazine.title)

                # Only update title and reorganize files for regular editions
                files_reorganized = False
                old_dir_to_cleanup = None
                if not is_special:
                    # Store old paths
                    old_pdf_path = Path(magazine.file_path)
                    old_cover_path = Path(magazine.cover_path) if magazine.cover_path else None

                    # Reorganize files to match new title structure (without language folder)
                    try:
                        # Extract metadata from current path structure
                        category = (
                            magazine.extra_metadata.get("category", "Magazines")
                            if magazine.extra_metadata
                            else "Magazines"
                        )
                        issue_date = magazine.issue_date

                        # Build new path structure
                        safe_title = sanitize_filename(target_tracking.title)
                        month = issue_date.strftime("%B")
                        year = issue_date.strftime("%Y")
                        filename_base = f"{safe_title} - {month}{year}"

                        category_with_prefix = f"{category_prefix}{category}"
                        target_dir = organize_base_dir / category_with_prefix / safe_title / year
                        target_dir.mkdir(parents=True, exist_ok=True)

                        new_pdf_path = target_dir / f"{filename_base}.pdf"
                        new_cover_path = target_dir / f"{filename_base}.jpg" if old_cover_path else None

                        # Handle filename conflicts by appending timestamp
                        if new_pdf_path.exists() and new_pdf_path != old_pdf_path:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename_base_with_ts = f"{safe_title} - {month}{year} ({timestamp})"
                            new_pdf_path = target_dir / f"{filename_base_with_ts}.pdf"
                            if old_cover_path:
                                new_cover_path = target_dir / f"{filename_base_with_ts}.jpg"

                        # Move PDF file
                        if old_pdf_path.exists() and new_pdf_path != old_pdf_path:
                            # Store directory for cleanup before moving files
                            old_dir_to_cleanup = old_pdf_path.parent
                            shutil.move(str(old_pdf_path), str(new_pdf_path))
                            logger.info(f"Moved PDF: {old_pdf_path} -> {new_pdf_path}")
                            magazine.file_path = str(new_pdf_path)
                            files_reorganized = True
                        elif new_pdf_path == old_pdf_path:
                            # File is already in correct location
                            magazine.file_path = str(new_pdf_path)
                        else:
                            logger.warning(f"PDF file not found: {old_pdf_path}")

                        # Move cover file if it exists
                        if (
                            old_cover_path
                            and old_cover_path.exists()
                            and new_cover_path
                            and new_cover_path != old_cover_path
                        ):
                            shutil.move(str(old_cover_path), str(new_cover_path))
                            logger.info(f"Moved cover: {old_cover_path} -> {new_cover_path}")
                            magazine.cover_path = str(new_cover_path)
                        elif new_cover_path:
                            magazine.cover_path = str(new_cover_path)

                        # Update title after file operations
                        magazine.title = target_tracking.title

                    except Exception as e:
                        logger.error(f"Error reorganizing magazine files: {e}", exc_info=True)
                        # Still update the tracking_id and title even if file move failed
                        magazine.title = target_tracking.title

                db_session.commit()

                # Clean up old directory after successful commit
                if old_dir_to_cleanup and old_dir_to_cleanup.exists():
                    cleanup_empty_directories(old_dir_to_cleanup, organize_base_dir)

                msg = f"Moved issue from '{old_title}' to '{target_tracking.title}'"
                if files_reorganized:
                    msg += " and reorganized files"

                logger.info(msg)
                return {
                    "success": True,
                    "message": msg,
                    "old_tracking_id": old_tracking_id,
                    "new_tracking_id": target_tracking_id,
                    "files_reorganized": files_reorganized,
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Move issue to tracking error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
