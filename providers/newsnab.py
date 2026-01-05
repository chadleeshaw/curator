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

        if not self.api_key:
            raise ValueError("Newsnab provider requires api_key")

    def search(self, query: str) -> List[SearchResult]:
        """
        Search Newsnab-compatible service for NZBs.

        Args:
            query: Magazine title to search for

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            # Use XML API - it's more reliable and well-supported
            # (v1 JSON API often has issues with Prowlarr aggregators)
            results = self._search_xml_api(query)
            return results

        except Exception as e:
            logger.error(f"Newsnab search error: {e}")

        return results

    def _search_xml_api(self, query: str) -> List[SearchResult]:
        """Search using the legacy /api XML endpoint"""
        results = []

        try:
            url = f"{self.api_url}/api"
            params = {
                "apikey": self.api_key,
                "t": "search",
                "q": query,
                "cat": "7010",  # Magazine category
            }

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

            logger.info(f"Newsnab (XML API) found {len(results)} results for '{query}'")

        except requests.exceptions.RequestException as e:
            logger.debug(f"Newsnab XML API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab XML parse error: {e}")

        return results
