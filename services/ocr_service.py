"""OCR service for extracting text from cover art images."""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import re

from PIL import Image

# Increase Pillow's decompression bomb limit for high-res images (300 DPI)
# Default is ~89 MP, we need ~130 MP for magazine covers at 300 DPI
Image.MAX_IMAGE_PIXELS = 200000000  # 200 megapixels

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR

    OCR_AVAILABLE = True
    # Cache for PaddleOCR instances by language
    _paddle_ocr_cache = {}  # {lang_code: PaddleOCR instance}
except ImportError:
    OCR_AVAILABLE = False
    _paddle_ocr_cache = {}

try:
    from pypdf import PdfReader

    PDF_TEXT_AVAILABLE = True
except ImportError:
    PDF_TEXT_AVAILABLE = False
    logger.debug("pypdf not available for PDF text extraction")

# Mapping from common language names to PaddleOCR language codes
LANGUAGE_TO_PADDLE = {
    "english": "en",
    "en": "en",
    "french": "fr",
    "fr": "fr",
    "german": "de",
    "de": "de",
    "spanish": "es",
    "es": "es",
    "italian": "it",
    "it": "it",
    "portuguese": "pt",
    "pt": "pt",
    "russian": "ru",
    "ru": "ru",
    "chinese": "ch",
    "ch": "ch",
    "zh": "ch",
    "japanese": "ja",
    "ja": "ja",
    "korean": "ko",
    "ko": "ko",
    "arabic": "arabic",
    "ar": "arabic",
    "latin": "latin",
    "la": "latin",
}


def _get_paddle_ocr(language: Optional[str] = None):
    """
    Get or create PaddleOCR instance for specified language.
    Instances are cached to avoid reloading models.

    Args:
        language: Language name or code (e.g., "English", "en", "French", "fr")
                 If None or not recognized, defaults to English.

    Returns:
        PaddleOCR instance or None if not available
    """
    if not OCR_AVAILABLE:
        return None

    # Normalize language to PaddleOCR code
    if language:
        lang_code = LANGUAGE_TO_PADDLE.get(language.lower(), "en")
    else:
        lang_code = "en"

    # Return cached instance if available
    if lang_code in _paddle_ocr_cache:
        return _paddle_ocr_cache[lang_code]

    # Create new instance
    try:
        logger.info(f"Initializing PaddleOCR for language: {lang_code}")
        ocr = PaddleOCR(
            use_angle_cls=True,  # Enable text angle classification
            lang=lang_code,  # Language code
            show_log=False,  # Reduce verbosity
            use_gpu=False,  # Use CPU by default (can be configured later)
        )
        _paddle_ocr_cache[lang_code] = ocr
        return ocr
    except Exception as e:
        logger.error(f"Failed to initialize PaddleOCR for language {lang_code}: {e}")
        # Fallback to English
        if lang_code != "en":
            logger.info("Falling back to English OCR")
            return _get_paddle_ocr("en")
        return None


# Track if we've already warned about PaddleOCR not being installed
_PADDLEOCR_WARNING_LOGGED = False


