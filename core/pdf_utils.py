"""
PDF processing utilities.
Centralized PDF cover extraction logic.
"""
import logging
from pathlib import Path
from typing import Optional

from pdf2image import convert_from_path

from core.constants import PDF_COVER_DPI_LOW, PDF_COVER_QUALITY

logger = logging.getLogger(__name__)


def extract_cover_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = PDF_COVER_DPI_LOW,
    quality: int = PDF_COVER_QUALITY
) -> Optional[Path]:
    """
    Extract first page of PDF as cover image.

    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save cover image
        dpi: Resolution for extraction
        quality: JPEG quality (1-100)

    Returns:
        Path to extracted cover image, or None if failed
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        cover_path = output_dir / f"{pdf_path.stem}.jpg"

        images = convert_from_path(
            str(pdf_path), first_page=1, last_page=1, dpi=dpi
        )
        if not images:
            logger.warning(f"Could not extract images from PDF: {pdf_path}")
            return None

        images[0].save(str(cover_path), "JPEG", quality=quality)
        logger.info(f"Extracted cover: {cover_path}")
        return cover_path

    except ImportError:
        logger.warning("pdf2image not available. Install with: pip install pdf2image Pillow")
        return None
    except Exception as e:
        logger.error(f"Error extracting cover from {pdf_path}: {e}")
        return None
