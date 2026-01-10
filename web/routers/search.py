"""
Search routes for periodicals
"""

import logging
import re
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from models.database import Magazine
from web.schemas import APIError, SearchRequest
from core.constants import LANGUAGE_TO_COUNTRY, LANGUAGE_KEYWORDS, COUNTRY_INDICATORS

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_search_providers = None
_metadata_providers = None
_title_matcher = None
_session_factory = None


def set_dependencies(
    search_providers, metadata_providers, title_matcher, session_factory
):
    """Set dependencies from main app"""
    global _search_providers, _metadata_providers, _title_matcher, _session_factory
    _search_providers = search_providers
    _metadata_providers = metadata_providers
    _title_matcher = title_matcher
    _session_factory = session_factory


def _filter_edition_variants(
    results: List[Dict[str, Any]], query: str
) -> List[Dict[str, Any]]:
    """
    Filter out edition variants (kids, traveller, uk, etc.) from search results.
    Prioritizes the main edition when multiple variants of the same periodical are found.

    Args:
        results: List of search result dictionaries
        query: Original search query

    Returns:
        Filtered list with main editions prioritized
    """
    if not results:
        return results

    # Common edition suffixes to filter out
    edition_suffixes = [
        "kids",
        "traveller",
        "traveler",
        "uk",
        "us",
        "world",
        "international",
        "junior",
        "student",
        "pro",
        "premium",
        "lite",
        "digital",
    ]

    # Group by base title (before edition suffix)
    title_groups = {}
    for result in results:
        title = result.get("title", "").lower()

        # Find the base title by removing known edition suffixes
        base_title = title
        for suffix in edition_suffixes:
            # Match suffix at the end, with common separators
            patterns = [
                f" {suffix}$",
                f"\\s+{suffix}\\s*$",
                f" {suffix}\\s+",
            ]
            for pattern in patterns:
                base_title = re.sub(pattern, "", base_title, flags=re.IGNORECASE)

        base_title = base_title.strip()

        if base_title not in title_groups:
            title_groups[base_title] = []
        title_groups[base_title].append((result, title))

    # For each base title group, keep only the main edition (shortest/simplest title)
    filtered_results = []
    for base_title, group in title_groups.items():
        if group:
            # Sort by title length (main edition typically has shortest title)
            sorted_group = sorted(group, key=lambda x: len(x[1]))
            filtered_results.append(sorted_group[0][0])

    return filtered_results


