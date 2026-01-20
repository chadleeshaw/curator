"""
Date parsing and formatting utilities.
Centralized month name and number handling.
"""

from datetime import UTC, datetime

from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH


def normalize_month_name(month_str: str) -> str:
    """
    Convert month abbreviation to full month name.

    Args:
        month_str: Month abbreviation (case-insensitive)

    Returns:
        Full month name in lowercase, or original string if not found
    """
    # Try to find the month in MONTH_TO_NUMBER and convert back to full name
    month_lower = month_str.lower()
    month_num = MONTH_TO_NUMBER.get(month_lower)
    if month_num:
        return NUMBER_TO_MONTH[month_num].lower()
    return month_str


def month_abbr_to_number(month_abbr: str) -> int:
    """
    Convert month abbreviation to month number (1-12).

    Args:
        month_abbr: Month abbreviation (e.g., "Jan", "Feb")

    Returns:
        Month number (1-12), or 0 if not found
    """
    return MONTH_TO_NUMBER.get(month_abbr.lower(), 0)


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
