"""
Utility functions for core operations.

This module provides common utility functions used across the application.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from core.constants.files import BLACKLISTED_FILE_EXTENSIONS
from core.constants.title import SPECIAL_EDITION_KEYWORDS

logger = logging.getLogger(__name__)


def generate_olid(title: str) -> str:
    """
    Generate OLID (Open Library ID) from title by normalizing to lowercase and replacing spaces/hyphens with underscores.

    Args:
        title: The title to convert to an OLID

    Returns:
        Normalized OLID string

    Examples:
        >>> generate_olid("Wired Magazine")
        'wired_magazine'
        >>> generate_olid("PC-Gamer")
        'pc_gamer'
    """
    return title.lower().replace(" ", "_").replace("-", "_")


def cleanup_empty_directories(start_path: Path, base_dir: Path) -> None:
    """
    Remove empty directories from start_path up to base_dir.

    Uses efficient `find -type d -empty -delete` command to remove all empty
    directories in one pass, then walks upward from start_path to base_dir
    removing any newly-empty parent directories.

    Args:
        start_path: Starting directory to check for emptiness
        base_dir: Base directory to stop at (won't delete this)

    Returns:
        None

    Examples:
        >>> cleanup_empty_directories(Path("/data/magazines/title/2024"), Path("/data"))
        # Removes /data/magazines/title/2024 if empty (including nested empty dirs),
        # then /data/magazines/title if empty, etc.
    """
    try:
        if not start_path.exists() or not start_path.is_dir():
            return

        # Don't delete the base directory itself
        if start_path == base_dir:
            return

        # First pass: Use efficient find command to remove all empty directories under start_path
        # This is much faster than Python iteration for large directory trees
        try:
            import subprocess

            # Only run find if start_path exists and is not the base_dir
            result = subprocess.run(
                ["find", str(start_path), "-depth", "-type", "d", "-empty", "-delete"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                # Fall back to Python implementation if find command fails
                logger.debug(f"Find command failed, using Python fallback: {result.stderr}")
                _cleanup_empty_directories_python(start_path, base_dir)
        except FileNotFoundError:
            # find command not available (e.g., Windows), use Python implementation
            logger.debug("Find command not available, using Python fallback")
            _cleanup_empty_directories_python(start_path, base_dir)

        # Second pass: Walk upward from start_path to base_dir removing newly-empty parents
        # This handles the case where start_path itself or its parents became empty
        current = start_path
        while current not in (
            base_dir,
            current.parent,
        ):  # Prevent infinite loop at root
            if not current.exists():
                # Directory was already removed, move to parent
                current = current.parent
                continue

            if current.is_dir():
                # Check if directory is now empty
                try:
                    if not any(current.iterdir()):
                        logger.info(f"Removing empty parent directory: {current}")
                        current.rmdir()
                        current = current.parent
                    else:
                        # Stop if directory has contents
                        break
                except OSError:
                    # Can't iterate or remove, stop here
                    break
            else:
                break
    except Exception as e:
        logger.warning(f"Error cleaning up empty directories: {e}")


def _cleanup_empty_directories_python(start_path: Path, base_dir: Path) -> None:
    """
    Python fallback for cleanup_empty_directories when find command unavailable.

    Args:
        start_path: Starting directory to clean up
        base_dir: Base directory to stop at (won't delete this)
    """
    try:
        # Walk directory tree bottom-up so we can remove empty parent dirs
        for dirpath, dirnames, filenames in os.walk(str(start_path), topdown=False):
            dir_path = Path(dirpath)

            # Don't remove base directory
            if dir_path == base_dir:
                continue

            # Check if directory is empty (no files and no subdirs)
            try:
                if not any(dir_path.iterdir()):
                    logger.debug(f"Removing empty directory: {dir_path}")
                    dir_path.rmdir()
            except OSError:
                pass  # Directory not empty or can't be removed
    except Exception as e:
        logger.debug(f"Error in Python directory cleanup: {e}")


def hash_file_in_chunks(file_path: str, algorithm=hashlib.sha256, chunk_size: int = 8192) -> Optional[str]:
    """
    Calculate the hash of a file without loading the entire file into memory.

    This function reads the file in chunks, making it memory-efficient for large files.
    SHA256 is fast (~500 MB/s) and the chunked approach allows hashing of multi-GB files
    without memory concerns.

    Args:
        file_path: The path to the file to hash
        algorithm: The hash algorithm to use (default: hashlib.sha256)
        chunk_size: The size of each chunk to read in bytes (default: 8192)

    Returns:
        The hexadecimal hash digest, or None if an error occurred

    Examples:
        >>> hash_file_in_chunks('magazine.pdf')
        'a3b5c2d1e4f5...'
        >>> hash_file_in_chunks('large_file.iso', chunk_size=65536)  # 64KB chunks
        'f4e3d2c1b0a9...'
    """
    try:
        file_hash = algorithm()
        path = Path(file_path)

        # Diagnostic checks for common failure scenarios
        if not path.exists():
            logger.error(f"Cannot hash file - does not exist: {file_path}")
            return None

        if not path.is_file():
            logger.error(f"Cannot hash file - not a regular file: {file_path}")
            return None

        if not os.access(file_path, os.R_OK):
            logger.error(f"Cannot hash file - no read permission: {file_path}")
            return None

        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                file_hash.update(chunk)
        return file_hash.hexdigest()
    except PermissionError as e:
        logger.error(f"Permission denied hashing file {file_path}: {e}")
        return None
    except OSError as e:
        logger.error(f"OS error hashing file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error hashing file {file_path}: {type(e).__name__}: {e}")
        return None


def is_special_edition(title: str) -> bool:
    """
    Detect if a magazine title represents a special edition.

    Special editions are typically annual issues, holiday specials, collector's editions,
    or other non-standard releases that should be grouped separately from regular issues.

    Args:
        title: Magazine title to check

    Returns:
        True if the title contains special edition keywords, False otherwise

    Examples:
        >>> is_special_edition("Wired - Holiday Special 2024")
        True
        >>> is_special_edition("National Geographic Annual Edition")
        True
        >>> is_special_edition("PC Gamer - June 2024")
        False
    """
    if not title:
        return False

    title_lower = title.lower()
    return any(keyword in title_lower for keyword in SPECIAL_EDITION_KEYWORDS)


def find_pdf_epub_files(directory: Path, recursive: bool = True) -> list[Path]:
    """
    Search for PDF, EPUB, CBZ, and CBR files in a directory, filtering out blacklisted extensions.

    Args:
        directory: Directory to search
        recursive: If True, search recursively with glob("**/*.ext"), else use glob("*.ext")

    Returns:
        List of Path objects for all PDF, EPUB, CBZ, and CBR files found (excluding blacklisted files)

    Examples:
        >>> files = find_pdf_epub_files(Path("/downloads"))
        >>> pdf_only = [f for f in files if f.suffix == '.pdf']
    """
    if not directory.exists():
        return []

    pattern = "**/*" if recursive else "*"
    pdf_files = list(directory.glob(f"{pattern}.pdf"))
    epub_files = list(directory.glob(f"{pattern}.epub"))
    cbz_files = list(directory.glob(f"{pattern}.cbz"))
    cbr_files = list(directory.glob(f"{pattern}.cbr"))

    all_files = pdf_files + epub_files + cbz_files + cbr_files

    # Filter out any files with blacklisted extensions and log them
    filtered_files = []
    for file in all_files:
        if file.suffix.lower() in BLACKLISTED_FILE_EXTENSIONS:
            logger.warning(f"Skipping blacklisted file extension '{file.suffix}': {file.name}")
        else:
            filtered_files.append(file)

    return filtered_files
