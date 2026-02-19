"""
Internet Archive result filtering utilities.

Shared between auto-download (SearchService) and UI search (filters.py)
to ensure consistent IA result quality in both paths.

IA search is broad: it returns items where the search term appears
anywhere in metadata, not just in the title. These filters protect
against collection archives and irrelevant matches.
"""

import logging
import re
from typing import Any, Dict, Optional

from core.constants.validation import METADATA_WORDS, PERIODICAL_MODIFIERS

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


def _has_periodical_modifier(title: str, query_term: str) -> tuple[bool, Optional[str]]:
    """
    Check if title has modifying words after the query term that indicate
    a DIFFERENT periodical (not just a variant).

    Examples:
        "Wired Times" has modifier "times" → different periodical
        "Wired Magazine" has no modifier (magazine is metadata) → same periodical
        "Wired UK" has no modifier (UK is regional variant) → same periodical

    Args:
        title: Normalized title (lowercase, spaces instead of dots/dashes)
        query_term: The search term to look for

    Returns:
        Tuple of (has_modifier, modifier_word)
    """
    words = title.split()
    query_lower = query_term.lower()

    # Find where query term appears
    try:
        query_idx = words.index(query_lower)
    except ValueError:
        # Query term not found as whole word
        return False, None

    # Check next 2-3 words after the query term
    for i in range(query_idx + 1, min(query_idx + 3, len(words))):
        if i >= len(words):
            break

        word = words[i]

        # Skip metadata words
        if word in METADATA_WORDS:
            continue

        # Skip numbers and dates
        if re.match(r"^\d+$", word):  # Pure numbers
            continue
        if re.match(r"^\d{4}$", word):  # Years
            continue
        if re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", word):  # Months
            continue

        # Skip very short words (likely acronyms/variants like "UK", "US")
        if len(word) <= 2:
            continue

        # Check if it's a known periodical modifier
        if word in PERIODICAL_MODIFIERS:
            return True, word

    return False, None


def _build_word_boundary_pattern(term: str) -> str:
    """
    Create a regex pattern with smart word boundaries for matching terms.

    Handles special characters correctly:
    - "magazine" -> uses \b on both sides (normal word)
    - "c++" -> uses \b at start, lookahead at end (ends with special char)

    This fixes the issue where "c++ Magazine" searches failed because \b doesn't
    work after non-word characters like +.

    Args:
        term: Search term (already lowercased)

    Returns:
        Regex pattern string with appropriate word boundaries
    """
    escaped = re.escape(term)

    # Check if term starts/ends with word character (alphanumeric or underscore)
    starts_with_word = bool(re.match(r"^\w", term))
    ends_with_word = bool(re.search(r"\w$", term))

    if starts_with_word and ends_with_word:
        # Normal word like "magazine" - use boundaries on both sides
        return rf"\b{escaped}\b"
    elif starts_with_word and not ends_with_word:
        # Word ending with special char like "40+" or "c++"
        # Use boundary at start, lookahead for space/non-word/end at finish
        return rf"\b{escaped}(?=\s|[^\w]|$)"
    elif not starts_with_word and ends_with_word:
        # Word starting with special char (rare, e.g., ".net", "+plus")
        # Can't use lookbehind (variable width), so just match the term with end boundary
        return rf"{escaped}\b"
    else:
        # All special chars (very rare)
        return escaped


