"""
Provider cache constants - cache retention, sync settings

This module defines all constants related to the provider cache system,
which caches search result URLs from providers to reduce API calls and
improve search performance.
"""

# Cache retention and cleanup
CACHE_RETENTION_DAYS = 90
"""Default number of days to retain cached releases"""

CACHE_CLEANUP_BATCH_SIZE = 1000
"""Number of stale releases to delete per cleanup batch"""

# Sync settings
DEFAULT_SYNC_INTERVAL_SECONDS = 1800
"""Default sync interval (30 minutes)"""

MIN_SYNC_INTERVAL_SECONDS = 600
"""Minimum allowed sync interval (10 minutes)"""

MAX_SYNC_INTERVAL_SECONDS = 86400
"""Maximum allowed sync interval (24 hours)"""

INITIAL_SYNC_LIMIT = 100
"""Number of releases to fetch per provider on initial sync"""

INCREMENTAL_SYNC_LIMIT = 100
"""Number of releases to fetch per provider on incremental sync"""

# Database settings
CACHE_DB_FILENAME = "provider_cache.db"
"""Filename for cache database"""

# FTS5 search configuration
FTS5_MIN_TOKEN_LENGTH = 3
"""Minimum token length for FTS5 search"""

FTS5_TOKENIZER = "unicode61"
"""FTS5 tokenizer to use"""

# Deduplication settings
FUZZY_MATCH_SIMILARITY_THRESHOLD = 80
"""Minimum similarity score (0-100) for fuzzy matching"""

# Upload date parsing formats (try in order)
UPLOAD_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822: "Mon, 20 Jan 2025 12:34:56 +0000"
    "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone: "2025-01-20T12:34:56+0000"
    "%Y-%m-%d %H:%M:%S",  # Simple format: "2025-01-20 12:34:56"
]
"""Date formats to try when parsing upload_date from provider responses"""
