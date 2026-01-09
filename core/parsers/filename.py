"""Filename parsing and sanitization utilities."""
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.parsers.date import month_abbr_to_number


def parse_filename_for_metadata(filename: str) -> Dict[str, Any]:
    """
    Try to extract metadata from filename.

    Expected format: {Magazine Title} - {Abbr}{Year}
    Examples:
    - "Wired Magazine - Dec2006"
    - "National Geographic - Mar2023"

    Args:
        filename: Filename without extension

    Returns:
        Dict with extracted metadata (title, month, year)
    """
    pattern = r"^(.+?)\s*-\s*([A-Za-z]{3})(\d{4})$"
    match = re.match(pattern, filename)

    if match:
        title, month_abbr, year = match.groups()

        month = month_abbr_to_number(month_abbr.capitalize())
        if month:
            try:
                issue_date = datetime(int(year), month, 1)
                return {
                    "title": title.strip(),
                    "issue_date": issue_date,
                    "confidence": "high",
                }
            except ValueError:
                pass

    return {"confidence": "low"}


def sanitize_filename(filename: str, max_length: Optional[int] = 200) -> str:
    """
    Sanitize filename for filesystem compatibility.

    Removes invalid filesystem characters and optionally limits length.
    Invalid characters include: < > : " / \\ | ? *

    Args:
        filename: Original filename to sanitize
        max_length: Maximum length (default 200, set to None for unlimited)

    Returns:
        Sanitized filename safe for all filesystems

    Examples:
        >>> sanitize_filename('My File: Test.pdf')
        'My File Test.pdf'
        >>> sanitize_filename('A' * 250, max_length=200)
        'AAAA...' (200 chars)
        >>> sanitize_filename('Test/Path\\File.pdf', max_length=None)
        'TestPathFile.pdf'
    """
    # Remove invalid filesystem characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "", filename)

    # Remove leading/trailing spaces
    sanitized = sanitized.strip()

    # Limit length if specified
    if max_length is not None:
        return sanitized[:max_length]

    return sanitized
