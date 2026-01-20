"""
Language detection utilities for periodicals.

Detects language from title, filename, or metadata.
"""

import re

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
