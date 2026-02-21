"""
Torznab provider for searching torrent indexers.
Supports any Torznab-compatible API endpoint (Prowlarr, Jackett, and others).

Torznab is a standardised XML/RSS API built on top of Newznab, adapted for torrents.
Results include magnet links and/or .torrent file URLs alongside seeder/leecher info.
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import requests

from core.constants.providers import (
    NEWSNAB_REQUEST_TIMEOUT,
    UPLOAD_DATE_FORMATS,
)
from core.interfaces import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

# Torznab XML namespaces
_TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
_NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"

# Default Torznab categories covering magazines, comics, and ebooks:
# 5000=TV (some indexers put periodicals here), 7000=Books, 7010=Books/Mags,
# 7020=Books/EBook, 7030=Books/Comics
TORZNAB_DEFAULT_CATEGORIES = "5000,7000,7010,7020,7030"

TORZNAB_DEFAULT_SEARCH_LIMIT = 100

TORZNAB_DEFAULT_REQUEST_DELAY = 1.0


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string using known upload date formats."""
    if not date_str:
        return None
    for fmt in UPLOAD_DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _attr(item: ET.Element, name: str, namespace: str = _TORZNAB_NS) -> Optional[str]:
    """Extract a torznab/newznab attribute value from an RSS item element."""
    # Try the requested namespace first, then the other; deduplicate to avoid double-checking
    for ns in dict.fromkeys((namespace, _TORZNAB_NS, _NEWZNAB_NS)):
        el = item.find(f"{{{ns}}}attr[@name='{name}']")
        if el is not None:
            return el.get("value")
    return None


def _int_attr(item: ET.Element, name: str) -> Optional[int]:
    """Extract an integer torznab attribute, returning None if missing or non-numeric."""
    value = _attr(item, name)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class TorznabProvider(SearchProvider):
    """Search provider for Torznab-compatible indexers (Prowlarr, Jackett, etc.)."""

    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config)

        api_url = config.get("api_url", "").rstrip("/")
        for suffix in ("/api/v1", "/api"):
            if api_url.endswith(suffix):
                api_url = api_url[: -len(suffix)]
                break
        self.api_url = api_url

        self.api_key = config.get("api_key", "")
        self.categories = config.get("categories", TORZNAB_DEFAULT_CATEGORIES)
        self.search_limit = config.get("search_limit", TORZNAB_DEFAULT_SEARCH_LIMIT)
        self.request_delay = config.get("request_delay_seconds", TORZNAB_DEFAULT_REQUEST_DELAY)

        if not self.api_url:
            raise ValueError("Torznab provider requires api_url")

    # -------------------------------------------------------------------------
    # SearchProvider interface
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        category: str = None,
        aliases: Optional[Sequence[str]] = None,
    ) -> List[SearchResult]:
        """
        Search a Torznab indexer for the given query.

        Args:
            query: Search term (periodical title)
            category: Optional Curator category filter (ignored — Torznab uses numeric IDs)
            aliases: Optional additional search terms (searched separately and merged)

        Returns:
            List of SearchResult with torrent URLs/magnets
        """
        results = self._search_query(query)

        if aliases:
            seen_urls = {r.url for r in results}
            for alias in aliases:
                if self.request_delay > 0:
                    time.sleep(self.request_delay)
                for result in self._search_query(alias):
                    if result.url not in seen_urls:
                        results.append(result)
                        seen_urls.add(result.url)

        return results

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection by fetching the indexer capabilities.

        Returns:
            Dict with success status and message
        """
        try:
            params = {"t": "caps", "apikey": self.api_key}
            response = requests.get(
                f"{self.api_url}/api",
                params=params,
                timeout=NEWSNAB_REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            try:
                root = ET.fromstring(response.content)
                server_el = root.find("server")
                title = server_el.get("title", "Torznab") if server_el is not None else "Torznab"
            except ET.ParseError:
                title = "Torznab"

            return {"success": True, "message": f"Connection successful — {title}"}

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timeout — check your API URL and network",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Connection failed — check your API URL and network",
            }
        except Exception as e:
            logger.error(f"Torznab connection test error: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {e}"}

    def get_provider_info(self) -> Dict[str, Any]:
        info = super().get_provider_info()
        info["api_url"] = self.api_url
        return info

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _search_query(self, query: str) -> List[SearchResult]:
        """Execute a single search query and return parsed results."""
        params: Dict[str, Any] = {
            "t": "search",
            "q": query,
            "cat": self.categories,
            "limit": self.search_limit,
        }
        if self.api_key:
            params["apikey"] = self.api_key

        try:
            response = requests.get(
                f"{self.api_url}/api",
                params=params,
                timeout=NEWSNAB_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.warning(f"Torznab search timeout: {query}")
            return []
        except requests.exceptions.ConnectionError:
            logger.warning(f"Torznab connection error: {query}")
            return []
        except Exception as e:
            logger.error(f"Torznab search error: {e}")
            return []

        return self._parse_response(response.content, query)

    def _parse_response(self, content: bytes, query: str) -> List[SearchResult]:
        """Parse Torznab RSS XML and return SearchResult objects."""
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error(f"Torznab XML parse error: {e}")
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        results = []
        for item in channel.findall("item"):
            result = self._parse_item(item)
            if result:
                results.append(result)

        logger.debug(f"Torznab search '{query}' returned {len(results)} results")
        return results

    def _parse_item(self, item: ET.Element) -> Optional[SearchResult]:
        """Parse a single RSS item element into a SearchResult."""
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            return None
        title = title_el.text.strip()

        magnet = _attr(item, "magneturl") or _attr(item, "magnetUrl")
        enclosure = item.find("enclosure")
        enclosure_url = enclosure.get("url") if enclosure is not None else None
        url = magnet or enclosure_url

        if not url:
            link_el = item.find("link")
            url = link_el.text.strip() if link_el is not None and link_el.text else None

        if not url:
            logger.debug(f"Torznab item '{title}' has no downloadable URL, skipping")
            return None

        pubdate_el = item.find("pubDate")
        pub_date = _parse_date(pubdate_el.text if pubdate_el is not None else None)

        raw = {
            "provider": self.name,
            "seeders": _int_attr(item, "seeders"),
            "leechers": _int_attr(item, "leechers"),
            "size": _int_attr(item, "size"),
            "grabs": _int_attr(item, "grabs"),
            "category": _attr(item, "category"),
            "magnet": magnet,
            "torrent_url": enclosure_url,
            "is_torrent": True,
        }

        return SearchResult(
            title=title,
            url=url,
            provider=self.name,
            publication_date=pub_date,
            raw_metadata={k: v for k, v in raw.items() if v is not None},
        )
