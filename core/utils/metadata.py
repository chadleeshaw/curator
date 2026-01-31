"""
Metadata utilities for periodical metadata extraction and manipulation.

DEPRECATED: This module has been reorganized into core.utils.metadata/
Import from the new location instead:
    from core.utils.metadata import get_cover_page_index, get_metadata_field, etc.
"""

# Re-export from new location for backward compatibility
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
