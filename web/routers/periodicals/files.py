"""
File operations for periodicals
"""

import asyncio
import mimetypes
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from core.constants.files import PDF_RENDER_PAGE_WORKERS, PDF_RENDER_THUMBNAIL_WORKERS
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from web.utils.responses import success_response
from core.utils.files import get_library_dir
from core.utils.general import cleanup_empty_directories, is_special_edition
from core.utils.metadata_builder import is_periodical_special_edition
from core.utils.readers import (
    get_epub_metadata,
    get_epub_chapter,
    get_epub_image,
    get_comic_metadata,
    get_comic_page,
    get_comic_page_thumbnail,
    get_pdf_metadata,
    get_pdf_page,
    get_pdf_page_thumbnail,
)
from services.file_operations import reorganize_periodical_files

from . import _shared
from web.routers.auth import get_verify_token

router = _shared.router
logger = _shared.logger

_POOL_SETTINGS = {
    "page": ("CURATOR_PDF_RENDER_PAGE_WORKERS", "render_page_workers", PDF_RENDER_PAGE_WORKERS),
    "thumbnail": ("CURATOR_PDF_RENDER_THUMBNAIL_WORKERS", "render_thumbnail_workers", PDF_RENDER_THUMBNAIL_WORKERS),
}
_render_pools: Dict[str, ProcessPoolExecutor] = {}


def _positive_worker_count(raw, default: int) -> int:
    """A configured worker count, or the default when the value is unusable."""
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return default
    return count if count > 0 else default


def _configured_pool_size(config_key: str) -> Optional[int]:
    """Worker count from pdf config, or None when config cannot be read."""
    try:
        from core.config import ConfigLoader

        return ConfigLoader().get_pdf().get(config_key)
    except Exception:
        logger.debug("PDF render pool size is using the default", exc_info=True)
        return None


def _render_pool_size(pool_name: str) -> int:
    """Workers for one pool. An environment variable wins over config."""
    env_name, config_key, default = _POOL_SETTINGS[pool_name]
    raw = os.environ.get(env_name)
    if raw is None:
        raw = _configured_pool_size(config_key)
    return _positive_worker_count(raw, default)


def _get_render_pool(pool_name: str) -> ProcessPoolExecutor:
    """Return the page or thumbnail pool, creating it on first use.

    PDF rendering holds the GIL, so threads render one page at a time. Separate
    process pools let pages render in parallel and keep thumbnails from delaying
    them. Workers use spawn, matching the OCR pool, because fork is unsafe with
    threads already running.
    """
    pool = _render_pools.get(pool_name)
    if pool is None:
        pool = ProcessPoolExecutor(
            max_workers=_render_pool_size(pool_name),
            mp_context=multiprocessing.get_context("spawn"),
        )
        _render_pools[pool_name] = pool
    return pool


def shutdown_render_pools() -> None:
    """Stop PDF render workers. Called when the application shuts down."""
    pools = list(_render_pools.items())
    _render_pools.clear()
    for name, pool in pools:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            logger.warning("Could not shut down the %s PDF render pool", name, exc_info=True)


async def _render_in_process(pool_name: str, func: Callable[..., bytes], *args: Any) -> bytes:
    """Run a PDF render function in the named process pool.

    A worker that dies (for example MuPDF on a corrupt file) breaks the pool.
    Drop it so the next request starts a fresh one.
    """
    pool = _get_render_pool(pool_name)
    try:
        return await asyncio.get_running_loop().run_in_executor(pool, func, *args)
    except BrokenProcessPool:
        broken = _render_pools.pop(pool_name, None)
        if broken is not None:
            try:
                broken.shutdown(wait=False, cancel_futures=True)
            except Exception:
                logger.warning("Could not shut down the broken %s PDF render pool", pool_name, exc_info=True)
        raise


