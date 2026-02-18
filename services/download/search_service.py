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
from core.utils.ia_filtering import filter_ia_result

logger = logging.getLogger(__name__)


class SearchService:
    """Service for searching periodical issues across providers"""

    # Default priority for providers without explicit priority
    DEFAULT_PROVIDER_PRIORITY = 50

    def __init__(self, search_providers: List[SearchProvider], fuzzy_threshold: int = 80):
        """
        Initialize search service.

        Args:
            search_providers: List of search provider instances (Newsnab, InternetArchive, RSS)
            fuzzy_threshold: Threshold for fuzzy title matching (0-100)
        """
        self.search_providers = search_providers
        self.parser = Parser()
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

    def search_periodical_issues(
        self,
        periodical_title: str,
        session: Session,
        aliases: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.

        Args:
            periodical_title: Title of the periodical to search for (may include language)
            session: Database session
            aliases: Optional list of alternative search terms (e.g., from tracking record)

        Returns:
            List of search results with deduplication
        """
        search_title = periodical_title
        language_filter = None

        # Extract language filter from title if present
        # Pattern: "Title - Language" where Language is one of the supported languages
        language_names = "|".join([lang.capitalize() for lang in LANGUAGE_INDICATORS.keys()])
        language_pattern = rf"\s+-\s+({language_names})$"
        match = re.search(language_pattern, periodical_title, re.IGNORECASE)

        if match:
            search_title = periodical_title[: match.start()].strip()
            language_filter = match.group(1).capitalize()  # Normalize to capitalized form
            logger.info(f"Searching for '{search_title}' with language filter: {language_filter}")

        all_results = []
        provider_errors = []

        # Use ThreadPoolExecutor to search providers in parallel
        with ThreadPoolExecutor(max_workers=len(self.search_providers)) as executor:
            for provider in self.search_providers:
                try:
                    logger.debug(f"Searching {provider.name} for: {search_title}")

                    # Execute search with timeout, passing aliases for RSS cache matching and IA OR queries
                    future = executor.submit(provider.search, search_title, None, aliases)
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

                        # Filter IA collection archives and poor title matches
                        if not filter_ia_result(
                            result_title=result.title,
                            result_provider=result.provider,
                            raw_metadata=result.raw_metadata,
                            search_query=search_title,
                        ):
                            continue

                        # Apply language filter if specified
                        if language_filter and parsed.language != language_filter:
                            logger.debug(
                                f"Skipping result with language '{parsed.language}' "
                                f"(filter: {language_filter}): {result.title}"
                            )
                            continue

                        # Apply edition variant filter
                        normalized_search = search_title.replace(".", " ").replace("_", " ")
                        normalized_result = parsed.title.replace(".", " ").replace("_", " ")

                        search_variant = self.title_matcher.extract_edition_variant(normalized_search)
                        result_variant = self.title_matcher.extract_edition_variant(normalized_result)

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
                                "fuzzy_match_group_id": get_fuzzy_group_id(parsed.title),
                            }
                        )

                except Exception as e:
                    logger.error(f"Error searching {provider.name} for '{periodical_title}': {e}")
                    provider_errors.append({"provider": provider.name, "error": str(e)})

        # Log provider errors summary if any occurred
        if provider_errors:
            logger.warning(
                f"Provider errors during search for '{periodical_title}': " f"{len(provider_errors)} provider(s) failed"
            )
            for error_info in provider_errors:
                logger.debug(f"  {error_info['provider']}: {error_info['error']}")

        # Deduplicate results, preferring higher priority providers
        deduplicated = self._deduplicate_with_provider_preference(all_results)

        logger.debug(
            f"Found {len(all_results)} results for '{periodical_title}' across {len(self.search_providers)} providers "
            f"({len(deduplicated)} after deduplication)"
        )
        return deduplicated

    def _get_deduplication_key(self, result: Dict[str, Any]) -> str:
        """
        Generate a unique key for deduplicating search results.

        This key distinguishes different issues of the same periodical by including:
        - Base title (via fuzzy_group_id)
        - Publication date (year-month if available)
        - Issue/volume numbers (if available)

        Args:
            result: Search result dict with title, publication_date, raw_metadata

        Returns:
            Unique string key for deduplication

        Examples:
            "Tech Magazine No 10 - Jan 2024" -> "tech_2024-01_i10"
            "Tech Magazine No 11 - Feb 2024" -> "tech_2024-02_i11"
            "Wired Vol 30 No 1" -> "wired_v30_i1"
        """
        # Start with title-only fuzzy group ID (reuse if already calculated)
        fuzzy_group = result.get("fuzzy_match_group_id") or get_fuzzy_group_id(result["title"])
        key_parts = [fuzzy_group]

        # Add publication date if available (year-month precision)
        pub_date = result.get("publication_date")
        if pub_date:
            key_parts.append(pub_date.strftime("%Y-%m"))

        # Add volume/issue numbers if available from metadata
        metadata = result.get("raw_metadata", {})
        if metadata.get("volume"):
            key_parts.append(f"v{metadata['volume']}")
        if metadata.get("issue"):
            key_parts.append(f"i{metadata['issue']}")

        return "_".join(key_parts)

    def _deduplicate_with_provider_preference(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate search results, keeping results from preferred providers.

        When multiple providers return the same item (same issue of the same periodical),
        keep the result from the higher priority provider (lower priority number).

        Different issues are distinguished by publication date and/or volume/issue numbers,
        so they will NOT be deduplicated against each other.

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

        # Group results by deduplication key (title + date + issue/volume)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for result in results:
            group_id = self._get_deduplication_key(result)
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
