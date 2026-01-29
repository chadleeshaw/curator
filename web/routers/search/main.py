"""
Search routes for periodicals
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_

from core.constants.country import LANGUAGE_TO_COUNTRY
from core.constants.errors import ErrorMessages
from core.constants.language import LANGUAGE_KEYWORDS
from core.parsers.country import detect_country
from core.parsers.date import normalize_month_name
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import DownloadSubmission, Periodical, SearchResult
from services.issue_discovery import IssueDiscoveryService
from web.schemas import APIError, SearchRequest
from web.utils.responses import success_response

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_search_providers = None
_metadata_providers = None
_title_matcher = None
_session_factory = None
_provider_cache_service = None


def set_dependencies(
    search_providers: Any,
    metadata_providers: Any,
    title_matcher: Any,
    session_factory: Callable,
    provider_cache_service: Any = None,
) -> None:
    """Set dependencies from main app"""
    global _search_providers, _metadata_providers, _title_matcher, _session_factory, _provider_cache_service
    _search_providers = search_providers
    _metadata_providers = metadata_providers
    _title_matcher = title_matcher
    _session_factory = session_factory
    _provider_cache_service = provider_cache_service


def _get_fuzzy_group_id(title: str) -> str:
    """
    Get a normalized group ID for fuzzy matching duplicates.
    Uses title matching to create consistent grouping.

    Args:
        title: Title to normalize

    Returns:
        Group ID string
    """
    # Normalize title: lowercase, remove special chars, collapse spaces
    normalized = " ".join(title.lower().split())

    # Normalize common month abbreviations to full names for better matching
    words = []
    for word in normalized.split():
        words.append(normalize_month_name(word))

    # Keep first few significant words as group ID
    group_words = [w for w in words if len(w) > 2][:3]
    return "-".join(group_words)


def _filter_edition_variants(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Filter out edition variants that don't match the query.

    If searching for "National Geographic", this filters OUT:
    - "National Geographic Little Kids" (different publication)
    - "National Geographic Traveller" (different publication)

    But KEEPS:
    - "National Geographic" (matches query)
    - "National Geographic December 2024" (same publication, just with date)

    Args:
        results: List of search result dictionaries
        query: Original search query

    Returns:
        Filtered list with only results matching query edition
    """
    if not results:
        return results

    if not _title_matcher:
        logger.warning("TitleMatcher not available, skipping edition variant filter")
        return results

    filtered = []

    # Extract edition variant from query
    query_variant = _title_matcher._extract_edition_variant(query)
    logger.debug(f"Filtering edition variants: Query '{query}' has variant: {query_variant}")
    logger.debug(f"Examining {len(results)} results...")

    for result in results:
        raw_title = result.get("title", "")

        # Lightly normalize the title (dots → spaces) but preserve dates, issue numbers, country codes
        # Don't use clean_release_title() as it removes too much metadata
        normalized_title = raw_title.replace(".", " ").replace("_", " ")
        result_variant = _title_matcher._extract_edition_variant(normalized_title)

        # Keep result if edition variants match
        # - Both have no variant: keep (e.g., "National Geographic" query, "National Geographic" result)
        # - Both have same variant: keep (e.g., "PC Gamer US" query, "PC Gamer US" result)
        # - One has variant, other doesn't: filter out (e.g., "National Geographic" query, "National Geographic Kids" result)
        # - Both have different variants: filter out (e.g., "PC Gamer US" query, "PC Gamer UK" result)

        # Compare variants (None == None is OK, any mismatch is filtered)
        if (query_variant is None and result_variant is None) or (
            query_variant is not None and result_variant is not None and query_variant == result_variant
        ):
            filtered.append(result)
            logger.debug(f"  ✓ KEEP: '{raw_title}' → '{normalized_title}' (variant: {result_variant})")
        else:
            logger.debug(
                f"  ✗ FILTERED: '{raw_title}' → '{normalized_title}' (variant: {result_variant}) "
                f"doesn't match query '{query}' (variant: {query_variant})"
            )

    return filtered