def _filter_by_language_and_country(
    results: List[Dict[str, Any]],
    language: str = None,
    country: str = None
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

    # Import country detection
    from core.parsers.country import detect_country

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
    for code in ['US', 'UK', 'CA', 'AU', 'NZ', 'IE']:
        if code not in country_to_language:
            country_to_language[code] = 'English'

    filtered = []

    for result in results:
        title = result.get("title", "").lower()

        # Detect country in title
        detected_country = detect_country(title)

        # Detect language in title using centralized LANGUAGE_KEYWORDS
        detected_language = None
        for lang, indicators in language_indicators.items():
            for indicator in indicators:
                if re.search(rf'\b{re.escape(indicator)}\b', title, re.IGNORECASE):
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
                    f"Inferred country {detected_country} from language {detected_language}: "
                    f"{result['title'][:50]}"
                )

        # If we detected a country but no language, infer language from country
        if detected_country and not detected_language:
            if detected_country in country_to_language:
                detected_language = country_to_language[detected_country]
                logger.debug(
                    f"Inferred language {detected_language} from country {detected_country}: "
                    f"{result['title'][:50]}"
                )

        # Default to US/English if no indicators found (most common)
        if not detected_country:
            detected_country = 'US'
        if not detected_language:
            detected_language = 'English'

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
            logger.debug(
                f"Match: '{result['title'][:50]}' - "
                f"Detected: {detected_language}/{detected_country}"
            )
        else:
            logger.debug(
                f"Filtered out: '{result['title'][:50]}' - "
                f"Detected: {detected_language}/{detected_country}, "
                f"Wanted: {language}/{country}"
            )

    return filtered


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
async def search(request: SearchRequest) -> Dict[str, Any]:
    """
    Search for magazines.

    - Automatic mode: aggregate all providers, deduplicate by title similarity
    - Manual mode: search specific providers, return all results grouped
    """
    try:
        all_results = []

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
                            "publication_date": (
                                result.publication_date.isoformat()
                                if result.publication_date
                                else None
                            ),
                            "raw_metadata": result.raw_metadata,
                        }
                    )
            except Exception as e:
                logger.error(f"Error searching {provider.name}: {e}")

        # Deduplicate results by title similarity
        deduplicated = _title_matcher.deduplicate_results(all_results)

        if request.mode == "automatic":
            # Return best match from each group
            grouped_results = []
            for group_id, results in deduplicated.items():
                if results:
                    best = sorted(
                        results, key=lambda x: x.get("match_score", 0), reverse=True
                    )[0]
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

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def search_periodical_providers(
    query: str = Query(...),
    language: str = Query(None, description="Filter by language (e.g., English, German)"),
    country: str = Query(None, description="Filter by country code (e.g., US, UK, DE)"),
    category: str = Query(None, description="Filter by category (e.g., Magazines, Comics)"),
    tracking_id: int = Query(None, description="Scope library status to specific tracking ID")
) -> Dict[str, Any]:
    """
    Search for periodical issues by querying SEARCH providers only (Newsnab, RSS).
    Does NOT query metadata providers - use /api/periodicals/search-metadata for that.

    Args:
        query: Periodical title to search for (as query parameter)
        language: Optional language filter to match specific editions
        country: Optional country code filter to match specific editions
        category: Optional category filter for provider search (narrows results)
        tracking_id: Optional tracking ID to scope library status checks (shows only if in this tracking)

    Returns:
        Issue search results from search providers, filtered by language/country/category if specified
    """
    try:
        if not query or len(query.strip()) < 2:
            raise HTTPException(
                status_code=400, detail="Query must be at least 2 characters"
            )

        logger.debug(f"Searching for issues: {query}")

        db_session = _session_factory()
        try:
            # Search across SEARCH providers ONLY (Newsnab, RSS)
            all_results = []
            provider_errors = []

            if _search_providers:
                for provider in _search_providers:
                    try:
                        # Pass category to provider if specified
                        provider_results = provider.search(query.strip(), category=category)
                        all_results.extend(provider_results)
                    except Exception as e:
                        error_msg = f"{provider.__class__.__name__}: {str(e)}"
                        logger.warning(f"Error searching provider: {error_msg}")
                        provider_errors.append(error_msg)

                # If category filter was used but no results found, try again without category
                if category and len(all_results) == 0:
                    logger.info(f"No results with category '{category}', expanding search to all categories")
                    for provider in _search_providers:
                        try:
                            provider_results = provider.search(query.strip(), category=None)
                            all_results.extend(provider_results)
                        except Exception as e:
                            pass  # Already logged above
            else:
                error_msg = "No search providers configured"
                logger.warning(error_msg)
                provider_errors.append(error_msg)

            # Get all existing magazines from database
            all_magazines_in_db = db_session.query(Magazine).all()

            # For "in library" detection: scope to tracking_id if specified
            if tracking_id:
                scoped_magazines = [m for m in all_magazines_in_db if m.tracking_id == tracking_id]
            else:
                scoped_magazines = all_magazines_in_db

            # Create a more specific set: title + date for exact matching (scoped to tracking)
            existing_title_dates = {
                (m.title.lower(), m.issue_date.strftime("%Y-%m") if m.issue_date else "")
                for m in scoped_magazines
            }
            # Also keep simple title set for backward compatibility (scoped to tracking)
            existing_titles = {m.title.lower() for m in scoped_magazines}

            # Search library for matching titles using fuzzy matching (scoped to tracking)
            matching_library_issues = []
            if _title_matcher:
                for mag in scoped_magazines:
                    is_match, score = _title_matcher.match(query.strip(), mag.title)
                    if is_match:
                        matching_library_issues.append(mag)
            else:
                # Fallback to substring matching if no matcher available
                query_lower = query.strip().lower()
                matching_library_issues = [
                    m for m in scoped_magazines if query_lower in m.title.lower()
                ]

            # Convert provider results to dictionaries
            result_dicts = []
            for result in all_results[:200]:  # Increase limit before filtering
                # Extract date for more precise "already downloaded" check
                pub_date_str = ""
                if result.publication_date:
                    pub_date_str = result.publication_date.strftime("%Y-%m")

                # Check if this specific issue (title + date) already exists
                title_lower = result.title.lower()
                is_downloaded = (title_lower, pub_date_str) in existing_title_dates

                result_dicts.append({
                    "title": result.title,
                    "url": result.url,
                    "provider": result.provider,
                    "publication_date": (
                        result.publication_date.isoformat()
                        if result.publication_date
                        else None
                    ),
                    "metadata": result.raw_metadata or {},
                    "already_downloaded": is_downloaded,
                    "from_provider": True,
                })

            # Apply language and country filters EARLY (before expensive operations)
            # Default to US/English if not specified
            filter_language = language if language else 'English'
            filter_country = country if country else 'US'
            result_dicts = _filter_by_language_and_country(
                result_dicts, filter_language, filter_country
            )
            logger.debug(
                f"After language/country filter: {len(result_dicts)} results "
                f"(language={filter_language}, country={filter_country})"
            )

            # Filter out edition variants (kids, traveller, etc.)
            result_dicts = _filter_edition_variants(result_dicts, query)

            # Apply fuzzy matching to get best matches
            # Score results and sort by relevance
            scored_results = []
            for result in result_dicts:
                is_match, score = _title_matcher.match(query.strip(), result["title"])
                scored_results.append((result, score))

            # Sort by score (higher is better) and keep top results
            scored_results.sort(key=lambda x: x[1], reverse=True)
            result_dicts = [
                r[0] for r in scored_results[:50]
            ]  # Keep top 50 by fuzzy score

            # Add library issues that aren't in provider results
            provider_titles = {r["title"].lower() for r in result_dicts}
            for mag in matching_library_issues:
                if mag.title.lower() not in provider_titles:
                    # For library-only items, append year to title so frontend parser can extract it
                    year = mag.issue_date.year if mag.issue_date else None
                    title_with_year = f"{mag.title} {year}" if year else mag.title

                    result_dicts.append(
                        {
                            "title": title_with_year,
                            "url": "",  # No URL for library-only items
                            "provider": "📚 Library",
                            "publication_date": (
                                mag.issue_date.isoformat() if mag.issue_date else None
                            ),
                            "metadata": mag.extra_metadata or {},
                            "already_downloaded": True,
                            "from_provider": False,
                        }
                    )

            if result_dicts:
                logger.debug(f"Found {len(result_dicts)} results for: {query}")
                return {
                    "found": True,
                    "results": result_dicts,
                    "message": f"Found {len(result_dicts)} results for '{query}'",
                    "provider_errors": provider_errors if provider_errors else None,
                }
            else:
                error_context = ""
                if provider_errors:
                    error_context = f" Errors: {'; '.join(provider_errors)}"
                logger.debug(f"No results found for query: {query}{error_context}")
                return {
                    "found": False,
                    "message": f"No results found for '{query}' - Try a different search term{error_context}",
                    "results": [],
                    "provider_errors": provider_errors if provider_errors else None,
                }

        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Periodical search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


