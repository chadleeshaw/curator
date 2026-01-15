"""OCR service for extracting text from cover art images."""

import logging
import os
import signal
import warnings
from pathlib import Path
from typing import Optional, Dict
import re

from PIL import Image

from core.constants import (
    MAX_IMAGE_PIXELS,
    OCR_DISABLE_ENV_VALUES,
    OCR_TEXT_DETECTION_THRESHOLD,
    OCR_TEXT_UNCLIP_RATIO,
    OCR_ISSUE_PATTERNS,
    OCR_YEAR_PATTERN,
    OCR_MONTH_NAMES,
    OCR_VOLUME_PATTERNS,
    OCR_SPECIAL_EDITION_INDICATORS,
    LANGUAGE_TO_PADDLEOCR,
    OCR_MIN_MEMORY_MB,
    PDF_COVER_DPI_OCR,
)

# Suppress various warnings from PaddleOCR and dependencies
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Increase Pillow's decompression bomb limit for high-res images
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

logger = logging.getLogger(__name__)


class OCRServiceConfig:
    """Manages OCR service state and configuration."""

    def __init__(self):
        self.cpu_incompatible = False
        self.ocr_disabled = self._check_ocr_disabled()
        self.paddleocr_cache = {}
        self.warning_logged = False

    @staticmethod
    def _check_ocr_disabled():
        """Check if OCR is disabled via environment variable."""
        disabled = os.environ.get('DISABLE_OCR', '').lower() in OCR_DISABLE_ENV_VALUES
        if disabled:
            logger.info("OCR is disabled via DISABLE_OCR environment variable")
        return disabled


# Global configuration instance
_ocr_config = OCRServiceConfig()


def _sigill_handler(signum, frame):
    """Handle SIGILL to prevent container crashes from CPU incompatibility."""
    logger.error("SIGILL (Illegal Instruction) detected - CPU does not support PaddleOCR requirements")
    logger.error("CPU lacks AVX/AVX2/AVX512 instruction sets required by PaddleOCR")
    logger.error("OCR functionality will be disabled")
    _ocr_config.cpu_incompatible = True
    raise RuntimeError("CPU instruction set incompatible with PaddleOCR (SIGILL)")


# Install SIGILL handler before importing PaddleOCR
signal.signal(signal.SIGILL, _sigill_handler)

# Only import PaddleOCR if not explicitly disabled
if not _ocr_config.ocr_disabled:
    try:
        from paddleocr import PaddleOCR

        OCR_AVAILABLE = True
    except (ImportError, OSError, RuntimeError, Exception) as e:
        logger.warning(f"PaddleOCR not available: {e}")
        OCR_AVAILABLE = False
        PaddleOCR = None  # type: ignore
else:
    OCR_AVAILABLE = False
    PaddleOCR = None  # type: ignore


def _log_paddleocr_error(lang_code: str, error: Exception) -> None:
    """
    Log PaddleOCR initialization error with CPU compatibility information.

    This helper provides consistent error logging for PaddleOCR initialization
    failures, including guidance on potential CPU instruction set issues.

    Args:
        lang_code: PaddleOCR language code that failed to initialize
        error: Exception that occurred during initialization
    """
    logger.error(f"Failed to initialize PaddleOCR for language {lang_code}: {error}")
    logger.error("This may be due to CPU instruction set incompatibility (e.g., AVX/AVX2 requirements)")


def _check_memory_available() -> bool:
    """
    Check if sufficient memory is available for PaddleOCR initialization.

    PaddleOCR requires significant memory (~4GB) to load models. This function
    checks system memory before attempting initialization to prevent OOM crashes.
    If psutil is not available or memory check fails, returns True to allow
    initialization attempt (fail-safe behavior).

    Returns:
        True if sufficient memory is available or cannot be checked (fail-safe).
        False if insufficient memory detected, OCR will be disabled.

    Note:
        Sets _ocr_config.cpu_incompatible = True when insufficient memory detected
        to prevent future initialization attempts.
    """
    try:
        import psutil
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        if available_mb < OCR_MIN_MEMORY_MB:
            logger.error(
                f"Insufficient memory for PaddleOCR: {available_mb:.0f}MB available, "
                f"need ~{OCR_MIN_MEMORY_MB}MB"
            )
            logger.error("OCR functionality will be disabled to prevent OOM crashes")
            _ocr_config.cpu_incompatible = True
            return False
        logger.debug(f"Available memory: {available_mb:.0f}MB - sufficient for PaddleOCR")
        return True
    except ImportError:
        logger.warning("psutil not available - cannot check memory before PaddleOCR initialization")
        return True
    except Exception as e:
        logger.warning(f"Could not check available memory: {e}")
        return True


