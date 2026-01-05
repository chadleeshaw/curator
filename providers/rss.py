import logging
from datetime import datetime
from typing import List

import feedparser

from core.bases import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class RSSProvider(SearchProvider):
    """Search provider for RSS feeds of magazines"""

    def __init__(self, config):
        super().__init__(config)
        self.feed_url = config.get("feed_url")

        if not self.feed_url:
            raise ValueError("RSS provider requires feed_url")

    def search(self, query: str) -> List[SearchResult]:
        """
        Search RSS feed for matching magazine titles.

        Args:
            query: Magazine title to search for (used to filter feed)

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            # Fetch and parse feed
            feed = feedparser.parse(self.feed_url)

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
                    pub_date = datetime(*entry.published_parsed[:6])

                result = SearchResult(
                    title=title,
                    url=entry.get("link", ""),
                    provider=self.type,
                    publication_date=pub_date,
                    raw_metadata={
                        "summary": entry.get("summary", ""),
                        "guid": entry.get("id", ""),
                    },
                )
                results.append(result)

            logger.info(f"RSS found {len(results)} results for '{query}'")

        except Exception as e:
            logger.error(f"RSS search error: {e}")

        return results
