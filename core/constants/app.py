"""
Application-wide constants for configuration and system behavior
"""

# ==============================================================================
# Matching and Deduplication
# ==============================================================================

DEFAULT_FUZZY_THRESHOLD = 80
"""Default threshold for fuzzy string matching (0-100)"""

TITLE_MATCH_THRESHOLD = 85
"""Higher threshold for strict title matching (0-100)"""


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

MAX_DOWNLOAD_RETRIES = 1
"""Maximum number of retry attempts for failed downloads"""

MAX_DOWNLOADS = 10
"""Maximum number of concurrent downloads allowed system-wide"""

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

OCR_PROCESSOR_INTERVAL = 10
"""Interval for running OCR text extraction on queued covers (10 seconds)"""

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