def _normalize_language_code(language: Optional[str]) -> str:
    """
    Normalize language name or code to PaddleOCR language code.

    Args:
        language: Language name or code (e.g., "English", "en", "French", "fr")

    Returns:
        PaddleOCR language code (e.g., "en", "fr", "german")
    """
    if language:
        return LANGUAGE_TO_PADDLEOCR.get(language.lower(), "en")
    return "en"


def _create_paddleocr_instance(lang_code: str):
    """
    Create a new PaddleOCR instance for the specified language.

    Attempts to initialize PaddleOCR with optimized parameters for performance.
    If initialization fails due to CPU incompatibility (SIGILL/AVX errors),
    disables OCR functionality. For other errors, attempts fallback to English.

    Args:
        lang_code: PaddleOCR language code (e.g., "en", "fr", "german")

    Returns:
        PaddleOCR instance if successful, None if initialization fails

    Note:
        - Caches successful instances in _ocr_config.paddleocr_cache
        - Sets _ocr_config.cpu_incompatible = True on CPU instruction errors
        - Recursively calls _get_paddleocr_reader("en") for fallback
    """
    try:
        logger.info(f"Initializing PaddleOCR for language: {lang_code}")
        # PaddleOCR parameters optimized for performance
        # GPU is controlled via environment variable USE_GPU=False
        ocr = PaddleOCR(
            use_textline_orientation=False,  # Disable for faster processing
            lang=lang_code,
            text_det_box_thresh=OCR_TEXT_DETECTION_THRESHOLD,
            text_det_unclip_ratio=OCR_TEXT_UNCLIP_RATIO,
        )
        _ocr_config.paddleocr_cache[lang_code] = ocr
        return ocr
    except (RuntimeError, OSError, SystemError) as e:
        error_msg = str(e).lower()
        # Check for CPU instruction errors (SIGILL indicators)
        # PaddleOCR requires AVX/AVX2 instruction sets; older CPUs may not support these
        if "illegal instruction" in error_msg or "sigill" in error_msg or "avx" in error_msg:
            logger.error(f"PaddleOCR CPU incompatibility detected: {e}")
            logger.error("CPU does not support required instruction sets (AVX/AVX2/AVX512)")
            logger.error("OCR functionality will be disabled to prevent crashes")
            _ocr_config.cpu_incompatible = True
            return None

        _log_paddleocr_error(lang_code, e)
        # Try English as fallback - many language packs may fail but English is usually available
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
    if not OCR_AVAILABLE or _ocr_config.cpu_incompatible:
        return None

    # Normalize language to PaddleOCR code
    lang_code = _normalize_language_code(language)

    # Return cached instance if available
    if lang_code in _ocr_config.paddleocr_cache:
        return _ocr_config.paddleocr_cache[lang_code]

    # Check available memory before initializing
    if not _check_memory_available():
        return None

    # Create new instance
    return _create_paddleocr_instance(lang_code)


def _parse_paddle_ocr_results(result) -> list:
    """
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
        if hasattr(item, 'rec_texts'):
            texts = item.rec_texts
        elif isinstance(item, dict) and 'rec_texts' in item:
            texts = item['rec_texts']

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
    potential_years = re.finditer(r'(?<![0-9])([12][09O])([0-9O]{2})(?![0-9])', cleaned_text)
    for match in potential_years:
        cleaned_year = match.group(0).replace('O', '0')
        try:
            # Check if it's a valid year range
            year_num = int(cleaned_year)
            if 1900 <= year_num <= 2099:
                return year_num
        except ValueError:
            continue

    # Also try cleaning O's systematically
    cleaned_text = re.sub(r'(?<=[12])O', '0', cleaned_text)  # 2O -> 20
    cleaned_text = re.sub(r'(?<=\d)O', '0', cleaned_text)  # 20O, 2O0, etc. -> clean all

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
    """Service for extracting text from images using OCR."""

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available and CPU compatible."""
        return OCR_AVAILABLE and not _ocr_config.cpu_incompatible

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
            if not _ocr_config.warning_logged:
                logger.warning("PaddleOCR not available. Install with: pip install paddleocr")
                _ocr_config.warning_logged = True
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
            if not result:
                logger.debug(f"No text detected in image: {image_path}")
                return ""

            # Extract text from results
            text_parts = _parse_paddle_ocr_results(result)
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
        # Create a version with newlines replaced by spaces for multi-word phrase matching
        text_upper_spaced = text_upper.replace('\n', ' ')

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
            temp_dir = file_path.parent / ".ocr_temp"
            temp_dir.mkdir(exist_ok=True)
            cover_path = temp_dir / f"{file_path.stem}_ocr.png"

            if file_path.suffix.lower() == ".pdf":
                from pdf2image import convert_from_path

                # Extract at high DPI for OCR
                images = convert_from_path(
                    str(file_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_OCR, fmt="png"
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
