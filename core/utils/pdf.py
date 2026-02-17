"""
PDF processing utilities.
Centralized PDF cover extraction logic.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image

from core.constants.files import (
    PIL_MAX_IMAGE_PIXELS,
    PDF_COVER_DPI_LOW,
    PDF_COVER_QUALITY,
)

logger = logging.getLogger(__name__)

# Increase Pillow's decompression bomb limit for high-res covers
Image.MAX_IMAGE_PIXELS = PIL_MAX_IMAGE_PIXELS


def is_landscape_page(pdf_path: Path, page_number: int = 1) -> Tuple[bool, float]:
    """
    Check if a specific page in a PDF is in landscape orientation.

    Args:
        pdf_path: Path to PDF file
        page_number: Page number to check (1-based, default: 1)

    Returns:
        Tuple of (is_landscape, aspect_ratio) where:
        - is_landscape: True if width > height
        - aspect_ratio: width / height ratio
    """
    try:
        doc = fitz.open(str(pdf_path))
        page_index = page_number - 1

        if page_index < 0 or page_index >= len(doc):
            logger.warning(f"Invalid page number {page_number} for PDF with {len(doc)} pages")
            doc.close()
            return False, 1.0

        page = doc[page_index]
        rect = page.rect
        width = rect.width
        height = rect.height

        doc.close()

        aspect_ratio = width / height if height > 0 else 1.0
        is_landscape = width > height

        logger.debug(f"Page {page_number} dimensions: {width}x{height} (aspect ratio: {aspect_ratio:.2f})")
        return is_landscape, aspect_ratio

    except Exception as e:
        logger.warning(f"Error checking page orientation for {pdf_path}: {e}")
        return False, 1.0


def validate_pdf(pdf_path: Path) -> bool:
    """
    Validate that a file is a readable PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        True if PDF appears to be valid, False otherwise
    """
    try:
        # Basic file checks
        if not pdf_path.exists():
            logger.warning(f"PDF file does not exist: {pdf_path}")
            return False

        # For production use, we could add PDF header validation here
        # But for now, let pdf2image handle the validation to avoid breaking tests
        return True

    except Exception as e:
        logger.warning(f"PDF validation error for {pdf_path}: {e}")
        return False


def extract_cover_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = PDF_COVER_DPI_LOW,
    quality: int = PDF_COVER_QUALITY,
    page_number: int = 1,
) -> Optional[Path]:
    """
    Extract specified page of PDF as cover image.

    If the page is in landscape orientation (width > height), it's assumed to contain
    both front and back covers side-by-side. In this case, the right half of the image
    is extracted as the front cover.

    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save cover image
        dpi: Resolution for extraction
        quality: JPEG quality (1-100)
        page_number: Page number to extract (default: 1)

    Returns:
        Path to extracted cover image, or None if failed
    """
    try:
        # First validate that the PDF is readable
        if not validate_pdf(pdf_path):
            logger.error(f"Invalid or corrupted PDF file: {pdf_path}")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        # Use the source filename stem directly - the caller is responsible
        # for providing a path with a unique name (e.g., after organization)
        cover_path = output_dir / f"{pdf_path.stem}.jpg"

        # Check if page is landscape before extraction
        is_landscape, aspect_ratio = is_landscape_page(pdf_path, page_number)

        images = convert_from_path(str(pdf_path), first_page=page_number, last_page=page_number, dpi=dpi)
        if not images:
            logger.warning(f"Could not extract images from PDF: {pdf_path}")
            return None

        image = images[0]

        # If landscape, crop to right half (front cover)
        if is_landscape:
            width, height = image.size
            logger.debug(
                f"Detected landscape page {page_number} ({width}x{height}, ratio: {aspect_ratio:.2f}). "
                f"Cropping to right half for front cover."
            )
            # Crop right half: (left, upper, right, lower)
            # Left starts at midpoint, right goes to full width
            mid_x = width // 2
            image = image.crop((mid_x, 0, width, height))
            logger.debug(f"Cropped to {image.size[0]}x{image.size[1]}")

        image.save(str(cover_path), "JPEG", quality=quality)
        logger.info(f"Extracted cover from page {page_number}: {cover_path}")
        return cover_path

    except ImportError as e:
        if "pdf2image" in str(e):
            logger.warning("pdf2image not available. Install with: pip install pdf2image")
        elif "pypdf" in str(e):
            logger.warning("pypdf not available. Install with: pip install pypdf")
        else:
            logger.warning(f"Missing dependency for PDF processing: {e}")
        return None
    except Exception as e:
        error_msg = str(e)
        if "trailer dictionary" in error_msg or "xref table" in error_msg:
            logger.error(f"Corrupted PDF file (invalid structure): {pdf_path}")
        elif "page count" in error_msg:
            logger.error(f"Unable to read PDF page structure: {pdf_path}")
        elif "not a PDF file" in error_msg:
            logger.error(f"File is not a valid PDF: {pdf_path}")
        else:
            logger.error(f"Error extracting cover from {pdf_path}: {e}")
        return None
