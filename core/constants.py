"""
Application constants and configuration values
"""

# ==============================================================================
# Matching and Deduplication
# ==============================================================================

DEFAULT_FUZZY_THRESHOLD = 80
"""Default fuzzy matching threshold (0-100) for title deduplication"""

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
"""Maximum number of downloads to submit globally across all tracked periodicals"""

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
    "NL": ["[NL]", " NL ", ".NL.", "Netherlands", "Dutch", "Holland"],
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
}
"""Keywords and patterns used to detect country from periodical titles"""


# ==============================================================================
# Language Detection Keywords
# ==============================================================================

LANGUAGE_KEYWORDS = {
    "German": ["German", "Deutsch", "Deutschland"],
    "French": ["French", "Français", "France"],
    "Spanish": ["Spanish", "Español", "España"],
    "Italian": ["Italian", "Italiano", "Italia"],
    "Portuguese": ["Portuguese", "Português"],
    "Dutch": ["Dutch", "Nederlands", "nederlands", "Holland"],
    "Polish": ["Polish", "Polski", "Polska"],
    "Russian": ["Russian", "Русский"],
    "Ukrainian": ["Ukrainian", "Українська"],
    "Japanese": ["Japanese", "日本語", "Japan"],
    "Chinese": ["Chinese", "中文", "China"],
    "Korean": ["Korean", "한국어", "Korea"],
}
"""Keywords used to detect language from periodical titles"""
