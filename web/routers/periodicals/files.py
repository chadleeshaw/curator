"""
File operations for periodicals
"""

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from core.constants.category import DEFAULT_CATEGORY
from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir, get_category_prefix
from core.utils.general import cleanup_empty_directories, is_special_edition
from core.utils.epub_reader import get_epub_metadata, get_epub_chapter, get_epub_image
from core.utils.comic_reader import (
    get_comic_metadata,
    get_comic_page,
    get_comic_page_thumbnail,
)
from core.utils.pdf_reader import get_pdf_metadata, get_pdf_page, get_pdf_page_thumbnail
from models.database import Periodical
from services.file_operations import reorganize_periodical_files

from . import _shared

router = _shared.router
logger = _shared.logger


@router.get("/periodicals/{periodical_id}/pdf")
@handle_api_errors("Get file", logger)
async def get_pdf(periodical_id: int):
    """
    Get magazine file (PDF, EPUB, CBZ, or CBR).

    Files are served inline for browser viewing. Users with EPUB browser extensions
    can view EPUBs directly; others will get a download prompt.
    """

    def fetch_file_path(db_session):
        _, file_path = _shared.get_periodical_with_file(db_session, periodical_id)
        return file_path

    file_path = await with_db_session(_shared._session_factory, fetch_file_path)

    # Detect file type and set appropriate media type and headers
    file_extension = file_path.suffix.lower()
    if file_extension == ".epub":
        media_type = "application/epub+zip"
    elif file_extension == ".pdf":
        media_type = "application/pdf"
    elif file_extension == ".cbz":
        media_type = "application/vnd.comicbook+zip"
    elif file_extension == ".cbr":
        media_type = "application/vnd.comicbook-rar"
    else:
        # Fallback to octet-stream for unknown types
        media_type = "application/octet-stream"

    # Serve inline - browsers will display if they can, download if they can't
    headers = {"Content-Disposition": f'inline; filename="{file_path.name}"'}

    return FileResponse(file_path, media_type=media_type, headers=headers)


@router.get("/periodicals/{periodical_id}/epub/metadata")
@handle_api_errors("Get EPUB metadata", logger)
async def get_epub_metadata_endpoint(periodical_id: int) -> Dict[str, Any]:
    """
    Get EPUB metadata and chapter list.

    Returns:
        Dictionary with title, author, chapters list, and chapter count
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's an EPUB file
        if file_path.suffix.lower() != ".epub":
            raise HTTPException(status_code=400, detail="File is not an EPUB")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get EPUB metadata (this may take a moment for large EPUBs)
    metadata = await run_in_thread(lambda: get_epub_metadata(file_path))

    if not metadata:
        raise HTTPException(status_code=500, detail="Failed to extract EPUB metadata")

    return metadata


@router.get("/periodicals/{periodical_id}/epub/chapter/{chapter_index}")
@handle_api_errors("Get EPUB chapter", logger)
async def get_epub_chapter_endpoint(periodical_id: int, chapter_index: int) -> HTMLResponse:
    """
    Get specific EPUB chapter content as HTML.

    Args:
        periodical_id: The periodical ID
        chapter_index: Zero-based chapter index

    Returns:
        HTML content of the chapter
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's an EPUB file
        if file_path.suffix.lower() != ".epub":
            raise HTTPException(status_code=400, detail="File is not an EPUB")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get chapter content with periodical_id for image URL rewriting
    chapter_html = await run_in_thread(lambda: get_epub_chapter(file_path, chapter_index, periodical_id))

    if chapter_html is None:
        raise HTTPException(status_code=404, detail="Chapter not found")

    response = HTMLResponse(content=chapter_html)
    # Add cache headers for EPUB chapters (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.get("/periodicals/{periodical_id}/epub/image/{image_name}")