def _filter_non_periodicals(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter out non-periodical content (movies, audiobooks, soundtracks, etc.).

    Uses the same validation logic as IssueDiscoveryService to ensure
    only actual periodicals are returned to users.

    Args:
        results: List of search result dictionaries

    Returns:
        Filtered list with only periodical content
    """
    if not results:
        return results

    # Create a temporary IssueDiscoveryService instance for validation
    validator = IssueDiscoveryService()
    filtered = []

    for result in results:
        # Convert result dict to format expected by validator
        search_result = {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "provider": result.get("provider", ""),
            "category": result.get("metadata", {}).get("category", ""),
            "size": result.get("metadata", {}).get("size", 0),
        }

        # Validate using IssueDiscoveryService validation
        if validator._validate_is_periodical(search_result):
            filtered.append(result)
        else:
            logger.debug(f"Filtered out non-periodical: {result.get('title', '')}")

    logger.debug(f"Filtered {len(results) - len(filtered)} non-periodical results")
    return filtered


def _filter_by_language_and_country(
    results: List[Dict[str, Any]], language: str = None, country: str = None
) -> List[Dict[str, Any]]:
    """
    Filter search results by language and/or country.

    Looks for language and country indicators in titles (e.g., "UK", "DE", "German").
    Makes smart assumptions: German → DE, FR → French, etc.
    If no indicators found in title, assumes US/English (most common default).

    Args:
        results: List of search result dictionaries
        language: Language to filter by (e.g., "English", "German")
        country: Country code to filter by (e.g., "US", "UK", "DE")

    Returns:
        Filtered list matching the specified language/country
    """
    if not results or (not language and not country):
        return results

    # Build language indicators from centralized LANGUAGE_KEYWORDS
    language_indicators = {}
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        # Convert keywords to lowercase for matching
        language_indicators[lang] = [kw.lower() for kw in keywords]

    # Build reverse mapping: Country to Language
    country_to_language = {}
    for lang, country_code in LANGUAGE_TO_COUNTRY.items():
        country_to_language[country_code] = lang
    # Add English-speaking countries
    for code in ["US", "UK", "CA", "AU", "NZ", "IE"]:
        if code not in country_to_language:
            country_to_language[code] = "English"

    filtered = []

    for result in results:
        title = result.get("title", "").lower()

        # Detect country in title
        detected_country = detect_country(title)

        # Detect language in title using centralized LANGUAGE_KEYWORDS
        detected_language = None
        for lang, indicators in language_indicators.items():
            for indicator in indicators:
                if re.search(rf"\b{re.escape(indicator)}\b", title, re.IGNORECASE):
                    detected_language = lang
                    break
            if detected_language:
                break

        # Smart assumptions:
        # If we detected a language but no country, infer country from language
        if detected_language and not detected_country:
            if detected_language in LANGUAGE_TO_COUNTRY:
                detected_country = LANGUAGE_TO_COUNTRY[detected_language]
                logger.debug(
                    f"Inferred country {detected_country} from language {detected_language}: " f"{result['title'][:50]}"
                )

        # If we detected a country but no language, infer language from country
        if detected_country and not detected_language:
            if detected_country in country_to_language:
                detected_language = country_to_language[detected_country]
                logger.debug(
                    f"Inferred language {detected_language} from country {detected_country}: " f"{result['title'][:50]}"
                )

        # Default to US/English if no indicators found (most common)
        if not detected_country:
            detected_country = "US"
        if not detected_language:
            detected_language = "English"

        # Apply filters
        language_match = True
        country_match = True

        if language:
            language_match = detected_language == language

        if country:
            country_match = detected_country == country

        # Keep result if it matches all specified filters
        if language_match and country_match:
            filtered.append(result)
            logger.debug(f"Match: '{result['title'][:50]}' - " f"Detected: {detected_language}/{detected_country}")
        else:
            logger.debug(
                f"Filtered out: '{result['title'][:50]}' - "
                f"Detected: {detected_language}/{detected_country}, "
                f"Wanted: {language}/{country}"
            )

    return filtered


def _get_cached_search_results(
    db_session, query: str, tracking_id: Optional[int] = None, cache_ttl_days: int = 7
) -> List[SearchResult]:
    """
    Retrieve cached search results from database.

    Args:
        db_session: Database session
        query: Search query string
        tracking_id: Optional tracking ID for scoped search
        cache_ttl_days: How many days cache is valid

    Returns:
        List of cached SearchResult models
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=cache_ttl_days)

    cached_query = (
        db_session.query(SearchResult)
        .filter(SearchResult.query == query)
        .filter(SearchResult.created_at >= cutoff_date)
    )

    # If tracking_id provided, filter by associated tracking
    if tracking_id:
        cached_query = cached_query.join(DownloadSubmission, isouter=True).filter(
            or_(
                DownloadSubmission.tracking_id == tracking_id,
                DownloadSubmission.tracking_id.is_(None),
            )
        )

    return cached_query.all()


