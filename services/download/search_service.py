"""
Search service for periodical issues across providers.
Handles provider search with timeout, parsing, and filtering.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from core.interfaces import SearchProvider
from core.constants.app import PROVIDER_SEARCH_TIMEOUT
from core.parsers import Parser, TitleMatcher, LANGUAGE_INDICATORS

logger = logging.getLogger(__name__)


class SearchService:
    """Service for searching periodical issues across providers"""

    def __init__(self, search_providers: List[SearchProvider], fuzzy_threshold: int = 80):
        """
        Initialize search service.

        Args:
            search_providers: List of search providers to use
            fuzzy_threshold: Fuzzy matching threshold for title matching
        """
        self.search_providers = search_providers
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

    def search_periodical_issues(self, periodical_title: str, session: Session) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.

        Args:
            periodical_title: Title of the periodical to search for (may include language)
            session: Database session (for compatibility, not currently used)

        Returns:
            List of search results with deduplication grouping
        """
        search_title = periodical_title
        language_filter = None

        # Extract language filter from title if present
        language_names = "|".join([lang.capitalize() for lang in LANGUAGE_INDICATORS.keys()])
        language_pattern = rf"\s+-\s+({language_names})$"
        match = re.search(language_pattern, periodical_title, re.IGNORECASE)

        if match:
            search_title = periodical_title[: match.start()].strip()
            language_filter = match.group(1)
            logger.info(f"Searching for '{search_title}' with language filter: {language_filter}")

        all_results = []

        with ThreadPoolExecutor(max_workers=1) as executor:
            for provider in self.search_providers:
                try:
                    logger.debug(f"Searching {provider.name} for: {search_title}")

                    # Execute search with timeout
                    future = executor.submit(provider.search, search_title)
                    try:
                        results = future.result(timeout=PROVIDER_SEARCH_TIMEOUT)
                    except FuturesTimeoutError:
                        logger.warning(
                            f"Search timeout ({PROVIDER_SEARCH_TIMEOUT}s) for {provider.name} "
                            f"searching '{periodical_title}'"
                        )
                        continue

                    for result in results:
                        # Parse search result using unified parser
                        parsed = self.parser.parse_search_result(
                            title=result.title,
                            url=result.url,
                            provider=result.provider,
                            publication_date=result.publication_date,
                            raw_metadata=result.raw_metadata,
                        )

                        # Skip if parser rejected as non-periodical (movies/TV/audiobooks)
                        if parsed is None:
                            logger.debug(f"Skipping non-periodical result: {result.title}")
                            continue

                        # Apply language filter if specified
                        if language_filter and parsed.language != language_filter:
                            continue

                        # Apply edition variant filter
                        normalized_search = search_title.replace(".", " ").replace("_", " ")
                        normalized_result = parsed.title.replace(".", " ").replace("_", " ")

                        search_variant = self.title_matcher._extract_edition_variant(normalized_search)
                        result_variant = self.title_matcher._extract_edition_variant(normalized_result)

                        # Skip results with mismatched edition variants
                        if not (
                            (search_variant is None and result_variant is None)
                            or (
                                search_variant is not None
                                and result_variant is not None
                                and search_variant == result_variant
                            )
                        ):
                            logger.debug(
                                f"Skipping edition variant mismatch: '{parsed.title}' (variant: {result_variant}) "
                                f"doesn't match search '{search_title}' (variant: {search_variant})"
                            )
                            continue

                        all_results.append(
                            {
                                "title": parsed.title,
                                "original_title": parsed.original_title,
                                "url": parsed.url,
                                "provider": parsed.provider,
                                "publication_date": parsed.publication_date,
                                "raw_metadata": parsed.raw_metadata,
                            }
                        )

                except Exception as e:
                    logger.error(f"Error searching {provider.name} for '{periodical_title}': {e}")

        logger.debug(
            f"Found {len(all_results)} results for '{periodical_title}' across {len(self.search_providers)} providers"
        )
        return all_results
