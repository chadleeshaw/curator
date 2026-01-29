"""
Reader utilities for extracting content from PDF, EPUB, and Comic files.

This module provides a unified interface for reading different periodical formats.
"""

from core.utils.readers.pdf import get_pdf_metadata, get_pdf_page, get_pdf_page_thumbnail
from core.utils.readers.epub import get_epub_metadata, get_epub_chapter, get_epub_image
from core.utils.readers.comic import (
    get_comic_metadata,
    get_comic_page,
    get_comic_page_thumbnail,
)

__all__ = [
    # PDF utilities
    "get_pdf_metadata",
    "get_pdf_page",
    "get_pdf_page_thumbnail",
    # EPUB utilities
    "get_epub_metadata",
    "get_epub_chapter",
    "get_epub_image",
    # Comic utilities
    "get_comic_metadata",
    "get_comic_page",
    "get_comic_page_thumbnail",
]
