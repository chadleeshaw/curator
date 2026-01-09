"""
Date parsing and formatting utilities.
Centralized month name and number handling.
"""
from datetime import UTC, datetime

MONTH_NAME_MAPPING = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "may": "may",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}

MONTH_NUMBER_MAPPING = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def normalize_month_name(month_str: str) -> str:
    """
    Convert month abbreviation to full month name.

    Args:
        month_str: Month abbreviation (case-insensitive)

    Returns:
        Full month name in lowercase, or original string if not found
    """
    return MONTH_NAME_MAPPING.get(month_str.lower(), month_str)


def month_abbr_to_number(month_abbr: str) -> int:
    """
    Convert month abbreviation to month number (1-12).

    Args:
        month_abbr: Month abbreviation (e.g., "Jan", "Feb")

    Returns:
        Month number (1-12), or 0 if not found
    """
    return MONTH_NUMBER_MAPPING.get(month_abbr, 0)


def utc_now() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        Current datetime in UTC timezone

    Note:
        This is the preferred way to get current time for consistency.
        Always use UTC internally and convert to local time for display.
        Use this instead of datetime.now() or datetime.now(UTC).
    """
    return datetime.now(UTC)
