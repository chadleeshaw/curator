"""
Language detection utilities for periodicals.

Detects language from title, filename, or metadata.
"""

import re
from typing import Optional

from core.constants.country import COUNTRY_TO_LANGUAGE
from core.constants.language import (
    DEFAULT_LANGUAGE,
    LANGUAGE_KEYWORDS,
)


# Use language keywords from constants
LANGUAGE_INDICATORS = LANGUAGE_KEYWORDS


def detect_language(text: str, default: str = DEFAULT_LANGUAGE) -> str:
    """
    Detect language from text (title, filename, or description).

    Args:
        text: Text to analyze (title, filename, etc.)
        default: Default language if none detected (default: DEFAULT_LANGUAGE)

    Returns:
        Detected language name (capitalized), or default if not detected

    Examples:
        >>> detect_language("Wired.Magazine.No.10.2024.GERMAN.HYBRID.MAGAZINE")
        'German'
        >>> detect_language("Wired Magazine February 2024")
        'English'
    """
    if not text:
        return default

    text_upper = text.upper()

    # Check for language indicators
    for language, indicators in LANGUAGE_INDICATORS.items():
        for indicator in indicators:
            # Look for whole word matches or as part of compound words (case-insensitive)
            if re.search(rf"\b{re.escape(indicator.upper())}\b", text_upper):
                return language.capitalize()

    # Default to configured default language if no language indicator found
    return default


def infer_language_from_country(country: Optional[str], current_language: str) -> str:
    """
    Infer language from country code if language is still default.

    This is useful when country is detected but language is not explicitly specified.
    For example: "Wired UK" → country="UK", language inferred as "English"

    Args:
        country: ISO country code (e.g., "UK", "DE", "FR") or None
        current_language: Current detected language

    Returns:
        Inferred language if country maps to one, otherwise current_language

    Examples:
        >>> infer_language_from_country("DE", "English")
        'German'
        >>> infer_language_from_country("UK", "English")
        'English'
        >>> infer_language_from_country(None, "English")
        'English'
        >>> infer_language_from_country("FR", "French")
        'French'
    """
    if country and current_language == DEFAULT_LANGUAGE and country in COUNTRY_TO_LANGUAGE:
        return COUNTRY_TO_LANGUAGE[country]
    return current_language
