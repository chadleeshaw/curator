"""
File utilities for consistent path resolution and operations.

This module provides utilities organized by concern:
- paths: Path resolution and library management
- operations: File operations and scanning
- formats: Format detection and conversions
"""

# Path management utilities
from core.utils.files.paths import (
    get_library_dir,
    get_category_prefix,
    resolve_periodical_file_path,
    get_periodical_file_and_cover_paths,
    verify_periodical_files_exist,
    strip_duplicate_suffixes,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_CATEGORY_PREFIX,
)

__all__ = [
    # Path utilities
    "get_library_dir",
    "get_category_prefix",
    "resolve_periodical_file_path",
    "get_periodical_file_and_cover_paths",
    "verify_periodical_files_exist",
    "strip_duplicate_suffixes",
    "DEFAULT_LIBRARY_DIR",
    "DEFAULT_CATEGORY_PREFIX",
]
