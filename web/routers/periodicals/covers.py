"""
Cover image operations for periodicals
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Query, Response
from fastapi.responses import FileResponse

from core.constants.errors import ErrorMessages
from core.utils import run_in_thread
from models.database import Magazine

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
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()

                if not magazine or not magazine.cover_path:
                    raise HTTPException(status_code=404, detail=ErrorMessages.COVER_NOT_FOUND)

                cover_path = Path(magazine.cover_path)
                if not cover_path.exists():
                    raise HTTPException(status_code=404, detail="Cover file not found")

                return cover_path
            finally:
                db_session.close()

        cover_path = await run_in_thread(_db_operation)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get cover error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/periodicals/{magazine_id}/regenerate-cover")
async def regenerate_cover(magazine_id: int, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Regenerate cover image from a specific PDF page.

    Args:
        magazine_id: ID of the periodical
        request_data: Dict with 'page_number' field

    Returns:
        Success response with new cover path
    """
    try:
        from core.utils.pdf import extract_cover_from_pdf
        from core.constants.ocr import PDF_COVER_DPI_OCR
        from core.constants.files import PDF_COVER_QUALITY_HIGH
        from services.ocr.service import OCRService

        page_number = request_data.get("page_number", 1)
        if page_number < 1:
            raise HTTPException(status_code=400, detail="Page number must be >= 1")

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.PERIODICAL_NOT_FOUND)

                pdf_path = Path(magazine.file_path)
                if not pdf_path.exists():
                    raise HTTPException(status_code=404, detail="PDF file not found on disk")

                # Determine cover directory from config
                if _shared._organize_base_dir:
                    cover_dir = _shared._organize_base_dir / ".covers"
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
                db_session.commit()

                logger.info(f"Regenerated cover for magazine {magazine_id} from page {page_number}")

                return {
                    "success": True,
                    "message": f"Cover regenerated from page {page_number}",
                    "cover_path": str(cover_path),
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating cover: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
