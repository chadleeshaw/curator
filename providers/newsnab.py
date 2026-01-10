"""
Newsnab provider for searching NZB indexers.
Supports Newsnab-compatible APIs like Prowlarr, NZBHydra, and others.
"""
import logging
import xml.etree.ElementTree as ET
from typing import List

import requests

from core.bases import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class NewsnabProvider(SearchProvider):
    """Search provider for Newsnab indexers (Prowlarr aggregator, etc.)"""

    def __init__(self, config):
        super().__init__(config)
        api_url = config.get("api_url", "http://localhost:9696")

        # Store the original URL - it might include indexer ID like /1/api
        self.api_url_raw = api_url.rstrip("/")

        # Strip only trailing /api or /api/v1 to get base URL for v1 endpoint construction
        # but keep any indexer ID like /1
        api_url = api_url.rstrip("/")
        for suffix in ["/api/v1", "/api"]:
            if api_url.endswith(suffix):
                api_url = api_url[: -len(suffix)]

        self.api_url = api_url
        self.api_key = config.get("api_key")

        # Allow configurable categories (comma-separated) or default to all book-related categories
        # Common Newznab categories: 7000=Books (all), 7010=Magazines, 7020=Ebooks, 7030=Comics
        self.categories = config.get("categories", "7000,7010,7020,7030")  # All books including magazines

        # Category name to Newznab ID mapping
        self.category_map = {
            "Magazines": "7010",
            "Comics": "7030",
            "Articles": "7020",  # Ebooks
            "News": "7010",  # Same as magazines
        }

        if not self.api_key:
            raise ValueError("Newsnab provider requires api_key")

    def search(self, query: str, category: str = None) -> List[SearchResult]:
        """
        Search Newsnab-compatible service for NZBs.

        Args:
            query: Magazine title to search for
            category: Optional category filter ("Magazines", "Comics", etc.)

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            # Use XML API - it's more reliable and well-supported
            # (v1 JSON API often has issues with Prowlarr aggregators)
            results = self._search_xml_api(query, category)
            return results

        except Exception as e:
            logger.error(f"Newsnab search error: {e}")

        return results

    def _search_xml_api(self, query: str, category: str = None) -> List[SearchResult]:
        """Search using the legacy /api XML endpoint"""
        results = []

        try:
            # Determine which categories to search
            cat_ids = self.categories  # Default: all configured categories

            if category and category in self.category_map:
                # If specific category requested, use its ID
                cat_ids = self.category_map[category]
                logger.debug(f"Using category filter: {category} -> {cat_ids}")

            url = f"{self.api_url}/api"
            params = {
                "apikey": self.api_key,
                "t": "search",
                "q": query,
                "cat": cat_ids,
            }

            logger.debug(f"Newsnab searching: query='{query}', categories={cat_ids}, url={url}")

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            # Parse RSS/XML response
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                enclosure_elem = item.find("enclosure")

                if title_elem is not None and title_elem.text:
                    # Get NZB URL from enclosure or link
                    nzb_url = ""
                    if enclosure_elem is not None:
                        nzb_url = enclosure_elem.get("url", "")
                    elif link_elem is not None:
                        nzb_url = link_elem.text or ""

                    result = SearchResult(
                        title=title_elem.text,
                        url=nzb_url,
                        provider=self.type,
                        raw_metadata={
                            "indexer": item.findtext("indexer", ""),
                        },
                    )
                    results.append(result)

            logger.info(f"Newsnab (XML API) found {len(results)} results for '{query}' in categories {self.categories}")

        except requests.exceptions.RequestException as e:
            logger.debug(f"Newsnab XML API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab XML parse error: {e}")

        return results
