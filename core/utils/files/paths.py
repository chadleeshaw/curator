"""
File path utilities for consistent path resolution across the application.

This module provides utilities for resolving file paths, library directories,
and ensuring consistent path handling across different environments.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

from core.constants.category import CATEGORIES

logger = logging.getLogger(__name__)

# Default paths (can be overridden by configuration)
DEFAULT_LIBRARY_DIR = "./local/data"
DEFAULT_CATEGORY_PREFIX = "_"


def get_library_dir(storage_config: Optional[dict] = None, default: str = DEFAULT_LIBRARY_DIR) -> Path:
    """
    Get the library directory from config or use default.

    Args:
        storage_config: Storage configuration dictionary
        default: Default library directory path

    Returns:
        Resolved Path object for library directory

    Example:
        >>> library_dir = get_library_dir(storage_config)
        >>> print(library_dir)
        /Users/user/curator/local/data
    """
    if storage_config:
        library_path = storage_config.get("library_dir", default)
    else:
        library_path = default

    return Path(library_path).resolve()


def get_category_prefix(import_config: Optional[dict] = None, default: str = DEFAULT_CATEGORY_PREFIX) -> str:
    """
    Get the category prefix from config or use default.

    Args:
        import_config: Import configuration dictionary
        default: Default category prefix

    Returns:
        Category prefix string (e.g., "_")

    Example:
        >>> prefix = get_category_prefix(import_config)
        >>> print(prefix)
        _
    """
    if import_config:
        return import_config.get("category_prefix", default)
    return default


def resolve_periodical_file_path(
    stored_path: str,
    library_base_dir: Optional[Path] = None,
    category_prefix: str = DEFAULT_CATEGORY_PREFIX,
) -> Path:
    """
    Resolve a periodical file path from the database to the actual filesystem location.

    This handles cases where:
    - Path is stored as absolute (e.g., from Docker container: /app/local/data/...)
    - Path needs to be resolved relative to configured library_dir
    - Path may be from a different environment

    Args:
        stored_path: File path stored in database (may be absolute or relative)
        library_base_dir: Base library directory (if None, uses default)
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Resolved Path object pointing to actual file location

    Raises:
        FileNotFoundError: If file cannot be found after resolution attempts

    Example:
        >>> path = resolve_periodical_file_path("/app/local/data/_Magazines/Wired/2024/issue.pdf")
        >>> print(path)
        /Users/user/curator/local/data/_Magazines/Wired/2024/issue.pdf
    """
    stored = Path(stored_path)

    # If stored path exists as-is, use it (same environment)
    if stored.exists():
        return stored

    # Get library base dir if not provided
    if library_base_dir is None:
        library_base_dir = Path(DEFAULT_LIBRARY_DIR).resolve()

    # Try resolving relative to library_dir if configured
    if library_base_dir:
        # Extract the relative path from stored path
        # This handles cases where stored path is from different environment
        # Example: /app/local/data/_Magazines/... -> _Magazines/...

        # Find the library folder marker (e.g., "_Magazines", "_Comics", etc.)
        parts = stored.parts
        # Build category markers from constants (e.g., "_Magazines", "_Comics")
        category_markers = [f"{category_prefix}{category}" for category in CATEGORIES]

        for i, part in enumerate(parts):
            if part in category_markers:
                # Reconstruct path from category marker onwards
                relative_path = Path(*parts[i:])
                resolved = library_base_dir / relative_path
                if resolved.exists():
                    logger.debug(f"Resolved path: {stored_path} -> {resolved}")
                    return resolved
                break

    # Last resort: check if it's directly under library_dir
    if library_base_dir:
        filename = stored.name
        potential = library_base_dir / filename
        if potential.exists():
            logger.debug(f"Resolved by filename: {stored_path} -> {potential}")
            return potential

    # Could not resolve
    raise FileNotFoundError(f"Could not resolve file path: {stored_path}")


def get_periodical_file_and_cover_paths(
    periodical,
    library_base_dir: Optional[Path] = None,
    category_prefix: str = DEFAULT_CATEGORY_PREFIX,
) -> Tuple[Path, Optional[Path]]:
    """
    Get resolved file and cover paths for a periodical.

    Args:
        periodical: Periodical database object with file_path and cover_path
        library_base_dir: Base library directory (if None, uses default)
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Tuple of (file_path, cover_path) where cover_path may be None

    Raises:
        FileNotFoundError: If file path cannot be resolved

    Example:
        >>> file_path, cover_path = get_periodical_file_and_cover_paths(magazine)
        >>> print(file_path)
        /Users/user/curator/local/data/_Magazines/Wired/2024/issue.pdf
    """
    file_path = resolve_periodical_file_path(periodical.file_path, library_base_dir, category_prefix)

    cover_path = None
    if periodical.cover_path:
        try:
            cover_path = resolve_periodical_file_path(periodical.cover_path, library_base_dir, category_prefix)
        except FileNotFoundError:
            logger.warning(f"Cover file not found: {periodical.cover_path}")
            # Continue without cover - not critical

    return file_path, cover_path


def verify_periodical_files_exist(periodical, library_base_dir: Optional[Path] = None) -> Tuple[bool, bool]:
    """
    Verify that a periodical's files exist on the filesystem.

    Args:
        periodical: Periodical database object with file_path and cover_path
        library_base_dir: Base library directory (if None, uses default)

    Returns:
        Tuple of (file_exists, cover_exists)

    Example:
        >>> file_exists, cover_exists = verify_periodical_files_exist(magazine)
        >>> if not file_exists:
        >>>     print("File missing!")
    """
    file_exists = False
    cover_exists = False

    try:
        file_path = resolve_periodical_file_path(periodical.file_path, library_base_dir)
        file_exists = file_path.exists()
    except FileNotFoundError:
        pass

    if periodical.cover_path:
        try:
            cover_path = resolve_periodical_file_path(periodical.cover_path, library_base_dir)
            cover_exists = cover_path.exists()
        except FileNotFoundError:
            pass

    return file_exists, cover_exists


def strip_duplicate_suffixes(filename: str) -> str:
    """
    Strip timestamp and counter suffixes from filename stem to prevent accumulation.

    Removes patterns like:
    - (20260203_151457) - timestamp format
    - (2), (3), (10) - counter format
    - Combinations: (20260203_151457) (3)

    Args:
        filename: Filename (with or without extension)

    Returns:
        Filename with suffixes stripped

    Examples:
        >>> strip_duplicate_suffixes("Magazine (20260203_151457).jpg")
        'Magazine.jpg'
        >>> strip_duplicate_suffixes("Magazine (20260203_151457) (3).jpg")
        'Magazine.jpg'
        >>> strip_duplicate_suffixes("Magazine (Special Edition).jpg")
        'Magazine (Special Edition).jpg'
    """
    import re

    # Split extension
    if "." in filename:
        stem, ext = filename.rsplit(".", 1)
    else:
        stem, ext = filename, ""

    # Pattern matches:
    # - Timestamp: (YYYYMMDD_HHMMSS)
    # - Counter: (N) where N is 1-4 digits
    # Multiple times, with optional spaces between
    pattern = r"(\s*\(\d{8}_\d{6}\)|\s*\(\d{1,4}\))+$"

    # Strip all matching suffixes from the end
    cleaned_stem = re.sub(pattern, "", stem).strip()

    # Reconstruct filename
    return f"{cleaned_stem}.{ext}" if ext else cleaned_stem
