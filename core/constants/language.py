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

LANGUAGE_KEYWORDS = {
    "German": ["German", "Deutsch", "Deutschland", "DE"],
    "French": ["French", "Français", "Francais", "FRANCAIS", "France", "FR"],
    "Spanish": ["Spanish", "Español", "Espanol", "ESPANOL", "España", "ES"],
    "Italian": ["Italian", "Italiano", "Italia", "IT"],
    "Portuguese": ["Portuguese", "Português", "Portugues", "PORTUGUES", "PT"],
    "Dutch": ["Dutch", "Nederlands", "nederlands", "Holland", "NL"],
    "Polish": ["Polish", "Polski", "Polska", "PL"],
    "Russian": ["Russian", "Русский", "RU"],
    "Slovak": ["Slovak", "Slovenčina", "Slovensky", "SK"],
    "Ukrainian": ["Ukrainian", "Українська", "UA"],
    "Japanese": ["Japanese", "日本語", "Japan", "JP"],
    "Chinese": ["Chinese", "中文", "China", "CN", "ZH"],
    "Korean": ["Korean", "한국어", "Korea", "KR"],
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
