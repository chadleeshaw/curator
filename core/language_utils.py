"""
Language detection utilities for periodicals.

Detects language from title, filename, or metadata.
"""

import re
from typing import Optional


# Common language indicators in titles and filenames
LANGUAGE_INDICATORS = {
    "german": ["GERMAN", "DEUTSCH", "DE"],
    "french": ["FRENCH", "FRANCAIS", "FRANÇAIS", "FR"],
    "spanish": ["SPANISH", "ESPANOL", "ESPAÑOL", "ES"],
    "italian": ["ITALIAN", "ITALIANO", "IT"],
    "portuguese": ["PORTUGUESE", "PORTUGUES", "PORTUGUÊS", "PT"],
    "dutch": ["DUTCH", "NEDERLANDS", "NL"],
    "polish": ["POLISH", "POLSKI", "PL"],
    "russian": ["RUSSIAN", "РУССКИЙ", "RU"],
    "japanese": ["JAPANESE", "日本語", "JP"],
    "chinese": ["CHINESE", "中文", "ZH", "CN"],
    "korean": ["KOREAN", "한국어", "KR"],
}


def detect_language(text: str, default: str = "English") -> str:
    """
    Detect language from text (title, filename, or description).

    Args:
        text: Text to analyze (title, filename, etc.)
        default: Default language if none detected (default: "English")

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
            # Look for whole word matches or as part of compound words
            if re.search(rf'\b{re.escape(indicator)}\b', text_upper):
                return language.capitalize()

    # Default to English if no language indicator found
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
        return "English"

    lang_lower = language.lower()

    # Map common codes to full names
    language_map = {
        "en": "English",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
        "pl": "Polish",
        "ru": "Russian",
        "ja": "Japanese",
        "zh": "Chinese",
        "ko": "Korean",
    }

    if lang_lower in language_map:
        return language_map[lang_lower]

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
    if not language or language.lower() == "english":
        return base_olid

    # Append language code to OLID
    lang_suffix = language.lower()
    return f"{base_olid}_{lang_suffix}"
