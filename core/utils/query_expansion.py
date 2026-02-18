"""
Query expansion utilities for fuzzy search against providers.

Generates variations of search queries to improve match rates when titles are
stored differently in provider databases (e.g., "National Geographic Kids Travel"
vs "Kids Travel", "PC Gamer US" vs "PC Gamer United States").
"""

import logging
from typing import List, Set

from core.constants.periodical import (
    AUDIENCE_PERIODICAL_INDICATORS,
    NORTH_AMERICAN_PERIODICAL_INDICATORS,
    OTHER_REGIONAL_PERIODICAL_INDICATORS,
)
from core.constants.title import COMMON_PERIODICAL_WORDS

logger = logging.getLogger(__name__)


def _contains_protected_country(words: List[str]) -> bool:
    """
    Check if a list of words contains a protected (non-North American) country indicator.

    Args:
        words: List of words to check

    Returns:
        True if any word is a protected country indicator
    """
    return any(w.lower() in OTHER_REGIONAL_PERIODICAL_INDICATORS for w in words)


def _is_too_generic(words: List[str]) -> bool:
    """
    Check if a variant is too generic (only common periodical words + countries/regions).

    Variants like "Magazine Germany" or "Journal Russia" are too broad and would
    return too many false positives.

    Args:
        words: List of words to check

    Returns:
        True if the variant would be too generic
    """
    if not words:
        return True

    # Check if all words are either common periodical words or country indicators
    all_words_lower = [w.lower() for w in words]
    for word in all_words_lower:
        if (
            word not in COMMON_PERIODICAL_WORDS
            and word not in OTHER_REGIONAL_PERIODICAL_INDICATORS
            and word not in NORTH_AMERICAN_PERIODICAL_INDICATORS
        ):
            # Found a meaningful word - not too generic
            return False

    # All words are either common periodical words or countries - too generic
    return True


