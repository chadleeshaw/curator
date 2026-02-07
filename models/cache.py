"""
Cache database models for NZB content caching.

This module defines models for the separate cache database,
which stores NZB file content fetched from providers to avoid
repeated provider hits on download retries.

Models:
    NzbCache: Cached NZB content keyed by download URL
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
    cached_at = Column(DateTime, default=utcnow, nullable=False)
