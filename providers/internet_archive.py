"""
Internet Archive provider for searching archive.org.
Provides access to millions of free books, magazines, and periodicals.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from internetarchive import search_items, get_item, configure as ia_configure

from core.constants.internet_archive import (
    IA_CATEGORY_COLLECTION_MAP,
    IA_DEFAULT_MEDIATYPE,
    IA_DEFAULT_ROWS,
    IA_DEFAULT_SORT,
    IA_PERIODICAL_COLLECTIONS,
    IA_PREFERRED_FORMATS,
    IA_COLLECTION_FORMATS,
    IA_COLLECTION_KEYWORDS,
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

        # Optional authentication for accessing restricted items
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._configure_auth()

        logger.info(
            f"[{self.name}] Initialized with collections={self.collections}, "
            f"formats={self.preferred_formats}, priority={self.priority}, "
            f"authenticated={bool(self.username)}"
        )

    def _configure_auth(self):
        """
        Configure Internet Archive authentication if credentials provided.
        This enables access to restricted items that require login.
        """
        if self.username and self.password:
            try:
                config_path = ia_configure(self.username, self.password)
                logger.info(f"[{self.name}] Configured IA authentication for {self.username}")
                logger.debug(f"[{self.name}] IA config written to: {config_path}")
            except Exception as e:
                logger.error(f"[{self.name}] Failed to configure IA authentication: {e}")

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

    def _build_search_query(self, query: str, category: Optional[str] = None, include_collections: bool = True) -> str:
        """
        Build Internet Archive search query string.

        Args:
            query: User search query (periodical title)
            category: Optional category filter (narrows collections when provided)
            include_collections: Whether to filter by configured collections

        Returns:
            Formatted IA search query string
        """
        parts = []

        # Add title search - sanitize special characters for better matching
        if query:
            # Replace & with AND for better search compatibility
            sanitized_query = query.replace("&", " ")
            # Search in title field
            parts.append(f'title:("{sanitized_query}")')

        # Add mediatype filter
        parts.append(f"mediatype:{self.mediatype}")

        # Add collection filter if collections specified and requested
        if include_collections and self.collections:
            # If category specified, narrow to category-specific collections
            if category and category in IA_CATEGORY_COLLECTION_MAP:
                category_collections = [c for c in IA_CATEGORY_COLLECTION_MAP[category] if c in self.collections]
                # Fall back to all configured collections if no overlap
                collections = category_collections if category_collections else self.collections
            else:
                collections = self.collections
            collection_query = " OR ".join([f"collection:{c}" for c in collections])
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
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue

        # Try year-only as fallback if string starts with 4 digits
        if len(date_str) >= 4 and date_str[:4].isdigit():
            try:
                return datetime.strptime(date_str[:4], "%Y")
            except (ValueError, TypeError):
                pass

        return None

    def _is_collection_title(self, title: str) -> bool:
        """
        Check if the title indicates this is a collection archive.

        Args:
            title: Item title

        Returns:
            True if title suggests this is a collection
        """
        if not title:
            return False
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in IA_COLLECTION_KEYWORDS)

    def _get_available_formats(self, item_metadata: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build a dictionary of available files grouped by format.

        Args:
            item_metadata: Item metadata from IA API

        Returns:
            Dict mapping format name to list of file info dicts
        """
        files = item_metadata.get("files", [])
        format_files = {}
        for f in files:
            fmt = f.get("format", "")
            name = f.get("name", "")
            if fmt and name:
                size_str = f.get("size", "0")
                try:
                    size = int(size_str) if size_str else 0
                except (ValueError, TypeError):
                    size = 0
                format_files.setdefault(fmt, []).append({"name": name, "format": fmt, "size": size})
        return format_files

    def _has_collection_format(self, format_files: Dict[str, List[Dict[str, Any]]]) -> bool:
        """
        Check if the item has collection archive formats (ZIP, TAR, etc.)

        Args:
            format_files: Dict of available formats from _get_available_formats

        Returns:
            True if collection formats are available
        """
        return any(fmt in format_files for fmt in IA_COLLECTION_FORMATS)

    def _get_best_file_format(
        self, item_metadata: Dict[str, Any], prefer_collection: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best downloadable file from item metadata.

        Args:
            item_metadata: Item metadata from IA API
            prefer_collection: If True, prefer collection archive formats (ZIP, etc.)

        Returns:
            Dict with 'name', 'format', 'size', and 'is_collection' of best file, or None
        """
        format_files = self._get_available_formats(item_metadata)
        if not format_files:
            return None

        # If preferring collection, try collection formats first
        if prefer_collection:
            for collection_fmt in IA_COLLECTION_FORMATS:
                if collection_fmt in format_files:
                    file_info = format_files[collection_fmt][0]
                    file_info["is_collection"] = True
                    return file_info

        # Find best format in order of preference (individual files)
        for preferred_fmt in self.preferred_formats:
            if preferred_fmt in format_files:
                file_info = format_files[preferred_fmt][0]
                file_info["is_collection"] = False
                return file_info

        # Fallback: return any PDF-like format
        for fmt, files_list in format_files.items():
            if "pdf" in fmt.lower():
                file_info = files_list[0].copy()
                file_info["is_collection"] = False
                return file_info

        # Last resort: try collection formats even if not preferred
        for collection_fmt in IA_COLLECTION_FORMATS:
            if collection_fmt in format_files:
                file_info = format_files[collection_fmt][0]
                file_info["is_collection"] = True
                return file_info

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

            # Build search query with collection filter
            ia_query = self._build_search_query(query, category, include_collections=True)
            logger.debug(f"[{self.name}] Searching IA with query: {ia_query}")

            # Execute search
            # Note: rows is passed via params dict in newer internetarchive versions
            search_results = search_items(
                ia_query,
                fields=IA_SEARCH_FIELDS,
                sorts=[self.sort],
                params={"rows": self.max_results},
            )

            # Process results
            results = self._process_search_results(search_results, query)

            # If no results found and we have collection filters, try broader search
            if not results and self.collections:
                logger.info(
                    f"[{self.name}] No results in configured collections for '{query}', " f"trying broader search..."
                )
                self._apply_request_delay()
                self._track_request()

                ia_query_broad = self._build_search_query(query, category, include_collections=False)
                logger.debug(f"[{self.name}] Broad search query: {ia_query_broad}")

                search_results_broad = search_items(
                    ia_query_broad,
                    fields=IA_SEARCH_FIELDS,
                    sorts=[self.sort],
                    params={"rows": self.max_results},
                )
                results = self._process_search_results(search_results_broad, query)

                if results:
                    logger.info(f"[{self.name}] Found {len(results)} results in broader search for '{query}'")

        except Exception as e:
            logger.error(f"[{self.name}] Search error for '{query}': {e}", exc_info=True)

        return results

    def _process_search_results(self, search_results, query: str) -> List[SearchResult]:
        """
        Process search results from Internet Archive.

        Args:
            search_results: Iterator of search results from IA API
            query: Original search query (for logging)

        Returns:
            List of SearchResult objects
        """
        results = []
        result_count = 0
        skipped_no_format = 0

        for item in search_results:
            if result_count >= self.max_results:
                break
            try:
                identifier = item.get("identifier")
                if not identifier:
                    continue

                # Check if item has any preferred file formats
                available_formats = item.get("format", [])
                if isinstance(available_formats, str):
                    available_formats = [available_formats]

                has_preferred_format = False
                for preferred in self.preferred_formats:
                    preferred_lower = preferred.lower()
                    for fmt in available_formats:
                        if preferred_lower in fmt.lower():
                            has_preferred_format = True
                            break
                    if has_preferred_format:
                        break

                if not has_preferred_format:
                    skipped_no_format += 1
                    continue

                title = item.get("title", identifier)
                if isinstance(title, list):
                    title = title[0] if title else identifier

                # Parse date
                date_str = item.get("date")
                if isinstance(date_str, list):
                    date_str = date_str[0] if date_str else None
                publication_date = self._parse_date(date_str)

                # Detect if this is a collection based on title keywords or item_count
                is_collection = self._is_collection_title(title)

                # Get item_count for collection-type items (number of sub-items)
                item_count = item.get("item_count")
                if isinstance(item_count, str):
                    try:
                        item_count = int(item_count)
                    except (ValueError, TypeError):
                        item_count = None

                # Collections typically have item_count > 1 (bundle of multiple files)
                # Single issues usually have item_count = None, 0, or 1
                if item_count is not None and item_count > 1:
                    is_collection = True
                    logger.debug(f"[{self.name}] Detected collection by item_count={item_count}: {title}")

                # Build metadata
                raw_metadata = {
                    "identifier": identifier,
                    "creator": item.get("creator", ""),
                    "description": item.get("description", ""),
                    "collection": item.get("collection", []),
                    "mediatype": item.get("mediatype", ""),
                    "is_collection": is_collection,
                    "item_count": item_count,  # File/item count from IA API
                    "available_formats": available_formats,  # List of available formats
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
                result_count += 1

            except Exception as e:
                logger.warning(f"[{self.name}] Error parsing search result: {e}")
                continue

        if skipped_no_format > 0:
            logger.info(
                f"[{self.name}] Found {len(results)} results for '{query}' "
                f"(skipped {skipped_no_format} items without preferred formats)"
            )
        else:
            logger.info(f"[{self.name}] Found {len(results)} results for '{query}'")

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
                params={"rows": 1},
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
