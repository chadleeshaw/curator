"""
Search service for periodical issues across providers.
Handles provider search with timeout, parsing, and filtering.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.interfaces import SearchProvider
from core.constants.app import PROVIDER_SEARCH_TIMEOUT
from core.parsers import Parser, TitleMatcher, LANGUAGE_INDICATORS
from core.utils.fuzzy_matching import get_fuzzy_group_id

logger = logging.getLogger(__name__)


class SearchService:
    """Service for searching periodical issues across providers"""

    # Default priority for providers without explicit priority
    DEFAULT_PROVIDER_PRIORITY = 50

    def __init__(self, search_providers: List[SearchProvider], fuzzy_threshold: int = 80):
        """
        Initialize search service.

        Args:
            search_providers: List of search providers to use
            fuzzy_threshold: Fuzzy matching threshold for title matching
        """
        # Sort providers by priority (lower = higher priority, searched first)
        self.search_providers = sorted(
            search_providers, key=lambda p: getattr(p, "priority", self.DEFAULT_PROVIDER_PRIORITY)
        )
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

        # Log provider order
        provider_info = [
            (p.name, getattr(p, "priority", self.DEFAULT_PROVIDER_PRIORITY)) for p in self.search_providers
        ]
        logger.info(f"SearchService initialized with providers (by priority): {provider_info}")

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

                        # Skip IA collection archives (they contain many issues, not single issues)
                        raw_metadata = result.raw_metadata or {}
                        if raw_metadata.get("is_collection"):
                            logger.debug(f"Skipping IA collection archive: {result.title}")
                            continue

                        # For IA results, verify title actually matches the periodical we're searching for
                        # IA returns items where search term appears anywhere in metadata, not just title
                        if result.provider == "internet_archive":
                            # Check if the search title appears in the result title
                            result_title_lower = result.title.lower()
                            search_terms = search_title.lower().split()
                            # Require all significant search terms (3+ chars) to be in the title
                            significant_terms = [t for t in search_terms if len(t) >= 3]
                            if significant_terms:
                                matching_terms = sum(1 for t in significant_terms if t in result_title_lower)
                                match_ratio = matching_terms / len(significant_terms)
                                if match_ratio < 0.5:
                                    logger.debug(
                                        f"Skipping IA result with poor title match: '{result.title}' "
                                        f"(searching for '{search_title}', match ratio: {match_ratio:.1%})"
                                    )
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

        # Deduplicate results, preferring higher priority providers
        deduplicated = self._deduplicate_with_provider_preference(all_results)

        logger.debug(
            f"Found {len(all_results)} results for '{periodical_title}' across {len(self.search_providers)} providers "
            f"({len(deduplicated)} after deduplication)"
        )
        return deduplicated

    def _deduplicate_with_provider_preference(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate search results, keeping results from preferred providers.

        When multiple providers return the same item (based on fuzzy title matching),
        keep the result from the higher priority provider (lower priority number).

        Args:
            results: List of search result dicts

        Returns:
            Deduplicated list with preferred provider results
        """
        if not results:
            return []

        # Get provider priorities for sorting
        provider_priorities = {
            p.type: getattr(p, "priority", self.DEFAULT_PROVIDER_PRIORITY) for p in self.search_providers
        }

        # Group results by fuzzy match (including publication date for uniqueness)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for result in results:
            group_id = get_fuzzy_group_id(result["title"], result.get("publication_date"))
            groups.setdefault(group_id, []).append(result)

        # For each group, keep the result from highest priority provider
        deduplicated = []
        for group_id, group_results in groups.items():
            if len(group_results) == 1:
                deduplicated.append(group_results[0])
            else:
                # Sort by provider priority (lower = better)
                group_results.sort(
                    key=lambda r: provider_priorities.get(r.get("provider"), self.DEFAULT_PROVIDER_PRIORITY)
                )
                best_result = group_results[0]
                deduplicated.append(best_result)

                # Log when we prefer one provider over another
                if len(group_results) > 1:
                    other_providers = [r.get("provider") for r in group_results[1:]]
                    logger.debug(
                        f"Dedup: keeping '{best_result['title']}' from {best_result.get('provider')} "
                        f"over {other_providers}"
                    )

        return deduplicated
