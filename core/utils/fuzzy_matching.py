"""
Fuzzy matching utilities for deduplication and grouping.
Shared utilities for normalizing titles and creating group IDs.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from core.constants.title import TITLE_SKIP_WORDS
from core.parsers import normalize_month_name

logger = logging.getLogger(__name__)


def get_fuzzy_group_id(title: str, publication_date: Optional[datetime] = None) -> str:
    """
    Generate a normalized fuzzy match group ID for deduplication.

    Normalizes the title to group similar search results/issues together.
    This prevents duplicate downloads of the same content from different providers.

    IMPORTANT: The fuzzy_group_id should be based on title ONLY to support
    items without publication dates (e.g., volume/issue numbers only).
    Publication dates should be stored separately and used for additional
    filtering when available.

    Args:
        title: Title to normalize
        publication_date: DEPRECATED - kept for backward compatibility but should
                         not be used. Pass None or omit this parameter.

    Returns:
        Normalized string for grouping (title-based only)

    Examples:
        >>> get_fuzzy_group_id("National Geographic Magazine")
        'national-geographic'
        >>> get_fuzzy_group_id("The National Geographic")
        'national-geographic'
        >>> get_fuzzy_group_id("Wired, The Magazine")
        'wired'
        >>> get_fuzzy_group_id("Wired Vol 30 No 1")
        'wired-vol-30-no-1'
    """
    # DEPRECATED: publication_date parameter should not be used
    if publication_date is not None:
        logger.warning(
            "get_fuzzy_group_id() called with publication_date - this is deprecated. "
            "Store publication_date separately for filtering."
        )

    # Convert to lowercase and strip whitespace
    normalized = title.lower().strip()

    # Remove all punctuation FIRST (replace with spaces)
    # This prevents commas/periods from sticking to words
    for char in [",", ";", ":", "-", "_", ".", "!", "?", "(", ")", "[", "]", "{", "}"]:
        normalized = normalized.replace(char, " ")

    # Split into words (removes extra whitespace automatically)
    words = normalized.split()

    # Remove leading "the" if present (TITLE_SKIP_WORDS already includes "the")
    if words and words[0] == "the":
        words = words[1:]

    # Remove noise words from TITLE_SKIP_WORDS constant
    # Includes: the, a, an, and, or, of, magazine, mag, comic, edition
    words = [word for word in words if word not in TITLE_SKIP_WORDS]

    # Normalize month names for better matching
    words = [normalize_month_name(word) for word in words]

    # Join with hyphens
    return "-".join(words) if words else ""
