"""
Comic reader utilities for CBZ/CBR files.

DEPRECATED: This module has been moved to core.utils.readers.comic
Import from the new location instead:
    from core.utils.readers.comic import get_comic_metadata, get_comic_page, get_comic_page_thumbnail
"""

# Re-export from new location for backward compatibility
from core.utils.readers.comic import get_comic_metadata, get_comic_page, get_comic_page_thumbnail

__all__ = ["get_comic_metadata", "get_comic_page", "get_comic_page_thumbnail"]