# @router.post(
#     "/periodicals/search-metadata",
#     summary="Search for periodical metadata",
#     description="Query metadata providers (CrossRef, Wikipedia) for periodical information. Does not search for downloadable issues.",
#     responses={
#         200: {
#             "description": "Metadata retrieved successfully",
#             "content": {
#                 "application/json": {
#                     "example": {
#                         "query": "Wired",
#                         "results": [
#                             {
#                                 "title": "Wired Magazine",
#                                 "publisher": "Condé Nast",
#                                 "issn": "1059-1028",
#                             }
#                         ],
#                         "total": 1,
#                     }
#                 }
#             },
#         },
#         400: {"description": "Invalid query parameter", "model": APIError},
#         500: {"description": "Metadata search failed", "model": APIError},
#     },
# )
# async def search_periodical_metadata(query: str = Query(...)) -> Dict[str, Any]:
#     """
#     Search for periodical metadata using only METADATA providers (CrossRef, Wikipedia).
#     This does NOT include search providers like Newsnab or RSS.

#     Args:
#         query: Periodical title to search for (as query parameter)

#     Returns:
#         Periodical metadata from metadata sources
#     """
#     try:
#         if not query or len(query.strip()) < 2:
#             raise HTTPException(
#                 status_code=400, detail="Query must be at least 2 characters"
#             )

