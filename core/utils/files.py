"""
File utilities for consistent path resolution and operations.

DEPRECATED: This module has been reorganized into core.utils.files/
Import from the new location instead:
    from core.utils.files import get_library_dir, resolve_periodical_file_path, etc.
"""

# Re-export from new location for backward compatibility
from core.utils.files.paths import (
    get_library_dir,
    get_category_prefix,
    resolve_periodical_file_path,
    get_periodical_file_and_cover_paths,
    verify_periodical_files_exist,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_CATEGORY_PREFIX,
)

__all__ = [
    "get_library_dir",
    "get_category_prefix",
    "resolve_periodical_file_path",
    "get_periodical_file_and_cover_paths",
    "verify_periodical_files_exist",
    "DEFAULT_LIBRARY_DIR",
    "DEFAULT_CATEGORY_PREFIX",
]
