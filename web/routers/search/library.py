"""
Library matching and deduplication helpers.

Handles matching search results against the local library and
deduplicating results that already exist in the library.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from core.constants.date import NUMBER_TO_MONTH
from core.parsers import utc_now
from models.database import DownloadSubmission

from core.utils.fuzzy_matching import get_fuzzy_group_id
from .dependencies import get_title_matcher
from .filters import filter_by_language_and_country

logger = logging.getLogger(__name__)


def deduplicate_against_library(
    results: List[Dict[str, Any]],
    library_items: List,
) -> List[Dict[str, Any]]:
    """
    Mark provider results that already exist in library, keeping them as replacement options.

    Provider results matching library items are marked as already_downloaded instead of being
    removed. This allows the frontend to show them as replacement/re-download options in the
    library item detail modal.

    Args:
        results: Provider results to check against library
        library_items: Library items to check against

    Returns:
        All results with library-matching ones marked accordingly
    """
    deduplicated = []
    title_matcher = get_title_matcher()

    for result in results:
        matched_library_item = None

        for lib_item in library_items:
            if result.get("publication_date") and title_matcher:
                is_match, score = title_matcher.matches_library_item_with_date_range(
                    provider_title=result["title"],
                    provider_date=result["publication_date"],
                    library_title=lib_item.title,
                    library_date=lib_item.issue_date,
                    date_tolerance_days=7,
                )

                if is_match:
                    matched_library_item = lib_item
                    logger.debug(
                        f"Library match: '{result['title']}' matches library item "
                        f"'{lib_item.title}' (score: {score})"
                    )
                    break

        if matched_library_item:
            # Keep the result but mark it as already in library
            result["status"] = "available"
            result["status_badge"] = "Available"
            result["library_item_id"] = matched_library_item.id
            result["already_downloaded"] = True
            result["download_failed"] = False
            result["from_provider"] = True

            # Format publication date to ISO string
            pub_date = result.get("publication_date")
            if pub_date:
                if isinstance(pub_date, datetime):
                    result["publication_date"] = pub_date.isoformat()
                elif not isinstance(pub_date, str):
                    result["publication_date"] = str(pub_date)

            deduplicated.append(result)
        else:
            # Add status badge for available items
            result["status"] = "available"
            result["status_badge"] = "Available"
            result["library_item_id"] = None
            result["already_downloaded"] = False
            result["download_failed"] = False
            result["from_provider"] = True

            # Format publication date to ISO string
            pub_date = result.get("publication_date")
            if pub_date:
                if isinstance(pub_date, datetime):
                    result["publication_date"] = pub_date.isoformat()
                elif not isinstance(pub_date, str):
                    result["publication_date"] = str(pub_date)

            deduplicated.append(result)

    return deduplicated


def mark_failed_downloads(
    results: List[Dict[str, Any]],
    tracking_id: Optional[int],
    db,
) -> None:
    """
    Mark results that have previously failed to download.

    Args:
        results: Results to mark (modified in place)
        tracking_id: Optional tracking ID to scope failures
        db: Database session
    """
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

    for result in results:
        fuzzy_group = get_fuzzy_group_id(result["title"])
        if fuzzy_group in failed_fuzzy_groups:
            result["status"] = "failed"
            result["status_badge"] = "Failed Before"
            result["download_failed"] = True


def get_library_matches(
    query: str,
    library_items: List,
    filter_language: str,
    filter_country: str,
) -> List[Dict[str, Any]]:
    """
    Get library items that match the search query.

    Args:
        query: Search query
        library_items: Library items to check
        filter_language: Language filter
        filter_country: Country filter

    Returns:
        List of library match dicts with status badges
    """
    matches = []
    title_matcher = get_title_matcher()

    if not title_matcher:
        return matches

    for lib_item in library_items:
        is_match, score = title_matcher.match(query.strip(), lib_item.title)

        if is_match:
            # Append month and year to title for frontend parser to correctly group issues
            if lib_item.issue_date:
                year = lib_item.issue_date.year
                month_name = NUMBER_TO_MONTH.get(lib_item.issue_date.month)
                if month_name:
                    title_with_year = f"{lib_item.title} {month_name} {year}"
                else:
                    title_with_year = f"{lib_item.title} {year}"
            else:
                title_with_year = lib_item.title

            matches.append(
                {
                    "title": title_with_year,
                    "publication_date": lib_item.issue_date.isoformat() if lib_item.issue_date else None,
                    "status": "in_library",
                    "status_badge": "In Library",
                    "library_item_id": lib_item.id,
                    "file_path": lib_item.file_path,
                    "cover_path": lib_item.cover_path,
                    "provider": "Library",
                    "url": "",
                    "metadata": lib_item.extra_metadata or {},
                    "already_downloaded": True,
                    "download_failed": False,
                    "from_provider": False,
                }
            )

    # Apply language/country filter
    return filter_by_language_and_country(matches, filter_language, filter_country)


def sort_results_by_relevance(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Sort results by fuzzy match score and date.

    Args:
        results: Results to sort
        query: Original search query

    Returns:
        Sorted results list
    """
    title_matcher = get_title_matcher()
    if not title_matcher:
        return results

    def _get_date_timestamp(pub_date) -> float:
        """Safely get timestamp from publication_date."""
        if not pub_date:
            return 0
        if isinstance(pub_date, datetime):
            return pub_date.timestamp()
        if isinstance(pub_date, str):
            try:
                return datetime.fromisoformat(pub_date.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                return 0
        return 0

    scored_results = []
    for result in results:
        is_match, score = title_matcher.match(query.strip(), result["title"])
        scored_results.append((result, score))

    scored_results.sort(
        key=lambda x: (
            -x[1],  # Higher score first
            -_get_date_timestamp(x[0].get("publication_date")),
        )
    )

    return [r[0] for r in scored_results]


def build_search_response(
    query: str,
    library_matches: List[Dict[str, Any]],
    provider_results: List[Dict[str, Any]],
    cached_results: List,
    provider_errors: List[str],
) -> Dict[str, Any]:
    """
    Build the final search response dict.

    Args:
        query: Original search query
        library_matches: Library match results
        provider_results: Provider results (deduplicated)
        cached_results: Cached results (for age calculation)
        provider_errors: List of provider errors

    Returns:
        Response dict
    """
    # Calculate cache age once (handle naive/aware datetime comparison)
    cache_age_days = None
    if cached_results:
        now = utc_now()
        cache_created = cached_results[0].created_at
        # Strip timezone if needed for consistent comparison with SQLite naive datetimes
        if cache_created and cache_created.tzinfo is None:
            now = now.replace(tzinfo=None)
        cache_age_days = (now - cache_created).days if cache_created else None

    final_results = library_matches + provider_results

    if final_results:
        sample_titles = [r.get("title", "N/A") for r in final_results[:3]]
        logger.debug(f"Sample result titles: {sample_titles}")

        return {
            "found": True,
            "results": final_results,
            "library_matches": len(library_matches),
            "available_to_download": len([r for r in provider_results if r.get("status") == "available"]),
            "total_results": len(final_results),
            "provider_errors": provider_errors if provider_errors else None,
            "from_cache": len(cached_results) > 0,
            "cache_age_days": cache_age_days,
            "message": f"Found {len(final_results)} results for '{query}'",
        }

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
        "cache_age_days": cache_age_days,
    }
