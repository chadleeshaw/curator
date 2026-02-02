"""
Search API endpoints.

Contains all FastAPI route handlers for search functionality.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from core.constants.errors import ErrorMessages
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import Periodical
from web.schemas import APIError, SearchRequest
from web.utils.responses import success_response

from .cache import (
    get_cached_search_results,
    merge_search_results,
    save_search_results_to_cache,
)
from .dependencies import (
    get_provider_cache_service,
    get_search_providers,
    get_session_factory,
    get_title_matcher,
)
from .filters import (
    filter_by_language_and_country,
    filter_edition_variants,
    filter_non_periodicals,
)
from .library import (
    build_search_response,
    deduplicate_against_library,
    get_library_matches,
    mark_failed_downloads,
    sort_results_by_relevance,
)
from .providers import (
    build_search_queries,
    fetch_from_provider_cache,
    fetch_from_providers,
)

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger(__name__)


@router.post(
    "/search",
    summary="Search for periodicals",
    description="Search across configured providers for magazines, comics, and newspapers. Supports automatic deduplication or manual provider selection.",
    responses={
        200: {
            "description": "Search results retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "results": [
                            {
                                "title": "Wired Magazine - January 2024",
                                "url": "http://example.com/wired.nzb",
                                "provider": "newsnab",
                                "publication_date": "2024-01-01",
                            }
                        ],
                        "total": 1,
                        "mode": "automatic",
                    }
                }
            },
        },
        500: {"description": "Search failed", "model": APIError},
    },
)
@handle_api_errors("Search", logger)
async def search(request: SearchRequest) -> Dict[str, Any]:
    """
    Search for magazines.

    - Automatic mode: aggregate all providers, deduplicate by title similarity
    - Manual mode: search specific providers, return all results grouped
    """
    all_results = []
    provider_cache_service = get_provider_cache_service()
    search_providers = get_search_providers()
    title_matcher = get_title_matcher()

    # Try provider cache first if available
    if provider_cache_service:
        try:
            cached_releases = provider_cache_service.search(request.query.strip(), limit=100)
            if cached_releases:
                logger.info(f"Found {len(cached_releases)} results from provider cache")
                for release in cached_releases:
                    # Note: cache.search() returns dicts, not objects
                    raw_meta = release.get("raw_metadata") or {}
                    # Handle raw_metadata being a JSON string (from raw SQL)
                    if isinstance(raw_meta, str):
                        try:
                            raw_meta = json.loads(raw_meta)
                        except (json.JSONDecodeError, TypeError):
                            raw_meta = {}
                    all_results.append(
                        {
                            "title": release.get("title"),
                            "url": release.get("download_url"),
                            "provider": release.get("provider_name"),
                            "publication_date": release.get("upload_date") or release.get("publication_date"),
                            "raw_metadata": raw_meta,
                            "from_cache": True,
                        }
                    )
        except Exception as e:
            logger.warning(f"Provider cache search failed, falling back to direct providers: {e}")

    # Determine which providers to search
    providers = search_providers if search_providers else []
    active_providers = providers
    if request.mode == "manual" and request.providers:
        active_providers = [p for p in providers if p.type in request.providers]

    # Search each provider
    for provider in active_providers:
        try:
            results = provider.search(request.query)
            for result in results:
                all_results.append(
                    {
                        "title": result.title,
                        "url": result.url,
                        "provider": result.provider,
                        "publication_date": (result.publication_date.isoformat() if result.publication_date else None),
                        "raw_metadata": result.raw_metadata,
                    }
                )
        except Exception as e:
            logger.error(f"Error searching {provider.name}: {e}", exc_info=True)

    # Deduplicate results by title similarity
    deduplicated = title_matcher.deduplicate_results(all_results)

    if request.mode == "automatic":
        # Return best match from each group
        grouped_results = []
        for group_id, results in deduplicated.items():
            if results:
                best = sorted(results, key=lambda x: x.get("match_score", 0), reverse=True)[0]
                grouped_results.append(best)
        return {
            "mode": "automatic",
            "query": request.query,
            "results": grouped_results,
            "total": len(grouped_results),
        }
    else:
        # Return all grouped by similarity
        return {
            "mode": "manual",
            "query": request.query,
            "groups": deduplicated,
            "total": len(all_results),
        }


@router.post(
    "/periodicals/search-providers",
    summary="Search providers for periodical issues",
    description="Search Newsnab and RSS providers for downloadable periodical issues. Does not query metadata providers.",
    responses={
        200: {
            "description": "Issue search results retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "query": "Wired",
                        "results": [{"title": "Wired - Jan 2024", "url": "http://..."}],
                        "total": 1,
                    }
                }
            },
        },
        400: {"description": "Invalid query parameter", "model": APIError},
        500: {"description": "Search failed", "model": APIError},
    },
)
@handle_api_errors("Search periodical providers", logger)
async def search_periodical_providers(
    query: str = Query(..., description="Periodical title to search for"),
    language: str = Query(None, description="Filter by language (e.g., English, German)"),
    country: str = Query(None, description="Filter by country code (e.g., US, UK, DE)"),
    category: str = Query(None, description="Filter by category (e.g., Periodicals, Comics)"),
    tracking_id: int = Query(None, description="Scope library status to specific tracking ID"),
    force_refresh: bool = Query(False, description="Bypass cache and fetch fresh results"),
    cache_ttl_days: int = Query(7, description="Cache validity in days"),
) -> Dict[str, Any]:
    """
    Search for periodical issues with intelligent caching and library deduplication.

    Flow:
    1. Check cache for recent results (within cache_ttl_days)
    2. Fetch fresh results from providers (only new items)
    3. Merge cached + fresh results (deduplicated)
    4. Match against library (fuzzy title + date range)
    5. Hide provider results that exist in library
    6. Add library-only items with status badges
    7. Return unified result list with status indicators
    """
    session_factory = get_session_factory()

    def operation(db):
        if not query or len(query.strip()) < 2:
            raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

        logger.info(f"Searching for issues: '{query}' (tracking_id={tracking_id}, force_refresh={force_refresh})")

        # Step 1: Build search queries (with aliases)
        search_queries = build_search_queries(query, tracking_id, db)

        # Step 2: Load cached results
        cached_results = []
        if not force_refresh:
            cached_results = get_cached_search_results(db, query, tracking_id, cache_ttl_days)
            logger.debug(f"Found {len(cached_results)} cached results for '{query}'")

        # Step 3: Fetch fresh results from providers
        seen_urls = set()
        fresh_results = []
        provider_errors = []

        if not force_refresh:
            fresh_results = fetch_from_provider_cache(search_queries, seen_urls)

        direct_results, direct_errors = fetch_from_providers(search_queries, category, seen_urls)
        fresh_results.extend(direct_results)
        provider_errors.extend(direct_errors)

        logger.debug(f"Fetched {len(fresh_results)} fresh results from providers")

        # Step 4: Merge and filter results
        all_results = merge_search_results(cached_results, fresh_results)
        total_before_filtering = len(all_results)

        all_results = filter_non_periodicals(all_results)
        non_periodical_filtered = total_before_filtering - len(all_results)

        # Step 5: Save fresh results to cache
        if fresh_results:
            save_search_results_to_cache(db, query, fresh_results, tracking_id)

        # Step 6: Apply language/country/edition filters
        filter_language = language if language else "English"
        filter_country = country if country else "US"

        results_before_lang = len(all_results)
        filtered_results = filter_by_language_and_country(all_results, filter_language, filter_country)
        language_country_filtered = results_before_lang - len(filtered_results)

        results_before_edition = len(filtered_results)
        filtered_results = filter_edition_variants(filtered_results, query)
        edition_filtered = results_before_edition - len(filtered_results)

        # Step 7: Load library items (scoped by tracking_id)
        library_items = db.query(Periodical).all()
        if tracking_id:
            library_items = [m for m in library_items if m.tracking_id == tracking_id]
        logger.debug(f"Checking against {len(library_items)} library items")

        # Step 8: Deduplicate against library
        deduplicated_results = deduplicate_against_library(filtered_results, library_items)
        duplicates_removed = len(filtered_results) - len(deduplicated_results)

        # Log filter summary
        logger.info(
            f"Search summary for '{query}': {len(deduplicated_results)} results | "
            f"Filters: language={filter_language}, country={filter_country} | "
            f"Removed: {non_periodical_filtered} non-periodicals, "
            f"{language_country_filtered} language/country, {edition_filtered} editions, "
            f"{duplicates_removed} library duplicates"
        )

        # Step 9: Mark failed downloads
        mark_failed_downloads(deduplicated_results, tracking_id, db)

        # Step 10: Get library matches
        library_matches = get_library_matches(query, library_items, filter_language, filter_country)

        # Step 11: Sort results by relevance
        final_results = sort_results_by_relevance(library_matches + deduplicated_results, query)

        # Step 12: Build and return response
        return build_search_response(query, library_matches, deduplicated_results, cached_results, provider_errors)

    return await with_db_session(session_factory, operation)


@router.get(
    "/periodicals/editions/{magazine_title}",
    summary="Get periodical editions",
    description="Retrieve all available editions/issues of a specific periodical by searching configured providers.",
    responses={
        200: {
            "description": "Editions retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "periodical": "Wired",
                        "editions": [{"title": "Wired - Jan 2024", "url": "http://..."}],
                        "total": 1,
                    }
                }
            },
        },
        400: {"description": "Invalid periodical title", "model": APIError},
        503: {
            "description": ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE,
            "model": APIError,
        },
    },
)
@handle_api_errors("Get periodical editions", logger)
async def get_periodical_editions(magazine_title: str) -> Dict[str, Any]:
    """
    Get all editions/publications of a specific periodical by searching providers.

    Args:
        magazine_title: Periodical title (e.g., 'PC Gamer')

    Returns:
        List of search results for the periodical
    """
    if not magazine_title or len(magazine_title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Invalid periodical title")

    search_providers = get_search_providers()
    provider_cache_service = get_provider_cache_service()

    if not search_providers:
        logger.error(ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)
        raise HTTPException(status_code=503, detail=ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)

    # Search across search providers for specific editions
    results = []

    # Try provider cache first if available
    if provider_cache_service:
        try:
            cached_releases = provider_cache_service.search(magazine_title.strip(), limit=100)
            if cached_releases:
                logger.info(f"Found {len(cached_releases)} results from provider cache for '{magazine_title}'")
                for release in cached_releases:
                    results.append(
                        type(
                            "SearchResult",
                            (),
                            {
                                "title": release.title,
                                "url": release.download_url,
                                "provider": release.provider_name,
                                "publication_date": (
                                    datetime.fromisoformat(release.raw_metadata.get("upload_date"))
                                    if release.raw_metadata and release.raw_metadata.get("upload_date")
                                    else None
                                ),
                                "raw_metadata": release.raw_metadata or {},
                            },
                        )()
                    )
        except Exception as e:
            logger.warning(f"Provider cache search failed, falling back to direct providers: {e}")

    for provider in search_providers:
        try:
            provider_results = provider.search(magazine_title.strip())
            results.extend(provider_results)
        except Exception as e:
            logger.warning(f"Error searching provider {provider.__class__.__name__}: {e}")

    if results:
        return success_response(None, results=results)
    else:
        raise HTTPException(status_code=404, detail=f"Could not find editions for {magazine_title}")


@router.get("/indexer-cache/status")
@handle_api_errors("Get provider cache status", logger)
async def get_provider_cache_status() -> Dict[str, Any]:
    """
    Get provider cache statistics and status.

    Returns:
        Dictionary with cache statistics including:
        - total_entries: Number of cached releases
        - last_sync: Timestamp of last successful sync
        - providers: List of providers and their release counts
    """
    provider_cache_service = get_provider_cache_service()

    if not provider_cache_service:
        return {
            "enabled": False,
            "total_entries": 0,
            "last_sync": None,
            "providers": [],
        }

    def _get_stats():
        stats = provider_cache_service.get_stats()
        return {
            "enabled": True,
            "total_entries": stats.get("total_releases", 0),
            "last_sync": stats.get("last_sync"),
            "oldest_release": stats.get("oldest_release"),
            "newest_release": stats.get("newest_release"),
            "providers": stats.get("providers", []),
        }

    return await run_in_thread(_get_stats)
