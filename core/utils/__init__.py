"""
Core utilities package - centralized utility functions

This package reorganizes utility modules for better organization and discoverability.
"""

# Async utilities
from .aasync import run_in_thread

# Database utilities
from .db import get_db_session

# CBZ/CBR utilities
from .cbz import (
    extract_cover_from_cbz,
    extract_cover_from_cbr,
    validate_cbz,
    validate_cbr,
)

# EPUB utilities
from .epub import extract_cover_from_epub, extract_text_from_epub

# General utilities
from .general import (
    cleanup_empty_directories,
    find_pdf_epub_files,
    generate_olid,
    hash_file_in_chunks,
    is_special_edition,
)

# PDF utilities
from .pdf import extract_cover_from_pdf, validate_pdf

# Thumbnail utilities
from .thumbnail import (
    THUMBNAIL_MAX_HEIGHT,
    THUMBNAIL_MAX_WIDTH,
    THUMBNAIL_QUALITY,
    generate_thumbnail,
    get_or_create_thumbnail,
)

__all__ = [
    # Async utilities
    "run_in_thread",
    # CBZ/CBR utilities
    "extract_cover_from_cbz",
    "extract_cover_from_cbr",
    "validate_cbz",
    "validate_cbr",
    # Database utilities
    "get_db_session",
    # EPUB utilities
    "extract_cover_from_epub",
    "extract_text_from_epub",
    # General utilities
    "cleanup_empty_directories",
    "find_pdf_epub_files",
    "generate_olid",
    "hash_file_in_chunks",
    "is_special_edition",
    # PDF utilities
    "extract_cover_from_pdf",
    "validate_pdf",
    # Thumbnail utilities
    "THUMBNAIL_MAX_HEIGHT",
    "THUMBNAIL_MAX_WIDTH",
    "THUMBNAIL_QUALITY",
    "generate_thumbnail",
    "get_or_create_thumbnail",
]
