"""
Search provider helpers for fetching results from providers.

Handles fetching from provider cache and direct provider searches.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.constants.errors import ErrorMessages

from .dependencies import get_provider_cache_service, get_search_providers

logger = logging.getLogger(__name__)


def build_search_queries(query: str, tracking_id: Optional[int], db) -> List[str]:
    """
    Build search queries including aliases from tracking record.

    Args:
        query: Base search query
        tracking_id: Optional tracking ID to get aliases from
        db: Database session

    Returns:
        List of search queries (always includes original query)
    """
    search_queries = [query.strip()]

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


def fetch_from_provider_cache(
    search_queries: List[str],
    seen_urls: set,
) -> List[Dict[str, Any]]:
    """
    Fetch results from provider cache service.

    Args:
        search_queries: List of queries to search
        seen_urls: Set of already seen URLs (modified in place)

    Returns:
        List of result dicts from cache
    """
    results = []
    provider_cache_service = get_provider_cache_service()

    if not provider_cache_service:
        return results

    try:
        for search_query in search_queries:
            cached_releases = provider_cache_service.search(search_query, limit=100)
            if not cached_releases:
                continue

            logger.info(f"Found {len(cached_releases)} results from provider cache for '{search_query}'")

            for r in cached_releases:
                download_url = r.get("download_url")
                if not download_url or download_url in seen_urls:
                    continue

                seen_urls.add(download_url)

                # Handle raw_metadata being a JSON string
                raw_meta = r.get("raw_metadata") or {}
                if isinstance(raw_meta, str):
                    try:
                        raw_meta = json.loads(raw_meta)
                    except (json.JSONDecodeError, TypeError):
                        raw_meta = {}

                # Parse publication date
                pub_date = r.get("upload_date") or r.get("publication_date")
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pub_date = None

                results.append(
                    {
                        "title": r.get("title"),
                        "url": download_url,
                        "provider": r.get("provider_name"),
                        "publication_date": pub_date,
                        "metadata": raw_meta,
                        "from_cache": True,
                    }
                )
    except Exception as e:
        logger.warning(f"Provider cache search failed, falling back to direct providers: {e}")

    return results


def fetch_from_providers(
    search_queries: List[str],
    category: Optional[str],
    seen_urls: set,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Fetch results from direct search providers.

    Args:
        search_queries: List of queries to search
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

    # Search each query against each provider
    for search_query in search_queries:
        for provider in search_providers:
            try:
                provider_results = provider.search(search_query, category=category)
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
        for search_query in search_queries:
            for provider in search_providers:
                try:
                    provider_results = provider.search(search_query, category=None)
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