#         logger.debug(f"Searching for metadata: {query}")

#         if not _metadata_providers:
#             logger.warning("No metadata providers configured")
#             return {
#                 "found": False,
#                 "message": "No metadata providers available",
#                 "results": [],
#             }

#         all_results = []
#         for provider in _metadata_providers:
#             try:
#                 logger.debug(
#                     f"Searching metadata provider: {provider.name} (type: {provider.type})"
#                 )
#                 provider_results = provider.search(query.strip())
#                 logger.debug(
#                     f"Provider {provider.name} returned {len(provider_results)} results"
#                 )
#                 all_results.extend(provider_results)
#             except Exception as e:
#                 logger.warning(
#                     f"Error searching metadata provider {provider.__class__.__name__}: {e}",
#                     exc_info=True,
#                 )

#         if all_results:
#             logger.debug(f"Found {len(all_results)} metadata results for: {query}")
#             # Convert SearchResult objects to dictionaries
#             result_dicts = [
#                 {
#                     "title": result.title,
#                     "url": result.url,
#                     "provider": result.provider,
#                     "publication_date": (
#                         result.publication_date.isoformat()
#                         if result.publication_date
#                         else None
#                     ),
#                     "raw_metadata": result.raw_metadata or {},
#                 }
#                 for result in all_results[:50]  # Limit to 50 results
#             ]
#             return {
#                 "found": True,
#                 "results": result_dicts,
#                 "message": f"Found {len(all_results)} metadata results for '{query}'",
#             }
#         else:
#             logger.debug(f"No metadata results found for query: {query}")
#             return {
#                 "found": False,
#                 "message": f"No metadata found for '{query}'",
#                 "results": [],
#             }

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Metadata search error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


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
                        "editions": [
                            {"title": "Wired - Jan 2024", "url": "http://..."}
                        ],
                        "total": 1,
                    }
                }
            },
        },
        400: {"description": "Invalid periodical title", "model": APIError},
        503: {"description": "No search providers configured", "model": APIError},
    },
)
async def get_periodical_editions(magazine_title: str) -> Dict[str, Any]:
    """
    Get all editions/publications of a specific periodical by searching providers.

    Args:
        magazine_title: Periodical title (e.g., 'PC Gamer')

    Returns:
        List of search results for the periodical
    """
    try:
        if not magazine_title or len(magazine_title.strip()) < 2:
            raise HTTPException(status_code=400, detail="Invalid periodical title")

        if not _search_providers:
            logger.error("No search providers configured")
            raise HTTPException(
                status_code=503, detail="No search providers configured."
            )

        # Search across search providers for specific editions
        results = []
        for provider in _search_providers:
            try:
                provider_results = provider.search(magazine_title.strip())
                results.extend(provider_results)
            except Exception as e:
                logger.warning(
                    f"Error searching provider {provider.__class__.__name__}: {e}"
                )

        if results:
            return {"success": True, "results": results}
        else:
            raise HTTPException(
                status_code=404, detail=f"Could not find editions for {magazine_title}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get editions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
