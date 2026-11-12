"""
Language detection and mapping constants
"""

# ==============================================================================
# Default Language
# ==============================================================================

DEFAULT_LANGUAGE = "English"
"""Default language for periodicals when none is detected"""


# ==============================================================================
# Supported Languages
# ==============================================================================

SUPPORTED_LANGUAGES = [
    "English",
    "German",
    "French",
    "Spanish",
    "Italian",
    "Portuguese",
    "Dutch",
    "Polish",
    "Russian",
    "Slovak",
    "Ukrainian",
    "Japanese",
    "Chinese",
    "Korean",
]
"""List of supported languages for periodical tracking and parsing"""


LANGUAGE_TO_PADDLEOCR = {
    "english": "en",
    "en": "en",
    "french": "fr",
    "fr": "fr",
    "german": "german",
    "de": "german",
    "spanish": "es",
    "es": "es",
    "italian": "it",
    "it": "it",
    "portuguese": "pt",
    "pt": "pt",
    "russian": "ru",
    "ru": "ru",
    "chinese": "ch",
    "ch": "ch",
    "zh": "ch",
    "japanese": "japan",
    "ja": "japan",
    "korean": "korean",
    "ko": "korean",
    "slovak": "en",
    "sk": "en",
    "arabic": "ar",
    "ar": "ar",
    "latin": "latin",
    "la": "latin",
}
"""Mapping from language names/codes to PaddleOCR language codes"""


# ==============================================================================
# Language Detection Keywords
# ==============================================================================

LANGUAGE_NAMES = {
    "German": ["German", "Deutsch", "DE"],
    "French": ["French", "Français", "Francais", "FRANCAIS", "FR"],
    "Spanish": ["Spanish", "Español", "Espanol", "ESPANOL", "ES"],
    "Italian": ["Italian", "Italiano", "IT"],
    "Portuguese": ["Portuguese", "Português", "Portugues", "PORTUGUES", "PT"],
    "Dutch": ["Dutch", "Nederlands", "nederlands", "NL"],
    "Polish": ["Polish", "Polski", "PL"],
    "Russian": ["Russian", "Русский", "RU"],
    "Slovak": ["Slovak", "Slovenčina", "Slovensky", "SK"],
    "Ukrainian": ["Ukrainian", "Українська", "UA"],
    "Japanese": ["Japanese", "日本語", "JP"],
    "Chinese": ["Chinese", "中文", "CN", "ZH"],
    "Korean": ["Korean", "한국어", "KR"],
}
"""Words that name a language. A search filter matches only these."""

LANGUAGE_COUNTRY_NAMES = {
    "German": ["Deutschland"],
    "French": ["France"],
    "Spanish": ["España"],
    "Italian": ["Italia"],
    "Dutch": ["Holland"],
    "Polish": ["Polska"],
    "Japanese": ["Japan"],
    "Chinese": ["China"],
    "Korean": ["Korea"],
}
"""Country names that hint at a language in an edition tag, but don't name it."""

LANGUAGE_KEYWORDS = {
    language: names + LANGUAGE_COUNTRY_NAMES.get(language, []) for language, names in LANGUAGE_NAMES.items()
}
"""Keywords used to detect language from periodical titles"""


# ==============================================================================
# English Language Indicators
# ==============================================================================

ENGLISH_INDICATORS = [
    "english",
    " en ",
    " en-",
    "-en ",
    "usa",
    " uk ",
    " uk-",
    "-uk ",
    " us ",
    " us-",
    "-us ",
]
"""
Language and region indicators for English editions.

Used to detect English-language periodicals from search results and filenames.
Space-bounded indicators (e.g., ' en ') prevent false matches with words containing 'en'.
"""