def _save_search_results_to_cache(
    db_session,
    query: str,
    results: List[Dict[str, Any]],
    tracking_id: Optional[int] = None,
) -> None:
    """
    Save new search results to database cache.

    Deduplicates against existing cache by:
    - Fuzzy match group ID (title similarity)
    - Publication date (same month)
    """
    for result in results:
        # Generate fuzzy match group for deduplication
        fuzzy_group_id = _get_fuzzy_group_id(result["title"])

        # Check if already cached
        pub_date = result.get("publication_date")
        if pub_date:
            existing = (
                db_session.query(SearchResult)
                .filter(SearchResult.fuzzy_match_group_id == fuzzy_group_id)
                .filter(SearchResult.query == query)
                .filter(func.date_trunc("month", SearchResult.publication_date) == func.date_trunc("month", pub_date))
                .first()
            )
        else:
            # No date, just check by fuzzy group and query
            existing = (
                db_session.query(SearchResult)
                .filter(SearchResult.fuzzy_match_group_id == fuzzy_group_id)
                .filter(SearchResult.query == query)
                .first()
            )

        if not existing:
            # Cache new result
            cached_result = SearchResult(
                provider=result.get("provider", "unknown"),
                query=query,
                title=result["title"],
                url=result.get("url", ""),
                publication_date=pub_date,
                raw_metadata=result.get("metadata", {}),
                fuzzy_match_group_id=fuzzy_group_id,
            )
            db_session.add(cached_result)

    try:
        db_session.commit()
    except Exception as e:
        logger.error(f"Error saving search results to cache: {e}")
        db_session.rollback()


