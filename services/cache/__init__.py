"""
NZB content cache service.

Caches NZB file content fetched from providers to avoid repeated
provider hits on download retries and resubmissions.
"""

from .provider_cache import NzbCacheService

__all__ = [
    "NzbCacheService",
]
