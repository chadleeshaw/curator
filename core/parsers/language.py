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


def _indicator_in_text(indicator: str, text_upper: str) -> bool:
    """True when a language keyword is present as a tag or an edition phrase.

    ``[ES]``, ``.German.``, ``-DE-``, and ``Swedish Edition`` count. A bare
    ``German``, ``Sweden``, or ``it`` does not.
    """
    code = indicator.upper()
    escaped = re.escape(code)
    tagged = bool(
        re.search(rf"(?:\[\s*|\(\s*|_\s*|-\s*){escaped}(?:\s*\]|\s*\)|\s*_|\s*-)", text_upper)
        or re.search(rf"\.{escaped}\.", text_upper)
    )
    if len(code) <= 2 and code.isascii() and code.isalpha():
        return tagged
    # A directory such as /German/ is a tag. A bare word is not.
    in_directory = bool(re.search(rf"/{escaped}/", text_upper))
    edition = bool(re.search(rf"\b{escaped}\s+EDITION\b", text_upper))
    return tagged or in_directory or edition


def _language_from_edition_phrase(text: str) -> Optional[str]:
    """Swedish Edition selects Swedish even when that name is not a keyword."""
    languages = sorted(set(COUNTRY_TO_LANGUAGE.values()), key=len, reverse=True)
    for language in languages:
        if language == DEFAULT_LANGUAGE:
            continue
        if re.search(rf"\b{re.escape(language)}\s+edition\b", text, re.IGNORECASE):
            return language
    return None


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

    edition_language = _language_from_edition_phrase(text)
    if edition_language:
        return edition_language

    # Check for language indicators
    for language, indicators in LANGUAGE_INDICATORS.items():
        for indicator in indicators:
            if _indicator_in_text(indicator, text_upper):
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
