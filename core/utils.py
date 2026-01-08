"""
Utility functions for core operations.

This module provides common utility functions used across the application.
"""

import re
from pathlib import Path
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


def is_special_edition(title: str) -> bool:
    """
    Detect if a magazine title represents a special edition.

    Special editions are typically annual issues, holiday specials, collector's editions,
    or other non-standard releases that should be grouped separately from regular issues.

    Args:
        title: Magazine title to check

    Returns:
        True if the title contains special edition keywords, False otherwise

    Examples:
        >>> is_special_edition("Wired - Holiday Special 2024")
        True
        >>> is_special_edition("National Geographic Annual Edition")
        True
        >>> is_special_edition("PC Gamer - June 2024")
        False
    """
    if not title:
        return False

    title_lower = title.lower()
    special_keywords = [
        "special",
        "annual",
        "collector",
        "collectors",
        "holiday",
        "christmas",
        "summer special",
        "winter special",
        "spring special",
        "fall special",
        "collector's edition",
        "commemorative",
        "anniversary",
        "yearbook",
        "best of",
    ]

    return any(keyword in title_lower for keyword in special_keywords)


def find_pdf_epub_files(directory: Path, recursive: bool = True) -> list[Path]:
    """
    Search for PDF and EPUB files in a directory.

    Args:
        directory: Directory to search
        recursive: If True, search recursively with glob("**/*.ext"), else use glob("*.ext")

    Returns:
        List of Path objects for all PDF and EPUB files found

    Examples:
        >>> files = find_pdf_epub_files(Path("/downloads"))
        >>> pdf_only = [f for f in files if f.suffix == '.pdf']
    """
    if not directory.exists():
        return []

    pattern = "**/*" if recursive else "*"
    pdf_files = list(directory.glob(f"{pattern}.pdf"))
    epub_files = list(directory.glob(f"{pattern}.epub"))

    return pdf_files + epub_files
