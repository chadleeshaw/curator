"""
File operations for periodicals
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils.general import is_special_edition, cleanup_empty_directories
from core.utils import run_in_thread
from core.utils.epub_reader import get_epub_metadata, get_epub_chapter, get_epub_image
from models.database import Magazine

from . import _shared

router = _shared.router
logger = _shared.logger


@router.get("/periodicals/{magazine_id}/pdf")
async def get_pdf(magazine_id: int):
    """
    Get magazine file (PDF or EPUB).

    Files are served inline for browser viewing. Users with EPUB browser extensions
    can view EPUBs directly; others will get a download prompt.
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                file_path = Path(magazine.file_path)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="File not found")

                return file_path
            finally:
                db_session.close()

        file_path = await run_in_thread(_db_operation)

        # Detect file type and set appropriate media type and headers
        file_extension = file_path.suffix.lower()
        if file_extension == ".epub":
            media_type = "application/epub+zip"
        elif file_extension == ".pdf":
            media_type = "application/pdf"
        else:
            # Fallback to octet-stream for unknown types
            media_type = "application/octet-stream"

        # Serve inline - browsers will display if they can, download if they can't
        headers = {"Content-Disposition": f'inline; filename="{file_path.name}"'}

        return FileResponse(file_path, media_type=media_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}/epub/metadata")
async def get_epub_metadata_endpoint(magazine_id: int) -> Dict[str, Any]:
    """
    Get EPUB metadata and chapter list.

    Returns:
        Dictionary with title, author, chapters list, and chapter count
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                file_path = Path(magazine.file_path)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="File not found")

                # Verify it's an EPUB file
                if file_path.suffix.lower() != ".epub":
                    raise HTTPException(status_code=400, detail="File is not an EPUB")

                return file_path
            finally:
                db_session.close()

        file_path = await run_in_thread(_db_operation)

        # Get EPUB metadata (this may take a moment for large EPUBs)
        metadata = await run_in_thread(lambda: get_epub_metadata(file_path))

        if not metadata:
            raise HTTPException(status_code=500, detail="Failed to extract EPUB metadata")

        return JSONResponse(content=metadata)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get EPUB metadata error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}/epub/chapter/{chapter_index}")
async def get_epub_chapter_endpoint(magazine_id: int, chapter_index: int) -> HTMLResponse:
    """
    Get specific EPUB chapter content as HTML.

    Args:
        magazine_id: The periodical ID
        chapter_index: Zero-based chapter index

    Returns:
        HTML content of the chapter
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                file_path = Path(magazine.file_path)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="File not found")

                # Verify it's an EPUB file
                if file_path.suffix.lower() != ".epub":
                    raise HTTPException(status_code=400, detail="File is not an EPUB")

                return file_path
            finally:
                db_session.close()

        file_path = await run_in_thread(_db_operation)

        # Get chapter content with magazine_id for image URL rewriting
        chapter_html = await run_in_thread(lambda: get_epub_chapter(file_path, chapter_index, magazine_id))

        if chapter_html is None:
            raise HTTPException(status_code=404, detail="Chapter not found")

        return HTMLResponse(content=chapter_html)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get EPUB chapter error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}/epub/image/{image_name}")
async def get_epub_image_endpoint(magazine_id: int, image_name: str):
    """
    Get an image from an EPUB file.

    Args:
        magazine_id: The periodical ID
        image_name: Name of the image file (e.g., 'cover.jpg')

    Returns:
        Image data with appropriate content type
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                file_path = Path(magazine.file_path)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="File not found")

                # Verify it's an EPUB file
                if file_path.suffix.lower() != ".epub":
                    raise HTTPException(status_code=400, detail="File is not an EPUB")

                return file_path
            finally:
                db_session.close()

        file_path = await run_in_thread(_db_operation)

        # Get image content
        image_data = await run_in_thread(lambda: get_epub_image(file_path, image_name))

        if image_data is None:
            raise HTTPException(status_code=404, detail="Image not found")

        # Determine content type from file extension
        import mimetypes

        content_type = mimetypes.guess_type(image_name)[0] or "application/octet-stream"

        from fastapi.responses import Response

        return Response(content=image_data, media_type=content_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get EPUB image error: {e}", exc_info=True)
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