def _merge_search_results(
    cached_results: List[SearchResult], fresh_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merge cached and fresh results, removing duplicates.

    Fresh results take precedence over cached (newer data).
    """
    # Convert cached to dict format
    cached_dicts = [
        {
            "title": r.title,
            "url": r.url,
            "provider": r.provider,
            "publication_date": r.publication_date,
            "metadata": r.raw_metadata or {},
            "fuzzy_match_group_id": r.fuzzy_match_group_id,
            "from_cache": True,
        }
        for r in cached_results
    ]

    # Create lookup set for fresh results (by fuzzy group + month)
    fresh_keys = set()
    for r in fresh_results:
        fuzzy_group = _get_fuzzy_group_id(r["title"])
        pub_date = r.get("publication_date")
        date_key = pub_date.strftime("%Y-%m") if pub_date else None
        fresh_keys.add((fuzzy_group, date_key))

    # Filter out cached results that exist in fresh results
    deduplicated_cached = []
    for r in cached_dicts:
        pub_date = r.get("publication_date")
        date_key = pub_date.strftime("%Y-%m") if pub_date else None
        key = (r["fuzzy_match_group_id"], date_key)

        if key not in fresh_keys:
            deduplicated_cached.append(r)

    # Mark fresh results
    for r in fresh_results:
        r["from_cache"] = False

    # Merge and return
    return fresh_results + deduplicated_cached


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

    # Try provider cache first if available
    if _provider_cache_service:
        try:
            cached_releases = _provider_cache_service.search(request.query.strip(), limit=100)
            if cached_releases:
                logger.info(f"Found {len(cached_releases)} results from provider cache")
                for release in cached_releases:
                    all_results.append(
                        {
                            "title": release.title,
                            "url": release.download_url,
                            "provider": release.provider_name,
                            "publication_date": (
                                release.raw_metadata.get("upload_date")
                                if release.raw_metadata and release.raw_metadata.get("upload_date")
                                else None
                            ),
                            "raw_metadata": release.raw_metadata or {},
                            "from_cache": True,
                        }
                    )
        except Exception as e:
            logger.warning(f"Provider cache search failed, falling back to direct providers: {e}")

    # Determine which providers to search
    providers = _search_providers if _search_providers else []
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
    deduplicated = _title_matcher.deduplicate_results(all_results)

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

    def operation(db):
        if not query or len(query.strip()) < 2:
            raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

        logger.info(f"Searching for issues: '{query}' (tracking_id={tracking_id}, force_refresh={force_refresh})")

        # === STEP 1: Load Cached Results ===
        cached_results = []
        if not force_refresh:
            cached_results = _get_cached_search_results(db, query, tracking_id, cache_ttl_days)
            logger.debug(f"Found {len(cached_results)} cached results for '{query}'")

        # === STEP 2: Fetch Fresh Results from Providers ===
        fresh_results = []
        provider_errors = []

        # Try provider cache first if available
        if _provider_cache_service and not force_refresh:
            try:
                cached_releases = _provider_cache_service.search(query.strip(), limit=100)
                if cached_releases:
                    logger.info(f"Found {len(cached_releases)} results from provider cache")
                    fresh_results.extend(
                        [
                            {
                                "title": r.title,
                                "url": r.download_url,  # Note: cache uses download_url not url
                                "provider": r.provider_name,
                                "publication_date": (
                                    datetime.fromisoformat(r.raw_metadata.get("upload_date"))
                                    if r.raw_metadata and r.raw_metadata.get("upload_date")
                                    else None
                                ),
                                "metadata": r.raw_metadata or {},
                                "from_cache": True,
                            }
                            for r in cached_releases
                        ]
                    )
            except Exception as e:
                logger.warning(f"Provider cache search failed, falling back to direct providers: {e}")

        if _search_providers:
            for provider in _search_providers:
                try:
                    provider_results = provider.search(query.strip(), category=category)
                    fresh_results.extend(
                        [
                            {
                                "title": r.title,
                                "url": r.url,
                                "provider": r.provider,
                                "publication_date": r.publication_date,
                                "metadata": r.raw_metadata or {},
                            }
                            for r in provider_results
                        ]
                    )
                except Exception as e:
                    error_msg = f"{provider.__class__.__name__}: {str(e)}"
                    logger.warning(f"Error searching provider: {error_msg}")
                    provider_errors.append(error_msg)

            # If category filter was used but no results found, try again without category
            if category and len(fresh_results) == 0:
                logger.info(f"No results with category '{category}', expanding search to all categories")
                for provider in _search_providers:
                    try:
                        provider_results = provider.search(query.strip(), category=None)
                        fresh_results.extend(
                            [
                                {
                                    "title": r.title,
                                    "url": r.url,
                                    "provider": r.provider,
                                    "publication_date": r.publication_date,
                                    "metadata": r.raw_metadata or {},
                                }
                                for r in provider_results
                            ]
                        )
                    except Exception:
                        pass  # Already logged above
        else:
            error_msg = ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE
            logger.warning(error_msg)
            provider_errors.append(error_msg)

        logger.debug(f"Fetched {len(fresh_results)} fresh results from providers")

        # === STEP 3: Merge Cached + Fresh (Deduplicated) ===
        all_results = _merge_search_results(cached_results, fresh_results)
        logger.debug(f"Merged to {len(all_results)} total results")

        # === STEP 4: Filter Non-Periodicals ===
        # Remove movies, audiobooks, soundtracks, and other unsupported content
        all_results = _filter_non_periodicals(all_results)
        logger.debug(f"After non-periodical filter: {len(all_results)} results")

        # === STEP 5: Save Fresh Results to Cache ===
        if fresh_results:
            _save_search_results_to_cache(db, query, fresh_results, tracking_id)

        # === STEP 6: Apply Language/Country Filters ===
        filter_language = language if language else "English"
        filter_country = country if country else "US"
        filtered_results = _filter_by_language_and_country(all_results, filter_language, filter_country)
        logger.debug(
            f"After language/country filter: {len(filtered_results)} results (language={filter_language}, country={filter_country})"
        )

        # Filter out edition variants (kids, traveller, etc.)
        logger.debug(f"Before edition variant filter: {len(filtered_results)} results")
        filtered_results = _filter_edition_variants(filtered_results, query)
        logger.debug(f"After edition variant filter: {len(filtered_results)} results")

        # === STEP 7: Load Library Items (Scoped by tracking_id) ===
        library_items = db.query(Periodical).all()

        if tracking_id:
            library_items = [m for m in library_items if m.tracking_id == tracking_id]

        logger.debug(f"Checking against {len(library_items)} library items")

        # === STEP 8: Match Provider Results Against Library ===
        # Remove provider results that already exist in library using fuzzy + date range matching
        deduplicated_results = []

        for result in filtered_results:
            # Check if this result matches any library item
            is_duplicate = False

            for lib_item in library_items:
                if result.get("publication_date") and _title_matcher:
                    is_match, score = _title_matcher.matches_library_item_with_date_range(
                        provider_title=result["title"],
                        provider_date=result["publication_date"],
                        library_title=lib_item.title,
                        library_date=lib_item.issue_date,
                        date_tolerance_days=7,
                    )

                    if is_match:
                        logger.debug(
                            f"Hiding duplicate: '{result['title']}' matches library item '{lib_item.title}' (score: {score})"
                        )
                        is_duplicate = True
                        break

            if not is_duplicate:
                # Add status badge for available items
                result["status"] = "available"
                result["status_badge"] = "📥 Available"
                result["library_item_id"] = None
                result["already_downloaded"] = False
                result["download_failed"] = False
                result["from_provider"] = True
                # Format publication date
                if result.get("publication_date"):
                    result["publication_date"] = result["publication_date"].isoformat()
                deduplicated_results.append(result)

        # === STEP 9: Check Failed Downloads ===
        failed_downloads = (
            db.query(DownloadSubmission)
            .filter(
                or_(
                    DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                    DownloadSubmission.attempt_count >= 2,
                )
            )
            .all()
        )

        if tracking_id:
            failed_downloads = [d for d in failed_downloads if d.tracking_id == tracking_id]

        failed_fuzzy_groups = {d.fuzzy_match_group for d in failed_downloads if d.fuzzy_match_group}

        # Mark failed downloads
        for result in deduplicated_results:
            fuzzy_group = _get_fuzzy_group_id(result["title"])
            if fuzzy_group in failed_fuzzy_groups:
                result["status"] = "failed"
                result["status_badge"] = "⚠️ Failed Before"
                result["download_failed"] = True

        # === STEP 10: Add Library-Only Items ===
        # Items in library that match the query
        library_matches = []

        if _title_matcher:
            for lib_item in library_items:
                is_match, score = _title_matcher.match(query.strip(), lib_item.title)

                if is_match:
                    # For library-only items, append year to title so frontend parser can extract it
                    year = lib_item.issue_date.year if lib_item.issue_date else None
                    title_with_year = f"{lib_item.title} {year}" if year else lib_item.title

                    library_matches.append(
                        {
                            "title": title_with_year,
                            "publication_date": lib_item.issue_date.isoformat() if lib_item.issue_date else None,
                            "status": "in_library",
                            "status_badge": "📚 In Library",
                            "library_item_id": lib_item.id,
                            "file_path": lib_item.file_path,
                            "cover_path": lib_item.cover_path,
                            "provider": "📚 Library",
                            "url": "",
                            "metadata": lib_item.extra_metadata or {},
                            "already_downloaded": True,
                            "download_failed": False,
                            "from_provider": False,
                        }
                    )

        # Apply same language/country filter to library items
        library_matches = _filter_by_language_and_country(library_matches, filter_language, filter_country)

        # === STEP 11: Combine and Sort Results ===
        final_results = library_matches + deduplicated_results

        # Sort by relevance (fuzzy match score), then date (newest first)
        if _title_matcher:
            scored_results = []
            for result in final_results:
                is_match, score = _title_matcher.match(query.strip(), result["title"])
                scored_results.append((result, score))

            scored_results.sort(
                key=lambda x: (
                    -x[1],  # Higher score first
                    -(
                        datetime.fromisoformat(x[0]["publication_date"]).timestamp()
                        if x[0].get("publication_date")
                        else 0
                    ),
                )
            )
            final_results = [r[0] for r in scored_results]

        # === STEP 12: Return Response ===
        if final_results:
            logger.info(f"Found {len(final_results)} results for: {query}")
            return {
                "found": True,
                "results": final_results,
                "library_matches": len(library_matches),
                "available_to_download": len([r for r in deduplicated_results if r.get("status") == "available"]),
                "total_results": len(final_results),
                "provider_errors": provider_errors if provider_errors else None,
                "from_cache": len(cached_results) > 0,
                "cache_age_days": ((datetime.utcnow() - cached_results[0].created_at).days if cached_results else None),
                "message": f"Found {len(final_results)} results for '{query}'",
            }
        else:
            error_context = ""
            if provider_errors:
                error_context = f" Errors: {'; '.join(provider_errors)}"
            logger.info(f"No results found for query: {query}{error_context}")
            return {
                "found": False,
                "message": f"No results found for '{query}' - Try a different search term{error_context}",
                "results": [],
                "library_matches": 0,
                "available_to_download": 0,
                "total_results": 0,
                "provider_errors": provider_errors if provider_errors else None,
                "from_cache": len(cached_results) > 0,
                "cache_age_days": (datetime.utcnow() - cached_results[0].created_at).days if cached_results else None,
            }

    return await with_db_session(_session_factory, operation)


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

    if not _search_providers:
        logger.error(ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)
        raise HTTPException(status_code=503, detail=ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE)

    # Search across search providers for specific editions
    results = []

    # Try provider cache first if available
    if _provider_cache_service:
        try:
            cached_releases = _provider_cache_service.search(magazine_title.strip(), limit=100)
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

    for provider in _search_providers:
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
    if not _provider_cache_service:
        return {
            "enabled": False,
            "total_entries": 0,
            "last_sync": None,
            "providers": [],
        }

    def _get_stats():
        stats = _provider_cache_service.get_stats()
        return {
            "enabled": True,
            "total_entries": stats.get("total_releases", 0),
            "last_sync": stats.get("last_sync"),
            "oldest_release": stats.get("oldest_release"),
            "newest_release": stats.get("newest_release"),
            "providers": stats.get("providers", []),
        }

    return await run_in_thread(_get_stats)
