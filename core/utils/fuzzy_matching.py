"""
Fuzzy matching utilities for deduplication and grouping.
Shared utilities for normalizing titles and creating group IDs.
"""

import logging
from datetime import datetime
from typing import Optional

from core.parsers import normalize_month_name

logger = logging.getLogger(__name__)


def get_fuzzy_group_id(title: str, publication_date: Optional[datetime] = None) -> str:
    """
    Generate a normalized fuzzy match group ID for deduplication.

    Normalizes the title to group similar search results/issues together.
    This prevents duplicate downloads of the same content from different providers.

    Args:
        title: Title to normalize
        publication_date: Optional publication date to include in group ID

    Returns:
        Normalized string for grouping

    Examples:
        >>> get_fuzzy_group_id("National Geographic Magazine")
        'national-geographic-magazine'
        >>> get_fuzzy_group_id("The Economist", datetime(2024, 1, 15))
        'economist_2024-01'
    """
    # Convert to lowercase and strip whitespace
    normalized = title.lower().strip()

    # Remove common noise words that don't affect identity
    noise_words = ["the", "magazine", "comic", "edition"]
    for word in noise_words:
        normalized = normalized.replace(f" {word} ", " ")

    # Remove special characters and extra punctuation
    # Replace dashes, underscores, dots with spaces first
    for char in ["-", "_", "."]:
        normalized = normalized.replace(char, " ")

    # Normalize common month abbreviations to full names for better matching
    words = []
    for word in normalized.split():
        words.append(normalize_month_name(word))

    # Remove extra whitespace and rejoin
    normalized = " ".join(words)

    # Add date component if available for more precise grouping
    if publication_date:
        date_str = publication_date.strftime("%Y-%m")
        # Use underscore to separate title from date
        return f"{normalized}_{date_str}"

    # Replace spaces with hyphens for consistency
    return normalized.replace(" ", "-")
