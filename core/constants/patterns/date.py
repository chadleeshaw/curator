"""
Date-related regex patterns for parsing filenames.

Includes ISO dates, month-year patterns, and multi-month periods.
Supports multiple languages through dynamic pattern generation.
"""

from core.constants.date import get_month_regex_pattern

# ==============================================================================
# ISO DATE PATTERNS (language-agnostic)
# ==============================================================================

DATE_PATTERN_ISO_FULL = r"(\d{4})[-.\s](\d{1,2})[-.\s](\d{1,2})\b"
"""Pattern for full ISO dates: 2024-01-20, 2024.01.20, 2024 01 20"""

DATE_PATTERN_ISO_MONTH = r"(\d{4})[-.](\d{1,2})(?![-.\d])"
"""Pattern for ISO year-month: 2024-01, 2024.01"""

DATE_PATTERN_MONTH_YEAR_NUMERIC = r"\b(\d{1,2})[-/](\d{4})\b"
"""Pattern for numeric month-year: 01-2024, 1/2024"""

DATE_PATTERN_YEAR_ONLY = r"\b(\d{4})\b"
"""Pattern for standalone year: 2024"""

# Multi-month patterns (generic, works with any month names)
DATE_PATTERN_MULTI_MONTH = r"(.+?)\s*[-–]?\s*([A-Za-z]+)[/\-&]([A-Za-z]+)\s*(\d{4})"
"""Pattern for multi-month periods: June/July 2024, Jun/Jul2024"""

# ==============================================================================
# MULTILINGUAL MONTH-YEAR PATTERNS
# ==============================================================================


def get_month_year_pattern(languages: list[str] | None = None) -> str:
    """
    Generate pattern for full month name with year, supporting multiple languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Regex pattern string for matching "MonthName YYYY"

    Example:
        >>> pattern = get_month_year_pattern(["English", "Spanish"])
        >>> # Returns pattern matching "January 2024", "Enero 2024", etc.
    """
    month_pattern = get_month_regex_pattern(languages)
    return rf"\b({month_pattern})[\s]+(\d{{4}})\b"


def get_abbr_month_year_pattern(languages: list[str] | None = None) -> str:
    """
    Generate pattern for abbreviated month with year, supporting multiple languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Regex pattern string for matching "Mon YYYY" or "Mon2024"

    Example:
        >>> pattern = get_abbr_month_year_pattern(["English"])
        >>> # Returns pattern matching "Jan 2024", "Jan2024", etc.
    """
    month_pattern = get_month_regex_pattern(languages)
    return rf"\b({month_pattern})\.?[\s]*(\d{{4}})\b"


def get_abbr_month_year_pattern_no_boundary(languages: list[str] | None = None) -> str:
    """
    Generate pattern for abbreviated month with year (no word boundaries).

    This version matches month-year patterns in the middle of strings.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Regex pattern string for matching "Mon2024" anywhere in string

    Example:
        >>> pattern = get_abbr_month_year_pattern_no_boundary(["English"])
        >>> # Returns pattern matching "Jan2024" even in middle of filename
    """
    month_pattern = get_month_regex_pattern(languages)
    return rf"({month_pattern})\.?(\d{{4}})"


# Default patterns with all languages (for backward compatibility)
DATE_PATTERN_FULL_MONTH_YEAR = get_month_year_pattern()
"""Pattern for full month name with year: January 2024 (all languages)"""

DATE_PATTERN_ABBR_MONTH_YEAR = get_abbr_month_year_pattern()
"""Pattern for abbreviated month with year: Jan 2024, Jan2024 (all languages)"""

DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY = get_abbr_month_year_pattern_no_boundary()
"""Pattern for abbreviated month with year (no word boundaries, all languages)"""
