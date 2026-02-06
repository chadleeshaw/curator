"""
Cleanup utilities for file organization.

Contains mixin class with directory cleanup methods used after
file reorganization operations.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class CleanupMixin:
    """Mixin providing directory cleanup functionality."""

    def _safe_cleanup_library_directories(self, old_directories: set, base_dir: Path) -> int:
        """
        Safely clean up old library directories after files have been moved out.

        For each directory we moved files from:
        1. Remove leftover sidecar files (.nfo, .nzb, .txt, etc.) that are not periodicals
        2. Remove the directory ONLY if it is now empty

        This is safe: directories containing periodical files (.pdf, .epub, .cbz, .cbr)
        that were NOT moved will be left intact.

        Args:
            old_directories: Set of library directories we moved files from
            base_dir: Base directory to start cleanup from (for parent directory cleanup)

        Returns:
            Number of directories removed
        """
        from core.constants.files import SUPPORTED_FILE_EXTENSIONS

        removed_count = 0

        for old_dir in old_directories:
            try:
                if not old_dir.exists():
                    continue

                # Check if any periodical files remain — if so, do NOT remove
                remaining_periodicals = [
                    f for f in old_dir.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
                ]

                if remaining_periodicals:
                    logger.info(
                        f"Keeping directory (contains {len(remaining_periodicals)} periodical file(s)): {old_dir}"
                    )
                    continue

                # No periodical files remain — safe to remove leftover sidecars and the directory
                remaining_files = [f for f in old_dir.iterdir() if f.is_file()]
                for leftover in remaining_files:
                    logger.debug(f"Removing leftover sidecar file: {leftover}")
                    leftover.unlink()

                # Remove directory if now empty (no subdirectories either)
                if not any(old_dir.iterdir()):
                    old_dir.rmdir()
                    logger.info(f"Removed empty old directory: {old_dir}")
                    removed_count += 1
                else:
                    logger.info(f"Keeping directory (contains subdirectories): {old_dir}")

            except OSError as e:
                logger.warning(f"Could not clean up directory {old_dir}: {e}")

        # Then, clean up any empty parent directories left behind
        # Walk bottom-up to remove nested empty dirs
        for dirpath, dirnames, filenames in os.walk(str(base_dir), topdown=False):
            dir_path = Path(dirpath)

            # Skip the base directory itself
            if dir_path == base_dir:
                continue

            # Check if directory is empty
            try:
                if not any(dir_path.iterdir()):
                    logger.info(f"Removing empty parent directory: {dir_path}")
                    dir_path.rmdir()
                    removed_count += 1
            except OSError as e:
                logger.debug(f"Could not remove directory {dir_path}: {e}")

        if removed_count > 0:
            logger.info(f"Removed {removed_count} directories during cleanup")

        return removed_count

    def _cleanup_empty_directories(self, base_dir: Path) -> int:
        """
        Remove empty directories recursively using efficient find command.

        Uses `find -type d -empty -delete` for fast cleanup of large directory trees.
        Falls back to Python implementation if find command is unavailable.

        Args:
            base_dir: Base directory to start cleanup from

        Returns:
            Number of directories removed (0 when using find command, as it doesn't return count)
        """
        try:
            import subprocess

            # Use efficient find command to remove all empty directories
            result = subprocess.run(
                ["find", str(base_dir), "-type", "d", "-empty", "-delete"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info(f"Cleaned up empty directories in {base_dir}")
                return 0  # find command doesn't return count
            else:
                # Fall back to Python implementation
                logger.debug(f"Find command failed, using Python fallback: {result.stderr}")
                return self._cleanup_empty_directories_python(base_dir)

        except FileNotFoundError:
            # find command not available (e.g., Windows), use Python implementation
            logger.debug("Find command not available, using Python fallback")
            return self._cleanup_empty_directories_python(base_dir)

    def _cleanup_empty_directories_python(self, base_dir: Path) -> int:
        """
        Python fallback for _cleanup_empty_directories.

        Args:
            base_dir: Base directory to start cleanup from

        Returns:
            Number of directories removed
        """
        removed_count = 0

        # Walk directory tree bottom-up so we can remove empty parent dirs
        for dirpath, dirnames, filenames in os.walk(str(base_dir), topdown=False):
            dir_path = Path(dirpath)

            # Skip the base directory itself
            if dir_path == base_dir:
                continue

            # Check if directory is empty (no files and no subdirs with files)
            try:
                if not any(dir_path.iterdir()):
                    logger.info(f"Removing empty directory: {dir_path}")
                    dir_path.rmdir()
                    removed_count += 1
            except OSError as e:
                logger.debug(f"Could not remove directory {dir_path}: {e}")

        if removed_count > 0:
            logger.info(f"Removed {removed_count} empty directories from {base_dir}")

        return removed_count
