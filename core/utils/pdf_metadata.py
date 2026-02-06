"""Utility for embedding metadata into PDF files as natural text."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import pypdf for PDF metadata writing
try:
    from pypdf import PdfReader, PdfWriter

    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    logger.debug("pypdf not available for PDF metadata embedding")


def _build_natural_metadata_text(metadata: Dict[str, Any], title: Optional[str] = None) -> str:
    """
    Build natural text from metadata that text_scan can parse.

    Creates text in the same format that would appear in a typical magazine/periodical,
    so the existing pattern matching in OCRService.extract_metadata_from_text() will find it.

    Args:
        metadata: Dict with year, month, volume, issue_number
        title: Optional title

    Returns:
        Natural text like "January 2024\nVolume 5 Issue 12"
    """
    from core.constants.date import NUMBER_TO_MONTH

    parts = []

    # Add title if provided
    if title:
        parts.append(title)

    # Build date string: "January 2024" or just "2024"
    date_parts = []
    if metadata.get("month"):
        month_name = NUMBER_TO_MONTH.get(metadata["month"], "")
        if month_name:
            date_parts.append(month_name)
    if metadata.get("year"):
        date_parts.append(str(metadata["year"]))
    if date_parts:
        parts.append(" ".join(date_parts))

    # Build volume/issue string: "Volume 5 Issue 12" or "Vol. 5 No. 12"
    vol_issue_parts = []
    if metadata.get("volume"):
        vol_issue_parts.append(f"Volume {metadata['volume']}")
    if metadata.get("issue_number"):
        vol_issue_parts.append(f"Issue {metadata['issue_number']}")
    if vol_issue_parts:
        parts.append(" ".join(vol_issue_parts))

    return "\n".join(parts)


def embed_metadata_in_pdf(
    pdf_path: str,
    metadata: Dict[str, Any],
    title: Optional[str] = None,
) -> bool:
    """
    Embed metadata into a PDF file as natural text for text_scan to find.

    This writes metadata discovered by OCR into the PDF's document properties
    in a natural text format (e.g., "January 2024\nVolume 5 Issue 12") that
    the standard text_scan extraction will parse, just like a real TEXT PDF.

    Args:
        pdf_path: Path to the PDF file
        metadata: Metadata dict with keys like year, month, volume, issue_number
        title: Optional title to embed

    Returns:
        True if successful, False otherwise

    Note:
        Embeds metadata in PDF properties:
        - /Subject: Natural text format that text_scan will parse
        - /Keywords: Same natural text (some PDF readers show this)
        - /Title: Periodical title (if provided)
    """
    if not PYPDF_AVAILABLE:
        logger.warning("pypdf not available, cannot embed metadata in PDF")
        return False

    path = Path(pdf_path)
    if not path.exists():
        logger.warning(f"PDF file not found: {pdf_path}")
        return False

    if path.suffix.lower() != ".pdf":
        logger.debug(f"Not a PDF file, skipping metadata embed: {pdf_path}")
        return False

    # Check if we have any metadata to embed
    if not any(metadata.get(k) for k in ("year", "month", "volume", "issue_number")):
        logger.debug(f"No metadata to embed for {pdf_path}")
        return False

    try:
        # Read existing PDF
        reader = PdfReader(str(path))

        # Skip encrypted PDFs — we can't safely modify them
        if reader.is_encrypted:
            logger.debug(f"PDF is encrypted, skipping metadata embed: {path.name}")
            return False

        writer = PdfWriter()

        # Copy all pages
        for page in reader.pages:
            writer.add_page(page)

        # Build natural text that text_scan can parse
        natural_text = _build_natural_metadata_text(metadata, title)

        # Prepare metadata dict for PDF
        pdf_metadata = {
            "/Subject": natural_text,
            "/Keywords": natural_text,
            "/Producer": "Curator",
            "/ModDate": datetime.now().strftime("D:%Y%m%d%H%M%S"),
        }

        # Add title if provided
        if title:
            pdf_metadata["/Title"] = title

        # Preserve existing metadata where possible
        if reader.metadata:
            existing = reader.metadata
            # Keep existing title if we're not overwriting
            if not title and existing.get("/Title"):
                pdf_metadata["/Title"] = existing.get("/Title")
            # Keep author/creator
            if existing.get("/Author"):
                pdf_metadata["/Author"] = existing.get("/Author")
            if existing.get("/Creator"):
                pdf_metadata["/Creator"] = existing.get("/Creator")

        # Write metadata
        writer.add_metadata(pdf_metadata)

        # Write to temporary file first, then replace
        temp_path = path.with_suffix(".pdf.tmp")
        try:
            with open(temp_path, "wb") as f:
                writer.write(f)

            # Replace original with modified version
            temp_path.replace(path)
            logger.info(f"Embedded OCR metadata into PDF: {path.name} ({natural_text!r})")
            return True

        except Exception as write_error:
            logger.error(f"Failed to write PDF: {write_error}")
            if temp_path.exists():
                temp_path.unlink()
            return False

    except Exception as e:
        error_msg = str(e)
        # Encrypted/DRM PDFs that slip past is_encrypted check (e.g., AES without cryptography package)
        if "cryptography" in error_msg.lower() or "encrypted" in error_msg.lower():
            logger.debug(f"PDF is encrypted, skipping metadata embed: {path.name}")
        else:
            logger.error(f"Failed to embed metadata in PDF {pdf_path}: {e}")
        return False
