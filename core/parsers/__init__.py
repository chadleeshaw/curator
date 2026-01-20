"""
Parsing utilities for titles, metadata, dates, languages, countries, and filenames.
Centralized location for all parsing logic.
"""

from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH, NUMBER_TO_MONTH_ABBR
from core.parsers.categorizer import FileCategorizer
from core.parsers.country import ISO_COUNTRIES, detect_country, find_country
from core.parsers.date import month_abbr_to_number, normalize_month_name, utc_now
from core.parsers.filename import sanitize_filename
from core.parsers.language import (
    LANGUAGE_INDICATORS,
    detect_language,
)
from core.parsers.metadata import MetadataExtractor
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
    # Primary parser interface
    "Parser",
    # Data models
    "ParsedMetadata",
    "ParsedFilename",
    "ParsedFilepath",
    "ParsedSearchResult",
    "ParsedDownloadFile",
    # Title parsing
    "TitleMatcher",
    # Metadata extraction
    "MetadataExtractor",
    # Language detection
    "LANGUAGE_INDICATORS",
    "detect_language",
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
    # Categorization
    "FileCategorizer",
    # Filename utilities
    "sanitize_filename",
]
