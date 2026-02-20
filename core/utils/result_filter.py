"""
Search result filtering utilities.

Provides title-match validation and collection detection used by both the
auto-download pipeline (SearchService) and the UI search path (filters.py)
to ensure consistent result quality across all providers.
"""

import logging
import re
from typing import Any, Dict, Optional

from core.constants.validation import (
    COLLECTION_INDICATOR_WORDS,
    METADATA_WORDS,
    NON_PERIODICAL_KEYWORDS,
    PERIODICAL_INDICATOR_WORDS,
    PERIODICAL_MODIFIERS,
)

logger = logging.getLogger(__name__)

# Matches "YYYY-YYYY", "YYYY–YYYY", "YYYY to YYYY" — indicates a multi-year bundle
_YEAR_RANGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\s*[-–—]|to\s*(19\d{2}|20\d{2})\b", re.IGNORECASE)

# Matches a single modern year — a positive periodical signal when no range is present
_SINGLE_YEAR_RE = re.compile(r"\b(202[0-9]|203[0-9])\b")


def is_ia_collection(raw_metadata: Optional[Dict[str, Any]]) -> bool:
    """Return True if the IA metadata flags this item as a collection archive."""
    if not raw_metadata:
        return False
    return bool(raw_metadata.get("is_collection"))


def _has_year_range(title: str) -> bool:
    """Return True if the title contains a year range (e.g. '2020-2024', '2015 to 2020')."""
    return bool(_YEAR_RANGE_RE.search(title))


def _has_collection_indicators(title: str) -> bool:
    """Return True if the title contains multi-issue bundle keywords."""
    title_lower = title.lower()
    return any(indicator in title_lower for indicator in COLLECTION_INDICATOR_WORDS)


def _has_periodical_indicators(title: str) -> bool:
    """
    Return True if the title contains at least one signal that it is a single
    periodical issue (month name, issue number, volume, 'magazine', etc.).

    A single modern year counts as a positive signal unless it is part of a range.
    """
    title_lower = title.lower()

    if any(indicator in title_lower for indicator in PERIODICAL_INDICATOR_WORDS):
        return True

    if _SINGLE_YEAR_RE.search(title_lower) and not _has_year_range(title):
        return True

    return False


def _is_non_periodical(title: str, allow_collections: bool = False) -> bool:
    """
    Return True if the title should be rejected as non-periodical content.

    Catches multi-issue bundles (year ranges, collection keywords) and
    known non-periodical content types (photography books, manuals, etc.).

    Args:
        allow_collections: When True, skip the collection-indicator check.
            Used by the UI browse path where users intentionally browse
            collection archives (filter_collections=False).
    """
    title_lower = title.lower()

    if _has_year_range(title):
        return True

    if not allow_collections and _has_collection_indicators(title):
        return True

    return any(keyword in title_lower for keyword in NON_PERIODICAL_KEYWORDS)


def _has_periodical_modifier(title: str, query_term: str) -> tuple[bool, Optional[str]]:
    """
    Return True if a word immediately after the query term indicates a
    *different* periodical (e.g. "Wired Times" vs. "Wired").

    Skips metadata words, numbers, month names, and short variants like "UK".
    """
    words = title.split()
    try:
        query_idx = words.index(query_term.lower())
    except ValueError:
        return False, None

    for i in range(query_idx + 1, min(query_idx + 3, len(words))):
        word = words[i]
        if word in METADATA_WORDS:
            continue
        if re.match(r"^\d+$", word) or re.match(r"^\d{4}$", word):
            continue
        if re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", word):
            continue
        if len(word) <= 2:
            continue
        if word in PERIODICAL_MODIFIERS:
            return True, word

    return False, None


def _build_word_boundary_pattern(term: str) -> str:
    """
    Return a regex pattern that matches *term* as a whole word, handling
    terms that start or end with non-word characters (e.g. "c++", ".net").
    """
    escaped = re.escape(term)
    starts_with_word = bool(re.match(r"^\w", term))
    ends_with_word = bool(re.search(r"\w$", term))

    if starts_with_word and ends_with_word:
        return rf"\b{escaped}\b"
    elif starts_with_word:
        return rf"\b{escaped}(?=[^\w]|$)"
    elif ends_with_word:
        return rf"{escaped}\b"
    else:
        return escaped


def title_matches_query(
    result_title: str,
    search_query: str,
    min_match_ratio: float = 0.5,
    allow_collections: bool = False,
) -> bool:
    """
    Return True if *result_title* is a plausible match for *search_query*.

    Validation layers (applied in order):
    1. All significant query terms must appear in the title (word-boundary match).
       Short queries (1-2 terms) require 100 % match; longer queries require
       *min_match_ratio* (default 50 %).
    2. Non-periodical signals rejected (year ranges, photography/manual/etc.
       keywords; collection-bundle keywords unless *allow_collections* is True).
    3. For single-term queries:
       a. No periodical-modifier word immediately after the query term
          (rejects "Wired Times" when searching "Wired").
       b. At least one periodical indicator (month, issue number, "magazine", …).

    Args:
        allow_collections: When True, titles containing collection-indicator words
            (e.g. "complete collection", "archive") are not rejected on that basis.
            Pass True when the caller is in a UI browse context where collections
            are intentionally shown (*filter_collections=False* in filter_result).
    """
    normalized_title = re.sub(r"[_.\-]", " ", result_title.lower())
    normalized_query = re.sub(r"[_.\-]", " ", search_query.lower())

    significant_terms = [t for t in normalized_query.split() if len(t) >= 2]
    if not significant_terms:
        return True

    matching_terms = sum(
        1 for term in significant_terms if re.search(_build_word_boundary_pattern(term), normalized_title)
    )
    match_ratio = matching_terms / len(significant_terms)

    required_ratio = 1.0 if len(significant_terms) <= 2 else min_match_ratio
    if match_ratio < required_ratio:
        return False

    if _is_non_periodical(normalized_title, allow_collections=allow_collections):
        logger.debug(f"Rejected '{result_title}' for query '{search_query}': " f"non-periodical signals detected")
        return False

    if len(significant_terms) == 1:
        has_modifier, modifier = _has_periodical_modifier(normalized_title, significant_terms[0])
        if has_modifier:
            logger.debug(f"Rejected '{result_title}' for query '{search_query}': " f"periodical modifier '{modifier}'")
            return False

        if not allow_collections and not _has_periodical_indicators(normalized_title):
            logger.debug(f"Rejected '{result_title}' for query '{search_query}': " f"no periodical indicators found")
            return False

    return True


def filter_result(
    result_title: str,
    result_provider: str,
    raw_metadata: Optional[Dict[str, Any]],
    search_query: Optional[str] = None,
    filter_collections: bool = True,
) -> bool:
    """
    Return True if *result* should be kept, False if it should be dropped.

    For Internet Archive results applies collection detection and title-match
    validation.  Results from all other providers always pass.

    Args:
        result_title: Title of the search result.
        result_provider: Provider identifier (e.g. "internet_archive").
        raw_metadata: Provider metadata dict (used for IA collection flag).
        search_query: Original query string; skips title-match check when None.
        filter_collections: When False, collection archives are kept (used by
                            the UI search path where users browse collections).
    """
    if result_provider != "internet_archive":
        return True

    if filter_collections and is_ia_collection(raw_metadata):
        logger.debug(f"Filtered IA collection archive: {result_title}")
        return False

    if search_query and not title_matches_query(result_title, search_query, allow_collections=not filter_collections):
        logger.debug(f"Filtered poor title match: '{result_title}' (query: '{search_query}')")
        return False

    return True