def ia_title_matches_query(result_title: str, search_query: str, min_match_ratio: float = 0.5) -> bool:
    """
    Verify a search result's title actually matches the search query.

    Uses word-boundary matching and adaptive thresholds to filter out
    irrelevant results like industrial standards ("Hexagon Nuts and Bolts")
    when searching for magazine names ("Nuts UK").

    BUGS FIXED:
    - Bug #1: Now uses word boundaries to avoid substring matches
      (e.g., "nuts" no longer matches "donuts", "peanuts")
    - Bug #2: Adaptive threshold - requires 100% match for short queries
      (1-2 terms) to prevent broad matches like gardening books
    - Bug #3: Now checks 2+ character terms to include magazine names
      like "PC", "GQ", "OK"
    - Bug #4: Single-term queries check for periodical modifiers
      (e.g., "Wired" doesn't match "Wired Times")

    Args:
        result_title: The title of the search result
        search_query: The original search query
        min_match_ratio: Minimum fraction of significant search terms
                         that must appear in the title (default: 0.5 = 50%)
                         NOTE: Overridden for short queries (1-2 terms require 100%)

    Returns:
        True if the title is a reasonable match for the query
    """
    # Normalize title: replace underscores, dots, hyphens with spaces for word boundary matching
    # Before: "Time_Magazine" is one word, "magazine" doesn't match
    # After: "Time Magazine" allows "magazine" to match
    normalized_title = re.sub(r"[_.\-]", " ", result_title.lower())
    # Normalize query the same way as title (replace _, ., - with spaces)
    normalized_query = re.sub(r"[_.\-]", " ", search_query.lower())
    search_terms = normalized_query.split()

    # Check terms with 2+ characters (includes "PC", "GQ", "OK" but skips "a", "of", "the")
    # BUG FIX: Changed from 3+ to 2+ to include magazine abbreviations
    significant_terms = [t for t in search_terms if len(t) >= 2]
    if not significant_terms:
        return True  # No significant terms to check

    # BUG FIX: Use word boundaries to match whole words only
    # Before: "nuts" matched "donuts", "peanuts", "coconuts"
    # After: "nuts" only matches whole word "nuts"
    matching_terms = 0
    for term in significant_terms:
        # Escape special regex chars and match whole words
        # Use smart word boundaries to handle special chars like + in "40+"
        pattern = _build_word_boundary_pattern(term)
        if re.search(pattern, normalized_title):
            matching_terms += 1

    match_ratio = matching_terms / len(significant_terms)

    # BUG FIX: Adaptive threshold based on query length
    # Short queries (1-2 terms) require ALL terms to match (100%)
    # to avoid broad matches like "Cold-Hardy Fruits and Nuts" for "Nuts UK"
    if len(significant_terms) <= 2:
        required_ratio = 1.0  # 100% match required
        logger.debug(
            f"Short query '{search_query}' ({len(significant_terms)} terms) "
            f"requires 100% match: {matching_terms}/{len(significant_terms)} matched in '{result_title}'"
        )
    else:
        required_ratio = min_match_ratio  # Use provided ratio (default 50%)
        logger.debug(
            f"Long query '{search_query}' ({len(significant_terms)} terms) "
            f"requires {required_ratio * 100}% match: {matching_terms}/{len(significant_terms)} matched in '{result_title}'"
        )

    # First check: do the search terms appear in the title?
    if match_ratio < required_ratio:
        return False

    # BUG FIX #4: For single-term queries, check for periodical modifiers
    # "Wired" should NOT match "Wired Times" (different periodical)
    if len(significant_terms) == 1:
        has_modifier, modifier = _has_periodical_modifier(normalized_title, significant_terms[0])
        if has_modifier:
            logger.debug(
                f"Single-term query '{search_query}' rejected '{result_title}' "
                f"due to periodical modifier '{modifier}'"
            )
            return False

    return True


def filter_ia_result(
    result_title: str,
    result_provider: str,
    raw_metadata: Optional[Dict[str, Any]],
    search_query: Optional[str] = None,
    filter_collections: bool = True,
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
        filter_collections: If True (default), filter out collection archives.
                            Set to False for UI search where users can browse collections.

    Returns:
        True if the result should be kept, False if it should be filtered out
    """
    # Only apply IA-specific filters to IA results
    if result_provider != "internet_archive":
        return True

    # Filter out collection archives (unless disabled for UI search)
    if filter_collections and is_ia_collection(raw_metadata):
        logger.debug(f"Filtering IA collection archive: {result_title}")
        return False

    # Verify title actually matches the search query
    if search_query and not ia_title_matches_query(result_title, search_query):
        logger.debug(
            f"Filtering IA result with poor title match: '{result_title}' " f"(searching for '{search_query}')"
        )
        return False

    return True
