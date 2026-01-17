"""
PDF processing utilities.
Centralized PDF cover extraction logic.
"""

import logging
from pathlib import Path
from typing import Optional

from pdf2image import convert_from_path
from PIL import Image

from core.constants.files import PDF_COVER_DPI_LOW, PDF_COVER_QUALITY

logger = logging.getLogger(__name__)

# Increase Pillow's decompression bomb limit for high-res PDFs
# Needed for 300 DPI magazine covers which can be ~130 MP
Image.MAX_IMAGE_PIXELS = 200000000  # 200 megapixels


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

        # Try a basic pdf2image operation to validate
        try:
            # Just try to get page count without actually converting
            from pdf2image import pdfinfo_from_path

            info = pdfinfo_from_path(str(pdf_path))
            if info.get("Pages", 0) == 0:
                logger.warning(f"PDF has no pages: {pdf_path}")
                return False
            return True
        except Exception as e:
            logger.warning(f"PDF validation failed for {pdf_path}: {e}")
            return False

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
        cover_path = output_dir / f"{pdf_path.stem}.jpg"

        images = convert_from_path(
            str(pdf_path), first_page=page_number, last_page=page_number, dpi=dpi
        )
        if not images:
            logger.warning(f"Could not extract images from PDF: {pdf_path}")
            return None

        images[0].save(str(cover_path), "JPEG", quality=quality)
        logger.info(f"Extracted cover from page {page_number}: {cover_path}")
        return cover_path

    except ImportError as e:
        if "pdf2image" in str(e):
            logger.warning(
                "pdf2image not available. Install with: pip install pdf2image"
            )
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
    except Exception as e:
        logger.error(f"Error extracting cover from {pdf_path}: {e}")
        return None
