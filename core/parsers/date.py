"""
Date parsing and formatting utilities.
Centralized month name and number handling.
"""

from datetime import UTC, datetime
from typing import Optional, Tuple

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


def parse_month(month_str: str) -> Optional[int]:
    """
    Parse a month string to its number (1-12).

    Args:
        month_str: Month name or abbreviation (e.g., "January", "Jan", "jan")

    Returns:
        Month number (1-12) or None if not recognized
    """
    if not month_str:
        return None

    month_lower = month_str.lower().strip()
    return MONTH_TO_NUMBER.get(month_lower)


def parse_multi_month(month_str: str) -> Tuple[Optional[int], str]:
    """
    Parse a month string that may contain multiple months (e.g., "June/July").

    Args:
        month_str: Month string, possibly multi-month format

    Returns:
        Tuple of (first_month_number, display_string)
        first_month_number is None if not parseable
    """
    if not month_str:
        return None, ""

    month_str = month_str.strip()

    # Check for multi-month separators (including period and underscore)
    for sep in ["/", "-", "&", ".", "_"]:
        if sep in month_str:
            parts = month_str.split(sep)
            first_month = parts[0].strip()
            month_num = parse_month(first_month)
            if month_num:
                # Normalize display: "Jun/Jul" -> "June/July"
                normalized_parts = []
                for part in parts:
                    part = part.strip()
                    part_num = parse_month(part)
                    if part_num:
                        # Convert to full month name
                        normalized_parts.append(NUMBER_TO_MONTH[part_num])
                    else:
                        # Keep original if not recognized
                        normalized_parts.append(part.capitalize())
                return month_num, "/".join(normalized_parts)

    # Single month - convert to full name
    month_num = parse_month(month_str)
    if month_num:
        return month_num, NUMBER_TO_MONTH[month_num]
    return None, month_str.capitalize()


def parse_numeric_month_range(month1_str: str, month2_str: str) -> Tuple[Optional[int], str]:
    """
    Parse numeric month range (e.g., "11.10" meaning Nov/Oct or Oct/Nov).

    Args:
        month1_str: First month number as string (1-12)
        month2_str: Second month number as string (1-12)

    Returns:
        Tuple of (first_month_number, display_string)
        Returns the earlier month number and a formatted display string like "October/November"
        Returns (None, "") if either month is invalid

    Examples:
        >>> parse_numeric_month_range("11", "10")
        (10, "October/November")
        >>> parse_numeric_month_range("05", "06")
        (5, "May/June")
        >>> parse_numeric_month_range("12", "01")
        (12, "December/January")
    """
    try:
        month1 = int(month1_str)
        month2 = int(month2_str)

        # Validate both months are in valid range (1-12)
        if not (1 <= month1 <= 12 and 1 <= month2 <= 12):
            return None, ""

        # Get month names
        month1_name = NUMBER_TO_MONTH.get(month1)
        month2_name = NUMBER_TO_MONTH.get(month2)

        if not (month1_name and month2_name):
            return None, ""

        # Check if months are consecutive or span year boundary
        # Examples:
        # - 11, 10 -> Oct/Nov (consecutive, reversed order)
        # - 10, 11 -> Oct/Nov (consecutive, normal order)
        # - 12, 1  -> Dec/Jan (year boundary)
        # - 5, 6   -> May/Jun (consecutive, normal order)

        # Determine which is the "first" month chronologically
        # If month1 > month2 by 1, they're consecutive but reversed (like 11, 10)
        # If month2 > month1 by 1, they're consecutive normal order (like 10, 11)
        # If month1 == 12 and month2 == 1, it's year boundary (Dec/Jan)

        if month1 == month2 + 1:
            # Reversed order: 11, 10 -> use month2 first
            first_month = month2
            display = f"{month2_name}/{month1_name}"
        elif month1 == 12 and month2 == 1:
            # Year boundary: Dec/Jan -> use month1 first (December)
            first_month = month1
            display = f"{month1_name}/{month2_name}"
        else:
            # Normal order or non-consecutive -> use lower month number first
            first_month = min(month1, month2)
            if month1 < month2:
                display = f"{month1_name}/{month2_name}"
            else:
                display = f"{month2_name}/{month1_name}"

        return first_month, display

    except (ValueError, TypeError):
        return None, ""
