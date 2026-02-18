"""
Search result caching and deduplication helpers.

Handles caching of search results in the database and merging
cached results with fresh results from providers.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.parsers import utc_now
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import DownloadSubmission, SearchResult

logger = logging.getLogger(__name__)


def _normalize_publication_date(pub_date: Any) -> Optional[datetime]:
    """
    Normalize publication_date to datetime object.

    Handles both string (ISO format) and datetime objects.

    Args:
        pub_date: Publication date as string or datetime

    Returns:
        datetime object or None if invalid
    """
    if not pub_date:
        return None

    if isinstance(pub_date, str):
        try:
            return datetime.fromisoformat(pub_date.rstrip("Z"))
        except (ValueError, AttributeError):
            logger.debug(f"Failed to parse publication_date string: {pub_date}")
            return None
    elif isinstance(pub_date, datetime):
        return pub_date
    else:
        logger.debug(f"Unexpected publication_date type: {type(pub_date)}")
        return None


def _get_date_key(pub_date: Any) -> Optional[str]:
    """
    Extract YYYY-MM date key from publication date.

    Args:
        pub_date: Publication date as string or datetime

    Returns:
        Date key string (YYYY-MM) or None
    """
    normalized = _normalize_publication_date(pub_date)
    return normalized.strftime("%Y-%m") if normalized else None


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
    cutoff_date = utc_now() - timedelta(days=cache_ttl_days)

    cached_query = (
        db_session.query(SearchResult)
        .filter(SearchResult.query == query)
        .filter(SearchResult.created_at >= cutoff_date)
    )

    # If tracking_id provided, filter by associated tracking
    if tracking_id:
        try:
            cached_query = cached_query.join(DownloadSubmission, isouter=True).filter(
                or_(
                    DownloadSubmission.tracking_id == tracking_id,
                    DownloadSubmission.tracking_id.is_(None),
                )
            )
        except SQLAlchemyError as e:
            logger.warning(f"Failed to join DownloadSubmission for tracking_id {tracking_id}: {e}")
            # Fall back to unfiltered cache results if join fails
            logger.debug("Returning cache results without tracking_id filter")

    try:
        return cached_query.all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving cached search results: {e}")
        return []


def save_search_results_to_cache(
    db_session,
    query: str,
    results: List[Dict[str, Any]],
    tracking_id: Optional[int] = None,
) -> None:
    """
    Save new search results to database cache.

    Deduplicates against existing cache by:
    - Fuzzy match group ID (title similarity only)
    - Publication date (same month, stored separately)

    Note: fuzzy_group_id is title-only for consistency. Publication date
    is stored separately and used for month-level deduplication.
    """
    for result in results:
        # Normalize publication date for consistent handling
        pub_date = _normalize_publication_date(result.get("publication_date"))

        # Get or generate fuzzy match group for deduplication (reuse if already calculated)
        fuzzy_group_id = result.get("fuzzy_match_group_id") or get_fuzzy_group_id(result["title"])

        # Store in result dict for downstream use
        result["fuzzy_match_group_id"] = fuzzy_group_id

        # Check if already cached
        if pub_date:
            # SQLite-compatible month comparison using strftime
            pub_month = pub_date.strftime("%Y-%m")

            existing = (
                db_session.query(SearchResult)
                .filter(SearchResult.fuzzy_match_group_id == fuzzy_group_id)
                .filter(SearchResult.query == query)
                .filter(func.strftime("%Y-%m", SearchResult.publication_date) == pub_month)
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
    except IntegrityError:
        # Unique constraint violation - another request cached the same result concurrently
        # This is expected in high-concurrency scenarios, just rollback silently
        db_session.rollback()
        logger.debug("Cache entry already exists (concurrent insert), skipping")
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
        # Normalize publication date for type safety
        pub_date = _normalize_publication_date(r.get("publication_date"))

        # Get fuzzy_group_id (already calculated by SearchService or from cache)
        fuzzy_group = r.get("fuzzy_match_group_id") or get_fuzzy_group_id(r["title"])
        date_key = _get_date_key(pub_date)
        fresh_keys.add((fuzzy_group, date_key))

    # Filter out cached results that exist in fresh results
    deduplicated_cached = []
    for r in cached_dicts:
        # Use helper for type-safe date key extraction
        date_key = _get_date_key(r.get("publication_date"))
        key = (r["fuzzy_match_group_id"], date_key)

        if key not in fresh_keys:
            deduplicated_cached.append(r)

    # Mark fresh results
    for r in fresh_results:
        r["from_cache"] = False

    # Merge and return
    return fresh_results + deduplicated_cached
