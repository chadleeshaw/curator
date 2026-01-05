import logging
from typing import Any, Dict, List

import requests

from core.bases import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class CrossRefProvider(SearchProvider):
    """Search provider for CrossRef API - metadata about journals and publications"""

    def __init__(self, config):
        super().__init__(config)
        self.base_url = "https://api.crossref.org/v1"
        self.session = requests.Session()
        # Add user agent as per CrossRef API best practices
        self.session.headers.update(
            {
                "User-Agent": "Curator (https://github.com/yourusername/curator)",
            }
        )

    def search(self, query: str) -> List[SearchResult]:
        """
        Search CrossRef for journal/periodical metadata.

        Args:
            query: Magazine/journal title to search for

        Returns:
            List of SearchResult objects with publication metadata
        """
        results = []

        try:
            results = self._search_journals(query)
            if results:
                logger.info(
                    f"CrossRef search found {len(results)} results for '{query}'"
                )
                return results

        except Exception as e:
            logger.error(f"CrossRef search error: {e}")

        return results

    def _search_journals(self, query: str) -> List[SearchResult]:
        """Search for journals using CrossRef API"""
        results = []

        try:
            # Search journals endpoint
            url = f"{self.base_url}/journals"

            params = {
                "query": query,
                "rows": 20,
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            logger.debug(
                f"CrossRef API response for '{query}': {data.get('message', {}).get('total-results')} total results"
            )

            # Parse response
            if data.get("status") == "ok":
                items = data.get("message", {}).get("items", [])

                for item in items[:15]:  # Limit to 15 results
                    try:
                        result = self._parse_journal_item(item)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.debug(f"Error parsing CrossRef item: {e}")
                        continue

            logger.info(f"CrossRef API returned {len(results)} results for '{query}'")

        except requests.exceptions.RequestException as e:
            logger.warning(f"CrossRef API request failed: {e}")
        except Exception as e:
            logger.debug(f"CrossRef search error: {e}")

        return results

    def _parse_journal_item(self, item: Dict[str, Any]) -> SearchResult:
        """Parse a single journal item from CrossRef response"""
        try:
            # Extract title
            title = item.get("title")
            if not title:
                return None

            # Extract ISSN (prefer online, fall back to print)
            issn = None
            issn_list = item.get("ISSN", [])
            if issn_list:
                issn = issn_list[0]

            # Extract publisher
            publisher = item.get("publisher")

            # Extract URL
            url = item.get("URL")
            if not url:
                url = f"https://www.crossref.org/search?q={title.replace(' ', '+')}"

            # Extract publication dates
            coverage = item.get("coverage", {})
            coverage.get("coverageSince") if coverage else None

            if title and issn:
                result = SearchResult(
                    title=title,
                    url=url,
                    provider=self.type,
                    publication_date=None,
                    raw_metadata={
                        "issn": issn,
                        "publisher": publisher,
                        "issn_list": issn_list,
                        "coverage": coverage,
                        "source": "CrossRef API",
                        "crossref_id": item.get("ISSN-type"),
                    },
                )
                logger.debug(f"Added CrossRef result: {title} (ISSN: {issn})")
                return result

        except (KeyError, TypeError, IndexError) as e:
            logger.debug(f"Error parsing CrossRef journal item: {e}")

        return None
