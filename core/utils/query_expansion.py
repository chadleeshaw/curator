"""
Query expansion utilities for fuzzy search against providers.

Generates variations of search queries to improve match rates when titles are
stored differently in provider databases (e.g., "National Geographic Kids Travel"
vs "Kids Travel", "PC Gamer US" vs "PC Gamer United States").
"""

import logging
from typing import List, Set

from core.constants.edition import (
    EDITION_VARIANT_INDICATORS,
    REGIONAL_EDITION_INDICATORS,
)
from core.constants.title import COMMON_PERIODICAL_WORDS

logger = logging.getLogger(__name__)


def generate_query_variants(query: str, max_variants: int = 5) -> List[str]:
    """
    Generate search query variants to improve provider match rates.

    Strategy:
    1. Original query (highest priority)
    2. Remove common periodical words ("Magazine", "Journal", etc.)
    3. Remove regional indicators ("US", "UK", "USA", etc.)
    4. Remove edition variants ("Kids", "Professional", "Travel", etc.)
    5. Extract significant words (remove articles, keep meaningful terms)

    Args:
        query: Original search query
        max_variants: Maximum number of variants to generate (default: 5)

    Returns:
        List of query variants, ordered by specificity (most specific first)

    Examples:
        >>> generate_query_variants("National Geographic Kids Travel")
        ["National Geographic Kids Travel",
         "National Geographic Kids",
         "Geographic Kids Travel",
         "Kids Travel",
         "National Geographic"]

        >>> generate_query_variants("PC Gamer US Magazine")
        ["PC Gamer US Magazine",
         "PC Gamer US",
         "PC Gamer Magazine",
         "PC Gamer"]
    """
    if not query or len(query.strip()) < 2:
        return [query]

    variants: Set[str] = set()
    query_clean = query.strip()

    # Priority 1: Original query (exact match attempt)
    variants.add(query_clean)

    # Normalize for processing
    words = query_clean.split()

    # Priority 2: Remove common periodical words
    filtered_words = [w for w in words if w.lower() not in COMMON_PERIODICAL_WORDS]
    if filtered_words and len(filtered_words) != len(words):
        variants.add(" ".join(filtered_words))

    # Priority 3: Remove regional indicators
    regional_filtered = [w for w in words if w.lower() not in REGIONAL_EDITION_INDICATORS]
    if regional_filtered and len(regional_filtered) != len(words):
        variants.add(" ".join(regional_filtered))

    # Priority 4: Remove edition variants
    edition_filtered = [w for w in words if w.lower() not in EDITION_VARIANT_INDICATORS]
    if edition_filtered and len(edition_filtered) != len(words):
        variants.add(" ".join(edition_filtered))

    # Priority 5: Try combinations - keep first N significant words
    if len(words) > 2:
        # Keep first 2 words (e.g., "National Geographic" from "National Geographic Kids Travel")
        variants.add(" ".join(words[:2]))

        # Keep last 2 words (e.g., "Kids Travel" from "National Geographic Kids Travel")
        variants.add(" ".join(words[-2:]))

    # Priority 6: Remove articles and keep just significant words
    significant_words = [w for w in words if w.lower() not in {"the", "a", "an"}]
    if significant_words and len(significant_words) != len(words):
        variants.add(" ".join(significant_words))

    # Convert to list and sort by length (longer = more specific)
    variant_list = sorted(list(variants), key=len, reverse=True)

    # Limit to max_variants and ensure original query is always first
    if query_clean in variant_list:
        variant_list.remove(query_clean)
    variant_list.insert(0, query_clean)

    result = variant_list[:max_variants]
    logger.debug(f"Generated {len(result)} query variants for '{query}': {result}")
    return result


def expand_search_queries(
    query: str,
    max_queries: int = 3,
    min_query_length: int = 3,
) -> List[str]:
    """
    Generate expanded search queries for provider search.

    Similar to generate_query_variants but more conservative - only returns
    variants that are likely to improve results without too many false positives.

    Args:
        query: Original search query
        max_queries: Maximum number of queries to generate (default: 3)
        min_query_length: Minimum length for generated queries (default: 3 chars)

    Returns:
        List of search queries to try, ordered by priority

    Examples:
        >>> expand_search_queries("National Geographic Kids Travel")
        ["National Geographic Kids Travel",
         "National Geographic Kids",
         "Kids Travel"]

        >>> expand_search_queries("PC Gamer US")
        ["PC Gamer US",
         "PC Gamer"]
    """
    variants = generate_query_variants(query, max_variants=max_queries * 2)

    # Filter variants that are too short
    valid_variants = [v for v in variants if len(v) >= min_query_length]

    # Return top N
    result = valid_variants[:max_queries]
    logger.info(f"Expanded query '{query}' to {len(result)} searches: {result}")
    return result
