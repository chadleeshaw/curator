"""
Cache database models for NZB content and RSS feed entry caching.

This module defines models for the separate cache database,
which stores:
- NZB file content fetched from providers (avoid repeated hits)
- Individual RSS feed entries for cache-first auto-download (avoid rate limiting)

Models:
    NzbCache: Cached NZB content keyed by download URL
    RssFeedEntry: Individual RSS feed entries for cache-first matching
"""

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

from core.parsers import utc_now as utcnow

# Separate declarative base for cache database (not mixed with main database)
CacheBase = declarative_base()


class NzbCache(CacheBase):
    """
    Cached NZB file content, keyed by download URL.

    When a download is submitted, the NZB XML is fetched from the provider
    once and stored here. Subsequent downloads/retries use the cached content
    directly, avoiding provider rate limits.
    """

    __tablename__ = "nzb_cache"

    id = Column(Integer, primary_key=True)
    download_url = Column(String(1024), nullable=False, unique=True, index=True)
    nzb_content = Column(Text, nullable=False)
    cached_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class RssFeedEntry(CacheBase):
    """
    Individual RSS feed entries from providers, deduplicated by GUID.

    This is the foundation of the cache-first auto-download system. Instead of
    querying provider APIs per-periodical (which causes rate limiting), we:

    1. Phase 1 (Feed Sync): Poll each provider's RSS feed periodically (single HTTP GET).
       Upsert entries into this table using GUID for deduplication.
    2. Phase 2 (Local Match): Match all tracked periodicals against this local cache.
       No API calls needed — just local string matching against cached entries.

    This decouples discovery (cheap RSS polls) from matching (local-only) and
    prevents rate limiting even with hundreds of tracked periodicals.

    Status values:
        - "new": Fresh entry, not yet matched against tracking rules
        - "matched": Matches a tracked periodical, forwarded to issue discovery
        - "skipped": Doesn't match any tracked periodical
        - "expired": Older than retention window, eligible for cleanup
    """

    __tablename__ = "rss_feed_entries"

    id = Column(Integer, primary_key=True)

    # Identity — GUID is the unique key per provider
    guid = Column(String(512), nullable=False, index=True)
    provider_name = Column(String(255), nullable=False, index=True)

    # Content from RSS feed
    title = Column(String(512), nullable=False, index=True)
    url = Column(String(1024), nullable=False)  # NZB/download URL
    published_date = Column(DateTime(timezone=True), nullable=True, index=True)

    # Processing state
    status = Column(String(50), nullable=False, default="new", index=True)

    # Tracking
    first_seen = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    last_seen = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Optional metadata from the feed
    category = Column(String(100), nullable=True)
    raw_metadata = Column(Text, nullable=True)  # JSON string of extra fields

    # Composite unique constraint: one entry per GUID per provider
    __table_args__ = (UniqueConstraint("provider_name", "guid", name="uix_provider_guid"),)
