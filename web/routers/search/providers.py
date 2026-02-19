"""
Search provider helpers for fetching results from providers.

Handles fetching results from direct provider searches.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Optional

from core.constants.app import PROVIDER_SEARCH_TIMEOUT
from core.constants.errors import ErrorMessages
from core.constants.title import COLLECTION_DESCRIPTOR_WORDS

from .dependencies import get_search_providers

logger = logging.getLogger(__name__)


def _strip_collection_descriptors(query: str) -> str:
    """
    Strip collection descriptor words from a search query.

    Words like 'Collection', 'Pack', 'Bundle' express user intent
    (they want a collection) but are not part of the periodical title.
    Providers index by title, so these words narrow results incorrectly.

    Args:
        query: Raw search query

    Returns:
        Cleaned query with collection descriptors removed

    Examples:
        >>> _strip_collection_descriptors('Hobby Magazine Collection')
        'Hobby Magazine'
        >>> _strip_collection_descriptors('National Geographic Complete Collection')
        'National Geographic'
        >>> _strip_collection_descriptors('PC Gamer')
        'PC Gamer'
    """
    words = query.strip().split()
    cleaned = [w for w in words if w.lower() not in COLLECTION_DESCRIPTOR_WORDS]

    # Only use cleaned version if we still have meaningful words left
    if cleaned:
        result = " ".join(cleaned)
        # Collapse any double spaces from removed words
        result = re.sub(r"\s+", " ", result).strip()
        if result != query.strip():
            logger.debug(f"Stripped collection descriptors from query: '{query}' -> '{result}'")
        return result

    return query.strip()


def build_search_queries(query: str, tracking_id: Optional[int], db) -> List[str]:
    """
    Build search queries including aliases from tracking record.

    Strips collection descriptor words (e.g., 'Collection', 'Pack', 'Bundle')
    from the query since they express user intent but are not part of
    periodical titles indexed by providers.

    Args:
        query: Base search query
        tracking_id: Optional tracking ID to get aliases from
        db: Database session

    Returns:
        List of search queries (always includes original query)
    """
    cleaned_query = _strip_collection_descriptors(query)
    search_queries = [cleaned_query]

    if tracking_id:
        from models.database import PeriodicalTracking

        tracking_record = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if tracking_record and tracking_record.search_aliases:
            aliases = [a.strip() for a in tracking_record.search_aliases.split(",") if a.strip()]
            for alias in aliases:
                if alias not in search_queries:
                    search_queries.append(alias)
            if len(search_queries) > 1:
                logger.info(
                    f"Searching with title + {len(aliases)} aliases for '{tracking_record.title}': {search_queries}"
                )

    return search_queries


def fetch_from_providers(
    search_queries: List[str],
    category: Optional[str],
    seen_urls: set,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Fetch results from direct search providers.

    Passes the primary query and any aliases to each provider in a single call.
    Each provider handles aliases according to its capabilities:
    - Internet Archive: combines into a single OR query (one API call)
    - Newsnab: searches each alias separately
    - RSS: matches against all terms in the in-memory filter

    Args:
        search_queries: List of queries to search (first is primary, rest are aliases)
        category: Optional category filter
        seen_urls: Set of already seen URLs (modified in place)

    Returns:
        Tuple of (results list, provider errors list)
    """
    results = []
    provider_errors = []
    search_providers = get_search_providers()

    if not search_providers:
        error_msg = ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE
        logger.warning(error_msg)
        provider_errors.append(error_msg)
        return results, provider_errors

    # Split into primary query and aliases
    primary_query = search_queries[0]
    aliases = search_queries[1:] if len(search_queries) > 1 else None

    # Search each provider once with primary query + aliases (with timeout protection)
    # Use one worker per provider so a hung provider doesn't block others
    with ThreadPoolExecutor(max_workers=len(search_providers)) as executor:
        for provider in search_providers:
            try:
                future = executor.submit(provider.search, primary_query, category, aliases)
                try:
                    provider_results = future.result(timeout=PROVIDER_SEARCH_TIMEOUT)
                except FuturesTimeoutError:
                    error_msg = f"{provider.__class__.__name__}: timed out after {PROVIDER_SEARCH_TIMEOUT}s"
                    logger.warning(f"Provider search timeout: {error_msg}")
                    provider_errors.append(error_msg)
                    continue

                for r in provider_results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        results.append(
                            {
                                "title": r.title,
                                "url": r.url,
                                "provider": r.provider,
                                "publication_date": r.publication_date,
                                "metadata": r.raw_metadata or {},
                            }
                        )
            except Exception as e:
                error_msg = f"{provider.__class__.__name__}: {str(e)}"
                logger.warning(f"Error searching provider: {error_msg}")
                provider_errors.append(error_msg)

    # Retry without category filter if no results
    if category and len(results) == 0:
        logger.info(f"No results with category '{category}', expanding search to all categories")
        with ThreadPoolExecutor(max_workers=len(search_providers)) as executor:
            for provider in search_providers:
                try:
                    future = executor.submit(provider.search, primary_query, None, aliases)
                    try:
                        provider_results = future.result(timeout=PROVIDER_SEARCH_TIMEOUT)
                    except FuturesTimeoutError:
                        continue  # Already logged above for this provider

                    for r in provider_results:
                        if r.url not in seen_urls:
                            seen_urls.add(r.url)
                            results.append(
                                {
                                    "title": r.title,
                                    "url": r.url,
                                    "provider": r.provider,
                                    "publication_date": r.publication_date,
                                    "metadata": r.raw_metadata or {},
                                }
                            )
                except Exception:
                    pass  # Already logged above

    return results, provider_errors
