"""
Parsing utilities for titles, metadata, dates, languages, countries, and filenames.
Centralized location for all parsing logic.
"""

from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH, NUMBER_TO_MONTH_ABBR
from core.parsers.categorizer import FileCategorizer
from core.parsers.country import ISO_COUNTRIES, detect_country, find_country
from core.parsers.date import (
    month_abbr_to_number,
    normalize_month_name,
    utc_now,
    parse_month,
    parse_multi_month,
)
from core.parsers.filename import sanitize_filename
from core.parsers.language import (
    LANGUAGE_INDICATORS,
    detect_language,
    infer_language_from_country,
)
from core.parsers.metadata import FilenameParser
from core.parsers.models import (
    ParsedMetadata,
    ParsedFilename,
    ParsedFilepath,
    ParsedSearchResult,
    ParsedDownloadFile,
)
from core.parsers.title import TitleMatcher
from core.parsers.parser import Parser

__all__ = [
    # ============================================================================
    # PUBLIC API - Use these in your code
    # ============================================================================
    # Primary parser interface (RECOMMENDED - use this for all parsing)
    "Parser",
    # Data models (returned by Parser methods)
    "ParsedMetadata",
    "ParsedFilename",
    "ParsedFilepath",
    "ParsedSearchResult",
    "ParsedDownloadFile",
    # ============================================================================
    # INTERNAL PARSERS - Advanced use only
    # ============================================================================
    # These are used internally by Parser but exported for advanced users.
    # Most code should use Parser instead of these directly.
    # NOTE: FilenameParser and TitleMatcher may become private in future versions.
    # Use Parser.parse_file(), Parser.parse_search_result(), etc. instead.
    "FilenameParser",  # Advanced: Direct filename parsing
    "TitleMatcher",  # Advanced: Title matching and normalization
    # ============================================================================
    # UTILITY FUNCTIONS - Domain-specific helpers
    # ============================================================================
    # Language detection
    "LANGUAGE_INDICATORS",
    "detect_language",
    "infer_language_from_country",
    # Country detection
    "ISO_COUNTRIES",
    "detect_country",
    "find_country",
    # Date parsing and constants
    "MONTH_TO_NUMBER",
    "NUMBER_TO_MONTH",
    "NUMBER_TO_MONTH_ABBR",
    "normalize_month_name",
    "month_abbr_to_number",
    "utc_now",
    "parse_month",
    "parse_multi_month",
    # Categorization
    "FileCategorizer",
    # Filename utilities
    "sanitize_filename",
]
