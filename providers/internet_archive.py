"""
Internet Archive provider for searching archive.org.
Provides access to millions of free books, magazines, and periodicals.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from internetarchive import search_items, get_item

from core.constants.internet_archive import (
    IA_DEFAULT_MEDIATYPE,
    IA_DEFAULT_ROWS,
    IA_DEFAULT_SORT,
    IA_PERIODICAL_COLLECTIONS,
    IA_PREFERRED_FORMATS,
    IA_DEFAULT_REQUEST_DELAY,
    IA_DEFAULT_MAX_REQUESTS_PER_MINUTE,
    IA_SEARCH_TIMEOUT,
    IA_PROVIDER_TYPE,
    IA_SEARCH_FIELDS,
)
from core.interfaces import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class InternetArchiveProvider(SearchProvider):
    """Search provider for Internet Archive (archive.org)"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = IA_PROVIDER_TYPE

        # Configuration
        self.collections = config.get("collections", IA_PERIODICAL_COLLECTIONS)
        self.mediatype = config.get("mediatype", IA_DEFAULT_MEDIATYPE)
        self.preferred_formats = config.get("file_formats", IA_PREFERRED_FORMATS)
        self.max_results = config.get("max_results", IA_DEFAULT_ROWS)
        self.sort = config.get("sort", IA_DEFAULT_SORT)

        # Rate limiting
        self.request_delay = config.get("request_delay", IA_DEFAULT_REQUEST_DELAY)
        self.max_requests_per_minute = config.get("max_requests_per_minute", IA_DEFAULT_MAX_REQUESTS_PER_MINUTE)
        self._request_times: List[float] = []

        # Priority for provider preference (lower = higher priority)
        self.priority = config.get("priority", 10)

        logger.info(
            f"[{self.name}] Initialized with collections={self.collections}, "
            f"formats={self.preferred_formats}, priority={self.priority}"
        )

    def _check_rate_limit(self) -> bool:
        """
        Check if we're currently rate limited.

        Returns:
            True if rate limited, False otherwise
        """
        now = time.time()
        # Remove requests older than 1 minute
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self.max_requests_per_minute:
            logger.warning(
                f"[{self.name}] Rate limit reached ({len(self._request_times)}/{self.max_requests_per_minute} "
                f"requests in last minute)"
            )
            return True
        return False

    def _track_request(self):
        """Track a request for rate limiting"""
        self._request_times.append(time.time())

    def _apply_request_delay(self):
        """Apply delay between requests if needed"""
        if self.request_delay > 0 and self._request_times:
            time_since_last = time.time() - self._request_times[-1]
            if time_since_last < self.request_delay:
                delay = self.request_delay - time_since_last
                logger.debug(f"[{self.name}] Delaying {delay:.1f}s before request")
                time.sleep(delay)

    def _build_search_query(self, query: str, category: Optional[str] = None) -> str:
        """
        Build Internet Archive search query string.

        Args:
            query: User search query (periodical title)
            category: Optional category filter

        Returns:
            Formatted IA search query string
        """
        parts = []

        # Add title search
        if query:
            # Search in title field
            parts.append(f'title:("{query}")')

        # Add mediatype filter
        parts.append(f"mediatype:{self.mediatype}")

        # Add collection filter if collections specified
        if self.collections:
            collection_query = " OR ".join([f"collection:{c}" for c in self.collections])
            parts.append(f"({collection_query})")

        return " AND ".join(parts)

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse date string from Internet Archive metadata.

        Args:
            date_str: Date string in various formats

        Returns:
            Parsed datetime or None
        """
        if not date_str:
            return None

        # Try various date formats used by IA
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d",
            "%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str[: len(fmt.replace("%", ""))], fmt)
            except (ValueError, TypeError):
                continue

        return None

    def _get_best_file_format(self, item_metadata: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Find the best downloadable file from item metadata.

        Args:
            item_metadata: Item metadata from IA API

        Returns:
            Dict with 'name' and 'format' of best file, or None
        """
        files = item_metadata.get("files", [])
        if not files:
            return None

        # Build list of available files by format
        format_files = {}
        for f in files:
            fmt = f.get("format", "")
            name = f.get("name", "")
            if fmt and name:
                format_files.setdefault(fmt, []).append({"name": name, "format": fmt, "size": f.get("size", 0)})

        # Find best format in order of preference
        for preferred_fmt in self.preferred_formats:
            if preferred_fmt in format_files:
                # Return the first (usually only) file of this format
                return format_files[preferred_fmt][0]

        # Fallback: return any PDF-like format
        for fmt, files_list in format_files.items():
            if "pdf" in fmt.lower():
                return files_list[0]

        return None

    def search(self, query: str, category: Optional[str] = None) -> List[SearchResult]:
        """
        Search Internet Archive for periodicals.

        Args:
            query: Periodical title to search for
            category: Optional category filter (e.g., "Magazines", "Comics")

        Returns:
            List of SearchResult objects
        """
        if self._check_rate_limit():
            logger.warning(f"[{self.name}] Skipping search for '{query}' - rate limited")
            return []

        results = []

        try:
            self._apply_request_delay()
            self._track_request()

            # Build search query
            ia_query = self._build_search_query(query, category)
            logger.debug(f"[{self.name}] Searching: {ia_query}")

            # Execute search
            search_results = search_items(
                ia_query,
                fields=IA_SEARCH_FIELDS,
                sorts=[self.sort],
                rows=self.max_results,
                timeout=IA_SEARCH_TIMEOUT,
            )

            # Process results
            for item in search_results:
                try:
                    identifier = item.get("identifier")
                    if not identifier:
                        continue

                    title = item.get("title", identifier)
                    if isinstance(title, list):
                        title = title[0] if title else identifier

                    # Parse date
                    date_str = item.get("date")
                    if isinstance(date_str, list):
                        date_str = date_str[0] if date_str else None
                    publication_date = self._parse_date(date_str)

                    # Build metadata
                    raw_metadata = {
                        "identifier": identifier,
                        "creator": item.get("creator", ""),
                        "description": item.get("description", ""),
                        "collection": item.get("collection", []),
                        "mediatype": item.get("mediatype", ""),
                    }

                    # The URL is the item identifier - the client will resolve the actual file
                    result = SearchResult(
                        title=title,
                        url=identifier,  # Store identifier as URL, client will resolve
                        provider=self.type,
                        publication_date=publication_date,
                        raw_metadata=raw_metadata,
                    )
                    results.append(result)

                except Exception as e:
                    logger.warning(f"[{self.name}] Error parsing search result: {e}")
                    continue

            logger.info(f"[{self.name}] Found {len(results)} results for '{query}'")

        except Exception as e:
            logger.error(f"[{self.name}] Search error for '{query}': {e}", exc_info=True)

        return results

    def get_item_download_info(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Get download information for a specific item.

        Args:
            identifier: Internet Archive item identifier

        Returns:
            Dict with download URL and file info, or None
        """
        try:
            self._apply_request_delay()
            self._track_request()

            item = get_item(identifier)
            metadata = item.item_metadata

            # Find best file to download
            best_file = self._get_best_file_format(metadata)
            if not best_file:
                logger.warning(f"[{self.name}] No suitable file found for {identifier}")
                return None

            # Build download URL
            file_name = best_file["name"]
            download_url = f"https://archive.org/download/{identifier}/{file_name}"

            return {
                "identifier": identifier,
                "download_url": download_url,
                "file_name": file_name,
                "format": best_file["format"],
                "size": best_file.get("size", 0),
                "title": metadata.get("metadata", {}).get("title", identifier),
            }

        except Exception as e:
            logger.error(f"[{self.name}] Error getting item info for {identifier}: {e}")
            return None

    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Internet Archive.

        Returns:
            Dict with success status and message
        """
        try:
            # Try a simple search to verify connectivity
            test_results = search_items(
                "mediatype:texts",
                rows=1,
                timeout=10,
            )

            # Consume one result to verify the search works
            for _ in test_results:
                break

            return {
                "success": True,
                "message": "Connection to Internet Archive successful",
            }

        except Exception as e:
            logger.error(f"[{self.name}] Connection test failed: {e}")
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
            }
