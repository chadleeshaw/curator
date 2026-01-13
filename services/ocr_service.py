"""OCR service for extracting text from cover art images."""

import logging
import signal
import warnings
from pathlib import Path
from typing import Optional, Dict
import re

from PIL import Image

# Suppress various warnings from PaddleOCR and dependencies
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Increase Pillow's decompression bomb limit for high-res images (300 DPI)
# Default is ~89 MP, we need ~130 MP for magazine covers at 300 DPI
Image.MAX_IMAGE_PIXELS = 200000000  # 200 megapixels

logger = logging.getLogger(__name__)

# Global flag to track if PaddleOCR had a fatal CPU compatibility error
_PADDLEOCR_CPU_INCOMPATIBLE = False


def _sigill_handler(signum, frame):
    """Handle SIGILL to prevent container crashes from CPU incompatibility."""
    global _PADDLEOCR_CPU_INCOMPATIBLE
    logger.error("SIGILL (Illegal Instruction) detected - CPU does not support PaddleOCR requirements")
    logger.error("CPU lacks AVX/AVX2/AVX512 instruction sets required by PaddleOCR")
    logger.error("OCR functionality will be disabled")
    _PADDLEOCR_CPU_INCOMPATIBLE = True
    # Raise an exception instead of crashing
    raise RuntimeError("CPU instruction set incompatible with PaddleOCR (SIGILL)")


# Install SIGILL handler before importing PaddleOCR
signal.signal(signal.SIGILL, _sigill_handler)

try:
    from paddleocr import PaddleOCR

    OCR_AVAILABLE = True
    # Cache for PaddleOCR instances by language
    _paddleocr_cache = {}  # {lang_code: PaddleOCR instance}
except (ImportError, OSError, RuntimeError, Exception) as e:
    logger.warning(f"PaddleOCR not available: {e}")
    OCR_AVAILABLE = False
    _paddleocr_cache = {}

# Mapping from common language names to PaddleOCR language codes
LANGUAGE_TO_PADDLEOCR = {
    "english": "en",
    "en": "en",
    "french": "fr",
    "fr": "fr",
    "german": "german",
    "de": "german",
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
    "japanese": "japan",
    "ja": "japan",
    "korean": "korean",
    "ko": "korean",
    "arabic": "ar",
    "ar": "ar",
    "latin": "latin",
    "la": "latin",
}


def _get_paddleocr_reader(language: Optional[str] = None):
    """
    Get or create PaddleOCR instance for specified language.
    Instances are cached to avoid reloading models.

    Args:
        language: Language name or code (e.g., "English", "en", "French", "fr")
                If None or not recognized, defaults to English.

    Returns:
        PaddleOCR instance or None if not available
    """
    global _PADDLEOCR_CPU_INCOMPATIBLE

    if not OCR_AVAILABLE or _PADDLEOCR_CPU_INCOMPATIBLE:
        return None

    # Normalize language to PaddleOCR code
    if language:
        lang_code = LANGUAGE_TO_PADDLEOCR.get(language.lower(), "en")
    else:
        lang_code = "en"

    # Return cached instance if available
    if lang_code in _paddleocr_cache:
        return _paddleocr_cache[lang_code]

    # Create new instance
    try:
        logger.info(f"Initializing PaddleOCR for language: {lang_code}")
        # PaddleOCR parameters optimized for performance
        # GPU is controlled via environment variable USE_GPU=False
        ocr = PaddleOCR(
            use_textline_orientation=False,  # Disable for faster processing
            lang=lang_code,
            text_det_box_thresh=0.5,  # Lower threshold for faster detection
            text_det_unclip_ratio=1.5,  # Smaller ratio for less expansion
        )
        _paddleocr_cache[lang_code] = ocr
        return ocr
    except (RuntimeError, OSError, SystemError) as e:
        error_msg = str(e).lower()
        # Check for CPU instruction errors (SIGILL indicators)
        if "illegal instruction" in error_msg or "sigill" in error_msg or "avx" in error_msg:
            logger.error(f"PaddleOCR CPU incompatibility detected: {e}")
            logger.error("CPU does not support required instruction sets (AVX/AVX2/AVX512)")
            logger.error("OCR functionality will be disabled to prevent crashes")
            _PADDLEOCR_CPU_INCOMPATIBLE = True
            return None

        logger.error(f"Failed to initialize PaddleOCR for language {lang_code}: {e}")
        logger.error("This may be due to CPU instruction set incompatibility (e.g., AVX/AVX2 requirements)")
        # Fallback to English
        if lang_code != "en":
            logger.info("Falling back to English OCR")
            return _get_paddleocr_reader("en")
        return None
    except Exception as e:
        logger.error(f"Unexpected error initializing PaddleOCR for language {lang_code}: {e}", exc_info=True)
        # Fallback to English
        if lang_code != "en":
            logger.info("Falling back to English OCR")
            return _get_paddleocr_reader("en")
        return None


