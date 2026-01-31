"""
Metadata utilities for periodical metadata extraction and manipulation.

This module provides utilities for working with periodical metadata.
"""

from core.utils.metadata.extraction import (
    get_cover_page_index,
    set_cover_page_index,
    get_metadata_field,
)

__all__ = [
    "get_cover_page_index",
    "set_cover_page_index",
    "get_metadata_field",
]
