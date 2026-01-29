"""
EPUB reader utilities for extracting and serving chapters.

DEPRECATED: This module has been moved to core.utils.readers.epub
Import from the new location instead:
    from core.utils.readers.epub import get_epub_metadata, get_epub_chapter, get_epub_image
"""

# Re-export from new location for backward compatibility
from core.utils.readers.epub import get_epub_metadata, get_epub_chapter, get_epub_image

__all__ = ["get_epub_metadata", "get_epub_chapter", "get_epub_image"]
