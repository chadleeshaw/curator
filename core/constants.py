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

MAX_IMAGE_PIXELS = 200000000
"""Maximum image pixels for Pillow decompression (200 megapixels)"""

OCR_DISABLE_ENV_VALUES = ('true', '1', 'yes')
"""Environment variable values that disable OCR"""

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
    r"V\.?\s*(\d+)",  # V. 1 or V 1
]
"""Regex patterns for detecting volume numbers in OCR text"""

OCR_MONTH_NAMES = {
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
"""Month name to number mapping for OCR metadata extraction"""

MONTH_TO_NUMBER = {
    # Full month names
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    # Abbreviations
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    # Seasons
    'spring': 3, 'summer': 6, 'fall': 9, 'autumn': 9, 'winter': 12
}
"""Month/period name to number mapping for date parsing (case-insensitive)"""

NUMBER_TO_MONTH = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}
"""Month number to full English month name mapping"""

NUMBER_TO_MONTH_ABBR = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
}
"""Month number to abbreviated English month name mapping"""

OCR_SPECIAL_EDITION_INDICATORS = [
    "SPECIAL EDITION",
    "SPECIAL ISSUE",
    "LIMITED EDITION",
    "COLLECTOR",
    "ANNIVERSARY",
    "EXCLUSIVE",
    "HOLIDAY",
]
"""Keywords indicating special edition in OCR text"""

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
"""Mapping from language names/codes to PaddleOCR language codes"""

# ==============================================================================
# Application Constants
# ==============================================================================

DEFAULT_LANGUAGE = "English"
"""Default language for periodicals when none is detected"""

# ==============================================================================
# Matching and Deduplication
# ==============================================================================

DEFAULT_FUZZY_THRESHOLD = 80

TITLE_MATCH_THRESHOLD = 85
"""Higher threshold for strict title matching"""


# ==============================================================================
# File Processing
# ==============================================================================

PDF_COVER_DPI = 150
"""DPI setting for extracting cover images from PDFs"""

PDF_COVER_DPI_LOW = 60
"""Low DPI setting for thumbnails/previews"""

PDF_COVER_DPI_HIGH = 200
"""High DPI setting for quality cover images"""

PDF_COVER_DPI_OCR = 180
"""Optimal DPI for OCR text extraction (balances quality and performance, ~1360x1760 for 8.5x11")"""

OCR_IMAGE_MAX_DIMENSION = 1200
"""Maximum dimension (width or height) for OCR processing images in pixels"""

PDF_COVER_QUALITY = 50
"""JPEG quality for low resolution covers (1-100)"""

PDF_COVER_QUALITY_HIGH = 85
"""JPEG quality for high resolution covers (1-100)"""

MAX_FILENAME_LENGTH = 200
"""Maximum length for sanitized filenames"""

DEFAULT_ORGANIZATION_PATTERN = "{category}/{title}/{year}/"
"""Default pattern for organizing imported files"""

DUPLICATE_DATE_THRESHOLD_DAYS = 5
"""Days threshold for considering publications as duplicates"""

MIN_VALID_YEAR = 1900
"""Minimum valid year for publication dates"""

MAX_VALID_YEAR = 2100
"""Maximum valid year for publication dates"""


# ==============================================================================
# Pagination
# ==============================================================================

DEFAULT_PAGE_SIZE = 50
"""Default number of items per page for list endpoints"""

MAX_PAGE_SIZE = 100
"""Maximum allowed page size"""


# ==============================================================================
# Downloads and Retries
# ==============================================================================

MAX_DOWNLOAD_RETRIES = 3
"""Maximum number of retry attempts for failed downloads"""

MAX_DOWNLOADS_PER_BATCH = 10
"""Maximum number of concurrent downloads allowed system-wide (not per batch, but total)"""

DOWNLOAD_FILE_SEARCH_DEPTH = 2
"""Maximum directory depth to search for downloaded files"""

PROVIDER_SEARCH_TIMEOUT = 30
"""Timeout in seconds for provider search operations"""


# ==============================================================================
# Time Intervals (in seconds)
# ==============================================================================

AUTO_IMPORT_INTERVAL = 300
"""Interval for automatic file import checks (5 minutes)"""

AUTO_DOWNLOAD_INTERVAL = 1800
"""Interval for automatic download checks (30 minutes)"""

DOWNLOAD_MONITOR_INTERVAL = 30
"""Interval for checking download status (30 seconds)"""

CLEANUP_COVERS_INTERVAL = 86400
"""Interval for cleaning up orphaned covers (24 hours)"""

