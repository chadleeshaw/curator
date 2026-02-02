"""
Provider cache services for caching search provider results.

This module provides two main services:
1. ProviderCacheService: Manages cached releases from search providers
2. ProviderSyncService: Syncs with search providers in background

The cache uses a separate SQLite database with FTS5 full-text search
for fast local searching without hitting provider APIs. Download URLs
are stored in the database and used by download clients when needed.

Classes:
    ProviderCacheService: Manages cached releases from search providers
    ProviderSyncService: Syncs with search providers in background
"""

from .provider_cache import ProviderCacheService
from .provider_sync import ProviderSyncService
from .utils import escape_fts_query, parse_upload_date

__all__ = [
    "ProviderCacheService",
    "ProviderSyncService",
    "escape_fts_query",
    "parse_upload_date",
]
