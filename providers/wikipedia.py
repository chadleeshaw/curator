import logging
import re
from typing import Any, Dict, List

import requests

from core.bases import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class WikipediaProvider(SearchProvider):
    """Search provider for Wikipedia periodical metadata"""

    def __init__(self, config):
        super().__init__(config)
        self.base_url = "https://en.wikipedia.org/w/api.php"

    def search(self, query: str) -> List[SearchResult]:
        """
        Search Wikipedia for periodical metadata.

        Args:
            query: Magazine title to search for

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            # Search Wikipedia for the periodical
            results = self._search_wikipedia(query)

            if results:
                logger.info(f"Wikipedia search found {len(results)} results for '{query}'")

        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")

        return results

    def _search_wikipedia(self, query: str) -> List[SearchResult]:
        """Search Wikipedia using MediaWiki API"""
        results = []

        try:
            # First, search for pages matching the query
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": "0",  # Only article namespace
                "srlimit": "10",
                "format": "json"
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Magazine Curator)"
            }

            response = requests.get(self.base_url, params=search_params, headers=headers, timeout=10)
            response.raise_for_status()

            search_data = response.json()
            search_results = search_data.get("query", {}).get("search", [])

            # For each search result, get full page content
            for search_item in search_results[:5]:  # Limit to top 5 results
                title = search_item.get("title", "").strip()
                page_id = search_item.get("pageid", 0)

                if not title or not page_id:
                    continue

                # Get full page content
                page_data = self._get_page_info(page_id)
                if page_data:
                    result = SearchResult(
                        title=page_data["title"],
                        url=f"https://en.wikipedia.org/wiki/{page_data['title'].replace(' ', '_')}",
                        provider=self.type,
                        raw_metadata=page_data["metadata"]
                    )
                    results.append(result)

        except requests.exceptions.RequestException as e:
            logger.warning(f"Wikipedia search failed: {e}")
        except Exception as e:
            logger.error(f"Error parsing Wikipedia response: {e}")

        return results

    def _get_page_info(self, page_id: int) -> Dict[str, Any]:
        """Get detailed page information from Wikipedia"""
        try:
            # Get page content - use extracts to get full text
            page_params = {
                "action": "query",
                "pageids": page_id,
                "prop": "extracts|info",
                "explaintext": True,
                "exlimit": "max",  # Get full extract
                "inprop": "url",
                "format": "json"
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Magazine Curator)"
            }

            response = requests.get(self.base_url, params=page_params, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            page = list(pages.values())[0] if pages else None

            if not page:
                return None

            title = page.get("title", "")
            extract = page.get("extract", "")
            url = page.get("canonicalurl", "")

            # Also fetch the HTML page directly to extract ISSN from infobox
            # since the plain text extract doesn't include infobox data
            html_metadata = self._extract_metadata_from_html(title)

            # Extract metadata from the page content
            metadata = self._extract_metadata(title, extract)

            # Merge with HTML-extracted metadata (HTML metadata takes priority for ISSN)
            if html_metadata.get("issn") and not metadata.get("issn"):
                metadata["issn"] = html_metadata["issn"]
            if html_metadata.get("publisher") and not metadata.get("publisher"):
                metadata["publisher"] = html_metadata["publisher"]

            metadata["url"] = url
            metadata["source"] = "Wikipedia"

            return {
                "title": title,
                "url": url,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Error getting Wikipedia page info: {e}")
            return None

    def _extract_metadata_from_html(self, title: str) -> Dict[str, Any]:
        """Extract metadata from Wikipedia HTML page (infobox)"""
        metadata = {"issn": "", "publisher": ""}

        try:
            # Fetch the Wikipedia page HTML directly
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            headers = {"User-Agent": "Mozilla/5.0 (Magazine Curator)"}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            html = response.text

            # Extract ISSN from the HTML infobox
            # Pattern: ISSN link containing the ISSN number
            issn_patterns = [
                r"ISSN.*?</a></th><td[^>]*>.*?([0-9]{4}-[0-9]{3}[0-9X])",
                r"<a[^>]*href=\"[^\"]*n2:([0-9]{4}-[0-9]{3}[0-9X])\"",
                r">([0-9]{4}-[0-9]{3}[0-9X])</a>.*?ISSN",
            ]

            for pattern in issn_patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    metadata["issn"] = match.group(1).upper()
                    logger.debug(f"Found ISSN from HTML: {metadata['issn']}")
                    break

            # Extract publisher from HTML if present
            pub_pattern = r"[Pp]ublisher[^<]*</.*?<td[^>]*>([^<]+)"
            pub_match = re.search(pub_pattern, html, re.IGNORECASE)
            if pub_match:
                metadata["publisher"] = pub_match.group(1).strip()
                logger.debug(f"Found publisher from HTML: {metadata['publisher']}")

        except Exception as e:
            logger.debug(f"Error extracting metadata from HTML: {e}")

        return metadata

    def _extract_metadata(self, title: str, extract: str) -> Dict[str, Any]:
        """Extract metadata from Wikipedia page content"""
        metadata = {
            "title": title,
            "publisher": "",
            "issn": "",
            "country": "",
            "frequency": ""
        }

        if not extract:
            return metadata

        # Try to find publisher information
        publisher_patterns = [
            r"published by\s+([^,.\n]+)",
            r"publisher[:\s]+([^,.\n]+)",
            r"published[:\s]+([^,.\n]+)",
            r"owner[:\s]+([^,.\n]+)",
        ]

        for pattern in publisher_patterns:
            match = re.search(pattern, extract, re.IGNORECASE)
            if match:
                pub = match.group(1).strip()
                # Filter out bad matches
                if len(pub) < 100 and not pub.startswith("the "):
                    metadata["publisher"] = pub
                    break

        # Try to find ISSN - more aggressive patterns to catch Wikipedia's format
        # Wikipedia often shows ISSN in the info box with label "ISSN" followed by numbers
        issn_patterns = [
            r"(?:ISSN|issn)[\s:]+([0-9]{4}[\s-]?[0-9]{3}[\s-]?[0-9X])",  # ISSN: 1080-4471 or ISSN 1080 4471
            r"^ISSN\s+([0-9\-]{9,11})",  # Start of line, with variable spacing
            r"\bISSN\b\s*[=:]\s*([0-9]{4}[\s-]?[0-9]{3}[\s-]?[0-9X])",  # ISSN with = or :
            r"(?:ISSN|issn|print|online)[\s=:]+([0-9]{4}[\s-]?[0-9]{3}[\s-]?[0-9X])",  # Print/online variants
            r"([0-9]{4}[\s-]?[0-9]{3}[\s-]?[0-9X])(?:\s|$)",  # Just the ISSN format without label (last resort)
        ]

        # Search line by line for better accuracy
        lines = extract.split('\n')

        logger.debug(f"Searching for ISSN in {len(lines)} lines of Wikipedia extract")

        for i, line in enumerate(lines):
            # Skip very short lines that are unlikely to contain ISSN info
            if len(line.strip()) < 5:
                continue

            for pattern_idx, pattern in enumerate(issn_patterns):
                issn_match = re.search(pattern, line, re.IGNORECASE)
                if issn_match:
                    issn = issn_match.group(1).strip().replace(' ', '-').upper()
                    # Validate it looks like an ISSN (4 digits, hyphen, 3 digits, 1 digit or X)
                    if re.match(r"^\d{4}-\d{3}[\dX]$", issn):
                        metadata["issn"] = issn
                        logger.debug(f"Found ISSN '{issn}' on line {i + 1} (pattern {pattern_idx}): {line[:80]}")
                        break

            if metadata["issn"]:
                break

        # Also try searching in the whole text if not found in lines
        if not metadata["issn"]:
            logger.debug("ISSN not found in line-by-line search, trying whole text")
            for pattern in issn_patterns:
                issn_match = re.search(pattern, extract, re.IGNORECASE)
                if issn_match:
                    issn = issn_match.group(1).strip().replace(' ', '-').upper()
                    if re.match(r"^\d{4}-\d{3}[\dX]$", issn):
                        metadata["issn"] = issn
                        logger.debug(f"Found ISSN '{issn}' in full text")
                        break

        if not metadata["issn"]:
            logger.debug(f"No ISSN found for '{title}' in Wikipedia extract")

        # Try to find country information
        country_patterns = [
            r"based in\s+([^,.\n]+)",
            r"from\s+([^,.\n]+)",
            r"country[:\s]+([^,.\n]+)",
            r"(?:United Kingdom|United States|Canada|Australia|France|Germany|Japan|India)\b",
        ]

        for pattern in country_patterns:
            match = re.search(pattern, extract, re.IGNORECASE)
            if match:
                if match.lastindex:
                    metadata["country"] = match.group(1).strip()
                else:
                    metadata["country"] = match.group(0).strip()
                break

        # Try to find publication frequency
        frequency_patterns = [
            r"published\s+(\w+ly)",  # Monthly, Weekly, etc
            r"frequency[:\s]+([^,.\n]+)",
            r"(?:monthly|weekly|daily|quarterly|bi-weekly|bi-monthly|annually)\b",
        ]

        for pattern in frequency_patterns:
            match = re.search(pattern, extract, re.IGNORECASE)
            if match:
                if match.lastindex:
                    metadata["frequency"] = match.group(1).strip()
                else:
                    metadata["frequency"] = match.group(0).strip()
                break

        return metadata
