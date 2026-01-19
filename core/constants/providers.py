"""
Provider-specific constants for search providers and indexers
"""

# ==============================================================================
# Newsnab Provider Configuration
# ==============================================================================

NEWSNAB_DEFAULT_API_URL = "http://localhost:9696"
"""Default Newsnab API URL (typically Prowlarr)"""

NEWSNAB_DEFAULT_CATEGORIES = "7000,7010,7020,7030,6000,8000"
"""
Default Newsnab categories to search.
Common Newznab categories:
- 7000: Books (all)
- 7010: Magazines
- 7020: Ebooks
- 7030: Comics
- 6000: Adult
- 8000: Misc
"""

NEWSNAB_CATEGORY_MAP = {
    "Magazines": "7010",
    "Comics": "7030",
    "Articles": "7020",  # Ebooks
    "News": "7010",  # Same as magazines
}
"""Mapping of Curator category names to Newsnab category IDs"""

NEWSNAB_DEFAULT_MAX_REQUESTS_PER_HOUR = 100
"""Default maximum requests per hour for Newsnab providers"""

NEWSNAB_DEFAULT_REQUEST_DELAY = 1.0
"""Default delay in seconds between Newsnab requests"""

NEWSNAB_REQUEST_TIMEOUT = 10
"""Timeout in seconds for Newsnab API requests"""

NEWSNAB_DEFAULT_RATE_LIMIT_WAIT = 3600
"""Default wait time in seconds when rate limited (1 hour)"""

# ==============================================================================
# Time Conversion Constants
# ==============================================================================

SECONDS_PER_MINUTE = 60
"""Seconds in one minute"""

SECONDS_PER_HOUR = 3600
"""Seconds in one hour"""

SECONDS_PER_DAY = 86400
"""Seconds in one day (24 hours)"""