def generate_query_variants(query: str, max_variants: int = 5) -> List[str]:
    """
    Generate search query variants to improve provider match rates.

    Strategy:
    1. Original query (highest priority)
    2. Remove common periodical words ("Magazine", "Journal", etc.)
    3. Remove North American regional indicators ("US", "UK", "USA", "Canada")
       - International editions (Russia, Germany, France, etc.) are preserved
       - US/UK magazines typically don't include country in their name
       - International editions DO include country as part of their identity
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

        >>> generate_query_variants("Magazine Russia")
        ["Magazine Russia",
         "MG Russia",
         "Russia"]
        # Note: "Magazine" alone is NOT generated - Russia is preserved
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

    # Priority 3: Generate US/USA variants and remove North American regional indicators
    # For US editions, generate both "US" and "USA" variants since providers
    # may list titles either way (e.g., "Wired US" vs "Wired USA")
    # Also generate variant without regional indicator (e.g., "Wired")
    has_us = "us" in [w.lower() for w in words]
    has_usa = "usa" in [w.lower() for w in words]

    if has_us or has_usa:
        # Generate variant with alternate US/USA form
        if has_us:
            # Generate USA variant
            usa_words = [w if w.lower() != "us" else "USA" for w in words]
            variants.add(" ".join(usa_words))
        elif has_usa:
            # Generate US variant
            us_words = [w if w.lower() != "usa" else "US" for w in words]
            variants.add(" ".join(us_words))

    # Also generate variant without North American regional indicators
    # International editions (Russia, Germany, France, etc.) preserve their country
    # because it's part of their identity
    regional_filtered = [w for w in words if w.lower() not in NORTH_AMERICAN_PERIODICAL_INDICATORS]
    if regional_filtered and len(regional_filtered) != len(words):
        variants.add(" ".join(regional_filtered))

    # Priority 4: Remove edition variants
    edition_filtered = [w for w in words if w.lower() not in AUDIENCE_PERIODICAL_INDICATORS]
    if edition_filtered and len(edition_filtered) != len(words):
        variants.add(" ".join(edition_filtered))

    # Priority 5: Try combinations - keep first N significant words
    # BUT: Never drop protected (non-North American) country indicators
    # AND: Never create variants that are too generic (only common words + country)
    if len(words) > 2:
        # Keep first 2 words if it doesn't drop a protected country and isn't too generic
        first_two = words[:2]
        dropped_words = words[2:]
        if not _contains_protected_country(dropped_words) and not _is_too_generic(first_two):
            variants.add(" ".join(first_two))

        # Keep last 2 words if it doesn't drop a protected country and isn't too generic
        last_two = words[-2:]
        dropped_words = words[:-2]
        if not _contains_protected_country(dropped_words) and not _is_too_generic(last_two):
            variants.add(" ".join(last_two))

    # Priority 6: Remove articles and keep just significant words
    significant_words = [w for w in words if w.lower() not in {"the", "a", "an"}]
    if significant_words and len(significant_words) != len(words):
        variants.add(" ".join(significant_words))

    # Priority 7: Generate abbreviated variants (e.g., "Magazine USA" → "MG USA")
    if len(words) >= 2:
        # Abbreviate first word if it's long enough (4+ chars) and not already abbreviated
        first_word = words[0]
        if len(first_word) >= 4 and first_word.upper() != first_word:
            # Generate 2-letter abbreviation using prominent consonants
            # Skip position-1 consonants to avoid unwanted abbreviations
            # "Magazine" → "MG" (M at pos 0, G at pos 2)
            # "Wired" → "WR" (W at pos 0, R at pos 2)
            consonants = []
            for i, char in enumerate(first_word):
                if char.isalpha() and char.lower() not in "aeiouy":
                    # Skip consonants immediately after first letter
                    if i != 1:
                        consonants.append(char.upper())
                        if len(consonants) == 2:
                            break

            # Fallback: use first 2 letters if we don't have 2 consonants
            if len(first_word) >= 2 > len(consonants):
                initials = first_word[0].upper() + first_word[1].upper()
            else:
                initials = "".join(consonants[:2]) if len(consonants) >= 2 else None

            if initials and len(initials) == 2:
                # Create variant with initials + remaining words
                abbreviated = f"{initials} {' '.join(words[1:])}"
                variants.add(abbreviated)

                # Also create variant with initials only (no North American regional indicators)
                remaining_words = [w for w in words[1:] if w.lower() not in NORTH_AMERICAN_PERIODICAL_INDICATORS]
                if remaining_words:
                    variants.add(f"{initials} {' '.join(remaining_words)}")
                else:
                    variants.add(initials)

    # Convert to list and sort by custom ranking
    # Ranking priority:
    # 1. Original query (most specific)
    # 2. Last N words (often the actual magazine title)
    # 3. Variants without regional indicators (broader, higher match rate)
    # 4. US/USA swap variants (specific alternative forms)
    # 5. Longer variants (more specific)
    # 6. Shorter variants (broader match)
    def rank_variant(v: str) -> tuple:
        is_original = 1 if v == query_clean else 0
        is_last_words = 1 if len(words) > 2 and v == " ".join(words[-2:]) else 0

        # Check if this is a variant without regional indicators
        # (original had US/USA but this variant doesn't)
        had_regional = any(w.lower() in NORTH_AMERICAN_PERIODICAL_INDICATORS for w in words)
        has_regional = any(w.lower() in NORTH_AMERICAN_PERIODICAL_INDICATORS for w in v.split())
        is_regional_removed = 1 if had_regional and not has_regional else 0

        return (-is_original, -is_last_words, -is_regional_removed, -len(v))

    variant_list = sorted(list(variants), key=rank_variant)

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
    # Check if query contains US/USA - if so, add 1 to max to ensure both variants are included
    words = query.split()
    has_us_variant = any(w.lower() in {"us", "usa"} for w in words)
    effective_max = max_queries + 1 if has_us_variant else max_queries

    variants = generate_query_variants(query, max_variants=effective_max * 2)

    # Filter variants that are too short
    valid_variants = [v for v in variants if len(v) >= min_query_length]

    # Return top N (with bonus slot for US/USA variants)
    result = valid_variants[:effective_max]
    logger.debug(f"Expanded query '{query}' to {len(result)} searches: {result}")
    return result
