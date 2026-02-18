"""
Search result filtering functions.

Handles filtering of search results by language, country, periodical variants,
and non-periodical content.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.constants.country import LANGUAGE_TO_COUNTRY
from core.constants.periodical import AUDIENCE_PERIODICAL_INDICATORS
from core.constants.language import LANGUAGE_KEYWORDS
from core.parsers.country import detect_country
from core.utils.ia_filtering import filter_ia_result
from services.issue_discovery import IssueDiscoveryService

from .dependencies import get_title_matcher

logger = logging.getLogger(__name__)


def filter_periodical_variants(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Filter out periodical variants that don't match the query.

    If searching for "National Geographic", this filters OUT:
    - "National Geographic Little Kids" (different periodical)
    - "National Geographic Traveller" (different periodical)

    But KEEPS:
    - "National Geographic" (matches query)
    - "National Geographic December 2024" (same periodical, just with date)

    Args:
        results: List of search result dictionaries
        query: Original search query

    Returns:
        Filtered list with only results matching query periodical variant
    """
    if not results:
        return results

    title_matcher = get_title_matcher()
    if not title_matcher:
        logger.warning("TitleMatcher not available, skipping periodical variant filter")
        return results

    filtered = []

    # Extract edition variant from query
    query_variant = title_matcher.extract_periodical_variant(query)
    logger.debug(f"Filtering publication variants: Query '{query}' has variant: {query_variant}")
    logger.debug(f"Examining {len(results)} results...")

    # Determine if the query's variant is regional (country/geography-based: "uk", "us", "france", etc.)
    # vs. non-regional (audience/specialization-based: "kids", "pro", "expert", etc.).
    # Regional variants: any variant NOT in AUDIENCE_PERIODICAL_INDICATORS
    # Non-regional variants: "kids", "pro", "expert", "traveller", etc. (in AUDIENCE_PERIODICAL_INDICATORS)
    query_is_regional = query_variant is not None and query_variant not in AUDIENCE_PERIODICAL_INDICATORS

    for result in results:
        raw_title = result.get("title", "")

        # Lightly normalize the title (dots -> spaces) but preserve dates, issue numbers, country codes
        # Don't use clean_release_title() as it removes too much metadata
        normalized_title = raw_title.replace(".", " ").replace("_", " ")
        result_variant = title_matcher.extract_periodical_variant(normalized_title)

        # Keep result if publication variants are compatible:
        # - Both have no variant → keep (e.g., "National Geographic" query, "National Geographic" result)
        # - Both have the same variant → keep (e.g., "PC Gamer US" query, "PC Gamer US" result)
        # - Query has regional variant, result has no variant → keep
        #   Rationale: when searching "Nuts UK" with alias "Nuts", results like "Nuts Issue 45"
        #   are the same periodical just indexed without the regional suffix. Filtering these
        #   would silently drop valid issues found via the alias.
        # - Query has no variant, result has non-regional variant → filter (different periodical)
        # - Query has regional variant, result has different variant → filter (different periodical)
        keep = (
            (query_variant is None and result_variant is None)
            or (query_variant is not None and result_variant is not None and query_variant == result_variant)
            or (query_is_regional and result_variant is None)
        )

        if keep:
            filtered.append(result)
            logger.debug(f"  KEEP: '{raw_title}' -> '{normalized_title}' (variant: {result_variant})")
        else:
            logger.debug(
                f"  FILTERED: '{raw_title}' -> '{normalized_title}' (variant: {result_variant}) "
                f"doesn't match query '{query}' (variant: {query_variant})"
            )

    return filtered


def filter_non_periodicals(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter out non-periodical content (movies, audiobooks, soundtracks, etc.).

    Uses the same validation logic as IssueDiscoveryService to ensure
    only actual periodicals are returned to users.

    Args:
        results: List of search result dictionaries

    Returns:
        Filtered list with only periodical content
    """
    if not results:
        return results

    # Create a temporary IssueDiscoveryService instance for validation
    validator = IssueDiscoveryService()
    filtered = []

    for result in results:
        metadata = result.get("metadata", {})

        # Convert result dict to format expected by validator
        search_result = {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "provider": result.get("provider", ""),
            "category": metadata.get("category", ""),
            "size": metadata.get("size", 0),
        }

        # Validate using IssueDiscoveryService validation
        if validator._validate_is_periodical(search_result):
            filtered.append(result)
        else:
            logger.debug(f"[FILTER] Rejected as non-periodical: {result.get('title', '')}")

    logger.debug(f"[FILTER] Filtered {len(results) - len(filtered)} non-periodical results, kept {len(filtered)}")
    return filtered


def filter_ia_results(results: List[Dict[str, Any]], search_query: str) -> List[Dict[str, Any]]:
    """
    Filter Internet Archive results to remove poor title matches.

    IA search is broad — it returns items where the search term appears anywhere
    in metadata (description, creator, subject), not just the title. This filter
    removes results that don't actually match the search query.

    Collection archives are preserved so users can browse and download them
    from the UI. The auto-download path filters collections separately.

    Non-IA results pass through unchanged.

    Args:
        results: List of search result dictionaries
        search_query: The original search query for title-match verification

    Returns:
        Filtered list with only relevant IA results (plus all non-IA results)
    """
    if not results:
        return results

    filtered = []
    ia_filtered_count = 0

    for result in results:
        provider = result.get("provider", "")
        metadata = result.get("metadata", {})

        if filter_ia_result(
            result_title=result.get("title", ""),
            result_provider=provider,
            raw_metadata=metadata,
            search_query=search_query,
            filter_collections=False,
        ):
            filtered.append(result)
        else:
            ia_filtered_count += 1

    if ia_filtered_count > 0:
        logger.debug(f"[FILTER] Removed {ia_filtered_count} irrelevant Internet Archive results")

    return filtered


def filter_by_language_and_country(
    results: List[Dict[str, Any]], language: Optional[str] = None, country: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter search results by language and/or country.

    Looks for language and country indicators in titles (e.g., "UK", "DE", "German").
    Makes smart assumptions: German -> DE, FR -> French, etc.
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
    for code in ["US", "UK", "CA", "AU", "NZ", "IE"]:
        if code not in country_to_language:
            country_to_language[code] = "English"

    filtered = []

    for result in results:
        title = result.get("title", "").lower()

        # Detect country in title
        detected_country = detect_country(title)

        # Detect language in title using centralized LANGUAGE_KEYWORDS
        detected_language = None
        for lang, indicators in language_indicators.items():
            for indicator in indicators:
                if re.search(rf"\b{re.escape(indicator)}\b", title, re.IGNORECASE):
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
                    f"Inferred country {detected_country} from language {detected_language}: " f"{result['title'][:50]}"
                )

        # If we detected a country but no language, infer language from country
        if detected_country and not detected_language:
            if detected_country in country_to_language:
                detected_language = country_to_language[detected_country]
                logger.debug(
                    f"Inferred language {detected_language} from country {detected_country}: " f"{result['title'][:50]}"
                )

        # Default to US/English if no indicators found (most common)
        if not detected_country:
            detected_country = "US"
        if not detected_language:
            detected_language = "English"

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
            logger.debug(f"Match: '{result['title'][:50]}' - " f"Detected: {detected_language}/{detected_country}")
        else:
            logger.debug(
                f"Filtered out: '{result['title'][:50]}' - "
                f"Detected: {detected_language}/{detected_country}, "
                f"Wanted: {language}/{country}"
            )

    return filtered
