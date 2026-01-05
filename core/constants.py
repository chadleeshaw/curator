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

MAX_FILENAME_LENGTH = 200
"""Maximum length for sanitized filenames"""

DEFAULT_ORGANIZATION_PATTERN = "{category}/{title}/{year}/"
"""Default pattern for organizing imported files"""


# ==============================================================================
# Pagination
# ==============================================================================

DEFAULT_PAGE_SIZE = 50
"""Default number of items per page for list endpoints"""

MAX_PAGE_SIZE = 100
"""Maximum allowed page size"""


# ==============================================================================
# Time Intervals (in seconds)
# ==============================================================================

AUTO_IMPORT_INTERVAL = 300
"""Interval for automatic file import checks (5 minutes)"""

DOWNLOAD_MONITOR_INTERVAL = 60
"""Interval for checking download status (1 minute)"""

TASK_SCHEDULER_CHECK_INTERVAL = 60
"""Interval for task scheduler checking (1 minute)"""


# ==============================================================================
# Authentication
# ==============================================================================

TOKEN_EXPIRATION_HOURS = 24
"""JWT token expiration time in hours"""


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