@router.get("/periodicals/{periodical_id}/pdf")
@handle_api_errors("Get file", logger)
async def get_pdf(periodical_id: int, _username: str = Depends(get_verify_token)):
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
async def get_epub_metadata_endpoint(periodical_id: int, _username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Get EPUB metadata and chapter list.

    Returns:
        Dictionary with title, author, chapters list, and chapter count
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

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
async def get_epub_chapter_endpoint(
    periodical_id: int, chapter_index: int, _username: str = Depends(get_verify_token)
) -> HTMLResponse:
    """
    Get specific EPUB chapter content as HTML.

    Args:
        periodical_id: The periodical ID
        chapter_index: Zero-based chapter index

    Returns:
        HTML content of the chapter
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

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
async def get_epub_image_endpoint(periodical_id: int, image_name: str, _username: str = Depends(get_verify_token)):
    """
    Get an image from an EPUB file.

    Args:
        periodical_id: The periodical ID
        image_name: Name of the image file (e.g., 'cover.jpg')

    Returns:
        Image data with appropriate content type
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

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
async def get_comic_metadata_endpoint(periodical_id: int, _username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Get comic metadata and page list.

    Returns:
        Dictionary with title, format, page_count, pages list, and cover_page index
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

        if file_path.suffix.lower() not in [".cbz", ".cbr"]:
            raise HTTPException(status_code=400, detail="File is not a comic (CBZ/CBR)")

        cover_page = 0
        if periodical.extra_metadata and "cover_page" in periodical.extra_metadata:
            # Convert from 1-based (stored) to 0-based (used by frontend)
            cover_page = periodical.extra_metadata["cover_page"] - 1

        return file_path, cover_page

    file_path, cover_page = await with_db_session(_shared._session_factory, operation)

    # Get comic metadata
    metadata = await run_in_thread(lambda: get_comic_metadata(file_path))

    # Add cover page index to metadata
    metadata["cover_page"] = cover_page

    return metadata


@router.get("/periodicals/{periodical_id}/comic/page/{page_index}")
@handle_api_errors("Get comic page", logger)
async def get_comic_page_endpoint(periodical_id: int, page_index: int, _username: str = Depends(get_verify_token)):
    """
    Get specific comic page as image.

    Args:
        periodical_id: The periodical ID
        page_index: Zero-based page index

    Returns:
        Image data with appropriate content type
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

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
async def get_comic_page_thumbnail_endpoint(
    periodical_id: int, page_index: int, _username: str = Depends(get_verify_token)
):
    """
    Get thumbnail of a specific comic page.

    Args:
        periodical_id: The periodical ID
        page_index: Zero-based page index

    Returns:
        Thumbnail image data as JPEG
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

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
async def get_pdf_metadata_endpoint(periodical_id: int, _username: str = Depends(get_verify_token)) -> Dict[str, Any]:
    """
    Get PDF metadata including page count and cover page index.

    Returns:
        Dictionary with title, page_count, pages list, and cover_page index
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        cover_page = 0
        if periodical.extra_metadata and "cover_page" in periodical.extra_metadata:
            # Convert from 1-based (stored) to 0-based (used by frontend)
            cover_page = periodical.extra_metadata["cover_page"] - 1

        return file_path, cover_page

    file_path, cover_page = await with_db_session(_shared._session_factory, operation)

    # Get PDF metadata
    metadata = await run_in_thread(lambda: get_pdf_metadata(file_path))

    # Add cover page index to metadata
    metadata["cover_page"] = cover_page

    return metadata


@router.get("/periodicals/{periodical_id}/pdf/page/{page_index}")
@handle_api_errors("Get PDF page", logger)
async def get_pdf_page_endpoint(periodical_id: int, page_index: int, _username: str = Depends(get_verify_token)):
    """
    Get a specific page from a PDF as an image.

    Args:
        periodical_id: ID of the periodical
        page_index: Page index (0-based)

    Returns:
        Page image as JPEG
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get page image
    page_data = await _render_in_process("page", get_pdf_page, file_path, page_index)

    if page_data is None:
        raise HTTPException(status_code=404, detail="Page not found or extraction failed")

    response = Response(content=page_data, media_type="image/jpeg")
    # Add cache headers for full-size pages (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.get("/periodicals/{periodical_id}/pdf/page/{page_index}/thumbnail")
@handle_api_errors("Get PDF page thumbnail", logger)
async def get_pdf_page_thumbnail_endpoint(
    periodical_id: int, page_index: int, _username: str = Depends(get_verify_token)
):
    """
    Get a thumbnail of a specific page from a PDF.

    Args:
        periodical_id: ID of the periodical
        page_index: Page index (0-based)

    Returns:
        Thumbnail image as JPEG (200px height)
    """

    def operation(db):
        periodical, file_path = _shared.get_periodical_with_file(db, periodical_id)

        if file_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")

        return file_path

    file_path = await with_db_session(_shared._session_factory, operation)

    # Get thumbnail
    thumbnail_data = await _render_in_process("thumbnail", get_pdf_page_thumbnail, file_path, page_index)

    if thumbnail_data is None:
        raise HTTPException(status_code=404, detail="Page not found or thumbnail creation failed")

    response = Response(content=thumbnail_data, media_type="image/jpeg")
    # Add cache headers for thumbnails (cache for 7 days)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@router.post("/periodicals/{periodical_id}/move-to-tracking")
@handle_api_errors("Move issue to tracking", logger)
async def move_issue_to_tracking(
    periodical_id: int, target_tracking_id: int, _username: str = Depends(get_verify_token)
) -> Dict[str, Any]:
    """
    Move a single issue to a different tracking record.
    Useful for correcting misplaced issues.

    Args:
        periodical_id: ID of the issue to move
        target_tracking_id: ID of the tracking record to move the issue to
    """

    def operation(db):
        from models.database import PeriodicalTracking

        periodical = _shared.get_periodical_or_404(db, periodical_id)

        target_tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == target_tracking_id).first()
        if not target_tracking:
            raise HTTPException(status_code=404, detail="Target tracking record not found")

        old_title = periodical.title
        old_tracking_id = periodical.tracking_id

        library_base_dir = _shared._library_base_dir or get_library_dir(None)
        category_prefix = _shared._category_prefix

        periodical.tracking_id = target_tracking_id
        if target_tracking.language:
            periodical.language = target_tracking.language

        is_special = is_periodical_special_edition(periodical)

        files_reorganized = False
        old_dir_to_cleanup = None
        if not is_special:
            old_pdf_path = Path(periodical.file_path)
            old_dir_to_cleanup = old_pdf_path.parent

            result = reorganize_periodical_files(
                periodical,
                new_title=target_tracking.title,
                library_base_dir=library_base_dir,
                category_prefix=category_prefix,
                should_update_database=True,
            )

            if result.success:
                files_reorganized = result.files_moved
                periodical.title = target_tracking.title
            else:
                logger.error(f"Error reorganizing periodical files: {result.error}")
                periodical.title = target_tracking.title

        tracking_removed = False
        if old_tracking_id and old_tracking_id != target_tracking_id:
            tracking_removed = _shared.retire_empty_source_tracking(db, old_tracking_id, target_tracking_id)

        db.commit()

        if old_dir_to_cleanup and old_dir_to_cleanup.exists():
            cleanup_empty_directories(old_dir_to_cleanup, library_base_dir)

        msg = f"Moved issue from '{old_title}' to '{target_tracking.title}'"
        if files_reorganized:
            msg += " and reorganized files"

        logger.info(msg)
        return success_response(
            msg,
            old_tracking_id=old_tracking_id,
            new_tracking_id=target_tracking_id,
            files_reorganized=files_reorganized,
            tracking_removed=tracking_removed,
        )

    return await with_db_session(_shared._session_factory, operation)
