"""Text scanning service for extracting text directly from PDF and EPUB files."""

import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader
    PDF_TEXT_AVAILABLE = True
except ImportError:
    PDF_TEXT_AVAILABLE = False
    logger.debug("pypdf not available for PDF text extraction")


class TextScanService:
    """Service for extracting text directly from PDF and EPUB files (without OCR)."""

    @staticmethod
    def is_pdf_available() -> bool:
        """Check if PDF text extraction is available."""
        return PDF_TEXT_AVAILABLE

    @staticmethod
    def extract_text_from_pdf(pdf_path: str, max_pages: int = 3) -> str:
        """
        Extract text directly from PDF (for PDFs with embedded text).
        Much faster than OCR for text-based PDFs.

        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract (default: first 3 pages)

        Returns:
            Extracted text as string
        """
        if not PDF_TEXT_AVAILABLE:
            logger.debug("pypdf not available for PDF text extraction")
            return ""

        try:
            reader = PdfReader(pdf_path)
            text_parts = []

            # Extract text from first few pages
            for i, page in enumerate(reader.pages[:max_pages]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.debug(f"Could not extract text from page {i}: {e}")

            full_text = "\n".join(text_parts)
            return full_text.strip()
        except Exception as e:
            logger.debug(f"Could not extract text from PDF {pdf_path}: {e}")
            return ""

    @staticmethod
    def extract_text_from_epub(epub_path: Path, max_items: int = 2) -> str:
        """
        Extract text directly from EPUB file.

        Args:
            epub_path: Path to the EPUB file
            max_items: Maximum number of items to extract (default: 2)

        Returns:
            Extracted text as string
        """
        try:
            from core.epub_utils import extract_text_from_epub
            text = extract_text_from_epub(epub_path, max_items=max_items)
            return text
        except Exception as e:
            logger.debug(f"Could not extract text from EPUB {epub_path}: {e}")
            return ""

    @staticmethod
    def extract_metadata_from_text(text: str) -> Dict[str, any]:
        """
        Extract metadata from scanned text.

        Args:
            text: Extracted text from document

        Returns:
            Dictionary containing extracted metadata
        """
        import re

        metadata = {
            "issue_number": None,
            "year": None,
            "month": None,
            "volume": None,
            "special_edition": False,
            "detected_text": text,
        }

        # Clean up text
        text_upper = text.upper()
        # Also create a version with newlines replaced by spaces for multi-word phrase matching
        text_upper_spaced = text_upper.replace('\n', ' ')

        # Detect issue number patterns
        issue_patterns = [
            r"#(\d+)",  # #123
            r"ISSUE\s+(\d+)",  # Issue 123
            r"NO\.?\s*(\d+)",  # No. 123 or No 123
            r"NUMBER\s+(\d+)",  # Number 123
        ]

        for pattern in issue_patterns:
            match = re.search(pattern, text_upper)
            if match:
                metadata["issue_number"] = int(match.group(1))
                break

        # Detect year (4-digit number between 1900-2099)
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
        if year_match:
            metadata["year"] = int(year_match.group(1))

        # Detect month names
        months = {
            "JANUARY": 1,
            "FEBRUARY": 2,
            "MARCH": 3,
            "APRIL": 4,
            "MAY": 5,
            "JUNE": 6,
            "JULY": 7,
            "AUGUST": 8,
            "SEPTEMBER": 9,
            "OCTOBER": 10,
            "NOVEMBER": 11,
            "DECEMBER": 12,
            "JAN": 1,
            "FEB": 2,
            "MAR": 3,
            "APR": 4,
            "JUN": 6,
            "JUL": 7,
            "AUG": 8,
            "SEP": 9,
            "SEPT": 9,
            "OCT": 10,
            "NOV": 11,
            "DEC": 12,
        }

        for month_name, month_num in months.items():
            if month_name in text_upper:
                metadata["month"] = month_num
                break

        # Detect volume
        volume_patterns = [
            r"VOL\.?\s*(\d+)",  # Vol. 1 or Vol 1
            r"VOLUME\s+(\d+)",  # Volume 1
            r"V\.?\s*(\d+)",  # V. 1 or V 1
        ]

        for pattern in volume_patterns:
            match = re.search(pattern, text_upper)
            if match:
                metadata["volume"] = int(match.group(1))
                break

        # Detect special edition indicators
        # Use text_upper_spaced to handle multi-word phrases that may be split across lines
        special_indicators = [
            "SPECIAL EDITION",
            "SPECIAL ISSUE",
            "LIMITED EDITION",
            "COLLECTOR",
            "ANNIVERSARY",
            "EXCLUSIVE",
        ]

        for indicator in special_indicators:
            if indicator in text_upper_spaced:
                metadata["special_edition"] = True
                break

        return metadata

    @staticmethod
    def _has_sufficient_metadata(metadata: Dict[str, any]) -> bool:
        """
        Check if extracted metadata has enough information (year, month, or volume).

        Args:
            metadata: Dictionary containing extracted metadata

        Returns:
            True if metadata has year/month/volume, False otherwise
        """
        return (
            metadata.get("year") is not None
            or metadata.get("month") is not None
            or metadata.get("volume") is not None
        )

    @staticmethod
    def scan_document(file_path: str, language: Optional[str] = None) -> Dict[str, any]:
        """
        Scan a PDF or EPUB document and extract text-based metadata.
        This does NOT use OCR - only direct text extraction.

        Args:
            file_path: Path to the PDF or EPUB file
            language: Language hint (reserved for future use, not used in text extraction)

        Returns:
            Dictionary containing extracted metadata
        """
        logger.info(f"Scanning document for text: {file_path}")
        path = Path(file_path)
        text = ""
        metadata = {}

        # Try direct PDF text extraction
        if path.suffix.lower() == ".pdf" and PDF_TEXT_AVAILABLE:
            logger.debug("Attempting direct PDF text extraction")
            text = TextScanService.extract_text_from_pdf(file_path, max_pages=1)
            if text:
                logger.info("Successfully extracted text from PDF")
                metadata = TextScanService.extract_metadata_from_text(text)
                metadata["extraction_method"] = "pdf_text"

        # Try direct EPUB text extraction
        elif path.suffix.lower() == ".epub":
            logger.debug("Attempting direct EPUB text extraction")
            text = TextScanService.extract_text_from_epub(path, max_items=2)
            if text:
                logger.info("Successfully extracted text from EPUB")
                metadata = TextScanService.extract_metadata_from_text(text)
                metadata["extraction_method"] = "epub_text"

        if not text:
            logger.warning(f"No text extracted from {file_path}")
            return {
                "scanned": True,  # Text scan was attempted
                "text_found": False,
                "has_sufficient_metadata": False,
            }

        logger.debug(f"Extracted text: {text[:200]}...")  # Log first 200 chars

        metadata["scanned"] = True  # Text scan was performed
        metadata["text_found"] = True
        metadata["has_sufficient_metadata"] = TextScanService._has_sufficient_metadata(metadata)

        return metadata
