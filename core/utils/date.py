"""
Date parsing utilities for periodical metadata.
"""

from typing import Optional, Tuple

from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH


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

    # Check for multi-month separators
    for sep in ["/", "-", "&"]:
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
