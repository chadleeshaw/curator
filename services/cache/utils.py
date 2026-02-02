"""
Utility functions for provider cache services.

Contains FTS5 query escaping and date parsing helpers.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from core.constants.cache import UPLOAD_DATE_FORMATS

logger = logging.getLogger(__name__)


def escape_fts_query(query: str) -> str:
    """
    Escape a query string for safe use in SQLite FTS5 MATCH.

    FTS5 interprets special characters as operators:
    - Hyphens (-) as NOT operator
    - AND, OR, NOT as boolean operators
    - Quotes, parentheses as grouping

    This method wraps each word in double quotes to treat them as literals.

    Args:
        query: The raw search query

    Returns:
        Escaped query safe for FTS5 MATCH
    """
    if not query or not query.strip():
        return '""'

    # Split on whitespace, wrap each word in quotes
    # This handles hyphens, special chars, and reserved words
    words = query.split()
    escaped_words = []
    for word in words:
        # Escape any internal double quotes by doubling them
        escaped_word = word.replace('"', '""')
        escaped_words.append(f'"{escaped_word}"')

    return " ".join(escaped_words)


def parse_upload_date(result: Any) -> Optional[datetime]:
    """
    Parse upload_date from search result.

    Tries multiple date formats from raw_metadata.

    Args:
        result: SearchResult object with raw_metadata attribute

    Returns:
        Parsed datetime or None
    """
    if not result.raw_metadata:
        return None

    # Try to get upload_date from raw_metadata
    upload_date_str = result.raw_metadata.get("upload_date") or result.raw_metadata.get("pubDate")
    if not upload_date_str:
        return None

    # Try parsing with multiple formats
    for date_format in UPLOAD_DATE_FORMATS:
        try:
            return datetime.strptime(upload_date_str, date_format)
        except (ValueError, TypeError):
            continue

    logger.debug(f"Failed to parse upload_date: {upload_date_str}")
    return None
