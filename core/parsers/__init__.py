"""
Parsing utilities for titles, metadata, dates, languages, countries, and filenames.
Centralized location for all parsing logic.
"""
from core.parsers.categorizer import FileCategorizer
from core.parsers.country import ISO_COUNTRIES, detect_country, find_country
from core.parsers.date import (
    MONTH_NAME_MAPPING,
    MONTH_NUMBER_MAPPING,
    month_abbr_to_number,
    normalize_month_name,
    utc_now,
)
from core.parsers.filename import parse_filename_for_metadata, sanitize_filename
from core.parsers.language import (
    LANGUAGE_INDICATORS,
    detect_language,
    generate_language_aware_olid,
    normalize_language_name,
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
from core.parsers.unified_parser import UnifiedParser

__all__ = [
    # Unified parser (primary interface)
    "UnifiedParser",
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
    "normalize_language_name",
    "generate_language_aware_olid",
    # Country detection
    "ISO_COUNTRIES",
    "detect_country",
    "find_country",
    # Date parsing
    "MONTH_NAME_MAPPING",
    "MONTH_NUMBER_MAPPING",
    "normalize_month_name",
    "month_abbr_to_number",
    "utc_now",
    # Categorization
    "FileCategorizer",
    # Filename utilities
    "parse_filename_for_metadata",
    "sanitize_filename",
]
