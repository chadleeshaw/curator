"""
Utility functions for core operations.

This module provides common utility functions used across the application.
"""

import re
from typing import Optional


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
