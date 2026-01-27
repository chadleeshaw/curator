"""
Newsnab provider for searching NZB indexers.
Supports Newsnab-compatible APIs like Prowlarr, NZBHydra, and others.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from core.constants.cache import UPLOAD_DATE_FORMATS
from core.constants.providers import (
    NEWSNAB_CATEGORY_MAP,
    NEWSNAB_DEFAULT_API_URL,
    NEWSNAB_DEFAULT_CATEGORIES,
    NEWSNAB_DEFAULT_MAX_REQUESTS_PER_HOUR,
    NEWSNAB_DEFAULT_RATE_LIMIT_WAIT,
    NEWSNAB_DEFAULT_REQUEST_DELAY,
    NEWSNAB_REQUEST_TIMEOUT,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
)
from core.interfaces import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class NewsnabProvider(SearchProvider):
    """Search provider for Newsnab indexers (Prowlarr aggregator, etc.)"""

    def __init__(self, config):
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

        if not self.api_key:
            raise ValueError("Newsnab provider requires api_key")

    def _check_rate_limit(self) -> bool:
        """
        Check if we're currently rate limited.

        Returns:
            True if rate limited, False otherwise
        """
        # Check if we're in a rate limit cooldown period
        if self._rate_limit_until and datetime.now() < self._rate_limit_until:
            remaining = (self._rate_limit_until - datetime.now()).total_seconds()
            logger.warning(
                f"[{self.name}] Rate limited: {self._rate_limit_reason}. "
                f"Will retry in {remaining:.0f} seconds ({remaining / 3600:.1f} hours)"
            )
            return True

        # Check if we've exceeded our self-imposed rate limit
        now = time.time()
        # Remove requests older than 1 hour
        self._request_times = [t for t in self._request_times if now - t < SECONDS_PER_HOUR]

        if len(self._request_times) >= self.max_requests_per_hour:
            oldest_request = min(self._request_times)
            wait_until = datetime.fromtimestamp(oldest_request + SECONDS_PER_HOUR)
            remaining = (wait_until - datetime.now()).total_seconds()
            logger.warning(
                f"[{self.name}] Self-imposed rate limit reached "
                f"({len(self._request_times)}/{self.max_requests_per_hour} requests in last hour). "
                f"Will retry in {remaining:.0f} seconds"
            )
            self._rate_limit_until = wait_until
            self._rate_limit_reason = f"Self-limit: {self.max_requests_per_hour} requests/hour exceeded"
            return True

        return False

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

    def search(self, query: str = "", category: str = None) -> List[SearchResult]:
        """
        Search Newsnab-compatible service for NZBs.

        Args:
            query: Magazine title to search for. Empty string triggers RSS mode.
            category: Optional category filter ("Magazines", "Comics", etc.)

        Returns:
            List of SearchResult objects
        """
        # Check if we're rate limited
        if self._check_rate_limit():
            logger.warning(f"[{self.name}] Skipping search for '{query}' - rate limited")
            return []

        results = []

        try:
            # Add delay between requests to avoid hitting rate limits
            if self.request_delay_seconds > 0 and self._request_times:
                time_since_last = time.time() - self._request_times[-1]
                if time_since_last < self.request_delay_seconds:
                    delay = self.request_delay_seconds - time_since_last
                    logger.debug(f"[{self.name}] Delaying {delay:.1f}s before search")
                    time.sleep(delay)

            # Track this request
            self._track_request()

            # Use XML API - it's more reliable and well-supported
            # (v1 JSON API often has issues with Prowlarr aggregators)
            # If query is empty, use RSS mode to fetch latest releases
            if not query or query.strip() == "":
                results = self._search_xml_api_rss(category)
            else:
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

            response = requests.get(url, params=params, timeout=NEWSNAB_REQUEST_TIMEOUT)

            # Check for rate limit errors (HTTP 429 or specific status codes)
            if response.status_code == 429:  # Too Many Requests
                wait_time = None
                # Check Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        pass

                if not wait_time:
                    wait_time = NEWSNAB_DEFAULT_RATE_LIMIT_WAIT

                self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                self._rate_limit_reason = "HTTP 429 Too Many Requests"
                logger.error(
                    f"[{self.name}] Rate limited by provider (HTTP 429). "
                    f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                )
                return []

            response.raise_for_status()

            # Check for error messages in XML response
            root = ET.fromstring(response.content)

            # Check for error element in response
            error_elem = root.find(".//error")
            if error_elem is not None:
                error_code = error_elem.get("code", "")
                error_desc = error_elem.get("description", error_elem.text or "")

                # Check if it's a rate limit error
                wait_time = self._parse_rate_limit_from_error(error_desc)
                if wait_time:
                    self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                    self._rate_limit_reason = f"Provider error: {error_desc}"
                    logger.error(
                        f"[{self.name}] Rate limited by provider: {error_desc}. "
                        f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                    )
                    return []
                else:
                    logger.warning(f"[{self.name}] API error: {error_desc} (code: {error_code})")
                    return []

            # Parse RSS/XML response
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                enclosure_elem = item.find("enclosure")
                pubdate_elem = item.find("pubDate")

                if title_elem is not None and title_elem.text:
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

                    # Extract category from newznab:attr elements
                    category_id = None
                    for attr in item.findall(".//{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"):
                        if attr.get("name") == "category":
                            category_id = attr.get("value")
                            break

                    raw_metadata = {
                        "indexer": item.findtext("indexer", ""),
                    }
                    if upload_date:
                        raw_metadata["upload_date"] = upload_date.isoformat()
                    if category_id:
                        raw_metadata["category"] = category_id

                    result = SearchResult(
                        title=title_elem.text,
                        url=nzb_url,
                        provider=self.type,
                        raw_metadata=raw_metadata,
                    )
                    results.append(result)

            logger.debug(
                f"Newsnab (XML API) found {len(results)} results for '{query}' in categories {self.categories}"
            )

        except requests.exceptions.HTTPError as e:
            # Check if it's a rate limit error in the response text
            if e.response is not None:
                try:
                    error_text = e.response.text
                    wait_time = self._parse_rate_limit_from_error(error_text)
                    if wait_time:
                        self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                        self._rate_limit_reason = f"HTTP {e.response.status_code}: Rate limit"
                        logger.error(
                            f"[{self.name}] Rate limited by provider (HTTP {e.response.status_code}). "
                            f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                        )
                        return []
                except Exception:
                    pass

            logger.error(f"Newsnab XML API HTTP error: {e}")

        except requests.exceptions.RequestException as e:
            logger.debug(f"Newsnab XML API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab XML parse error: {e}")

        return results

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
                "t": "rss",  # RSS mode instead of search
                "cat": cat_ids,
                # DO NOT include 'q' parameter in RSS mode
            }

            logger.debug(f"Newsnab RSS mode: categories={cat_ids}, url={url}")

            response = requests.get(url, params=params, timeout=NEWSNAB_REQUEST_TIMEOUT)

            # Check for rate limit errors (HTTP 429 or specific status codes)
            if response.status_code == 429:  # Too Many Requests
                wait_time = None
                # Check Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        pass

                if not wait_time:
                    wait_time = NEWSNAB_DEFAULT_RATE_LIMIT_WAIT

                self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                self._rate_limit_reason = "HTTP 429 Too Many Requests"
                logger.error(
                    f"[{self.name}] Rate limited by provider (HTTP 429). "
                    f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                )
                return []

            response.raise_for_status()

            # Check for error messages in XML response
            root = ET.fromstring(response.content)

            # Check for error element in response
            error_elem = root.find(".//error")
            if error_elem is not None:
                error_code = error_elem.get("code", "")
                error_desc = error_elem.get("description", error_elem.text or "")

                # Check if RSS mode is not supported (common with Prowlarr aggregators)
                if error_code == "202":
                    logger.info(f"[{self.name}] RSS mode not supported (error 202), falling back to broad search")
                    # Fall back to broad search query for periodicals
                    return self._search_xml_api_rss_fallback(category)

                # Check if it's a rate limit error
                wait_time = self._parse_rate_limit_from_error(error_desc)
                if wait_time:
                    self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                    self._rate_limit_reason = f"Provider error: {error_desc}"
                    logger.error(
                        f"[{self.name}] Rate limited by provider: {error_desc}. "
                        f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                    )
                    return []
                else:
                    logger.warning(f"[{self.name}] API error: {error_desc} (code: {error_code})")
                    return []

            # Parse RSS/XML response
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                enclosure_elem = item.find("enclosure")
                pubdate_elem = item.find("pubDate")
                guid_elem = item.find("guid")

                if title_elem is not None and title_elem.text:
                    # Get NZB URL from enclosure or link
                    nzb_url = ""
                    if enclosure_elem is not None:
                        nzb_url = enclosure_elem.get("url", "")
                    elif link_elem is not None:
                        nzb_url = link_elem.text or ""

                    # Parse upload_date from pubDate element (CRITICAL for cache ranking)
                    upload_date = None
                    if pubdate_elem is not None and pubdate_elem.text:
                        upload_date = self._parse_upload_date(pubdate_elem.text)

                    # Extract category from newznab:attr elements
                    category_id = None
                    for attr in item.findall(".//{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"):
                        if attr.get("name") == "category":
                            category_id = attr.get("value")
                            break

                    # Build raw_metadata
                    raw_metadata = {
                        "indexer": item.findtext("indexer", ""),
                    }
                    if upload_date:
                        raw_metadata["upload_date"] = upload_date.isoformat()
                    if category_id:
                        raw_metadata["category"] = category_id

                    # Include GUID for deduplication (if available)
                    if guid_elem is not None and guid_elem.text:
                        raw_metadata["guid"] = guid_elem.text

                    result = SearchResult(
                        title=title_elem.text,
                        url=nzb_url,
                        provider=self.type,
                        raw_metadata=raw_metadata,
                    )
                    results.append(result)

            logger.debug(f"Newsnab (RSS mode) found {len(results)} results in categories {cat_ids}")

        except requests.exceptions.HTTPError as e:
            # Check if it's a rate limit error in the response text
            if e.response is not None:
                try:
                    error_text = e.response.text

                    # Check if RSS mode is not supported (HTTP 400 with error code 202)
                    if e.response.status_code == 400 and 'code="202"' in error_text:
                        logger.info(
                            f"[{self.name}] RSS mode not supported (HTTP 400, code 202), "
                            f"falling back to broad search"
                        )
                        return self._search_xml_api_rss_fallback(category)

                    wait_time = self._parse_rate_limit_from_error(error_text)
                    if wait_time:
                        self._rate_limit_until = datetime.now() + timedelta(seconds=wait_time)
                        self._rate_limit_reason = f"HTTP {e.response.status_code}: Rate limit"
                        logger.error(
                            f"[{self.name}] Rate limited by provider (HTTP {e.response.status_code}). "
                            f"Will wait {wait_time} seconds (~{wait_time / 3600:.1f} hours)"
                        )
                        return []
                except Exception:
                    pass

            logger.error(f"Newsnab RSS API HTTP error: {e}")

        except requests.exceptions.RequestException as e:
            logger.debug(f"Newsnab RSS API error: {e}")
        except ET.ParseError as e:
            logger.debug(f"Newsnab RSS parse error: {e}")

        return results

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
        search_terms = [
            "magazine",
            "2024",
            "2025",
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
                return parsed_date
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
            response = requests.get(url, params=params, timeout=10)

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
                        "title": server_elem.get("title", "Unknown"),
                        "version": server_elem.get("version", "Unknown"),
                    }

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

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timeout - check your API URL and network",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Connection failed - check your API URL and network",
            }
        except requests.exceptions.HTTPError as e:
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