@handle_api_errors("Get EPUB image", logger)
async def get_epub_image_endpoint(periodical_id: int, image_name: str):
    """
    Get an image from an EPUB file.

    Args:
        periodical_id: The periodical ID
        image_name: Name of the image file (e.g., 'cover.jpg')

    Returns:
        Image data with appropriate content type
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's an EPUB file
        if file_path.suffix.lower() != ".epub":
            raise HTTPException(status_code=400, detail="File is not an EPUB")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get image content
    image_data = await run_in_thread(lambda: get_epub_image(file_path, image_name))

    if image_data is None:
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine content type from file extension
    content_type = mimetypes.guess_type(image_name)[0] or "application/octet-stream"

    response = Response(content=image_data, media_type=content_type)
    # Add cache headers for EPUB images (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


# ============================================================================
# Comic Reader Endpoints (CBZ/CBR)
# ============================================================================


@router.get("/periodicals/{periodical_id}/comic/metadata")
@handle_api_errors("Get comic metadata", logger)
async def get_comic_metadata_endpoint(periodical_id: int) -> Dict[str, Any]:
    """
    Get comic metadata and page list.

    Returns:
        Dictionary with title, format, page_count, pages list, and cover_page index
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's a comic file
        if file_path.suffix.lower() not in [".cbz", ".cbr"]:
            raise HTTPException(status_code=400, detail="File is not a comic (CBZ/CBR)")

        # Get cover page index from extra_metadata (defaults to 0)
        cover_page = 0
        if magazine.extra_metadata and "cover_page" in magazine.extra_metadata:
            # Convert from 1-based (stored) to 0-based (used by frontend)
            cover_page = magazine.extra_metadata["cover_page"] - 1

        return file_path, cover_page

    file_path, cover_page = await with_db_session(_shared._session_factory, operation)

    # Get comic metadata
    metadata = await run_in_thread(lambda: get_comic_metadata(file_path))

    # Add cover page index to metadata
    metadata["cover_page"] = cover_page

    return metadata


@router.get("/periodicals/{periodical_id}/comic/page/{page_index}")
@handle_api_errors("Get comic page", logger)
async def get_comic_page_endpoint(periodical_id: int, page_index: int):
    """
    Get specific comic page as image.

    Args:
        periodical_id: The periodical ID
        page_index: Zero-based page index

    Returns:
        Image data with appropriate content type
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's a comic file
        if file_path.suffix.lower() not in [".cbz", ".cbr"]:
            raise HTTPException(status_code=400, detail="File is not a comic (CBZ/CBR)")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get page image
    image_data = await run_in_thread(lambda: get_comic_page(file_path, page_index))

    if image_data is None:
        raise HTTPException(status_code=404, detail="Page not found")

    # Determine content type from image data

    # Try to guess from magic bytes
    content_type = "image/jpeg"  # Default
    if image_data.startswith(b"\x89PNG"):
        content_type = "image/png"
    elif image_data.startswith(b"GIF"):
        content_type = "image/gif"
    elif image_data.startswith(b"RIFF") and b"WEBP" in image_data[:20]:
        content_type = "image/webp"

    response = Response(content=image_data, media_type=content_type)
    # Add cache headers for full-size pages (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.get("/periodicals/{periodical_id}/comic/page/{page_index}/thumbnail")
@handle_api_errors("Get comic page thumbnail", logger)
async def get_comic_page_thumbnail_endpoint(periodical_id: int, page_index: int):
    """
    Get thumbnail of a specific comic page.

    Args:
        periodical_id: The periodical ID
        page_index: Zero-based page index

    Returns:
        Thumbnail image data as JPEG
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Verify it's a comic file
        if file_path.suffix.lower() not in [".cbz", ".cbr"]:
            raise HTTPException(status_code=400, detail="File is not a comic (CBZ/CBR)")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get thumbnail
    thumbnail_data = await run_in_thread(lambda: get_comic_page_thumbnail(file_path, page_index))

    if thumbnail_data is None:
        raise HTTPException(status_code=404, detail="Page not found or thumbnail creation failed")

    response = Response(content=thumbnail_data, media_type="image/jpeg")
    # Add cache headers for thumbnails (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.get("/periodicals/{periodical_id}/pdf/metadata")
