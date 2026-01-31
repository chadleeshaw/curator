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
            from core.utils.epub import extract_text_from_epub

            text = extract_text_from_epub(epub_path, max_items=max_items)
            return text
        except Exception as e:
            logger.debug(f"Could not extract text from EPUB {epub_path}: {e}")
            return ""

    @staticmethod
    def extract_metadata_from_text(text: str) -> Dict[str, any]:
        """
        Extract metadata from scanned text.

        Uses OCRService's extraction logic for consistency and better error handling
        (handles spaces in years, O/0 confusion, etc.)

        NOTE: Text scan doesn't provide word-level confidence data, so confidence
        scores will be None. This is expected - text scan is for native PDFs with
        clean embedded text, which doesn't need confidence scoring.

        Args:
            text: Extracted text from document

        Returns:
            Dictionary containing extracted metadata (without confidence scores)
        """
        from services.ocr.service import OCRService

        # Use OCR's extraction logic (without word confidence data)
        # This gives us better year detection, consistent patterns, etc.
        metadata = OCRService.extract_metadata_from_text(text, words_data=None)

        # OCRService adds confidence fields (all None for text_scan)
        # We can keep them or remove them - keeping them makes output consistent
        # between text_scan and OCR, which is useful for the aggregation logic

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
            metadata.get("year") is not None or metadata.get("month") is not None or metadata.get("volume") is not None
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

        extension = path.suffix.lower()

        # CBZ/CBR files contain images, not text - they should use OCR instead
        if extension in [".cbz", ".cbr"]:
            logger.info(f"Skipping text scan for {extension.upper()} file (use OCR instead): {file_path}")
            return {
                "scanned": True,
                "text_found": False,
                "has_sufficient_metadata": False,
                "reason": f"{extension.upper()} files contain images, use OCR service instead",
            }

        # Try direct PDF text extraction
        if extension == ".pdf" and PDF_TEXT_AVAILABLE:
            logger.debug("Attempting direct PDF text extraction")
            text = TextScanService.extract_text_from_pdf(file_path, max_pages=1)
            if text:
                logger.info("Successfully extracted text from PDF")
                metadata = TextScanService.extract_metadata_from_text(text)
                metadata["extraction_method"] = "pdf_text"

        # Try direct EPUB text extraction
        elif extension == ".epub":
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
