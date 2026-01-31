"""
PDF reader utilities for page-by-page reading.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def get_pdf_metadata(pdf_path: Path) -> Dict[str, Any]:
    """
    Get PDF metadata including page count.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dictionary with PDF metadata
    """
    try:
        doc = fitz.open(pdf_path)
        metadata = {
            "title": pdf_path.stem,
            "format": "PDF",
            "page_count": len(doc),
            "pages": [f"Page {i + 1}" for i in range(len(doc))],
        }
        doc.close()
        return metadata
    except Exception as e:
        logger.error(f"Failed to get PDF metadata from {pdf_path}: {e}")
        raise


def get_pdf_page(pdf_path: Path, page_index: int, dpi: int = 120) -> bytes:
    """
    Extract a specific page from PDF as image bytes.

    Args:
        pdf_path: Path to PDF file
        page_index: Page index (0-based)
        dpi: Resolution for rendering (default: 120, reduced from 150 for faster loading)

    Returns:
        Image bytes (JPEG format)
    """
    try:
        doc = fitz.open(pdf_path)

        if page_index < 0 or page_index >= len(doc):
            doc.close()
            raise ValueError(f"Invalid page index: {page_index} (PDF has {len(doc)} pages)")

        # Get the page
        page = doc[page_index]

        # Render page to pixmap (image)
        # Calculate zoom factor for desired DPI (72 is PyMuPDF default DPI)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert to JPEG bytes with optimization for faster loading
        # Progressive JPEG loads in multiple passes for better perceived performance
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=80, optimize=True, progressive=True)
        img_bytes.seek(0)

        doc.close()
        return img_bytes.getvalue()

    except Exception as e:
        logger.error(f"Failed to extract page {page_index} from {pdf_path}: {e}")
        raise


def get_pdf_page_thumbnail(pdf_path: Path, page_index: int, max_height: int = 150) -> bytes:
    """
    Extract a thumbnail of a specific page from PDF.

    Args:
        pdf_path: Path to PDF file
        page_index: Page index (0-based)
        max_height: Maximum height of thumbnail (default: 150px, reduced from 200px)

    Returns:
        Thumbnail image bytes (JPEG format)
    """
    try:
        doc = fitz.open(pdf_path)

        if page_index < 0 or page_index >= len(doc):
            doc.close()
            raise ValueError(f"Invalid page index: {page_index} (PDF has {len(doc)} pages)")

        # Get the page
        page = doc[page_index]

        # Calculate zoom for thumbnail
        # Get page dimensions and calculate zoom to achieve desired height
        page_height = page.rect.height
        zoom = max_height / page_height
        mat = fitz.Matrix(zoom, zoom)

        # Render page to pixmap
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert to JPEG bytes with lower quality for faster loading
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=75, optimize=True)
        img_bytes.seek(0)

        doc.close()
        return img_bytes.getvalue()

    except Exception as e:
        logger.error(f"Failed to create thumbnail for page {page_index} from {pdf_path}: {e}")
        raise
