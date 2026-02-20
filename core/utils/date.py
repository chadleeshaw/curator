"""
Date parsing utilities for periodical metadata.
"""

from datetime import date, timedelta
from typing import Optional, Tuple

from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH, SEASON_MONTHS


def get_season_for_month(month: int) -> str:
    """
    Get the season name for a given month number.

    Args:
        month: Month number (1-12)

    Returns:
        Season name ("winter", "spring", "summer", "fall")
    """
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    return "winter"  # Default fallback


def dates_are_fuzzy_match(date1: date, date2: date, tolerance_months: int = 1) -> bool:
    """
    Check if two dates are close enough to be considered the same issue.

    This helps with duplicate detection when:
    - Search shows "February" but library has "January" (date defaulting)
    - "Winter 2024" could be Dec 2023, Jan 2024, or Feb 2024

    Args:
        date1: First date to compare
        date2: Second date to compare
        tolerance_months: Number of months tolerance (default 1)

    Returns:
        True if dates are likely the same issue, False otherwise

    Examples:
        >>> from datetime import date
        >>> dates_are_fuzzy_match(date(2024, 1, 1), date(2024, 2, 1))
        True  # Within 1 month tolerance
        >>> dates_are_fuzzy_match(date(2024, 1, 1), date(2024, 3, 1))
        False  # 2 months apart exceeds default tolerance
        >>> dates_are_fuzzy_match(date(2024, 12, 1), date(2025, 1, 1))
        True  # Winter issues span year boundary
    """
    if date1 == date2:
        return True

    months_diff = abs((date1.year - date2.year) * 12 + (date1.month - date2.month))
    if months_diff <= tolerance_months:
        return True

    # Handle Winter issues that span Dec/Jan year boundaries.
    # Only applies when one date is December and the other is January or February
    # of the following year — not for any same-season pair up to 12 months apart.
    earlier, later = (date1, date2) if date1 < date2 else (date2, date1)
    spans_year_boundary = earlier.month == 12 and later.month in (1, 2) and later.year == earlier.year + 1
    if spans_year_boundary:
        return True

    return False


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

    # Check for multi-month separators (including underscore for IA filenames)
    for sep in ["/", "-", "&", "_"]:
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
