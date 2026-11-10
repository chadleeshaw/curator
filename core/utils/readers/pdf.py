"""
PDF reader utilities for page-by-page reading.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# Rendering cost grows with output pixels, and a fixed DPI makes oversized pages
# (posters, high-res scans) come out several thousand pixels wide.
MAX_PAGE_WIDTH_PX = 1600

# A scan counts as "the whole page" when its image covers at least this much of the
# page, and is not much bigger than it (a larger image is a cropped spread).
_MIN_PAGE_COVERAGE = 0.95
_MAX_IMAGE_TO_PAGE_AREA = 1.15

# Colour spaces a browser shows correctly from the bare JPEG (not Lab, CMYK, Indexed...).
_BROWSER_SAFE_COLORSPACES = ("DeviceRGB", "DeviceGray", "ICCBased(RGB", "ICCBased(Gray")


def _embedded_page_jpeg(doc: fitz.Document, page: fitz.Page) -> Optional[bytes]:
    """
    Return the page's own JPEG if the page is nothing but one full-page scan.

    Most scanned magazines store each page as a single JPEG. Sending that file
    as-is takes a few milliseconds; rendering and re-encoding it takes 0.5-6 s
    and loses quality. Anything that would look different from the rendered page
    (several images, visible text, drawings, rotation, cropping, masks, colour
    spaces browsers don't handle) returns None so the caller renders normally.
    """
    if page.rotation:
        return None

    # Deliberately not get_image_info(xrefs=True): it hashes every image and takes seconds.
    shown = page.get_image_info()
    if len(shown) != 1:
        return None
    image = shown[0]

    scale_x, skew_y, skew_x, scale_y = image["transform"][:4]
    if skew_x or skew_y or scale_x <= 0 or scale_y <= 0:
        return None

    bbox, page_area = fitz.Rect(image["bbox"]), page.rect.get_area()
    if (bbox & page.rect).get_area() < _MIN_PAGE_COVERAGE * page_area:
        return None
    if bbox.get_area() > _MAX_IMAGE_TO_PAGE_AREA * page_area:
        return None

    if not image["cs-name"].startswith(_BROWSER_SAFE_COLORSPACES):
        return None

    # Find the image object: the one plain-JPEG resource with the displayed dimensions.
    # item = (xref, smask, width, height, bpc, colorspace, alt_cs, name, filter, ...)
    candidates = [
        item
        for item in page.get_images(full=True)
        if (item[2], item[3]) == (image["width"], image["height"]) and item[8] == "DCTDecode" and not item[1]
    ]
    if len(candidates) != 1:
        return None
    xref = candidates[0][0]
    if any(key in doc.xref_object(xref) for key in ("/Decode", "/Mask", "/SMask")):
        return None

    # An invisible OCR text layer (type 3) is fine; visible text or drawings on top are not.
    if page.get_cdrawings() or any(span["type"] != 3 and span["opacity"] > 0 for span in page.get_texttrace()):
        return None

    return doc.xref_stream_raw(xref)


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

    Scanned pages are returned as their embedded JPEG without re-rendering;
    everything else is rendered at *dpi*, capped at MAX_PAGE_WIDTH_PX wide.

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
            page_count = len(doc)
            doc.close()
            raise ValueError(f"Invalid page index: {page_index} (PDF has {page_count} pages)")

        # Get the page
        page = doc[page_index]

        embedded = _embedded_page_jpeg(doc, page)
        if embedded is not None:
            doc.close()
            return embedded

        # Render page to pixmap (image)
        # Calculate zoom factor for desired DPI (72 is PyMuPDF default DPI)
        zoom = min(dpi / 72, MAX_PAGE_WIDTH_PX / page.rect.width)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # No optimize/progressive: both add encoder passes, and the reader fetches the
        # whole image as a blob before showing it, so progressive display never happens.
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=80)
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
            page_count = len(doc)
            doc.close()
            raise ValueError(f"Invalid page index: {page_index} (PDF has {page_count} pages)")

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
        img.save(img_bytes, format="JPEG", quality=75)
        img_bytes.seek(0)

        doc.close()
        return img_bytes.getvalue()

    except Exception as e:
        logger.error(f"Failed to create thumbnail for page {page_index} from {pdf_path}: {e}")
        raise
