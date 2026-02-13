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

MAX_DOWNLOAD_RETRIES_IA = 5
"""Maximum retries for Internet Archive downloads (failures usually transient)"""

MAX_IMPORT_RETRIES = 3
"""Maximum number of retry attempts for failed file imports (file exists but import failed)"""

MAX_DOWNLOADS = 10
"""Maximum number of concurrent downloads allowed system-wide""" ""

DOWNLOAD_FILE_SEARCH_DEPTH = 2
"""Maximum directory depth to search for downloaded files"""

PROVIDER_SEARCH_TIMEOUT = 30
"""Timeout in seconds for provider search operations"""


# ==============================================================================
# Database Configuration
# ==============================================================================

DB_LOCK_TIMEOUT = 30.0
"""Timeout in seconds to wait for database locks before raising error"""

DB_LOCK_RETRY_MAX = 3
"""Maximum number of retries for database lock errors"""

DB_LOCK_RETRY_DELAY = 0.1
"""Initial delay in seconds between database lock retries (exponential backoff)"""


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

AUTO_METADATA_INTERVAL = 604800
"""Interval for automatic metadata backfill and sync (7 days / 1 week)"""

FEED_SYNC_INTERVAL = 900
"""Interval for RSS feed sync task (15 minutes)"""

FEED_SYNC_MATCH_BATCH_SIZE = 200
"""Maximum number of new RSS feed entries to match per auto-download run"""

FEED_ENTRY_RETENTION_DAYS = 7
"""Number of days to retain RSS feed entries before expiring them"""

SEARCH_RESULT_RETENTION_DAYS = 30
"""Number of days to retain search results in the main database before cleanup"""

TASK_SCHEDULER_CHECK_INTERVAL = 60
"""Interval for task scheduler checking (1 minute)"""


# ==============================================================================
# HTTP Timeouts
# ==============================================================================

HTTP_REQUEST_TIMEOUT = 10
"""Default timeout in seconds for HTTP requests to download clients and providers"""

VERSION_CHECK_TIMEOUT = 5
"""Timeout in seconds for checking application version updates"""

RESTART_SHUTDOWN_DELAY = 1
"""Delay in seconds before restarting/shutting down to allow response to be sent"""


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
