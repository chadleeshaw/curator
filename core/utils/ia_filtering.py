"""
Internet Archive result filtering utilities.

Shared between auto-download (SearchService) and UI search (filters.py)
to ensure consistent IA result quality in both paths.

IA search is broad: it returns items where the search term appears
anywhere in metadata, not just in the title. These filters protect
against collection archives and irrelevant matches.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def is_ia_collection(raw_metadata: Optional[Dict[str, Any]]) -> bool:
    """
    Check if an IA result is a collection archive (contains many issues, not a single issue).

    Args:
        raw_metadata: Result's raw_metadata dict

    Returns:
        True if this is a collection archive that should be skipped
    """
    if not raw_metadata:
        return False
    return bool(raw_metadata.get("is_collection"))


def ia_title_matches_query(result_title: str, search_query: str, min_match_ratio: float = 0.5) -> bool:
    """
    Verify an IA result's title actually matches the search query.

    IA returns items where the search term appears anywhere in metadata
    (description, creator, subject, etc.), not just the title. This
    function requires that a minimum fraction of significant search terms
    appear in the result title.

    Args:
        result_title: The title of the IA result
        search_query: The original search query
        min_match_ratio: Minimum fraction of significant search terms
                         that must appear in the title (default: 0.5 = 50%)

    Returns:
        True if the title is a reasonable match for the query
    """
    result_title_lower = result_title.lower()
    search_terms = search_query.lower().split()

    # Only check terms with 3+ characters (skip "the", "of", etc.)
    significant_terms = [t for t in search_terms if len(t) >= 3]
    if not significant_terms:
        return True  # No significant terms to check

    matching_terms = sum(1 for t in significant_terms if t in result_title_lower)
    match_ratio = matching_terms / len(significant_terms)
    return match_ratio >= min_match_ratio


def filter_ia_result(
    result_title: str,
    result_provider: str,
    raw_metadata: Optional[Dict[str, Any]],
    search_query: Optional[str] = None,
) -> bool:
    """
    Check whether an IA search result should be kept.

    Combines collection filtering and title-match verification into a
    single call. Non-IA results always pass.

    Args:
        result_title: Title of the search result
        result_provider: Provider name (e.g., "internet_archive")
        raw_metadata: Result's raw_metadata dict
        search_query: Original search query (for title-match verification).
                      If None, skips title-match check.

    Returns:
        True if the result should be kept, False if it should be filtered out
    """
    # Only apply IA-specific filters to IA results
    if result_provider != "internet_archive":
        return True

    # Filter out collection archives
    if is_ia_collection(raw_metadata):
        logger.debug(f"Filtering IA collection archive: {result_title}")
        return False

    # Verify title actually matches the search query
    if search_query and not ia_title_matches_query(result_title, search_query):
        logger.debug(
            f"Filtering IA result with poor title match: '{result_title}' " f"(searching for '{search_query}')"
        )
        return False

    return True