@handle_api_errors("Get PDF metadata", logger)
async def get_pdf_metadata_endpoint(periodical_id: int) -> Dict[str, Any]:
    """
    Get PDF metadata including page count and cover page index.

    Returns:
        Dictionary with title, page_count, pages list, and cover_page index
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Check if file is PDF
        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        # Get cover page index from extra_metadata (defaults to 0)
        cover_page = 0
        if magazine.extra_metadata and "cover_page" in magazine.extra_metadata:
            # Convert from 1-based (stored) to 0-based (used by frontend)
            cover_page = magazine.extra_metadata["cover_page"] - 1

        return file_path, cover_page

    file_path, cover_page = await with_db_session(_shared._session_factory, operation)

    # Get PDF metadata
    metadata = await run_in_thread(lambda: get_pdf_metadata(file_path))

    # Add cover page index to metadata
    metadata["cover_page"] = cover_page

    return metadata


@router.get("/periodicals/{periodical_id}/pdf/page/{page_index}")
@handle_api_errors("Get PDF page", logger)
async def get_pdf_page_endpoint(periodical_id: int, page_index: int):
    """
    Get a specific page from a PDF as an image.

    Args:
        periodical_id: ID of the magazine
        page_index: Page index (0-based)

    Returns:
        Page image as JPEG
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Check if file is PDF
        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get page image
    page_data = await run_in_thread(lambda: get_pdf_page(file_path, page_index))

    if page_data is None:
        raise HTTPException(status_code=404, detail="Page not found or extraction failed")

    response = Response(content=page_data, media_type="image/jpeg")
    # Add cache headers for full-size pages (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.get("/periodicals/{periodical_id}/pdf/page/{page_index}/thumbnail")
@handle_api_errors("Get PDF page thumbnail", logger)
async def get_pdf_page_thumbnail_endpoint(periodical_id: int, page_index: int):
    """
    Get a thumbnail of a specific page from a PDF.

    Args:
        periodical_id: ID of the magazine
        page_index: Page index (0-based)

    Returns:
        Thumbnail image as JPEG (200px height)
    """

    def operation(db):
        magazine, file_path = _shared.get_periodical_with_file(db, periodical_id)

        # Check if file is PDF
        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get thumbnail
    thumbnail_data = await run_in_thread(lambda: get_pdf_page_thumbnail(file_path, page_index))

    if thumbnail_data is None:
        raise HTTPException(status_code=404, detail="Page not found or thumbnail creation failed")

    response = Response(content=thumbnail_data, media_type="image/jpeg")
    # Add cache headers for thumbnails (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.post("/periodicals/{periodical_id}/move-to-tracking")
@handle_api_errors("Move issue to tracking", logger)
async def move_issue_to_tracking(periodical_id: int, target_tracking_id: int) -> Dict[str, Any]:
    """
    Move a single issue to a different tracking record.
    Useful for correcting misplaced issues.

    Args:
        periodical_id: ID of the issue to move
        target_tracking_id: ID of the tracking record to move the issue to
    """

    def operation(db):
        from models.database import PeriodicalTracking

        # Get the magazine to move
        magazine = _shared.get_periodical_or_404(db, periodical_id)

        # Get the target tracking record
        target_tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == target_tracking_id).first()
        if not target_tracking:
            raise HTTPException(status_code=404, detail="Target tracking record not found")

        old_title = magazine.title
        old_tracking_id = magazine.tracking_id

        # Get library directory and category prefix from shared module
        # These are already configured via set_dependencies() from main app
        library_base_dir = _shared._library_base_dir or get_library_dir(None)
        category_prefix = _shared._category_prefix

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
            # Store old directory for cleanup
            old_pdf_path = Path(magazine.file_path)
            old_dir_to_cleanup = old_pdf_path.parent

            # Reorganize files using shared utility
            result = reorganize_periodical_files(
                magazine,
                new_title=target_tracking.title,
                library_base_dir=library_base_dir,
                category_prefix=category_prefix,
                update_db=True,
            )

            if result.success:
                files_reorganized = result.files_moved
                # Update title after successful file operations
                magazine.title = target_tracking.title
            else:
                logger.error(f"Error reorganizing magazine files: {result.error}")
                # Still update the tracking_id and title even if file move failed
                magazine.title = target_tracking.title

        db.commit()

        # Clean up old directory after successful commit
        if old_dir_to_cleanup and old_dir_to_cleanup.exists():
            cleanup_empty_directories(old_dir_to_cleanup, library_base_dir)

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

    return await with_db_session(_shared._session_factory, operation)
