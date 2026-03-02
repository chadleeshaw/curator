"""
Newsnab provider for searching NZB indexers.
Supports Newsnab-compatible APIs like Prowlarr, NZBHydra, and others.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import httpx

from core.constants.providers import (
    NEWSNAB_CATEGORY_MAP,
    NEWSNAB_DEFAULT_API_URL,
    NEWSNAB_DEFAULT_CATEGORIES,
    NEWSNAB_DEFAULT_MAX_REQUESTS_PER_HOUR,
    NEWSNAB_DEFAULT_RATE_LIMIT_WAIT,
    NEWSNAB_DEFAULT_REQUEST_DELAY,
    NEWSNAB_DEFAULT_SEARCH_LIMIT,
    NEWSNAB_REQUEST_TIMEOUT,
    NEWSNAB_RSS_MAX_RESULTS,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    UPLOAD_DATE_FORMATS,
    SECONDS_PER_MINUTE,
)
from core.interfaces import SearchProvider, SearchResult
from core.parsers import utc_now

logger = logging.getLogger(__name__)


class NewsnabProvider(SearchProvider):
    """Search provider for Newsnab indexers (Prowlarr aggregator, etc.)"""

    def __init__(self, config, **kwargs):
        super().__init__(config)
        api_url = config.get("api_url", NEWSNAB_DEFAULT_API_URL)

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
        self.categories = config.get("categories", NEWSNAB_DEFAULT_CATEGORIES)

        # Category name to Newznab ID mapping
        self.category_map = NEWSNAB_CATEGORY_MAP

        # Rate limiting configuration
        self.max_requests_per_hour = config.get("max_requests_per_hour", NEWSNAB_DEFAULT_MAX_REQUESTS_PER_HOUR)
        self.request_delay_seconds = config.get("request_delay_seconds", NEWSNAB_DEFAULT_REQUEST_DELAY)

        # Rate limit tracking
        self._request_times: List[float] = []
        self._rate_limit_until: Optional[datetime] = None
        self._rate_limit_reason: Optional[str] = None
        self._rate_limit_logged: bool = False

        # RSS mode configuration (used by FeedSyncService for cache-first auto-download)
        self.rss_max_results = config.get("rss_max_results", NEWSNAB_RSS_MAX_RESULTS)

        # Search result limit per API query
        self.search_limit = config.get("search_limit", NEWSNAB_DEFAULT_SEARCH_LIMIT)

        if not self.api_key:
            raise ValueError("Newsnab provider requires api_key")

    @property
    def is_rate_limited(self) -> bool:
        """Check if this provider is currently rate limited."""
        if self._rate_limit_until and utc_now() < self._rate_limit_until:
            return True
        # Also check self-imposed limit without setting state
        now = time.time()
        active_requests = [t for t in self._request_times if now - t < SECONDS_PER_HOUR]
        return len(active_requests) >= self.max_requests_per_hour

    def _check_rate_limit(self) -> bool:
        """
        Check if we're currently rate limited.

        Returns:
            True if rate limited, False otherwise
        """
        # Check self-imposed limit if no external rate limit is active
        if not self._rate_limit_until:
            return self._check_self_imposed_limit()

        # External rate limit active - check if cooldown expired
        if utc_now() >= self._rate_limit_until:
            self._clear_rate_limit_state()
            return False

        # Still in cooldown - log once and return True
        self._log_rate_limit_once()
        return True

    def _clear_rate_limit_state(self) -> None:
        """Clear rate limit state after cooldown expires."""
        logger.info(f"[{self.name}] Rate limit cooldown expired, resuming searches")
        self._rate_limit_until = None
        self._rate_limit_reason = None
        self._rate_limit_logged = False

    def _log_rate_limit_once(self) -> None:
        """Log rate limit warning once per cooldown period."""
        if self._rate_limit_logged:
            return

        remaining = (self._rate_limit_until - utc_now()).total_seconds()
        logger.warning(
            f"[{self.name}] Rate limited: {self._rate_limit_reason}. "
            f"Will retry in {remaining:.0f} seconds ({remaining / 3600:.1f} hours)"
        )
        self._rate_limit_logged = True

    def _check_self_imposed_limit(self) -> bool:
        """
        Check if we've exceeded our self-imposed rate limit.

        Returns:
            True if self-imposed limit is reached, False otherwise
        """
        now = time.time()
        self._request_times = [t for t in self._request_times if now - t < SECONDS_PER_HOUR]

        if len(self._request_times) < self.max_requests_per_hour:
            return False

        # Self-imposed limit reached - set cooldown
        oldest_request = min(self._request_times)
        wait_until = datetime.fromtimestamp(oldest_request + SECONDS_PER_HOUR, tz=UTC)
        remaining = (wait_until - utc_now()).total_seconds()

        logger.warning(
            f"[{self.name}] Self-imposed rate limit reached "
            f"({len(self._request_times)}/{self.max_requests_per_hour} requests in last hour). "
            f"Will retry in {remaining:.0f} seconds"
        )

        self._rate_limit_until = wait_until
        self._rate_limit_reason = f"Self-limit: {self.max_requests_per_hour} requests/hour exceeded"
        self._rate_limit_logged = False
        return True

    def _track_request(self):
        """Track a request for rate limiting"""
        self._request_times.append(time.time())

    def _parse_rate_limit_from_error(self, error_text: str) -> Optional[int]:
        """
        Parse rate limit wait time from error response.

        Newsnab providers return errors like:
        - "Request limit reached. Please wait X seconds"
        - "Too Many Requests. Retry after X seconds"
        - "Daily limit exceeded"

        Args:
            error_text: Error message from provider

        Returns:
            Wait time in seconds, or None if not rate limit error
        """
        # Pattern 1: "wait X seconds" or "retry after X seconds"
        match = re.search(r"(?:wait|retry after)\s+(\d+)\s+seconds?", error_text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Pattern 2: "wait X minutes"
        match = re.search(r"wait\s+(\d+)\s+minutes?", error_text, re.IGNORECASE)
        if match:
            return int(match.group(1)) * SECONDS_PER_MINUTE

        # Pattern 3: "wait X hours"
        match = re.search(r"wait\s+(\d+)\s+hours?", error_text, re.IGNORECASE)
        if match:
            return int(match.group(1)) * SECONDS_PER_HOUR

        # Pattern 4: "daily limit exceeded" - assume 24 hour wait
        if re.search(r"daily limit|per day|24.?hour", error_text, re.IGNORECASE):
            return SECONDS_PER_DAY

        # Pattern 5: "hourly limit exceeded" - assume 1 hour wait
        if re.search(r"hourly limit|per hour", error_text, re.IGNORECASE):
            return SECONDS_PER_HOUR

        return None

    def _handle_http_429(self, response: httpx.Response) -> bool:
        """
        Handle HTTP 429 Too Many Requests response.

        Sets rate limit state and logs appropriate warning.

        Args:
            response: HTTP response with 429 status

        Returns:
            True if rate limited (caller should return empty results)
        """
        wait_time = None
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                wait_time = int(retry_after)
            except ValueError:
                pass

        if not wait_time:
            wait_time = NEWSNAB_DEFAULT_RATE_LIMIT_WAIT

        self._rate_limit_until = utc_now() + timedelta(seconds=wait_time)
        self._rate_limit_reason = "HTTP 429 Too Many Requests"
        self._rate_limit_logged = False
        logger.error(
            f"[{self.name}] Rate limited by provider (HTTP 429). "
            f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
        )
        return True

    def _check_xml_error(self, root: ET.Element) -> Optional[str]:
        """
        Check XML response for error element and handle rate limits.

        Args:
            root: Parsed XML root element

        Returns:
            Error code if error found (caller should handle), None if no error
        """
        error_elem = root.find(".//error")
        if error_elem is None:
            return None

        error_code = error_elem.get("code", "")
        error_desc = error_elem.get("description", error_elem.text or "")

        # Check if it's a rate limit error
        wait_time = self._parse_rate_limit_from_error(error_desc)
        if wait_time:
            self._rate_limit_until = utc_now() + timedelta(seconds=wait_time)
            self._rate_limit_reason = f"Provider error: {error_desc}"
            self._rate_limit_logged = False
            logger.error(
                f"[{self.name}] Rate limited by provider: {error_desc}. "
                f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
            )
            return error_code

        logger.warning(f"[{self.name}] API error: {error_desc} (code: {error_code})")
        return error_code

    def _parse_xml_items(self, root: ET.Element, include_guid: bool = False) -> List[SearchResult]:
        """
        Parse RSS/XML items into SearchResult objects.

        Args:
            root: Parsed XML root element
            include_guid: Whether to include GUID in raw_metadata (for RSS mode deduplication)

        Returns:
            List of SearchResult objects
        """
        results = []

        for item in root.findall(".//item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            enclosure_elem = item.find("enclosure")
            pubdate_elem = item.find("pubDate")

            if title_elem is None or not title_elem.text:
                continue

            # Get NZB URL from enclosure or link
            nzb_url = ""
            if enclosure_elem is not None:
                nzb_url = enclosure_elem.get("url", "")
            elif link_elem is not None:
                nzb_url = link_elem.text or ""

            # Parse upload_date from pubDate element
            upload_date = None
            if pubdate_elem is not None and pubdate_elem.text:
                upload_date = self._parse_upload_date(pubdate_elem.text)

            # Extract metadata from newznab:attr elements (category, size, files)
            category_id = None
            nzb_size = None
            nzb_files = None
            for attr in item.findall(".//{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"):
                attr_name = attr.get("name")
                if attr_name == "category":
                    category_id = attr.get("value")
                elif attr_name == "size":
                    try:
                        nzb_size = int(attr.get("value", 0))
                    except (ValueError, TypeError):
                        pass
                elif attr_name == "files":
                    try:
                        nzb_files = int(attr.get("value", 0))
                    except (ValueError, TypeError):
                        pass

            # Fallback: get size from enclosure length attribute if not in attrs
            if nzb_size is None and enclosure_elem is not None:
                try:
                    nzb_size = int(enclosure_elem.get("length", 0)) or None
                except (ValueError, TypeError):
                    pass

            raw_metadata = {
                "indexer": item.findtext("indexer", ""),
            }
            if upload_date:
                raw_metadata["upload_date"] = upload_date.isoformat()
            if category_id:
                raw_metadata["category"] = category_id
            if nzb_size:
                raw_metadata["size"] = nzb_size
            if nzb_files:
                raw_metadata["files"] = nzb_files

            # Include GUID for deduplication (RSS mode)
            if include_guid:
                guid_elem = item.find("guid")
                if guid_elem is not None and guid_elem.text:
                    raw_metadata["guid"] = guid_elem.text

            result = SearchResult(
                title=title_elem.text,
                url=nzb_url,
                provider=self.type,
                publication_date=upload_date,
                raw_metadata=raw_metadata,
            )
            results.append(result)

        return results

    def _handle_http_error_rate_limit(self, http_error: httpx.HTTPStatusError) -> bool:
        """
        Check if HTTP error contains rate limit info and set state accordingly.

        Args:
            http_error: HTTPError exception

        Returns:
            True if rate limited (caller should return empty results)
        """
        if http_error.response is None:
            return False

        try:
            error_text = http_error.response.text
            wait_time = self._parse_rate_limit_from_error(error_text)
            if wait_time:
                self._rate_limit_until = utc_now() + timedelta(seconds=wait_time)
                self._rate_limit_reason = f"HTTP {http_error.response.status_code}: Rate limit"
                self._rate_limit_logged = False
                logger.error(
                    f"[{self.name}] Rate limited by provider (HTTP {http_error.response.status_code}). "
                    f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                )
                return True
        except Exception:
            pass

        return False

    def search(
        self,
        query: str = "",
        category: str = None,
        aliases: Optional[Sequence[str]] = None,
    ) -> List[SearchResult]:
        """
        Search Newsnab-compatible service for NZBs.

        First tries cached RSS feed (if caching enabled) to avoid API rate limiting.
        Falls back to API search if RSS doesn't yield results.

        Args:
            query: Magazine title to search for. Empty string triggers RSS mode.
            category: Optional category filter ("Magazines", "Comics", etc.)
            aliases: Optional alternative search terms to search individually

        Returns:
            List of SearchResult objects
        """
        results = []

        # If query is empty, use RSS mode to fetch latest releases
        if not query or query.strip() == "":
            if self._check_rate_limit():
                logger.warning(f"[{self.name}] Skipping RSS fetch - rate limited")
                return []
            return self._search_xml_api_rss(category)

        if self._check_rate_limit():
            logger.warning(f"[{self.name}] Skipping API search for '{query}' - rate limited")
            return []

        try:
            # Search with exact query (no expansion)
            search_query = query

            # Add delay between requests to avoid hitting rate limits
            if self.request_delay_seconds > 0 and self._request_times:
                time_since_last = time.time() - self._request_times[-1]
                if time_since_last < self.request_delay_seconds:
                    delay = self.request_delay_seconds - time_since_last
                    logger.debug(f"[{self.name}] Delaying {delay:.1f}s before search")
                    time.sleep(delay)

            # Track this request
            self._track_request()

            # Search with exact query
            results = self._search_xml_api(search_query, category)

            logger.debug(f"[{self.name}] Query '{search_query}' returned {len(results)} results")

            # Search each alias as a separate API call
            if aliases:
                seen_urls = {r.url for r in results}
                for alias in aliases:
                    alias = alias.strip()
                    if not alias or alias == query:
                        continue
                    try:
                        if self.request_delay_seconds > 0 and self._request_times:
                            time_since_last = time.time() - self._request_times[-1]
                            if time_since_last < self.request_delay_seconds:
                                delay = self.request_delay_seconds - time_since_last
                                time.sleep(delay)
                        self._track_request()
                        alias_results = self._search_xml_api(alias, category)
                        for r in alias_results:
                            if r.url not in seen_urls:
                                seen_urls.add(r.url)
                                results.append(r)
                        logger.debug(f"[{self.name}] Alias '{alias}' returned {len(alias_results)} results")
                    except Exception as e:
                        logger.warning(f"[{self.name}] Alias search error for '{alias}': {e}")

            return results

        except Exception as e:
            logger.error(f"Newsnab search error: {e}", exc_info=True)

        return results

    def _search_xml_api(self, query: str, category: str = None) -> List[SearchResult]:
        """Search using the legacy /api XML endpoint"""
        try:
            # Determine which categories to search
            cat_ids = self.categories  # Default: all configured categories

            if category and category in self.category_map:
                cat_ids = self.category_map[category]
                logger.debug(f"Using category filter: {category} -> {cat_ids}")

            url = f"{self.api_url}/api"
            params = {
                "apikey": self.api_key,
                "t": "search",
                "q": query,
                "cat": cat_ids,
                "limit": self.search_limit,
            }

            logger.debug(f"Newsnab searching: query='{query}', categories={cat_ids}, url={url}")

            response = httpx.get(url, params=params, timeout=NEWSNAB_REQUEST_TIMEOUT)

            if response.status_code == 429:
                self._handle_http_429(response)
                return []

            response.raise_for_status()

            root = ET.fromstring(response.content)

            if self._check_xml_error(root) is not None:
                return []

            results = self._parse_xml_items(root, include_guid=False)

            logger.debug(
                f"Newsnab (XML API) found {len(results)} results for '{query}' in categories {self.categories}"
            )
            return results

        except httpx.HTTPStatusError as e:
            if self._handle_http_error_rate_limit(e):
                return []
            logger.error(f"Newsnab XML API HTTP error: {e}")

        except httpx.HTTPError as e:
            logger.debug(f"Newsnab XML API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab XML parse error: {e}")

        return []

    def _search_xml_api_rss(self, category: str = None) -> List[SearchResult]:
        """
        Search using the RSS mode (fetch latest releases without query).

        This method is used for cache sync operations to fetch the latest
        releases from the provider without a specific search query.

        Args:
            category: Optional category filter

        Returns:
            List of SearchResult objects
        """
        try:
            # Determine which categories to search
            cat_ids = self.categories  # Default: all configured categories

            if category and category in self.category_map:
                cat_ids = self.category_map[category]
                logger.debug(f"Using category filter: {category} -> {cat_ids}")

            url = f"{self.api_url}/api"
            params = {
                "apikey": self.api_key,
                "t": "search",  # Standard search endpoint
                "cat": cat_ids,
                "limit": self.rss_max_results,  # Limit results for RSS mode
                # DO NOT include 'q' parameter = latest releases
            }

            logger.debug(f"Newsnab RSS mode: categories={cat_ids}, url={url}")

            response = httpx.get(url, params=params, timeout=NEWSNAB_REQUEST_TIMEOUT)

            if response.status_code == 429:
                self._handle_http_429(response)
                return []

            response.raise_for_status()

            root = ET.fromstring(response.content)

            # Check for errors, with special handling for RSS-not-supported (code 202)
            error_elem = root.find(".//error")
            if error_elem is not None:
                error_code = error_elem.get("code", "")
                if error_code == "202":
                    logger.info(f"[{self.name}] RSS mode not supported (error 202), falling back to broad search")
                    return self._search_xml_api_rss_fallback(category)

                # Use standard error handling for other errors
                if self._check_xml_error(root) is not None:
                    return []

            results = self._parse_xml_items(root, include_guid=True)

            logger.debug(f"Newsnab (RSS mode) found {len(results)} results in categories {cat_ids}")
            return results

        except httpx.HTTPStatusError as e:
            # Check if RSS mode is not supported (HTTP 400 with error code 202)
            if e.response is not None and e.response.status_code == 400:
                try:
                    if 'code="202"' in e.response.text:
                        logger.info(
                            f"[{self.name}] RSS mode not supported (HTTP 400, code 202), "
                            f"falling back to broad search"
                        )
                        return self._search_xml_api_rss_fallback(category)
                except Exception:
                    pass

            if self._handle_http_error_rate_limit(e):
                return []
            logger.error(f"Newsnab RSS API HTTP error: {e}")

        except httpx.HTTPError as e:
            logger.debug(f"Newsnab RSS API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab RSS parse error: {e}")

        return []

    def _search_xml_api_rss_fallback(self, category: str = None) -> List[SearchResult]:
        """
        Fallback search method for providers that don't support RSS mode (like Prowlarr).

        Uses broad search queries to fetch recent releases across periodical categories.
        This is less efficient than RSS mode but works with Prowlarr aggregators.

        Args:
            category: Optional category filter

        Returns:
            List of SearchResult objects
        """
        logger.info(f"[{self.name}] Using RSS fallback: broad search for latest periodicals")

        # Use a set of broad search terms that cover most periodicals
        # These are common words that appear in magazine/periodical releases
        from datetime import datetime as _dt

        current_year = _dt.now().year
        search_terms = [
            "magazine",
            str(current_year),
            str(current_year - 1),
            "weekly",
            "monthly",
        ]

        all_results = []
        seen_guids = set()

        # Try a few broad searches to get a diverse set of recent releases
        for term in search_terms[:2]:  # Limit to 2 searches to avoid excessive API calls
            try:
                results = self._search_xml_api(term, category)

                # Deduplicate by GUID
                for result in results:
                    guid = result.raw_metadata.get("guid") if result.raw_metadata else None
                    if guid and guid not in seen_guids:
                        seen_guids.add(guid)
                        all_results.append(result)
                    elif not guid:
                        # No GUID, add anyway (will be deduped later by cache service)
                        all_results.append(result)

                # Stop if we have enough results
                if len(all_results) >= 100:
                    break

            except Exception as e:
                logger.warning(f"[{self.name}] RSS fallback search failed for '{term}': {e}")
                continue

        logger.info(
            f"[{self.name}] RSS fallback retrieved {len(all_results)} results "
            f"from {len(search_terms[:2])} search terms"
        )

        return all_results[:100]  # Limit to 100 results

    def _parse_upload_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse upload date from provider response.

        Tries multiple date formats commonly used by Newsnab providers.

        Args:
            date_str: Date string from provider (e.g., pubDate element)

        Returns:
            Parsed datetime object, or None if parsing fails
        """
        for date_format in UPLOAD_DATE_FORMATS:
            try:
                # Try parsing with the current format
                parsed_date = datetime.strptime(date_str.strip(), date_format)
                # Make timezone-aware (assume UTC)
                return parsed_date.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue

        # If all formats fail, log warning and return None
        logger.debug(f"[{self.name}] Failed to parse upload date: {date_str}")
        return None

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to the Newsnab provider.

        Returns:
            Dict with success status and message
        """
        try:
            # Try to hit the capabilities endpoint or a simple search
            url = f"{self.api_url}/api"
            params = {
                "apikey": self.api_key,
                "t": "caps",  # Capabilities endpoint - lightweight test
            }

            logger.info(f"Testing Newsnab connection to {url}")
            response = httpx.get(url, params=params, timeout=NEWSNAB_REQUEST_TIMEOUT)

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed - check your API key",
                    "status_code": 401,
                }

            if response.status_code == 404:
                return {
                    "success": False,
                    "message": "API endpoint not found - check your API URL",
                    "status_code": 404,
                }

            if response.status_code == 410:
                return {
                    "success": False,
                    "message": "Request rejected (410 Gone) - indexer may be down, account suspended, or API key revoked",
                    "status_code": 410,
                }

            response.raise_for_status()

            # Check if response is valid XML
            try:
                root = ET.fromstring(response.content)

                # Check for error in response
                error_elem = root.find(".//error")
                if error_elem is not None:
                    error_desc = error_elem.get("description", error_elem.text or "Unknown error")
                    return {
                        "success": False,
                        "message": f"API error: {error_desc}",
                    }

                # Success - check for server info if available
                server_elem = root.find(".//server")
                server_info = {}
                if server_elem is not None:
                    server_info = {
                        "title": server_elem.get("title"),
                        "version": server_elem.get("version"),
                    }
                    server_info = {k: v for k, v in server_info.items() if v}

                return {
                    "success": True,
                    "message": "Connection successful",
                    "server_info": server_info if server_info else None,
                }

            except ET.ParseError as e:
                return {
                    "success": False,
                    "message": f"Invalid XML response: {str(e)}",
                }

        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Connection timeout - check your API URL and network",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "message": "Connection failed - check your API URL and network",
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "message": f"HTTP error: {e.response.status_code}",
                "status_code": e.response.status_code,
            }
        except Exception as e:
            logger.error(f"Newsnab connection test error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}",
            }
