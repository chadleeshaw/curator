"""
Utility functions for core operations.

This module provides common utility functions used across the application.
"""

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

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

    Recursively removes empty directories (including nested empty subdirectories)
    starting from start_path and working upward until reaching base_dir or
    encountering a directory with files.

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
        current = start_path
        while current != base_dir and current.exists():
            if current.is_dir():
                # Check if directory contains any files (recursively)
                has_files = any(item.is_file() for item in current.rglob("*"))

                if not has_files:
                    # Directory only contains empty subdirectories or is completely empty
                    logger.info(f"Removing empty directory tree: {current}")
                    shutil.rmtree(current)
                    current = current.parent
                else:
                    # Stop if we find a directory with files
                    break
            else:
                break
    except Exception as e:
        logger.warning(f"Error cleaning up empty directories: {e}")


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
    file_hash = algorithm()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                file_hash.update(chunk)
        return file_hash.hexdigest()
    except IOError as e:
        logger.error(f"Error hashing file {file_path}: {e}")
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
    special_keywords = [
        "special",
        "annual",
        "collector",
        "collectors",
        "holiday",
        "christmas",
        "summer special",
        "winter special",
        "spring special",
        "fall special",
        "collector's edition",
        "commemorative",
        "anniversary",
        "yearbook",
        "best of",
    ]

    return any(keyword in title_lower for keyword in special_keywords)


def find_pdf_epub_files(directory: Path, recursive: bool = True) -> list[Path]:
    """
    Search for PDF and EPUB files in a directory.

    Args:
        directory: Directory to search
        recursive: If True, search recursively with glob("**/*.ext"), else use glob("*.ext")

    Returns:
        List of Path objects for all PDF and EPUB files found

    Examples:
        >>> files = find_pdf_epub_files(Path("/downloads"))
        >>> pdf_only = [f for f in files if f.suffix == '.pdf']
    """
    if not directory.exists():
        return []

    pattern = "**/*" if recursive else "*"
    pdf_files = list(directory.glob(f"{pattern}.pdf"))
    epub_files = list(directory.glob(f"{pattern}.epub"))

    return pdf_files + epub_files
