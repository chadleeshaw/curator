"""OCR service for extracting text from cover art images using PyMuPDF + Tesseract."""

import logging
import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, List

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from core.constants.date import OCR_MONTH_NAMES
from core.constants.language import (
    LANGUAGE_TO_PADDLEOCR,
)  # Will rename to LANGUAGE_TO_TESSERACT
from core.constants.ocr import (
    MAX_IMAGE_PIXELS,
    OCR_DISABLE_ENV_VALUES,
    OCR_ISSUE_PATTERNS,
    OCR_YEAR_PATTERN,
    OCR_VOLUME_PATTERNS,
    OCR_SPECIAL_EDITION_INDICATORS,
    PDF_COVER_DPI_OCR,
)

# Increase Pillow's decompression bomb limit for high-res images
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

logger = logging.getLogger(__name__)


class OCRServiceConfig:
    """Manages OCR service state and configuration."""

    def __init__(self):
        self.ocr_disabled = self._check_ocr_disabled()
        self.warning_logged = False
        self.tesseract_available = self._check_tesseract_available()

    @staticmethod
    def _check_ocr_disabled():
        """Check if OCR is disabled via environment variable."""
        disabled = os.environ.get("DISABLE_OCR", "").lower() in OCR_DISABLE_ENV_VALUES
        if disabled:
            logger.info("OCR is disabled via DISABLE_OCR environment variable")
        return disabled

    @staticmethod
    def _check_tesseract_available():
        """Check if Tesseract is available on the system."""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}")
            return False


# Global configuration instance
_ocr_config = OCRServiceConfig()

# Check if OCR is available
OCR_AVAILABLE = _ocr_config.tesseract_available and not _ocr_config.ocr_disabled


def _normalize_language_code(language: Optional[str]) -> str:
    """
    Normalize language name or code to Tesseract language code.

    Args:
        language: Language name or code (e.g., "English", "en", "French", "fr")

    Returns:
        Tesseract language code (e.g., "eng", "fra", "deu", "spa")
    """
    # Tesseract language codes mapping
    tesseract_codes = {
        "english": "eng",
        "en": "eng",
        "french": "fra",
        "fr": "fra",
        "french (france)": "fra",
        "german": "deu",
        "de": "deu",
        "spanish": "spa",
        "es": "spa",
        "italian": "ita",
        "it": "ita",
        "portuguese": "por",
        "pt": "por",
        "dutch": "nld",
        "nl": "nld",
        "russian": "rus",
        "ru": "rus",
        "chinese": "chi_sim",
        "zh": "chi_sim",
        "japanese": "jpn",
        "ja": "jpn",
        "korean": "kor",
        "ko": "kor",
    }

    if language:
        return tesseract_codes.get(language.lower(), "eng")
    return "eng"


def _parse_paddle_ocr_results(result) -> list:
    """
    Deprecated: Kept for backward compatibility.
    Parse PaddleOCR results to extract text lines.

    Args:
        result: PaddleOCR prediction result

    Returns:
        List of text strings
    """
    text_parts = []

    if not isinstance(result, list) or len(result) == 0:
        return text_parts

    for item in result:
        # Check if it has rec_texts attribute or key
        texts = None
        if hasattr(item, "rec_texts"):
            texts = item.rec_texts
        elif isinstance(item, dict) and "rec_texts" in item:
            texts = item["rec_texts"]

        if texts and isinstance(texts, list):
            text_parts.extend(texts)

    return text_parts


def _extract_issue_number(text_upper: str) -> Optional[int]:
    """
    Extract issue number from OCR text.

    Args:
        text_upper: Uppercase version of OCR text

    Returns:
        Issue number or None if not found
    """
    for pattern in OCR_ISSUE_PATTERNS:
        match = re.search(pattern, text_upper)
        if match:
            return int(match.group(1))
    return None


def _extract_year(text: str) -> Optional[int]:
    """
    Extract year from OCR text, handling common OCR errors.

    Args:
        text: OCR text (mixed case)

    Returns:
        Year (1900-2099) or None if not found
    """
    # First try standard pattern
    year_match = re.search(OCR_YEAR_PATTERN, text)
    if year_match:
        return int(year_match.group(1))

    # Handle OCR errors: O → 0
    # Look for 4-character sequences that could be years with OCR errors
    # Pattern: starts with 19 or 20 (or 1O, 2O), followed by 2 more digits/O's
    cleaned_text = text.upper()

    # Match sequences like: 2OOO, 20OO, 2O00, 19OO, etc. (may or may not have word boundaries)
    potential_years = re.finditer(r"(?<![0-9])([12][09O])([0-9O]{2})(?![0-9])", cleaned_text)
    for match in potential_years:
        cleaned_year = match.group(0).replace("O", "0")
        try:
            # Check if it's a valid year range
            year_num = int(cleaned_year)
            if 1900 <= year_num <= 2099:
                return year_num
        except ValueError:
            continue

    # Also try cleaning O's systematically
    cleaned_text = re.sub(r"(?<=[12])O", "0", cleaned_text)  # 2O -> 20
    cleaned_text = re.sub(r"(?<=\d)O", "0", cleaned_text)  # 20O, 2O0, etc. -> clean all

    year_match = re.search(OCR_YEAR_PATTERN, cleaned_text)
    if year_match:
        return int(year_match.group(1))

    return None


