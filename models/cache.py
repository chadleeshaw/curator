"""
Cache database models for provider result caching.

This module defines models for the separate provider cache database,
which stores search results from providers for fast local searching.
Uses a separate declarative base from the main database.

Models:
    CachedRelease: A release cached from a search provider
    SyncStatus: Tracks sync state for each provider
"""

from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.ext.declarative import declarative_base

from core.parsers import utc_now as utcnow

# Separate declarative base for cache database (not mixed with main database)
CacheBase = declarative_base()


class CachedRelease(CacheBase):
    """
    A release cached from a search provider.

    Stores metadata and download URL from Newsnab providers,
    RSS feeds, and other search providers for fast local searching.
    """

    __tablename__ = "cached_releases"

    # Primary identification
    id = Column(Integer, primary_key=True)
    guid = Column(String(512), nullable=False, unique=True, index=True)  # Unique ID from provider

    # Release metadata
    title = Column(String(512), nullable=False, index=True)
    normalized_title = Column(String(512), nullable=False, index=True)  # Lowercase, normalized for matching

    # Provider information
    provider_name = Column(String(100), nullable=False, index=True)  # e.g., "Prowlarr", "NZBHydra"
    provider_type = Column(String(50), nullable=False, index=True)  # e.g., "newsnab", "rss"

    # Download information
    download_url = Column(String(1024), nullable=False)  # NZB URL from provider

    # Release details
    size_bytes = Column(Integer, nullable=True)  # File size in bytes
    publication_date = Column(DateTime, nullable=True, index=True)  # When the content was published
    upload_date = Column(DateTime, nullable=True, index=True)  # When posted to Usenet (for quality ranking)
    category = Column(String(100), nullable=True, index=True)  # Category from provider
    language = Column(String(50), nullable=True, index=True)  # Language if detected
    country = Column(String(50), nullable=True, index=True)  # Country if detected

    # Deduplication
    fuzzy_match_group = Column(String(255), nullable=True, index=True)  # For fuzzy deduplication

    # Cache tracking
    first_seen = Column(DateTime, default=utcnow, nullable=False, index=True)  # When first cached
    last_seen = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)  # Last sync update

    # Raw metadata from provider (JSON)
    raw_metadata = Column(JSON, nullable=True)  # Provider-specific fields

    def to_dict(self) -> Dict[str, Any]:
        """Serialize CachedRelease to dictionary for API responses"""
        return {
            "id": self.id,
            "guid": self.guid,
            "title": self.title,
            "normalized_title": self.normalized_title,
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "download_url": self.download_url,
            "size_bytes": self.size_bytes,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "upload_date": self.upload_date.isoformat() if self.upload_date else None,
            "category": self.category,
            "language": self.language,
            "country": self.country,
            "fuzzy_match_group": self.fuzzy_match_group,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "raw_metadata": self.raw_metadata,
            "from_cache": True,  # Flag to indicate this is from cache
        }


class SyncStatus(CacheBase):
    """
    Tracks sync status for each search provider.

    Records when each provider was last synced, how many releases
    were cached, and markers for incremental sync.
    """

    __tablename__ = "sync_status"

    # Primary identification
    id = Column(Integer, primary_key=True)
    provider_name = Column(String(100), nullable=False, unique=True, index=True)  # Provider name (unique)

    # Sync timing
    last_sync_time = Column(DateTime, nullable=True, index=True)  # Last sync attempt (success or fail)
    last_successful_sync = Column(DateTime, nullable=True, index=True)  # Last successful sync

    # Incremental sync marker
    last_sync_release_guid = Column(String(512), nullable=True)  # GUID of most recent release from last sync

    # Statistics
    total_releases_cached = Column(Integer, default=0, nullable=False)  # Total releases in cache from this provider
    total_syncs = Column(Integer, default=0, nullable=False)  # Number of sync attempts
    failed_syncs = Column(Integer, default=0, nullable=False)  # Number of failed syncs
    last_sync_added = Column(Integer, default=0, nullable=False)  # Releases added in last sync
    last_sync_duration_seconds = Column(Float, nullable=True)  # Duration of last sync in seconds

    # Initial sync tracking
    initial_sync_completed = Column(Boolean, default=False, nullable=False)  # Whether initial sync is done

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SyncStatus to dictionary for API responses"""
        return {
            "id": self.id,
            "provider_name": self.provider_name,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "last_successful_sync": self.last_successful_sync.isoformat() if self.last_successful_sync else None,
            "last_sync_release_guid": self.last_sync_release_guid,
            "total_releases_cached": self.total_releases_cached,
            "total_syncs": self.total_syncs,
            "failed_syncs": self.failed_syncs,
            "last_sync_added": self.last_sync_added,
            "last_sync_duration_seconds": self.last_sync_duration_seconds,
            "initial_sync_completed": self.initial_sync_completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
