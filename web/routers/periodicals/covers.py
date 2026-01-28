"""
Cover image operations for periodicals
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Query, Response
from fastapi.responses import FileResponse

from core.constants.errors import ErrorMessages
from core.constants.files import PDF_COVER_QUALITY_HIGH
from core.constants.ocr import PDF_COVER_DPI_OCR
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.pdf import extract_cover_from_pdf
from services.ocr.service import OCRService
from web.utils.responses import success_response

from . import _shared

router = _shared.router
logger = _shared.logger


def add_cache_headers(response: Response, max_age: int = 86400) -> Response:
    """
    Add HTTP cache headers to response.

    Args:
        response: FastAPI Response object
        max_age: Cache duration in seconds (default: 86400 = 24 hours)

    Returns:
        Response with cache headers
    """
    response.headers["Cache-Control"] = f"public, max-age={max_age}, immutable"
    response.headers["ETag"] = f'"{hash(response.headers.get("content-length", "0"))}"'
    return response


@router.get("/periodicals/{magazine_id}/cover")
@handle_api_errors("Get cover", logger)
async def get_cover(
    magazine_id: int,
    thumbnail: bool = Query(default=True, description="Return thumbnail for UI"),
):
    """
    Get magazine cover image.

    Args:
        magazine_id: Magazine ID
        thumbnail: If True (default), returns optimized thumbnail for UI. If False, returns full resolution.
    """

    cover_path = await with_db_session(_shared._session_factory, lambda db: _get_cover_path(db, magazine_id))

    # Return thumbnail for UI (fast loading)
    if thumbnail:
        from core.utils.thumbnail import get_or_create_thumbnail

        loop = asyncio.get_event_loop()
        thumbnail_path = await loop.run_in_executor(None, get_or_create_thumbnail, cover_path)
        response = FileResponse(thumbnail_path, media_type="image/jpeg")
        return add_cache_headers(response, max_age=86400)  # Cache for 24 hours

    # Return full resolution (for downloads/printing)
    response = FileResponse(cover_path, media_type="image/jpeg")
    return add_cache_headers(response, max_age=86400)  # Cache for 24 hours


def _get_cover_path(db_session, magazine_id):
    """Helper to get cover path from database"""
    magazine = _shared.get_periodical_or_404(db_session, magazine_id)

    if not magazine.cover_path:
        raise HTTPException(status_code=404, detail=ErrorMessages.COVER_NOT_FOUND)

    cover_path = Path(str(magazine.cover_path))
    if not cover_path.exists():
        raise HTTPException(status_code=404, detail="Cover file not found")

    return cover_path


@router.post("/periodicals/{magazine_id}/regenerate-cover")
@handle_api_errors("Regenerate cover", logger)
async def regenerate_cover(magazine_id: int, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Regenerate cover image from a specific PDF page.

    Args:
        magazine_id: ID of the periodical
        request_data: Dict with 'page_number' field

    Returns:
        Success response with new cover path
    """
    page_number = request_data.get("page_number", 1)
    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be >= 1")

    def operation(db):
        magazine, pdf_path = _shared.get_periodical_with_file(db, magazine_id)

        # Determine cover directory from config
        if _shared._library_base_dir:
            cover_dir = _shared._library_base_dir / ".covers"
        else:
            # Fallback: use pdf's parent directory structure
            cover_dir = pdf_path.parent.parent.parent / ".covers"

        # Extract cover from specified page
        if OCRService.is_available():
            cover_path = extract_cover_from_pdf(
                pdf_path,
                cover_dir,
                dpi=PDF_COVER_DPI_OCR,
                quality=PDF_COVER_QUALITY_HIGH,
                page_number=page_number,
            )
        else:
            cover_path = extract_cover_from_pdf(pdf_path, cover_dir, page_number=page_number)

        if not cover_path:
            raise HTTPException(status_code=500, detail="Failed to extract cover from PDF")

        # Update database with new cover path and page number
        magazine.cover_path = str(cover_path)
        if magazine.extra_metadata is None:
            magazine.extra_metadata = {}
        magazine.extra_metadata["cover_page"] = page_number
        db.commit()

        logger.info(f"Regenerated cover for magazine {magazine_id} from page {page_number}")

        return success_response(
            f"Cover regenerated from page {page_number}",
            cover_path=str(cover_path),
        )

    return await with_db_session(_shared._session_factory, operation)
