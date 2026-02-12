"""
RSS feed cache service.

Provides persistent caching of RSS feeds from providers (Internet Archive,
Newsnab, etc.) to reduce API calls and avoid rate limiting. Feeds are stored
in the cache database and automatically expire based on TTL.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

import feedparser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.parsers import utc_now
from models.cache import CacheBase, RssCache

logger = logging.getLogger(__name__)


class RssCacheService:
    """
    Persistent RSS feed cache using SQLite.

    Stores RSS feeds keyed by provider name and cache key (e.g., 'magazines',
    '7010,7020', etc.). Feeds are automatically expired and refetched based
    on TTL. Survives application restarts for instant warm cache.
    """

    def __init__(self, cache_db_path: str):
        """
        Initialize RSS cache service.

        Args:
            cache_db_path: Path to cache SQLite database
        """
        self.cache_db_path = cache_db_path

        # Initialize database (shares engine with NZB cache)
        db_url = f"sqlite:///{cache_db_path}"
        self._engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)

        # Create tables if they don't exist
        CacheBase.metadata.create_all(self._engine)

        logger.info(f"RSS cache service initialized: {cache_db_path}")

    def get_feed(
        self, provider_name: str, cache_key: str, ttl_seconds: int = 3600
    ) -> Optional[feedparser.FeedParserDict]:
        """
        Get cached RSS feed if available and fresh, otherwise return None.

        Args:
            provider_name: Provider name (e.g., 'Internet Archive', 'Newsnab')
            cache_key: Cache key (e.g., 'magazines', '7010,7020')
            ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)

        Returns:
            Parsed feedparser.FeedParserDict if cached and fresh, None otherwise
        """
        session = self._session_factory()
        try:
            # Query for cached feed
            cached = (
                session.query(RssCache)
                .filter(
                    RssCache.provider_name == provider_name,
                    RssCache.cache_key == cache_key,
                )
                .first()
            )

            if not cached:
                logger.debug(f"[{provider_name}] RSS cache miss for '{cache_key}'")
                return None

            # Check if expired
            now = utc_now()

            # SQLite doesn't preserve timezone info, so ensure datetimes are tz-aware for comparison
            expires_at = cached.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            cached_at = cached.cached_at
            if cached_at is not None and cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=UTC)

            if expires_at < now:
                logger.debug(
                    f"[{provider_name}] RSS cache expired for '{cache_key}' "
                    f"(expired {(now - expires_at).total_seconds():.0f}s ago)"
                )
                # Delete expired entry
                session.delete(cached)
                session.commit()
                return None

            # Cache hit - deserialize and return
            logger.debug(
                f"[{provider_name}] RSS cache hit for '{cache_key}' "
                f"(age: {(now - cached_at).total_seconds():.0f}s)"
            )

            # Deserialize feed from JSON
            try:
                feed_dict = json.loads(cached.feed_content)
                # Reconstruct feedparser.FeedParserDict
                # We store the essential parts: feed, entries, bozo
                feed = feedparser.FeedParserDict()
                feed.update(feed_dict)
                return feed
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"[{provider_name}] Failed to deserialize cached feed: {e}")
                # Delete corrupted entry
                session.delete(cached)
                session.commit()
                return None

        finally:
            session.close()

    def save_feed(
        self, provider_name: str, cache_key: str, feed: feedparser.FeedParserDict, ttl_seconds: int = 3600
    ) -> bool:
        """
        Save RSS feed to cache.

        Args:
            provider_name: Provider name
            cache_key: Cache key
            feed: Parsed feedparser.FeedParserDict to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if saved successfully, False otherwise
        """
        session = self._session_factory()
        try:
            # Serialize feed to JSON (store essential parts)
            # feedparser.FeedParserDict is complex, we extract the key parts
            feed_dict = {
                "bozo": feed.bozo,
                "entries": [
                    {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "id": entry.get("id", ""),
                        "published": entry.get("published", ""),
                        "published_parsed": entry.get("published_parsed"),
                        # Preserve enclosures (contains NZB download URLs for Newsnab providers)
                        "enclosures": [
                            {"href": enc.get("href", ""), "type": enc.get("type", "")}
                            for enc in entry.get("enclosures", [])
                        ],
                    }
                    for entry in feed.entries
                ],
                "feed": {
                    "title": feed.feed.get("title", ""),
                    "link": feed.feed.get("link", ""),
                },
            }

            feed_content = json.dumps(feed_dict)
            now = utc_now()
            expires_at = now + timedelta(seconds=ttl_seconds)

            # Check if entry exists
            existing = (
                session.query(RssCache)
                .filter(
                    RssCache.provider_name == provider_name,
                    RssCache.cache_key == cache_key,
                )
                .first()
            )

            if existing:
                # Update existing
                existing.feed_content = feed_content
                existing.cached_at = now
                existing.expires_at = expires_at
                logger.debug(
                    f"[{provider_name}] Updated RSS cache for '{cache_key}' "
                    f"({len(feed.entries)} entries, TTL: {ttl_seconds}s)"
                )
            else:
                # Insert new
                entry = RssCache(
                    provider_name=provider_name,
                    cache_key=cache_key,
                    feed_content=feed_content,
                    cached_at=now,
                    expires_at=expires_at,
                )
                session.add(entry)
                logger.debug(
                    f"[{provider_name}] Cached RSS for '{cache_key}' "
                    f"({len(feed.entries)} entries, TTL: {ttl_seconds}s)"
                )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"[{provider_name}] Failed to save RSS cache: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def clear_expired(self) -> int:
        """
        Clear all expired RSS cache entries.

        Returns:
            Number of entries deleted
        """
        session = self._session_factory()
        try:
            now = utc_now()
            deleted = session.query(RssCache).filter(RssCache.expires_at < now).delete()
            session.commit()

            if deleted > 0:
                logger.info(f"Cleared {deleted} expired RSS cache entries")

            return deleted

        finally:
            session.close()

    def get_stats(self) -> dict:
        """
        Get RSS cache statistics.

        Returns:
            Dict with cache stats (total, by provider, etc.)
        """
        session = self._session_factory()
        try:
            total = session.query(RssCache).count()
            now = utc_now()
            valid = session.query(RssCache).filter(RssCache.expires_at >= now).count()
            expired = total - valid

            return {
                "total_cached": total,
                "valid": valid,
                "expired": expired,
            }

        finally:
            session.close()
