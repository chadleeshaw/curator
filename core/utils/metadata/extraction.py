"""
Metadata extraction utilities for periodicals.

This module provides functions for extracting and manipulating metadata fields
from periodical database objects.
"""

from typing import Optional

from models.database import Periodical


def get_cover_page_index(periodical: Periodical, zero_based: bool = True) -> int:
    """
    Get cover page index from periodical metadata.

    The cover page is stored in extra_metadata as a 1-based index (for human readability),
    but often needs to be used as a 0-based index (for arrays/frontend).

    Args:
        periodical: Periodical database object
        zero_based: If True, returns 0-based index; if False, returns 1-based (default: True)

    Returns:
        Cover page index (default: 0 for zero-based, 1 for one-based)

    Usage:
        # Get 0-based index for frontend
        cover_page = get_cover_page_index(magazine, zero_based=True)
        pages_data = {"cover_page": cover_page, "pages": [...]}

        # Get 1-based index for display
        display_page = get_cover_page_index(magazine, zero_based=False)
        print(f"Cover is on page {display_page}")
    """
    if not periodical.extra_metadata or "cover_page" not in periodical.extra_metadata:
        return 0 if zero_based else 1

    stored_value = periodical.extra_metadata["cover_page"]  # 1-based
    return stored_value - 1 if zero_based else stored_value


def set_cover_page_index(periodical: Periodical, page_index: int, zero_based: bool = True) -> None:
    """
    Set cover page index in periodical metadata.

    Automatically converts between 0-based and 1-based indexing.

    Args:
        periodical: Periodical database object
        page_index: Page index to set
        zero_based: If True, page_index is 0-based; if False, page_index is 1-based

    Usage:
        # Set from 0-based frontend value
        set_cover_page_index(magazine, 0, zero_based=True)  # Stores 1

        # Set from 1-based display value
        set_cover_page_index(magazine, 3, zero_based=False)  # Stores 3
    """
    if periodical.extra_metadata is None:
        periodical.extra_metadata = {}

    # Convert to 1-based for storage
    stored_value = page_index + 1 if zero_based else page_index
    periodical.extra_metadata["cover_page"] = stored_value


def get_metadata_field(periodical: Periodical, field_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a metadata field value from periodical with fallback.

    Checks multiple metadata sources in priority order:
    1. derived_metadata (from OCR/best source)
    2. extra_metadata (user-provided/import data)
    3. default value

    Args:
        periodical: Periodical database object
        field_name: Name of the field to retrieve
        default: Default value if field not found

    Returns:
        Field value or default

    Usage:
        category = get_metadata_field(magazine, "category", "Unknown")
        language = get_metadata_field(magazine, "language", "English")
    """
    # Try derived_metadata first (best quality)
    if periodical.derived_metadata and field_name in periodical.derived_metadata:
        value = periodical.derived_metadata[field_name]
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    # Try extra_metadata second
    if periodical.extra_metadata and field_name in periodical.extra_metadata:
        return periodical.extra_metadata[field_name]

    # Return default
    return default
