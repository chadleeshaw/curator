"""
Cache database models for NZB content and RSS feed caching.

This module defines models for the separate cache database,
which stores:
- NZB file content fetched from providers (avoid repeated hits)
- RSS feeds from providers (reduce API calls and rate limiting)

Models:
    NzbCache: Cached NZB content keyed by download URL
    RssCache: Cached RSS feeds keyed by provider + cache key
"""

from sqlalchemy import Column, DateTime, Integer, String, Text
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


class RssCache(CacheBase):
    """
    Cached RSS feeds from providers (Internet Archive, Newsnab, etc.).

    RSS feeds are fetched periodically and cached to avoid hitting provider
    APIs repeatedly. This reduces rate limiting and speeds up searches by
    allowing local filtering of cached feed entries.

    Cache entries expire based on TTL (typically 1 hour) and are automatically
    refreshed on next access.
    """

    __tablename__ = "rss_cache"

    id = Column(Integer, primary_key=True)
    provider_name = Column(String(255), nullable=False, index=True)
    cache_key = Column(String(255), nullable=False, index=True)  # collection, category, etc.
    feed_content = Column(Text, nullable=False)  # Serialized RSS feed (JSON or XML)
    cached_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Composite unique constraint: one cache entry per provider + key combination
    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("provider_name", "cache_key", name="uix_provider_cache_key"),
    )
