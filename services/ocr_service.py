"""OCR service for extracting text from cover art images."""
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import re

try:
    import pytesseract
    from PIL import Image
    import cv2  # pylint: disable=import-error
    import numpy as np
    OCR_AVAILABLE = True

    # Increase Pillow's decompression bomb limit for high-res images (300 DPI)
    # Default is ~89 MP, we need ~130 MP for magazine covers at 300 DPI
    Image.MAX_IMAGE_PIXELS = 200000000  # 200 megapixels
except ImportError:
    OCR_AVAILABLE = False
    np = None  # type: ignore

try:
    from pypdf import PdfReader
    PDF_TEXT_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_TEXT_AVAILABLE = True
    except ImportError:
        PDF_TEXT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Track if we've already warned about Tesseract not being installed
_TESSERACT_WARNING_LOGGED = False


class OCRService:
    """Service for extracting text from images using OCR."""

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available."""
        return OCR_AVAILABLE

    @staticmethod
    def preprocess_image(image_path: str) -> Optional[Any]:
        """
        Preprocess image for better OCR results.

        Args:
            image_path: Path to the image file

        Returns:
            Preprocessed image as numpy array, or None if failed
        """
        try:
            # Read image
            img = cv2.imread(image_path)  # pylint: disable=no-member
            if img is None:
                logger.error(f"Failed to read image: {image_path}")
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # pylint: disable=no-member

            # Apply adaptive thresholding to improve text detection
            thresh = cv2.adaptiveThreshold(  # pylint: disable=no-member
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # pylint: disable=no-member
                cv2.THRESH_BINARY, 11, 2  # pylint: disable=no-member
            )

            # Denoise
            denoised = cv2.fastNlMeansDenoising(thresh)  # pylint: disable=no-member

            return denoised
        except Exception as e:
            logger.error(f"Error preprocessing image {image_path}: {e}")
            return None

    @staticmethod
    def extract_text_from_image(image_path: str, preprocess: bool = True) -> str:
        """
        Extract text from an image file.

        Args:
            image_path: Path to the image file
            preprocess: Whether to preprocess the image for better OCR

        Returns:
            Extracted text as string
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR libraries not available")
            return ""

        try:
            if preprocess:
                # Use preprocessed image
                img_array = OCRService.preprocess_image(image_path)
                if img_array is None:
                    return ""

                # Convert numpy array to PIL Image
                img = Image.fromarray(img_array)
            else:
                # Use original image
                img = Image.open(image_path)

            # Extract text using Tesseract
            try:
                text = pytesseract.image_to_string(img, config='--psm 6')
                return text.strip()
            except pytesseract.TesseractNotFoundError:
                global _TESSERACT_WARNING_LOGGED
                if not _TESSERACT_WARNING_LOGGED:
                    logger.error(
                        "Tesseract OCR engine not found. Please install tesseract: "
                        "brew install tesseract (macOS), apt-get install tesseract-ocr (Ubuntu), "
                        "or download from https://github.com/tesseract-ocr/tesseract"
                    )
                    _TESSERACT_WARNING_LOGGED = True
                return ""
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
            'issue_number': None,
            'year': None,
            'month': None,
            'volume': None,
            'special_edition': False,
            'detected_text': text
        }

        # Clean up text
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        text_upper = text.upper()

        # Detect issue number patterns
        issue_patterns = [
            r'#(\d+)',  # #123
            r'ISSUE\s+(\d+)',  # Issue 123
            r'NO\.?\s*(\d+)',  # No. 123 or No 123
            r'NUMBER\s+(\d+)',  # Number 123
        ]

        for pattern in issue_patterns:
            match = re.search(pattern, text_upper)
            if match:
                metadata['issue_number'] = int(match.group(1))
                break

        # Detect year (4-digit number between 1900-2099)
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        if year_match:
            metadata['year'] = int(year_match.group(1))

        # Detect month names
        months = {
            'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4,
            'MAY': 5, 'JUNE': 6, 'JULY': 7, 'AUGUST': 8,
            'SEPTEMBER': 9, 'OCTOBER': 10, 'NOVEMBER': 11, 'DECEMBER': 12,
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
            'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'SEPT': 9,
            'OCT': 10, 'NOV': 11, 'DEC': 12
        }

        for month_name, month_num in months.items():
            if month_name in text_upper:
                metadata['month'] = month_num
                break

        # Detect volume
        volume_patterns = [
            r'VOL\.?\s*(\d+)',  # Vol. 1 or Vol 1
            r'VOLUME\s+(\d+)',  # Volume 1
            r'V\.?\s*(\d+)',  # V. 1 or V 1
        ]

        for pattern in volume_patterns:
            match = re.search(pattern, text_upper)
            if match:
                metadata['volume'] = int(match.group(1))
                break

        # Detect special edition indicators
        special_indicators = [
            'SPECIAL EDITION', 'SPECIAL ISSUE', 'LIMITED EDITION',
            'COLLECTOR', 'ANNIVERSARY', 'EXCLUSIVE'
        ]

        for indicator in special_indicators:
            if indicator in text_upper:
                metadata['special_edition'] = True
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
    def analyze_cover(cover_path: str) -> Dict[str, any]:
        """
        Analyze a cover image, PDF, or EPUB and extract metadata.
        For PDFs/EPUBs, tries direct text extraction first (faster), falls back to OCR.
        For images, uses OCR.

        Args:
            cover_path: Path to the cover image, PDF, or EPUB

        Returns:
            Dictionary containing extracted metadata
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR not available, skipping cover analysis")
            return {'ocr_available': False}

        logger.info(f"Analyzing cover: {cover_path}")
        path = Path(cover_path)
        text = ""

        # Try direct PDF text extraction first (much faster)
        if path.suffix.lower() == '.pdf' and PDF_TEXT_AVAILABLE:
            logger.debug("Attempting direct PDF text extraction")
            text = OCRService.extract_text_from_pdf(cover_path, max_pages=1)
            if text:
                logger.info("Successfully extracted text from PDF without OCR")

        # Try direct EPUB text extraction
        elif path.suffix.lower() == '.epub':
            logger.debug("Attempting direct EPUB text extraction")
            from core.epub_utils import extract_text_from_epub
            text = extract_text_from_epub(path, max_items=2)
            if text:
                logger.info("Successfully extracted text from EPUB without OCR")

        # Fall back to OCR if no text found or if it's an image
        if not text:
            logger.debug("Using OCR for text extraction")
            text = OCRService.extract_text_from_image(cover_path)

        if not text:
            logger.warning(f"No text extracted from {cover_path}")
            return {'ocr_available': True, 'text_found': False}

        logger.debug(f"Extracted text: {text[:200]}...")  # Log first 200 chars

        # Extract metadata from text
        metadata = OCRService.extract_metadata_from_text(text)

        if not text:
            logger.warning(f"No text extracted from {cover_path}")
            return {'ocr_available': True, 'text_found': False}

        logger.debug(f"Extracted text: {text[:200]}...")  # Log first 200 chars

        # Extract metadata from text
        metadata = OCRService.extract_metadata_from_text(text)
        metadata['ocr_available'] = True
        metadata['text_found'] = True

        return metadata