# Track if we've already warned about PaddleOCR not being installed
_OCR_WARNING_LOGGED = False


class OCRService:
    """Service for extracting text from images using OCR."""

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available and CPU compatible."""
        return OCR_AVAILABLE and not _PADDLEOCR_CPU_INCOMPATIBLE

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
            global _OCR_WARNING_LOGGED
            if not _OCR_WARNING_LOGGED:
                logger.warning("PaddleOCR not available. Install with: pip install paddleocr")
                _OCR_WARNING_LOGGED = True
            return ""

        try:
            ocr = _get_paddleocr_reader(language)
            if ocr is None:
                return ""

            # Run OCR on the image - wrap in try/catch for runtime errors
            try:
                result = ocr.predict(image_path)
            except (RuntimeError, OSError, SystemError) as e:
                logger.error(f"PaddleOCR prediction failed (possible CPU instruction incompatibility): {e}")
                logger.warning("Consider installing a CPU-compatible version or using Docker with proper architecture")
                return ""

            # PaddleOCR predict() returns a list of OCRResult objects
            # Each result has a 'rec_texts' field containing the detected text
            if not result:
                logger.debug(f"No text detected in image: {image_path}")
                return ""

            # Extract text from results
            text_parts = []

            # Handle PaddleOCR result format
            if isinstance(result, list) and len(result) > 0:
                for item in result:
                    # Check if it has rec_texts attribute or key
                    if hasattr(item, 'rec_texts'):
                        texts = item.rec_texts
                        if isinstance(texts, list):
                            text_parts.extend(texts)
                    elif isinstance(item, dict) and 'rec_texts' in item:
                        texts = item['rec_texts']
                        if isinstance(texts, list):
                            text_parts.extend(texts)

            full_text = "\n".join(str(t) for t in text_parts if t)
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
    def analyze_cover(cover_path: str, language: Optional[str] = None) -> Dict[str, any]:
        """
        Analyze a cover image, PDF, or EPUB using OCR to extract metadata.
        For PDFs/EPUBs, extracts a lossless cover image first, then applies OCR.
        For images, uses OCR directly.

        NOTE: This service is for OCR only. For direct text extraction from PDF/EPUB,
        use TextScanService.scan_document() instead.

        Args:
            cover_path: Path to the cover image, PDF, or EPUB
            language: Language name or code for OCR (e.g., "English", "French", "de", "es")
                     If None, defaults to English.

        Returns:
            Dictionary containing extracted metadata
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR not available, skipping cover analysis")
            return {"ocr_available": False}

        logger.info(f"Analyzing cover with OCR: {cover_path} (language: {language or 'English'})")
        path = Path(cover_path)
        text = ""
        metadata = {}

        # For PDF, extract a lossless cover image first
        if path.suffix.lower() == ".pdf":
            logger.debug("Extracting lossless cover image for OCR")
            cover_image_path = OCRService._extract_lossless_cover(path)
            if cover_image_path:
                logger.debug(f"Using OCR on lossless cover image: {cover_image_path}")
                text = OCRService.extract_text_from_image(str(cover_image_path), language=language)
                metadata["extraction_method"] = "ocr_image"
                # Clean up temporary cover image
                try:
                    cover_image_path.unlink()
                except Exception as e:
                    logger.debug(f"Could not delete temporary cover image: {e}")
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
        metadata = OCRService.extract_metadata_from_text(text)
        metadata["ocr_available"] = True
        metadata["text_found"] = True
        metadata["used_ocr"] = True

        return metadata

    @staticmethod
    def _extract_lossless_cover(file_path: Path) -> Optional[Path]:
        """
        Extract a lossless cover image (PNG) from PDF for OCR processing.

        Args:
            file_path: Path to PDF file

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

            logger.warning(f"Could not extract lossless cover from {file_path}")
            return None

        except Exception as e:
            logger.error(f"Error extracting lossless cover from {file_path}: {e}")
            return None
