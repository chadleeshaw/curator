"""
Provider-specific constants for search providers and indexers
"""

from core.constants.category import (
    CATEGORY_BOOK,
    CATEGORY_COMIC,
    CATEGORY_DOCUMENT,
    CATEGORY_MAGAZINE,
)

# ==============================================================================
# Newsnab Provider Configuration
# ==============================================================================

NEWSNAB_DEFAULT_API_URL = "http://localhost:9696"
"""Default Newsnab API URL (typically Prowlarr)"""

NEWSNAB_DEFAULT_CATEGORIES = "7000,7010,7020,7030,6000,8000,8010"
"""
Default Newsnab categories to search.
Standard Newsnab categories:
- 7000: Books (parent)
- 7010: Books/Mags (Magazines)
- 7020: Books/EBook
- 7030: Books/Comics
- 6000: XXX (adult - magazines, comics, books - requires pattern validation)
- 8000: Other (parent - requires pattern validation)
- 8010: Other/Misc (requires pattern validation)
- 8050: Other/Hashed (spam/obfuscated - explicitly excluded)

Note: Categories 6000, 8000, and 8010 are included because periodicals are sometimes
      placed there, but they require additional pattern-based validation.
"""

NEWSNAB_CATEGORY_MAP = {
    CATEGORY_MAGAZINE: "7010,8000,8010",  # Books/Mags + Other/Misc (periodicals sometimes in Other)
    CATEGORY_COMIC: "7030,8000,8010",  # Books/Comics + Other/Misc (comics sometimes in Other)
    CATEGORY_BOOK: "7000,7020",  # Books (parent) and Books/EBook
    CATEGORY_DOCUMENT: "7020",  # Books/EBook (documents/PDFs)
}
"""
Mapping of Curator category names to Newsnab category IDs for searching.

These are merged with the user's configured categories at search time,
so user-configured categories (e.g., 6000 for XXX) are always included.
8000 (Other) and 8010 (Other/Misc) are included because periodicals are sometimes categorized there.
8050 (Other/Hashed) is excluded as it's typically spam/obfuscated releases.
"""

NEWSNAB_DEFAULT_MAX_REQUESTS_PER_HOUR = 100
"""Default maximum requests per hour for Newsnab providers"""

NEWSNAB_DEFAULT_REQUEST_DELAY = 1.0
"""Default delay in seconds between Newsnab requests"""

NEWSNAB_REQUEST_TIMEOUT = 10
"""Timeout in seconds for Newsnab API requests"""

NEWSNAB_DEFAULT_RATE_LIMIT_WAIT = 300
"""Default wait time in seconds when rate limited without explicit Retry-After (5 minutes)"""

NEWSNAB_RSS_MAX_RESULTS = 100
"""Maximum number of RSS results to fetch (used by FeedSyncService for cache-first auto-download)"""

NEWSNAB_DEFAULT_SEARCH_LIMIT = 100
"""Default maximum number of results to request per Newsnab API search query.

Many indexers default to returning only 25-50 results without an explicit limit.
Setting this higher ensures collection items and older releases are included."""

# ==============================================================================
# Time Conversion Constants
# ==============================================================================

SECONDS_PER_MINUTE = 60
"""Seconds in one minute"""

SECONDS_PER_HOUR = 3600
"""Seconds in one hour"""

SECONDS_PER_DAY = 86400
"""Seconds in one day (24 hours)"""

# Upload date parsing formats (try in order)
UPLOAD_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822: "Mon, 20 Jan 2025 12:34:56 +0000"
    "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone: "2025-01-20T12:34:56+0000"
    "%Y-%m-%d %H:%M:%S",  # Simple format: "2025-01-20 12:34:56"
]
"""Date formats to try when parsing upload_date from provider responses"""