OCR_COVER_GENERATOR_INTERVAL = 300
"""Interval for generating high-res cover PNGs for OCR (5 minutes)"""

OCR_PROCESSOR_INTERVAL = 10
"""Interval for running OCR text extraction on queued covers (10 seconds)"""

OCR_MAX_WORKERS = 1
"""Default number of parallel OCR processes"""

OCR_BATCH_SIZE = 1
"""Default maximum number of OCR jobs to process per batch"""

OCR_MIN_MEMORY_MB = 4096
"""Minimum available memory in MB required for PaddleOCR initialization (4GB)"""

TASK_SCHEDULER_CHECK_INTERVAL = 60
"""Interval for task scheduler checking (1 minute)"""


# ==============================================================================
# Authentication
# ==============================================================================

TOKEN_EXPIRATION_HOURS = 24
"""JWT token expiration time in hours"""


# ==============================================================================
# Rate Limiting
# ==============================================================================

RATE_LIMIT_CALLS = 60
"""Maximum number of API calls per period"""

RATE_LIMIT_PERIOD = 60
"""Rate limit period in seconds"""

RATE_LIMIT_AUTH_CALLS = 10
"""Maximum number of auth API calls per period"""

RATE_LIMIT_AUTH_PERIOD = 60
"""Rate limit period for auth endpoints in seconds"""


# ==============================================================================
# Category Classification
# ==============================================================================

CATEGORY_MAGAZINES = "Magazines"
CATEGORY_COMICS = "Comics"
CATEGORY_ARTICLES = "Articles"
CATEGORY_NEWS = "News"

# Category keywords for automatic file categorization
CATEGORY_KEYWORDS = {
    CATEGORY_MAGAZINES: [
        "magazine",
        "national geographic",
        "wired",
        "time",
        "newsweek",
        "economist",
        "pc gamer",
        "forbes",
    ],
    CATEGORY_COMICS: [
        "comic",
        "marvel",
        "dc",
        "graphic novel",
        "comic book",
    ],
    CATEGORY_ARTICLES: [
        "article",
        "paper",
        "journal",
        "report",
    ],
    CATEGORY_NEWS: [
        "news",
        "daily",
        "newspaper",
    ],
}


# ==============================================================================
# File Organization
# ==============================================================================

ORGANIZED_FILENAME_PATTERN = "{title} - {month}{year}"
"""Pattern for organized filenames: e.g., 'Wired - Dec2006'"""

VOLUME_PREFIX = "Vol"
"""Prefix for volume numbers in filenames (e.g., 'Vol1')"""

ISSUE_PREFIX = "No"
"""Prefix for issue numbers in filenames (e.g., 'No123')"""

ORGANIZED_FILENAME_SEPARATOR = " - "
"""Separator used in organized filenames between components"""


# ==============================================================================
# Supported Languages
# ==============================================================================

SUPPORTED_LANGUAGES = [
    "English",
    "German",
    "French",
    "Spanish",
    "Italian",
    "Portuguese",
    "Dutch",
    "Polish",
    "Russian",
    "Ukrainian",
    "Japanese",
    "Chinese",
    "Korean",
]
"""List of supported languages for periodical tracking and parsing"""


# ==============================================================================
# ISO Country Codes
# ==============================================================================

ISO_COUNTRIES = {
    # North America
    "US": "United States",
    "CA": "Canada",
    "MX": "Mexico",
    # Europe
    "UK": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "PT": "Portugal",
    "NL": "Netherlands",
    "BE": "Belgium",
    "CH": "Switzerland",
    "AT": "Austria",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
    "PL": "Poland",
    "CZ": "Czech Republic",
    "HU": "Hungary",
    "RO": "Romania",
    "BG": "Bulgaria",
    "GR": "Greece",
    "IE": "Ireland",
    "SK": "Slovakia",
    "HR": "Croatia",
    "SI": "Slovenia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "EE": "Estonia",
    "IS": "Iceland",
    "LU": "Luxembourg",
    "MT": "Malta",
    "CY": "Cyprus",
    # Asia
    "JP": "Japan",
    "CN": "China",
    "KR": "South Korea",
    "IN": "India",
    "ID": "Indonesia",
    "TH": "Thailand",
    "MY": "Malaysia",
    "SG": "Singapore",
    "PH": "Philippines",
    "VN": "Vietnam",
    "TW": "Taiwan",
    "HK": "Hong Kong",
    # Oceania
    "AU": "Australia",
    "NZ": "New Zealand",
    # South America
    "BR": "Brazil",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Peru",
    "VE": "Venezuela",
    # Africa
    "ZA": "South Africa",
    "EG": "Egypt",
    "NG": "Nigeria",
    "KE": "Kenya",
    # Middle East & Eastern Europe
    "RU": "Russia",
    "UA": "Ukraine",
    "TR": "Turkey",
    "SA": "Saudi Arabia",
    "AE": "United Arab Emirates",
    "IL": "Israel",
}
"""ISO 3166-1 alpha-2 country codes for region-specific editions"""


