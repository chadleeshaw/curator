"""
Language detection utilities for periodicals.

Detects language from title, filename, or metadata.
"""

import re
from typing import Optional

from core.constants import (
    DEFAULT_LANGUAGE,
    LANGUAGE_CODE_MAP,
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


def normalize_language_name(language: str) -> str:
    """
    Normalize language name to standard format.

    Args:
        language: Language name in any format

    Returns:
        Normalized language name (capitalized)

    Examples:
        >>> normalize_language_name("GERMAN")
        'German'
        >>> normalize_language_name("en")
        'English'
    """
    if not language:
        return DEFAULT_LANGUAGE

    lang_lower = language.lower()

    # Use language code map from constants
    if lang_lower in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[lang_lower]

    # Return capitalized version
    return language.capitalize()


def generate_language_aware_olid(base_olid: str, language: str) -> str:
    """
    Generate a language-aware Open Library ID.

    Args:
        base_olid: Base OLID (e.g., "wired")
        language: Language name

    Returns:
        Language-specific OLID (e.g., "wired_german")

    Examples:
        >>> generate_language_aware_olid("wired", "German")
        'wired_german'
        >>> generate_language_aware_olid("wired", "English")
        'wired'
    """
    if not language or language.lower() == DEFAULT_LANGUAGE.lower():
        return base_olid

    # Append language code to OLID
    lang_suffix = language.lower()
    return f"{base_olid}_{lang_suffix}"
