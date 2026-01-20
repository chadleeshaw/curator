"""
Shared dependencies and state for periodicals router package
"""

import logging
from pathlib import Path
from typing import Callable, Optional, Tuple

from fastapi import APIRouter

from core.constants.date import MONTH_TO_NUMBER

router = APIRouter(prefix="/api", tags=["periodicals"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_organize_base_dir = None


def set_dependencies(session_factory: Callable, organize_base_dir: Optional[str] = None) -> None:
    """Set dependencies from main app"""
    global _session_factory, _organize_base_dir
    _session_factory = session_factory
    if organize_base_dir:
        _organize_base_dir = Path(organize_base_dir)


def parse_month_string(month_str: Optional[str]) -> Tuple[int, str]:
    """
    Parse a month string, handling multi-month formats like "June/July".

    Args:
        month_str: Month string to parse (e.g., "June", "June/July", "Jan-Feb")

    Returns:
        Tuple of (month_number, normalized_month_string)
        month_number is 1-12 (defaults to 1 if unparseable)
    """
    if not month_str:
        return 1, ""

    month_str = month_str.strip()
    if not month_str:
        return 1, ""

    # Handle multi-month formats: "June/July", "Jan-Feb", "March / April"
    # Use the first month for the date, but preserve original string
    separators = ["/", "-", "&"]
    first_month = month_str

    for sep in separators:
        if sep in month_str:
            first_month = month_str.split(sep)[0].strip()
            break

    # Look up the month number
    month_num = MONTH_TO_NUMBER.get(first_month.lower(), 0)

    # If not found, try common abbreviations
    if month_num == 0:
        abbrev_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month_num = abbrev_map.get(first_month.lower()[:3], 1)

    return month_num, month_str