def _extract_month(text_upper: str) -> Optional[int]:
    """
    Extract month from OCR text.

    Args:
        text_upper: Uppercase version of OCR text

    Returns:
        Month number (1-12) or None if not found
    """
    for month_name, month_num in OCR_MONTH_NAMES.items():
        if month_name in text_upper:
            return month_num
    return None


def _extract_volume(text_upper: str) -> Optional[int]:
    """
    Extract volume number from OCR text.

    Args:
        text_upper: Uppercase version of OCR text

    Returns:
        Volume number or None if not found
    """
    for pattern in OCR_VOLUME_PATTERNS:
        match = re.search(pattern, text_upper)
        if match:
            return int(match.group(1))
    return None


def _is_special_edition(text_upper_spaced: str) -> bool:
    """
    Detect if text indicates a special edition.

    Args:
        text_upper_spaced: Uppercase text with newlines replaced by spaces

    Returns:
        True if special edition indicators are found
    """
    for indicator in OCR_SPECIAL_EDITION_INDICATORS:
        if indicator in text_upper_spaced:
            return True
    return False


class OCRService:
    """Service for extracting text from images using Tesseract OCR."""

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available."""
        return OCR_AVAILABLE

    @staticmethod
    def extract_text_from_pdf_pages(
        pdf_path: str,
        max_pages: int = 2,
        dpi: int = 300,
        language: Optional[str] = None,
        confidence_threshold: int = 30,
    ) -> Dict[str, any]:
        """
        Extract text from first N pages of a PDF using PyMuPDF + Tesseract.
        Scans multiple pages because some PDFs have the cover on the second page.

        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to scan (default: 2 for cover + potential second cover)
            dpi: DPI for rendering PDF pages (default: 300 for good OCR quality)
            language: Language code for Tesseract (e.g., "eng", "fra", "deu")
            confidence_threshold: Minimum confidence score to include word (default: 30)

        Returns:
            Dictionary with OCR results per page including text, words with bounding boxes, and confidence
        """
        if not OCR_AVAILABLE:
            logger.warning("Tesseract OCR not available")
            return {"pages": [], "error": "OCR not available"}

        try:
            # Normalize language code
            lang_code = _normalize_language_code(language)

            # Open PDF
            doc = fitz.open(pdf_path)
            results = {
                "pages": [],
                "total_pages": doc.page_count,
                "scanned_pages": min(max_pages, doc.page_count),
            }

            # Process only the first N pages
            for page_num in range(min(max_pages, doc.page_count)):
                page = doc[page_num]

                # Render page to image at specified DPI
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Get structured OCR data as a dict
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang=lang_code)

                # Filter out low-confidence or empty detections
                words = []
                full_text_parts = []
                for i in range(len(data["text"])):
                    text = data["text"][i].strip()
                    conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0

                    if text and conf > confidence_threshold:
                        words.append(
                            {
                                "text": text,
                                "confidence": conf,
                                "box": {
                                    "left": data["left"][i],
                                    "top": data["top"][i],
                                    "width": data["width"][i],
                                    "height": data["height"][i],
                                },
                            }
                        )
                        full_text_parts.append(text)

                # Combine all text for this page
                page_text = " ".join(full_text_parts)

                results["pages"].append(
                    {
                        "page_number": page_num + 1,
                        "word_count": len(words),
                        "text": page_text,
                        "words": words,  # Detailed word-level data with positions
                    }
                )

                logger.debug(f"OCR extracted {len(words)} words from page {page_num + 1} of {pdf_path}")

            doc.close()

            # Combine all text from all pages
            all_text = "\n\n".join(page["text"] for page in results["pages"])
            results["full_text"] = all_text

            return results

        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path}: {e}", exc_info=True)
            return {"pages": [], "error": str(e)}

    @staticmethod
    def extract_text_from_image(
        image_path: str,
        preprocess: bool = False,
        language: Optional[str] = None,
        confidence_threshold: int = 30,
    ) -> str:
        """
        Extract text from an image file using Tesseract OCR.

        Args:
            image_path: Path to the image file
            preprocess: Deprecated parameter kept for backward compatibility
            language: Language name or code (e.g., "English", "French", "de", "es")
            confidence_threshold: Minimum confidence score to include word (default: 30)

        Returns:
            Extracted text as string
        """
        if not OCR_AVAILABLE:
            if not _ocr_config.warning_logged:
                logger.warning("Tesseract OCR not available. Install with: apt-get install tesseract-ocr")
                _ocr_config.warning_logged = True
            return ""

        try:
            # Normalize language code
            lang_code = _normalize_language_code(language)

            # Open image
            img = Image.open(image_path)

            # Get structured OCR data
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang=lang_code)

            # Filter and extract text
            text_parts = []
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0

                if text and conf > confidence_threshold:
                    text_parts.append(text)

            full_text = " ".join(text_parts)
            logger.debug(f"Tesseract extracted {len(text_parts)} words from {image_path}")
            return full_text.strip()

        except Exception as e:
            logger.error(f"Error extracting text from {image_path}: {e}")
            return ""

    @staticmethod
    def extract_metadata_from_text(text: str) -> Dict[str, any]:
        """
        Extract metadata from OCR text.

        Args:
            text: Extracted text from OCR

        Returns:
            Dictionary containing extracted metadata
        """
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
        # Create a version with newlines replaced by spaces for multi-word phrase matching
        text_upper_spaced = text_upper.replace("\n", " ")

        # Extract metadata using helper functions
        metadata["issue_number"] = _extract_issue_number(text_upper)
        metadata["year"] = _extract_year(text)
        metadata["month"] = _extract_month(text_upper)
        metadata["volume"] = _extract_volume(text_upper)
        metadata["special_edition"] = _is_special_edition(text_upper_spaced)

        return metadata

    @staticmethod
    def analyze_cover(cover_path: str, language: Optional[str] = None) -> Dict[str, any]:
        """
        Analyze a cover image or PDF using OCR to extract metadata.
        For PDFs, scans the first 2 pages (some PDFs have cover on page 2).
        For images, uses OCR directly.

        NOTE: This service is for OCR only. For direct text extraction from PDF/EPUB,
        use TextScanService.scan_document() instead.

        Args:
            cover_path: Path to the cover image or PDF
            language: Language name or code for OCR (e.g., "English", "French", "de", "es")
                     If None, defaults to English.

        Returns:
            Dictionary containing extracted metadata
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR not available, skipping cover analysis")
            return {"ocr_available": False}

        path = Path(cover_path)

        # Skip EPUB files - they are text-based and should use TextScanService
        if path.suffix.lower() == ".epub":
            logger.info(f"Skipping OCR for EPUB file (use TextScanService instead): {cover_path}")
            return {
                "ocr_available": True,
                "text_found": False,
                "used_ocr": False,
                "skipped": True,
                "reason": "EPUB files are text-based, use TextScanService.scan_document() instead",
            }

        logger.info(f"Analyzing cover with OCR: {cover_path} (language: {language or 'English'})")
        text = ""
        metadata = {}

        # For PDF, scan first 2 pages
        if path.suffix.lower() == ".pdf":
            logger.debug("Extracting text from first 2 pages of PDF using OCR")
            ocr_results = OCRService.extract_text_from_pdf_pages(
                str(path), max_pages=2, dpi=PDF_COVER_DPI_OCR, language=language
            )

            if "error" in ocr_results:
                logger.error(f"OCR failed: {ocr_results['error']}")
                return {
                    "ocr_available": True,
                    "text_found": False,
                    "used_ocr": True,
                    "error": ocr_results["error"],
                }

            # Combine text from all scanned pages
            text = ocr_results.get("full_text", "")
            metadata["extraction_method"] = "ocr_pdf_pages"
            metadata["pages_scanned"] = ocr_results.get("scanned_pages", 0)
            metadata["ocr_details"] = {
                "total_pages": ocr_results.get("total_pages", 0),
                "pages": [
                    {"page_number": p["page_number"], "word_count": p["word_count"]}
                    for p in ocr_results.get("pages", [])
                ],
            }
        else:
            # It's already an image file, use OCR directly
            logger.debug("Using OCR for text extraction on image file")
            text = OCRService.extract_text_from_image(cover_path, language=language)
            metadata["extraction_method"] = "ocr_image"

        if not text:
            logger.warning(f"No text extracted from {cover_path}")
            return {"ocr_available": True, "text_found": False, "used_ocr": True}

        logger.debug(f"Extracted text: {text[:200]}...")  # Log first 200 chars

        # Extract metadata from text
        extracted_metadata = OCRService.extract_metadata_from_text(text)
        metadata.update(extracted_metadata)
        metadata["ocr_available"] = True
        metadata["text_found"] = True
        metadata["used_ocr"] = True

        return metadata

    @staticmethod
    def _extract_lossless_cover(file_path: Path) -> Optional[Path]:
        """
        Deprecated: No longer used with PyMuPDF approach.
        Extract a lossless cover image (PNG) from PDF for OCR processing.

        Args:
            file_path: Path to PDF file

        Returns:
            Path to extracted PNG cover image, or None if failed
        """
        logger.warning("_extract_lossless_cover is deprecated with PyMuPDF approach")
        return None


# Export all public items for wildcard imports
__all__ = ["OCRService", "OCRServiceConfig"]
