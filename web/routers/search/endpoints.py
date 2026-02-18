"""
Search API endpoints.

Contains all FastAPI route handlers for search functionality.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from core.constants.errors import ErrorMessages
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
    get_search_providers,
    get_session_factory,
    get_title_matcher,
)
from .filters import (
    filter_by_language_and_country,
    filter_periodical_variants,
    filter_ia_results,
    filter_non_periodicals,
)
from .library import (
    build_search_response,
    deduplicate_against_library,
    get_library_matches,
    mark_failed_downloads,
)
from .enrichment import enrich_results_with_parsed_metadata
from .providers import (
    build_search_queries,
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
    search_providers = get_search_providers()
    title_matcher = get_title_matcher()

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

        direct_results, direct_errors = fetch_from_providers(search_queries, category, seen_urls)
        fresh_results.extend(direct_results)
        provider_errors.extend(direct_errors)

        logger.debug(f"Fetched {len(fresh_results)} fresh results from providers")

        # Step 4: Merge and filter results
        all_results = merge_search_results(cached_results, fresh_results)
        total_before_filtering = len(all_results)

        all_results = filter_non_periodicals(all_results)
        non_periodical_filtered = total_before_filtering - len(all_results)

        # Step 4b: Filter IA collection archives and poor title matches
        ia_before = len(all_results)
        all_results = filter_ia_results(all_results, query)
        ia_filtered = ia_before - len(all_results)

        # Step 5: Save fresh results to cache
        if fresh_results:
            save_search_results_to_cache(db, query, fresh_results, tracking_id)

        # Step 6: Apply language/country/edition filters
        # When language/country are None (user selected "Any"), don't filter
        filter_language = language if language else None
        filter_country = country if country else None

        results_before_lang = len(all_results)
        filtered_results = filter_by_language_and_country(all_results, filter_language, filter_country)
        language_country_filtered = results_before_lang - len(filtered_results)

        results_before_pub_variant = len(filtered_results)
        filtered_results = filter_periodical_variants(filtered_results, query)
        periodical_variants_filtered = results_before_pub_variant - len(filtered_results)

        # Step 7: Load library items (scoped by tracking_id)
        library_items = db.query(Periodical).all()
        if tracking_id:
            library_items = [m for m in library_items if m.tracking_id == tracking_id]
        logger.debug(f"Checking against {len(library_items)} library items")

        # Step 8: Check against library (mark matches, don't remove)
        deduplicated_results = deduplicate_against_library(filtered_results, library_items)
        library_matched = sum(1 for r in deduplicated_results if r.get("already_downloaded"))

        # Log filter summary
        logger.info(
            f"Search summary for '{query}': {len(deduplicated_results)} results | "
            f"Filters: language={filter_language}, country={filter_country} | "
            f"Removed: {non_periodical_filtered} non-periodicals, {ia_filtered} IA irrelevant, "
            f"{language_country_filtered} language/country, {periodical_variants_filtered} periodical variants | "
            f"{library_matched} matched to library"
        )

        # Step 9: Mark failed downloads
        mark_failed_downloads(deduplicated_results, tracking_id, db)

        # Step 10: Get library matches
        library_matches = get_library_matches(query, library_items, filter_language, filter_country)

        # Step 11: Enrich results with backend-parsed title metadata
        # so frontend doesn't need to duplicate title-parsing logic
        enrich_results_with_parsed_metadata(deduplicated_results)
        enrich_results_with_parsed_metadata(library_matches)

        # Step 12: Build and return response (sorts results internally)
        return build_search_response(query, library_matches, deduplicated_results, cached_results, provider_errors)

    return await with_db_session(session_factory, operation)


@router.get(
    "/periodicals/issues/{magazine_title}",
    summary="Get periodical issues",
    description="Retrieve all available issues of a specific periodical by searching configured providers.",
    responses={
        200: {
            "description": "Issues retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "periodical": "Wired",
                        "issues": [{"title": "Wired - Jan 2024", "url": "http://..."}],
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
@handle_api_errors("Get periodical issues", logger)
async def get_periodical_issues(magazine_title: str) -> Dict[str, Any]:
    """
    Get all available issues of a specific periodical by searching providers.

    Args:
        magazine_title: Periodical title (e.g., 'PC Gamer')

    Returns:
        List of search results for the periodical
    """
    if not magazine_title or len(magazine_title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Invalid periodical title")

    search_providers = get_search_providers()

    if not search_providers:
        logger.error(ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)
        raise HTTPException(status_code=503, detail=ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)

    # Search across search providers for specific issues
    results = []

    for provider in search_providers:
        try:
            provider_results = provider.search(magazine_title.strip())
            results.extend(provider_results)
        except Exception as e:
            logger.warning(f"Error searching provider {provider.__class__.__name__}: {e}")

    if results:
        return success_response(None, results=results)
    else:
        raise HTTPException(status_code=404, detail=f"Could not find issues for {magazine_title}")
