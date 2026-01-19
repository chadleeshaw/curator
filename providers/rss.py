import logging
import time
from datetime import datetime
from typing import List, Optional

import feedparser

from core.interfaces import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class RSSProvider(SearchProvider):
    """
    Search provider for RSS feeds with intelligent caching.

    Caches feed content to reduce redundant fetches and speed up searches.
    Multiple searches can be served from a single feed fetch.
    """

    def __init__(self, config):
        super().__init__(config)
        self.feed_url = config.get("feed_url")

        if not self.feed_url:
            raise ValueError("RSS provider requires feed_url")

        # Caching configuration
        self.cache_ttl = config.get("cache_ttl", 3600)  # Default: 1 hour
        self.enable_cache = config.get("enable_cache", True)

        # Cache storage
        self._feed_cache: Optional[feedparser.FeedParserDict] = None
        self._cache_time: Optional[float] = None
        self._cache_hits = 0
        self._cache_misses = 0

        logger.info(
            f"Initialized RSS provider: {self.name} "
            f"(cache_ttl={self.cache_ttl}s, caching={'enabled' if self.enable_cache else 'disabled'})"
        )

    def search(self, query: str, category: str = None) -> List[SearchResult]:
        """
        Search RSS feed for matching periodical titles.

        Uses cached feed if available and fresh, otherwise fetches and caches.

        Args:
            query: Periodical title to search for (used to filter feed)
            category: Optional category filter (not used for RSS feeds)

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            # Get feed (from cache or fetch)
            feed = self._get_feed()

            if not feed:
                logger.warning(f"Failed to fetch RSS feed: {self.feed_url}")
                return results

            if feed.bozo:
                logger.warning(f"RSS Feed parsing issue: {feed.bozo_exception}")

            query_lower = query.lower()

            for entry in feed.entries:
                title = entry.get("title", "")

                # Basic filtering: only include entries matching query
                if query_lower not in title.lower():
                    continue

                # Parse publication date if available
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                    except (TypeError, ValueError) as e:
                        logger.debug(f"Failed to parse publication date: {e}")

                result = SearchResult(
                    title=title,
                    url=entry.get("link", ""),
                    provider=self.type,
                    publication_date=pub_date,
                    raw_metadata={
                        "summary": entry.get("summary", ""),
                        "guid": entry.get("id", ""),
                        "author": entry.get("author", ""),
                        "category": entry.get("category", ""),
                    },
                )
                results.append(result)

            logger.info(
                f"RSS found {len(results)} results for '{query}' "
                f"(cache_hits={self._cache_hits}, cache_misses={self._cache_misses})"
            )

        except Exception as e:
            logger.error(f"RSS search error: {e}", exc_info=True)

        return results

    def _get_feed(self) -> Optional[feedparser.FeedParserDict]:
        """
        Get feed from cache if fresh, otherwise fetch and cache.

        Returns:
            Parsed feed or None if fetch fails
        """
        current_time = time.time()

        # Check if cache is enabled and fresh
        if (
            self.enable_cache
            and self._feed_cache is not None
            and self._cache_time is not None
            and (current_time - self._cache_time) < self.cache_ttl
        ):
            self._cache_hits += 1
            cache_age = int(current_time - self._cache_time)
            logger.debug(
                f"Using cached RSS feed (age: {cache_age}s, " f"ttl: {self.cache_ttl}s, hits: {self._cache_hits})"
            )
            return self._feed_cache

        # Cache miss - fetch feed
        self._cache_misses += 1
        logger.debug(f"Fetching RSS feed: {self.feed_url} (misses: {self._cache_misses})")

        try:
            feed = feedparser.parse(self.feed_url)

            # Cache the feed
            if self.enable_cache:
                self._feed_cache = feed
                self._cache_time = current_time
                logger.debug(f"Cached RSS feed (ttl: {self.cache_ttl}s)")

            return feed

        except Exception as e:
            logger.error(f"Failed to fetch RSS feed: {e}", exc_info=True)
            # If fetch fails but we have stale cache, use it
            if self.enable_cache and self._feed_cache is not None:
                logger.warning("Using stale cache due to fetch failure")
                return self._feed_cache

            return None

    def clear_cache(self) -> None:
        """Manually clear the feed cache. Useful for testing or forced refresh."""
        self._feed_cache = None
        self._cache_time = None
        logger.info(f"Cleared RSS feed cache for: {self.name}")

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache hits, misses, and hit rate
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0

        cache_age = None
        if self._cache_time:
            cache_age = int(time.time() - self._cache_time)

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 2),
            "cache_age_seconds": cache_age,
            "cache_ttl_seconds": self.cache_ttl,
            "is_cached": self._feed_cache is not None,
        }
