"""
Search result caching and deduplication helpers.

Handles caching of search results in the database and merging
cached results with fresh results from providers.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from core.parsers.date import normalize_month_name
from models.database import DownloadSubmission, SearchResult

logger = logging.getLogger(__name__)


def get_fuzzy_group_id(title: str) -> str:
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


def get_cached_search_results(
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


def save_search_results_to_cache(
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
        fuzzy_group_id = get_fuzzy_group_id(result["title"])

        # Check if already cached
        pub_date = result.get("publication_date")
        if pub_date:
            # SQLite-compatible month comparison using strftime
            # Format: YYYY-MM for month-level comparison
            if isinstance(pub_date, str):
                try:
                    pub_date_obj = datetime.fromisoformat(pub_date.rstrip("Z"))
                    pub_month = pub_date_obj.strftime("%Y-%m")
                except (ValueError, AttributeError):
                    pub_month = None
            else:
                pub_month = pub_date.strftime("%Y-%m") if pub_date else None

            if pub_month:
                existing = (
                    db_session.query(SearchResult)
                    .filter(SearchResult.fuzzy_match_group_id == fuzzy_group_id)
                    .filter(SearchResult.query == query)
                    .filter(func.strftime("%Y-%m", SearchResult.publication_date) == pub_month)
                    .first()
                )
            else:
                existing = (
                    db_session.query(SearchResult)
                    .filter(SearchResult.fuzzy_match_group_id == fuzzy_group_id)
                    .filter(SearchResult.query == query)
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


def merge_search_results(
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
        fuzzy_group = get_fuzzy_group_id(r["title"])
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
