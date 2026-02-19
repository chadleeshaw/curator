"""NZB content cache constants."""

# Database settings
CACHE_DB_FILENAME = "provider_cache.db"
"""Filename for cache database"""

# NZB content caching and rate limiting
DEFAULT_MAX_NZB_FETCHES_PER_HOUR = 50
"""Maximum NZB file fetches per hour per provider (rate limiting)"""

NZB_RATE_LIMIT_WINDOW_SECONDS = 3600
"""Rate limit window duration in seconds (1 hour)"""