# ==============================================================================
# Language to Country Mappings
# ==============================================================================

LANGUAGE_TO_COUNTRY = {
    "English": "US",
    "German": "DE",
    "French": "FR",
    "Spanish": "ES",
    "Italian": "IT",
    "Portuguese": "PT",
    "Dutch": "NL",
    "Polish": "PL",
    "Russian": "RU",
    "Ukrainian": "UA",
    "Japanese": "JP",
    "Chinese": "CN",
    "Korean": "KR",
}
"""Default country mapping for each supported language"""


LANGUAGE_CODE_MAP = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "cn": "Chinese",
    "ko": "Korean",
    "kr": "Korean",
    "ua": "Ukrainian",
}
"""Mapping from 2-letter language codes to full language names"""


# ==============================================================================
# Country Detection Indicators
# ==============================================================================

COUNTRY_INDICATORS = {
    "UK": ["[UK]", " UK ", ".UK.", "British", "Britain"],
    "US": ["[US]", " US ", ".US.", "American", "USA"],
    "DE": ["[DE]", " DE ", ".DE.", "German", "Deutschland", "Germany"],
    "FR": ["[FR]", " FR ", ".FR.", "French", "France"],
    "ES": ["[ES]", " ES ", ".ES.", "Spain", "Spanish", "España"],
    "IT": ["[IT]", " IT ", ".IT.", "Italy", "Italian", "Italia"],
    "PT": ["[PT]", " PT ", ".PT.", "Portugal", "Portuguese"],
    "NL": ["[NL]", " NL ", ".NL.", "Netherlands", "Dutch", "Holland", "Nederland"],
    "PL": ["[PL]", " PL ", ".PL.", "Poland", "Polish", "Polska"],
    "RU": ["[RU]", " RU ", ".RU.", "Russia", "Russian"],
    "UA": ["[UA]", " UA ", ".UA.", "Ukraine", "Ukrainian"],
    "JP": ["[JP]", " JP ", ".JP.", "Japan", "Japanese"],
    "CN": ["[CN]", " CN ", ".CN.", "China", "Chinese"],
    "KR": ["[KR]", " KR ", ".KR.", "Korea", "Korean"],
    "CA": ["[CA]", " CA ", ".CA.", "Canada", "Canadian"],
    "MX": ["[MX]", " MX ", ".MX.", "Mexico", "Mexican"],
    "AU": ["[AU]", " AU ", ".AU.", "Australia", "Australian"],
    "NZ": ["[NZ]", " NZ ", ".NZ.", "New Zealand"],
    "BR": ["[BR]", " BR ", ".BR.", "Brazil", "Brazilian"],
    "AR": ["[AR]", " AR ", ".AR.", "Argentina", "Argentine"],
    "ZA": ["[ZA]", " ZA ", ".ZA.", "South Africa", "Africa"],
}
"""Keywords and patterns used to detect country from periodical titles"""


# ==============================================================================
# Language Detection Keywords
# ==============================================================================

LANGUAGE_KEYWORDS = {
    "German": ["German", "Deutsch", "Deutschland", "DE"],
    "French": ["French", "Français", "Francais", "FRANCAIS", "France", "FR"],
    "Spanish": ["Spanish", "Español", "Espanol", "ESPANOL", "España", "ES"],
    "Italian": ["Italian", "Italiano", "Italia", "IT"],
    "Portuguese": ["Portuguese", "Português", "Portugues", "PORTUGUES", "PT"],
    "Dutch": ["Dutch", "Nederlands", "nederlands", "Holland", "NL"],
    "Polish": ["Polish", "Polski", "Polska", "PL"],
    "Russian": ["Russian", "Русский", "RU"],
    "Ukrainian": ["Ukrainian", "Українська", "UA"],
    "Japanese": ["Japanese", "日本語", "Japan", "JP"],
    "Chinese": ["Chinese", "中文", "China", "CN", "ZH"],
    "Korean": ["Korean", "한국어", "Korea", "KR"],
}
"""Keywords used to detect language from periodical titles"""
