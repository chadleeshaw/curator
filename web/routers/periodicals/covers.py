"""
Cover image operations for periodicals
"""

import shutil
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Query, Response, UploadFile, File
from fastapi.responses import FileResponse
from PIL import Image

from core.constants.errors import ErrorMessages
from core.constants.files import PDF_COVER_QUALITY_HIGH
from core.constants.ocr import PDF_COVER_DPI_OCR
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.pdf import extract_cover_from_pdf
from models.database import OCRJob
from services.ocr.queue import OCRQueueService
from services.ocr.service import OCRService
from web.utils.responses import success_response

from . import _shared

# Allowed image extensions for cover upload
ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

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

        thumbnail_path = await run_in_thread(lambda: get_or_create_thumbnail(cover_path))
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


@router.post("/periodicals/{magazine_id}/upload-cover")
@handle_api_errors("Upload cover", logger)
async def upload_cover(magazine_id: int, file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a custom cover image for a periodical.

    Args:
        magazine_id: ID of the periodical
        file: Image file to upload (jpg, png, webp)

    Returns:
        Success response with new cover path
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_COVER_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_COVER_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()

    def operation(db):
        magazine = _shared.get_periodical_or_404(db, magazine_id)

        # Determine cover directory from config
        if _shared._library_base_dir:
            cover_dir = _shared._library_base_dir / ".covers"
        else:
            # Fallback: use stored file path's parent directory structure
            if magazine.file_path:
                pdf_path = Path(magazine.file_path)
                cover_dir = pdf_path.parent.parent.parent / ".covers"
            else:
                raise HTTPException(status_code=500, detail="Unable to determine cover directory")

        cover_dir.mkdir(parents=True, exist_ok=True)

        # Determine output filename (use magazine's existing naming or generate from ID)
        if magazine.file_path:
            base_name = Path(magazine.file_path).stem
        else:
            base_name = f"magazine_{magazine_id}"

        # Always save as JPG for consistency
        cover_path = cover_dir / f"{base_name}.jpg"

        # Save and convert to JPG if needed
        temp_path = cover_dir / f"temp_{magazine_id}{file_ext}"
        try:
            with open(temp_path, "wb") as f:
                f.write(content)

            # Convert to JPG if not already
            if file_ext in {".png", ".webp"}:
                img = Image.open(temp_path)
                # Convert to RGB if necessary (for transparency)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(str(cover_path), "JPEG", quality=90)
                temp_path.unlink()
            else:
                # Already JPG, just move
                shutil.move(str(temp_path), str(cover_path))

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to save cover: {e}")

        # Store old cover path before updating (for thumbnail cleanup)
        old_cover_path = Path(magazine.cover_path) if magazine.cover_path else None

        # Update database with new cover path
        magazine.cover_path = str(cover_path)
        # Mark as custom uploaded cover (not from PDF)
        if magazine.extra_metadata is None:
            magazine.extra_metadata = {}
        magazine.extra_metadata["cover_uploaded"] = True
        magazine.extra_metadata.pop("cover_page", None)  # Remove page reference
        db.commit()

        # Invalidate thumbnail cache by removing old thumbnail
        if old_cover_path and old_cover_path.exists():
            # Thumbnails have _thumb suffix before extension
            old_thumbnail_path = old_cover_path.parent / f"{old_cover_path.stem}_thumb.jpg"
            if old_thumbnail_path.exists():
                old_thumbnail_path.unlink()
                logger.debug(f"Removed old thumbnail: {old_thumbnail_path}")

        logger.info(f"Uploaded custom cover for magazine {magazine_id}")

        return success_response(
            "Cover uploaded successfully",
            cover_path=str(cover_path),
        )

    return await with_db_session(_shared._session_factory, operation)


@router.post("/periodicals/{magazine_id}/regenerate-thumbnail-ocr")
@handle_api_errors("Regenerate thumbnail and OCR", logger)
async def regenerate_thumbnail_ocr(magazine_id: int) -> Dict[str, Any]:
    """
    Regenerate cover thumbnail and queue OCR for a single periodical.

    Extracts a fresh cover from the PDF (using the stored cover page or page 1),
    invalidates the cached thumbnail, and queues an OCR job.

    Args:
        magazine_id: ID of the periodical

    Returns:
        Success response with cover path and OCR job status
    """

    def operation(db):
        magazine, pdf_path = _shared.get_periodical_with_file(db, magazine_id)

        # Skip regeneration if a custom cover was uploaded and the file still exists
        if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
            if magazine.extra_metadata.get("cover_uploaded") and magazine.cover_path:
                cover_file = Path(magazine.cover_path)
                if cover_file.exists():
                    logger.info(f"Skipping regeneration for magazine {magazine_id} — custom uploaded cover exists")
                    return success_response(
                        "Skipped — custom uploaded cover exists. Use Edit Metadata to change the cover.",
                        cover_path=str(cover_file),
                        skipped=True,
                    )
                else:
                    logger.info(f"Custom cover missing for magazine {magazine_id}, regenerating from PDF")

        # Determine cover directory
        if _shared._library_base_dir:
            cover_dir = _shared._library_base_dir / ".covers"
        else:
            cover_dir = pdf_path.parent.parent.parent / ".covers"

        # Use stored cover page or default to 1
        page_number = 1
        if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
            page_number = magazine.extra_metadata.get("cover_page", 1)

        # Invalidate old thumbnail before regenerating
        if magazine.cover_path:
            old_cover = Path(magazine.cover_path)
            old_thumbnail = old_cover.parent / f"{old_cover.stem}_thumb.jpg"
            if old_thumbnail.exists():
                old_thumbnail.unlink()
                logger.debug(f"Removed old thumbnail: {old_thumbnail}")

        # Extract cover from PDF
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
            raise HTTPException(
                status_code=500,
                detail="Failed to extract cover from PDF. You can upload a thumbnail manually using Edit Metadata.",
            )

        # Update database with new cover path
        magazine.cover_path = str(cover_path)
        # Clear uploaded flag since we regenerated from PDF
        if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
            magazine.extra_metadata.pop("cover_uploaded", None)

        # Queue OCR job
        ocr_queued = False
        ocr_message = "OCR not available"
        if OCRService.is_available():
            job = OCRQueueService.queue_ocr_job(
                db=db,
                periodical_id=magazine_id,
                priority=OCRJob.PriorityEnum.HIGH.value,
                language=magazine.language,
            )
            if job:
                ocr_queued = True
                ocr_message = f"OCR job queued (job #{job.id})"
            else:
                ocr_message = "OCR job already queued for this periodical"
        else:
            ocr_message = "OCR (Tesseract) is not installed — OCR skipped"

        db.commit()

        logger.info(f"Regenerated thumbnail and queued OCR for magazine {magazine_id} (page {page_number})")

        return success_response(
            f"Thumbnail regenerated from page {page_number}. {ocr_message}",
            cover_path=str(cover_path),
            ocr_queued=ocr_queued,
            ocr_message=ocr_message,
        )

    return await with_db_session(_shared._session_factory, operation)
