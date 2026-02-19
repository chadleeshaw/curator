"""
OCR and image preprocessing constants
"""

# ==============================================================================
# OCR/Image Preprocessing Defaults
# ==============================================================================

OCR_RESIZE_WIDTH = 2000
"""Default width to resize images for OCR (pixels)"""

OCR_CONTRAST_ENHANCE = 2.0
"""Default contrast enhancement factor for OCR (float)"""

OCR_DENOISE_H = 30
"""Default denoising strength for OCR (int)"""

OCR_SHARPEN_KERNEL = [[0, -1, 0], [-1, 5, -1], [0, -1, 0]]
"""Default sharpening kernel for OCR (2D list)"""

OCR_DISABLE_ENV_VALUES = ("true", "1", "yes")
"""Environment variable values that disable OCR"""

OCR_TESSERACT_PSM = 11
"""Tesseract Page Segmentation Mode (PSM) - 11 = sparse text with no OSD (good for scattered cover elements)"""

OCR_TESSERACT_OEM = 1
"""Tesseract OCR Engine Mode (OEM) - 1 = LSTM neural network only (modern, more accurate)"""

OCR_TEXT_DETECTION_THRESHOLD = 0.5
"""PaddleOCR text detection threshold (lower = faster detection)"""

OCR_TEXT_UNCLIP_RATIO = 1.5
"""PaddleOCR text unclip ratio (smaller = less expansion)"""

OCR_ISSUE_PATTERNS = [
    r"#(\d+)",  # #123
    r"ISSUE\s+(\d+)",  # Issue 123
    r"NO\.?\s*(\d+)",  # No. 123 or No 123
    r"NUMBER\s+(\d+)",  # Number 123
]
"""Regex patterns for detecting issue numbers in OCR text"""

OCR_YEAR_PATTERN = r"(?<![0-9])(19\d{2}|20\d{2})"
"""Regex pattern for detecting year (1900-2099) in OCR text. Uses negative lookbehind to avoid matching middle of larger numbers."""

OCR_VOLUME_PATTERNS = [
    r"VOL\.?\s*(\d+)",  # Vol. 1 or Vol 1
    r"VOLUME\s+(\d+)",  # Volume 1
    r"(?<![A-Z])V\.?\s*(\d+)",
]
"""Regex patterns for detecting volume numbers in OCR text"""

OCR_MAX_VOLUME = 9999
"""Maximum reasonable volume number for periodicals (filters out zip codes, addresses, etc.)"""

OCR_SPECIAL_EDITION_INDICATORS = [
    " SPECIAL EDITION",
    " SPECIAL ISSUE",
    " LIMITED EDITION",
    " COLLECTOR EDITION",
    " COLLECTOR'S EDITION",
    " ANNIVERSARY EDITION",
    " ANNIVERSARY ISSUE",
    " EXCLUSIVE EDITION",
    " HOLIDAY EDITION",
    " HOLIDAY ISSUE",
]
"""Keywords indicating special edition in OCR text (with leading space to avoid false positives like 'non-exclusive')"""

OCR_IMAGE_MAX_DIMENSION = 1200
"""Maximum dimension (width or height) for OCR processing images in pixels"""

OCR_MAX_WORKERS = 1
"""Default number of parallel OCR processes"""

OCR_BATCH_SIZE = 5
"""Default maximum number of OCR jobs to process per batch"""

OCR_TIMEOUT_SECONDS = 300
"""Maximum time in seconds for a single OCR operation (default: 5 minutes)"""

OCR_MAX_PAGES = 2
"""Maximum number of PDF pages to scan for OCR (default: 2 - cover may be on page 2)"""

PDF_COVER_DPI_OCR = 200
"""DPI for OCR text extraction (~1511x1956 for 8.5x11"). Benchmarked at 200 vs 300 DPI — identical
accuracy on tested fixtures with ~45% faster Tesseract processing. 300 DPI baseline saved in"""

PNG_GENERATION_TIMEOUT = 30
"""Timeout in seconds for PDF-to-PNG conversion (poppler can hang on corrupted PDFs)"""

PDF_TEXT_SCAN_TIMEOUT = 3
"""Timeout in seconds for direct PDF text extraction (pypdf can hang on corrupted PDFs)"""
