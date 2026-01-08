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
"""Maximum number of downloads to submit per batch"""

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
