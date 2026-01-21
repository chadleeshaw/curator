"""
Validation constants for periodical detection and filtering.

Used to distinguish periodicals from books, collections, and other non-periodical content.
"""

from core.constants.category import (
    ACCEPTED_NEWSNAB_CATEGORIES,
    CATEGORY_PATTERNS,
    REJECTED_NEWSNAB_CATEGORIES,
)
from core.constants.date import get_month_year_patterns, get_season_year_patterns

# ==============================================================================
# Newsnab Category Codes
# ==============================================================================

# Re-export from category constants for backwards compatibility
NEWSNAB_BOOK_CATEGORIES = REJECTED_NEWSNAB_CATEGORIES
"""Book categories to reject (not periodicals)"""

NEWSNAB_PERIODICAL_CATEGORIES = ACCEPTED_NEWSNAB_CATEGORIES
"""Periodical categories to accept"""


# ==============================================================================
# Periodical Indicator Patterns
# ==============================================================================

# Regex patterns that indicate content IS a periodical issue
# These patterns suggest recurring publication with dates/issue numbers
#
# Note: Date patterns are now generated dynamically to support multiple languages.
# Use get_periodical_patterns() to get the full list with multilingual support.
PERIODICAL_PATTERNS_STATIC = [
    # Issue/Number patterns - strong indicators
    r"\b(issue|no\.?|number|nr\.?)\s*\d+\b",
    r"#\d+\b",  # "#123"
    # Volume patterns - moderate indicators
    r"\b(vol\.?|volume)\s*\d+",
    # Combined volume + issue - very strong indicator
    r"\bv\d+\s+(i|n|no\.?)\d+\b",  # "V12 N3", "V5 I2"
    # Weekly/bi-weekly date formats
    r"\b\d{4}[\.\s]\d{2}[\.\s]\d{2}\b",  # "2024.01.20" or "2024 01 20" (The Economist style)
]
"""Static periodical patterns (non-date-based)"""


def get_periodical_patterns(languages: list[str] | None = None) -> list[str]:
    """
    Get complete list of periodical indicator patterns with multilingual date support.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        List of regex pattern strings for detecting periodical indicators

    Example:
        >>> patterns = get_periodical_patterns(["English", "Spanish"])
        >>> # Returns patterns matching dates in English and Spanish, plus all static patterns
    """
    patterns = list(PERIODICAL_PATTERNS_STATIC)
    patterns.extend(get_month_year_patterns(languages))
    patterns.extend(get_season_year_patterns(languages))
    return patterns


# For backwards compatibility - default to all languages
PERIODICAL_PATTERNS = get_periodical_patterns()

# Patterns that indicate content is NOT a periodical (anti-patterns)
# These suggest collections, anthologies, books, or compilations
ANTI_PERIODICAL_PATTERNS = [
    # Collection/compilation indicators
    r"\b(complete|full|entire)\s+(collection|series)\b",
    r"\banthology\b",
    r"\bomnibus\b",
    r"\bcompendium\b",
    r"\bcollected\s+(works|edition)\b",
    # Range indicators (suggests collection of multiple issues/volumes)
    r"\b(volumes?|issues?)\s+\d+\s*-\s*\d+\b",  # "Volumes 1-5", "Issues 10-20"
    r"\b(vol|issue|no)\.?\s*\d+\s*-\s*\d+\b",  # "Vol 1-3", "No 5-10"
    r"\byear\s+\d+\s+pack\b",  # "Year 2023 Pack"
    r"\b\d{4}\s+(complete|full)\b",  # "2023 Complete"
    # Book-specific patterns
    r"\bedition\s+\d+(st|nd|rd|th)\b",  # "Edition 3rd" (textbooks)
    r"\bISBN\b",  # Books have ISBNs
    r"\b(hardcover|paperback|ebook)\b",  # Book formats
    # Novel/series indicators
    r"\bbook\s+\d+\b",  # "Book 1", "Book 2"
    r"\b(novel|trilogy|saga|series)\b",
    r"\bchapter\s+\d+\b",  # Chapters suggest book, not periodical
]


# ==============================================================================
# File Size Heuristics (in MB)
# ==============================================================================

# Typical file size ranges for different periodical types
FILE_SIZE_MIN_MB = 5  # Smaller files likely articles/books
FILE_SIZE_MAX_MB = 1000  # Larger files likely collections/packs

# Detailed ranges by type (for future enhancement)
FILE_SIZE_RANGES = {
    "magazine_pdf": (10, 500),  # Typical magazine PDF
    "comic_cbz": (50, 500),  # Comic book archive
    "newspaper_pdf": (5, 100),  # Newspapers are often smaller
}


# ==============================================================================
# Quality and Release Group Indicators
# ==============================================================================

# These don't directly indicate periodical/non-periodical,
# but help with metadata extraction quality assessment
QUALITY_INDICATORS = [
    "true pdf",
    "true.pdf",
    "retail",
    "original",
    "hq",
    "high quality",
    "scan",
    "digital",
]

# Common release group patterns (for removal during parsing)
RELEASE_GROUP_PATTERNS = [
    r"-[A-Z0-9]+$",  # "-PHOTOFILEv2", "-MAGAZINES"
    r"\[[A-Z0-9]+\]$",  # "[PHOTOFILE]"
]
