"""
Fuzzy matching utilities for deduplication and grouping.
Shared utilities for normalizing titles and creating group IDs.
"""

import re

from core.constants.title import TITLE_SKIP_WORDS
from core.parsers import normalize_month_name


def get_fuzzy_group_id(title: str) -> str:
    """
    Generate a normalized fuzzy match group ID for deduplication.

    Normalizes the title to group similar search results/issues together.
    This prevents duplicate downloads of the same content from different providers.

    Group IDs are title-based only to support items without publication dates
    (e.g., volume/issue numbers only). Publication dates should be stored separately
    and used for additional filtering when available.

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
    normalized = title.lower().strip()

    for char in [",", ";", ":", "-", "_", ".", "!", "?", "(", ")", "[", "]", "{", "}"]:
        normalized = normalized.replace(char, " ")

    words = normalized.split()

    if words and words[0] == "the":
        words = words[1:]

    words = [word for word in words if word not in TITLE_SKIP_WORDS]

    words = [normalize_month_name(word) for word in words]

    return "-".join(words) if words else ""