class OCRService:
    """Service for extracting text from images using OCR."""

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available."""
        return OCR_AVAILABLE

    @staticmethod
    def extract_text_from_image(image_path: str, preprocess: bool = False, language: Optional[str] = None) -> str:
        """
        Extract text from an image file using PaddleOCR.

        Args:
            image_path: Path to the image file (preferably PNG or TIFF for lossless quality)
            preprocess: Deprecated parameter kept for backward compatibility, not used with PaddleOCR
            language: Language name or code (e.g., "English", "French", "de", "es")
                     If None, defaults to English

        Returns:
            Extracted text as string
        """
        if not OCR_AVAILABLE:
            global _PADDLEOCR_WARNING_LOGGED
            if not _PADDLEOCR_WARNING_LOGGED:
                logger.warning("PaddleOCR not available. Install with: pip install paddleocr paddlepaddle")
                _PADDLEOCR_WARNING_LOGGED = True
            return ""

        try:
            ocr = _get_paddle_ocr(language)
            if ocr is None:
                return ""

            # Run OCR on the image
            result = ocr.ocr(image_path, cls=True)

            if not result or not result[0]:
                logger.debug(f"No text detected in image: {image_path}")
                return ""

            # Extract text from results
            # PaddleOCR returns: [[[bbox], (text, confidence)], ...]
            text_parts = []
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0] if isinstance(line[1], tuple) else line[1]
                    text_parts.append(text)

            full_text = "\n".join(text_parts)
            logger.debug(f"PaddleOCR extracted {len(text_parts)} text lines from {image_path}")
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
        text_lines = [line.strip() for line in text.split("\n") if line.strip()]
        text_upper = text.upper()

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
        special_indicators = [
            "SPECIAL EDITION",
            "SPECIAL ISSUE",
            "LIMITED EDITION",
            "COLLECTOR",
            "ANNIVERSARY",
            "EXCLUSIVE",
        ]

        for indicator in special_indicators:
            if indicator in text_upper:
                metadata["special_edition"] = True
                break

        return metadata

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
            logger.debug("PyPDF2 not available for PDF text extraction")
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
    def analyze_cover(cover_path: str, language: Optional[str] = None) -> Dict[str, any]:
        """
        Analyze a cover image, PDF, or EPUB and extract metadata.
        For PDFs/EPUBs, tries direct text extraction first (faster).
        If text extraction doesn't yield sufficient metadata (year/month/volume),
        falls back to OCR on a lossless image extraction.
        For images, uses OCR directly.

        Args:
            cover_path: Path to the cover image, PDF, or EPUB
            language: Language name or code for OCR (e.g., "English", "French", "de", "es")
                     If None, defaults to English. Used when falling back to OCR.

        Returns:
            Dictionary containing extracted metadata
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR not available, skipping cover analysis")
            return {"ocr_available": False}

        logger.info(f"Analyzing cover: {cover_path} (language: {language or 'English'})")
        path = Path(cover_path)
        text = ""
        metadata = {}
        used_ocr = False

        # Try direct PDF text extraction first (much faster)
        if path.suffix.lower() == ".pdf" and PDF_TEXT_AVAILABLE:
            logger.debug("Attempting direct PDF text extraction")
            text = OCRService.extract_text_from_pdf(cover_path, max_pages=1)
            if text:
                logger.info("Successfully extracted text from PDF without OCR")
                metadata = OCRService.extract_metadata_from_text(text)

                # Check if we have sufficient metadata
                if not OCRService._has_sufficient_metadata(metadata):
                    logger.info("PDF text extraction didn't yield sufficient metadata, will try OCR on lossless image")
                    text = ""  # Clear text to trigger OCR fallback

        # Try direct EPUB text extraction
        elif path.suffix.lower() == ".epub":
            logger.debug("Attempting direct EPUB text extraction")
            from core.epub_utils import extract_text_from_epub

            text = extract_text_from_epub(path, max_items=2)
            if text:
                logger.info("Successfully extracted text from EPUB without OCR")
                metadata = OCRService.extract_metadata_from_text(text)

                # Check if we have sufficient metadata
                if not OCRService._has_sufficient_metadata(metadata):
                    logger.info("EPUB text extraction didn't yield sufficient metadata, will try OCR on lossless image")
                    text = ""  # Clear text to trigger OCR fallback

        # Fall back to OCR if:
        # 1. No text was extracted, or
        # 2. Text was extracted but didn't have sufficient metadata (year/month/volume)
        # 3. It's an image file
        if not text:
            # For PDF/EPUB, we need to extract a lossless cover image first
            if path.suffix.lower() in [".pdf", ".epub"]:
                logger.debug("Extracting lossless cover image for OCR")
                cover_image_path = OCRService._extract_lossless_cover(path)
                if cover_image_path:
                    logger.debug(f"Using OCR on lossless cover image: {cover_image_path}")
                    text = OCRService.extract_text_from_image(str(cover_image_path), language=language)
                    used_ocr = True
                    # Clean up temporary cover image
                    try:
                        cover_image_path.unlink()
                    except Exception as e:
                        logger.debug(f"Could not delete temporary cover image: {e}")
            else:
                # It's already an image file, use OCR directly
                logger.debug("Using OCR for text extraction on image file")
                text = OCRService.extract_text_from_image(cover_path, language=language)
                used_ocr = True

        if not text:
            logger.warning(f"No text extracted from {cover_path}")
            return {"ocr_available": True, "text_found": False, "used_ocr": used_ocr}

        logger.debug(f"Extracted text: {text[:200]}...")  # Log first 200 chars

        # Extract metadata from text (if not already done)
        if not metadata or not OCRService._has_sufficient_metadata(metadata):
            metadata = OCRService.extract_metadata_from_text(text)

        metadata["ocr_available"] = True
        metadata["text_found"] = True
        metadata["used_ocr"] = used_ocr

        return metadata

    @staticmethod
    def _extract_lossless_cover(file_path: Path) -> Optional[Path]:
        """
        Extract a lossless cover image (PNG) from PDF or EPUB for OCR processing.

        Args:
            file_path: Path to PDF or EPUB file

        Returns:
            Path to extracted PNG cover image, or None if failed
        """
        try:
            from core.constants import PDF_COVER_DPI_OCR

            temp_dir = file_path.parent / ".ocr_temp"
            temp_dir.mkdir(exist_ok=True)
            cover_path = temp_dir / f"{file_path.stem}_ocr.png"

            if file_path.suffix.lower() == ".pdf":
                from pdf2image import convert_from_path

                # Extract at high DPI for OCR
                images = convert_from_path(
                    str(file_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_OCR, fmt="png"  # Use PNG format
                )
                if images:
                    images[0].save(str(cover_path), "PNG")
                    logger.debug(f"Extracted lossless PDF cover at {PDF_COVER_DPI_OCR} DPI: {cover_path}")
                    return cover_path

            elif file_path.suffix.lower() == ".epub":
                from ebooklib import epub
                from io import BytesIO

                book = epub.read_epub(str(file_path))
                cover_item = None

                # Try multiple methods to find cover
                for item in book.get_items():
                    if item.get_type() == 9:  # ITEM_COVER
                        cover_item = item
                        break

                if not cover_item:
                    for item in book.get_items():
                        if item.media_type and item.media_type.startswith("image/"):
                            if "cover" in item.get_name().lower():
                                cover_item = item
                                break

                if not cover_item:
                    for item in book.get_items():
                        if item.media_type and item.media_type.startswith("image/"):
                            cover_item = item
                            break

                if cover_item:
                    cover_data = cover_item.get_content()
                    img = Image.open(BytesIO(cover_data))

                    # Convert to RGB if needed
                    if img.mode in ("RGBA", "LA", "P"):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                        img = background

                    img.save(str(cover_path), "PNG")
                    logger.debug(f"Extracted lossless EPUB cover: {cover_path}")
                    return cover_path

            logger.warning(f"Could not extract lossless cover from {file_path}")
            return None

        except Exception as e:
            logger.error(f"Error extracting lossless cover from {file_path}: {e}")
            return None
