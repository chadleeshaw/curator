"""
Search routes for periodicals
"""

import logging
import re
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from models.database import Magazine
from web.schemas import SearchRequest

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


@router.post("/search")
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


@router.post("/periodicals/search-providers")
async def search_periodical_providers(query: str = Query(...)) -> Dict[str, Any]:
    """
    Search for periodical issues by querying SEARCH providers only (Newsnab, RSS).
    Does NOT query metadata providers - use /api/periodicals/search-metadata for that.

    Args:
        query: Periodical title to search for (as query parameter)

    Returns:
        Issue search results from search providers
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
                        provider_results = provider.search(query.strip())
                        all_results.extend(provider_results)
                    except Exception as e:
                        error_msg = f"{provider.__class__.__name__}: {str(e)}"
                        logger.warning(f"Error searching provider: {error_msg}")
                        provider_errors.append(error_msg)
            else:
                error_msg = "No search providers configured"
                logger.warning(error_msg)
                provider_errors.append(error_msg)

            # Get all existing magazines from database
            existing_magazines = db_session.query(Magazine).all()
            existing_titles = {m.title.lower() for m in existing_magazines}

            # Search library for matching titles by query substring
            query_lower = query.strip().lower()
            matching_library_issues = [
                m for m in existing_magazines if query_lower in m.title.lower()
            ]

            # Convert provider results to dictionaries
            result_dicts = [
                {
                    "title": result.title,
                    "url": result.url,
                    "provider": result.provider,
                    "publication_date": (
                        result.publication_date.isoformat()
                        if result.publication_date
                        else None
                    ),
                    "metadata": result.raw_metadata or {},
                    "already_downloaded": result.title.lower() in existing_titles,
                    "from_provider": True,
                }
                for result in all_results[:200]  # Increase limit before filtering
            ]

            # Filter out edition variants (kids, traveller, etc.)
            result_dicts = _filter_edition_variants(result_dicts, query)
            result_dicts = result_dicts[:100]  # Limit to 100 after filtering

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


@router.post("/periodicals/search-metadata")
async def search_periodical_metadata(query: str = Query(...)) -> Dict[str, Any]:
    """
    Search for periodical metadata using only METADATA providers (CrossRef, Wikipedia).
    This does NOT include search providers like Newsnab or RSS.

    Args:
        query: Periodical title to search for (as query parameter)

    Returns:
        Periodical metadata from metadata sources
    """
    try:
        if not query or len(query.strip()) < 2:
            raise HTTPException(
                status_code=400, detail="Query must be at least 2 characters"
            )

        logger.debug(f"Searching for metadata: {query}")

        if not _metadata_providers:
            logger.warning("No metadata providers configured")
            return {
                "found": False,
                "message": "No metadata providers available",
                "results": [],
            }

        all_results = []
        for provider in _metadata_providers:
            try:
                logger.debug(
                    f"Searching metadata provider: {provider.name} (type: {provider.type})"
                )
                provider_results = provider.search(query.strip())
                logger.debug(
                    f"Provider {provider.name} returned {len(provider_results)} results"
                )
                all_results.extend(provider_results)
            except Exception as e:
                logger.warning(
                    f"Error searching metadata provider {provider.__class__.__name__}: {e}",
                    exc_info=True,
                )

        if all_results:
            logger.debug(f"Found {len(all_results)} metadata results for: {query}")
            # Convert SearchResult objects to dictionaries
            result_dicts = [
                {
                    "title": result.title,
                    "url": result.url,
                    "provider": result.provider,
                    "publication_date": (
                        result.publication_date.isoformat()
                        if result.publication_date
                        else None
                    ),
                    "raw_metadata": result.raw_metadata or {},
                }
                for result in all_results[:50]  # Limit to 50 results
            ]
            return {
                "found": True,
                "results": result_dicts,
                "message": f"Found {len(all_results)} metadata results for '{query}'",
            }
        else:
            logger.debug(f"No metadata results found for query: {query}")
            return {
                "found": False,
                "message": f"No metadata found for '{query}'",
                "results": [],
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Metadata search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/periodicals/editions/{magazine_title}")
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
