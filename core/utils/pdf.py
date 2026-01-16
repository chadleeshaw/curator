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
        output_dir.mkdir(parents=True, exist_ok=True)
        cover_path = output_dir / f"{pdf_path.stem}.jpg"

        images = convert_from_path(str(pdf_path), first_page=page_number, last_page=page_number, dpi=dpi)
        if not images:
            logger.warning(f"Could not extract images from PDF: {pdf_path}")
            return None

        images[0].save(str(cover_path), "JPEG", quality=quality)
        logger.info(f"Extracted cover from page {page_number}: {cover_path}")
        return cover_path

    except ImportError:
        logger.warning("pdf2image not available. Install with: pip install pdf2image Pillow")
        return None
    except Exception as e:
        logger.error(f"Error extracting cover from {pdf_path}: {e}")
        return None
