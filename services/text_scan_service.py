"""Text scanning service for extracting text directly from PDF and EPUB files."""

import logging
import multiprocessing
from pathlib import Path
from typing import Optional, Dict

from core.constants.ocr import PDF_TEXT_SCAN_TIMEOUT

logger = logging.getLogger(__name__)

# Use 'spawn' context to avoid fork-safety issues in multithreaded processes
_mp_ctx = multiprocessing.get_context("spawn")

try:
    from pypdf import PdfReader

    PDF_TEXT_AVAILABLE = True
    # Suppress noisy pypdf warnings about malformed objects in corrupted/unusual PDFs
    logging.getLogger("pypdf._reader").setLevel(logging.ERROR)
except ImportError:
    PDF_TEXT_AVAILABLE = False
    logger.debug("pypdf not available for PDF text extraction")


def _read_pdf_in_process(pdf_path: str, max_pages: int, result_queue) -> None:
    """
    Read PDF text in a child process. Puts result into queue.

    Using a separate process allows us to hard-kill it if pypdf hangs
    on a corrupted file (threads cannot be killed in Python).
    """
    try:
        # Suppress pypdf warnings in child process too
        logging.getLogger("pypdf._reader").setLevel(logging.ERROR)

        reader = PdfReader(pdf_path)
        text_parts = []

        # Extract text from PDF metadata fields first
        if reader.metadata:
            for field in ("/Subject", "/Keywords"):
                value = reader.metadata.get(field)
                if value and isinstance(value, str):
                    text_parts.append(value)

        # Extract text from first few pages
        for i, page in enumerate(reader.pages[:max_pages]):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception:
                pass

        result_queue.put("\n".join(text_parts).strip())
    except Exception as e:
        result_queue.put(f"__ERROR__:{e}")


class TextScanService:
    """Service for extracting text directly from PDF and EPUB files (without OCR)."""

    @staticmethod
    def is_pdf_available() -> bool:
        """Check if PDF text extraction is available."""
        return PDF_TEXT_AVAILABLE

    @staticmethod
    def _read_pdf_text(pdf_path: str, max_pages: int) -> str:
        """Read text from PDF. Intended to be run inside a thread with a timeout."""
        reader = PdfReader(pdf_path)
        text_parts = []

        # Extract text from PDF metadata fields first
        # This picks up embedded metadata from previous OCR processing
        if reader.metadata:
            # Subject and Keywords often contain date/issue info
            for field in ("/Subject", "/Keywords"):
                value = reader.metadata.get(field)
                if value and isinstance(value, str):
                    text_parts.append(value)

        # Extract text from first few pages
        for i, page in enumerate(reader.pages[:max_pages]):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.debug(f"Could not extract text from page {i}: {e}")

        return "\n".join(text_parts).strip()

    @staticmethod
    def extract_text_from_pdf(pdf_path: str, max_pages: int = 3, timeout_seconds: int = PDF_TEXT_SCAN_TIMEOUT) -> str:
        """
        Extract text directly from PDF (for PDFs with embedded text).
        Much faster than OCR for text-based PDFs.

        Also extracts text from PDF metadata fields (Subject, Keywords) which may
        contain metadata embedded by previous OCR processing.

        Uses a child process with a hard kill timeout since pypdf can hang
        indefinitely on corrupted PDFs and Python threads cannot be killed.

        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract (default: first 3 pages)
            timeout_seconds: Timeout for reading corrupted/slow PDFs (default: 3s)

        Returns:
            Extracted text as string
        """
        if not PDF_TEXT_AVAILABLE:
            logger.debug("pypdf not available for PDF text extraction")
            return ""

        try:
            result_queue = _mp_ctx.Queue()
            proc = _mp_ctx.Process(
                target=_read_pdf_in_process,
                args=(pdf_path, max_pages, result_queue),
                daemon=True,
            )
            proc.start()
            proc.join(timeout=timeout_seconds)

            if proc.is_alive():
                # Process hung on corrupted PDF — kill it
                proc.kill()
                proc.join(timeout=2)
                logger.warning(f"PDF reading timed out after {timeout_seconds}s for {pdf_path} - file may be corrupted")
                return ""

            if not result_queue.empty():
                result = result_queue.get_nowait()
                if isinstance(result, str) and result.startswith("__ERROR__:"):
                    logger.debug(f"Could not extract text from PDF {pdf_path}: {result[10:]}")
                    return ""
                return result

            return ""
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

        For PDFs, first checks for Curator-embedded metadata (from previous OCR),
        then falls back to text extraction.

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

        # Try direct PDF text extraction (also reads metadata fields for embedded OCR data)
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
