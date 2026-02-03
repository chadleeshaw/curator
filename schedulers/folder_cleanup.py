"""
Folder cleanup task for removing folders without importable files.

This task complements the existing cleanup_empty_directories() utility by also
removing folders that contain files but no supported file types (.pdf, .epub, .cbz, .cbr).

Scans downloads and organized directories exhaustively to ensure:
- Folders with ONLY non-supported files are removed (e.g., only .nfo, .txt, .jpg files)
- Folders with ANY supported files are protected and kept
- Then uses existing cleanup_empty_directories() to remove truly empty folders
"""

import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

from core.constants import SUPPORTED_FILE_EXTENSIONS
from core.constants.category import CATEGORIES
from core.constants.files import IMPORT_MARKER_FILE
from core.utils import cleanup_empty_directories

logger = logging.getLogger(__name__)


class FolderCleanup:
    """Clean up empty folders and folders without importable files"""

    # Base protected folder names that should never be deleted
    BASE_PROTECTED_FOLDERS = {
        ".covers",  # Cover image cache
        ".thumbnails",  # Thumbnail cache
        ".ocr_covers",  # OCR processing images
        ".ocr_images",  # OCR processing images (alternative name)
        ".cache",  # General cache
        ".git",  # Version control
        ".tmp",  # Temporary files
    }

    def __init__(
        self,
        downloads_dir: str,
        library_dir: str,
        dry_run: bool = False,
        category_prefix: str = "_",
        enable_downloads_cleanup: bool = True,
        enable_library_cleanup: bool = True,
    ):  # pylint: disable=too-many-positional-arguments
        """
        Initialize folder cleanup.

        Args:
            downloads_dir: Path to downloads directory
            library_dir: Path to library directory
            dry_run: If True, only report what would be deleted without actually deleting
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
            enable_downloads_cleanup: If True, enable auto-cleanup of downloads folder
            enable_library_cleanup: If True, enable auto-cleanup of library folder
        """
        self.downloads_dir = Path(downloads_dir)
        self.library_dir = Path(library_dir)
        self.dry_run = dry_run
        self.category_prefix = category_prefix
        self.enable_downloads_cleanup = enable_downloads_cleanup
        self.enable_library_cleanup = enable_library_cleanup

        # Build complete protected folders set including category folders
        self.protected_folders: Set[str] = self._build_protected_folders()

    def _build_protected_folders(self) -> Set[str]:
        """
        Build complete set of protected folders including category folders.

        Returns:
            Set of folder names that should never be deleted
        """
        protected = set(self.BASE_PROTECTED_FOLDERS)

        # Add category folders (e.g., "_Magazines", "_Comics", "_Graphic Novels")
        for category in CATEGORIES:
            category_folder = f"{self.category_prefix}{category}"
            protected.add(category_folder)

        return protected

    def _scan_folder_exhaustively(self, folder: Path) -> Tuple[List[Path], List[Path], int]:
        """
        Exhaustively scan a folder and all subdirectories.

        Args:
            folder: Path to scan

        Returns:
            Tuple of (supported_files, other_files, total_size_bytes)
        """
        supported_files = []
        other_files = []
        total_size = 0

        try:
            for item in folder.rglob("*"):
                if item.is_file():
                    try:
                        file_size = item.stat().st_size
                        total_size += file_size

                        if item.suffix.lower() in SUPPORTED_FILE_EXTENSIONS:
                            supported_files.append(item)
                        else:
                            other_files.append(item)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Could not access file {item}: {e}")
        except (OSError, PermissionError) as e:
            logger.error(f"Could not scan folder {folder}: {e}")

        return supported_files, other_files, total_size

    def _is_safe_to_delete(self, folder: Path) -> Tuple[bool, str, Dict]:
        """
        Determine if a folder is safe to delete.

        A folder is safe to delete if:
        1. NOT a protected folder (.covers, .cache, etc.)
        2. NOT the root downloads or library directory
        3. It's completely empty (no files or subdirectories), OR
        4. It contains ONLY non-supported files (no .pdf, .epub, .cbz, .cbr)

        Args:
            folder: Path to check

        Returns:
            Tuple of (is_safe, reason, metadata)
            - is_safe: True if safe to delete
            - reason: Human-readable reason
            - metadata: Dict with file counts and sizes
        """
        if not folder.exists() or not folder.is_dir():
            return False, "Not a directory or doesn't exist", {}

        # CRITICAL: Never delete the root downloads or library directories themselves
        if folder.resolve() == self.downloads_dir.resolve():
            return False, "Root downloads directory - NEVER DELETE", {}
        if folder.resolve() == self.library_dir.resolve():
            return False, "Root library directory - NEVER DELETE", {}

        # Check for active import marker - indicates files are being imported
        import_marker = folder / IMPORT_MARKER_FILE
        if import_marker.exists():
            return False, "Import in progress (.importing marker present)", {}

        # Check if folder is protected (e.g., .covers, .cache, .git, _Magazines, _Comics)
        folder_name = folder.name
        if folder_name in self.protected_folders:
            return False, f"Protected folder: {folder_name}", {}

        # Also check if ANY parent directory is protected
        for parent in folder.parents:
            if parent.name in self.protected_folders:
                return False, f"Inside protected folder: {parent.name}", {}

        # Exhaustively scan for all files
        supported_files, other_files, total_size = self._scan_folder_exhaustively(folder)

        metadata = {
            "supported_count": len(supported_files),
            "other_count": len(other_files),
            "total_size": total_size,
            "supported_files": [str(f.relative_to(folder)) for f in supported_files[:5]],  # Sample
            "other_files": [str(f.relative_to(folder)) for f in other_files[:5]],  # Sample
        }

        # If any supported files exist, DO NOT DELETE
        if supported_files:
            return (
                False,
                f"Contains {len(supported_files)} importable file(s) - PROTECTED",
                metadata,
            )

        # If no files at all (completely empty)
        if not other_files:
            return True, "Completely empty folder", metadata

        # If only non-supported files
        return (
            True,
            f"Contains only {len(other_files)} non-importable file(s)",
            metadata,
        )

    def _delete_folder(self, folder: Path, reason: str) -> bool:
        """
        Delete a folder and all its contents.

        Args:
            folder: Path to delete
            reason: Reason for deletion (for logging)

        Returns:
            True if deleted successfully
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete: {folder} - {reason}")
            return True

        try:
            # Use shutil.rmtree for recursive deletion
            import shutil

            shutil.rmtree(folder)
            logger.info(f"Deleted folder: {folder} - {reason}")
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to delete folder {folder}: {e}")
            return False

    def cleanup_directory(self, base_dir: Path, description: str) -> Dict[str, int]:
        """
        Clean up a directory tree by removing empty folders and folders without importable files.

        Process:
        1. Remove folders containing only non-importable files
        2. Use existing cleanup_empty_directories() to remove truly empty folders

        Args:
            base_dir: Base directory to clean
            description: Description for logging (e.g., "downloads", "organized")

        Returns:
            Dict with cleanup statistics
        """
        if not base_dir.exists():
            logger.warning(f"{description} directory doesn't exist: {base_dir}")
            return {
                "scanned": 0,
                "deleted": 0,
                "protected": 0,
                "errors": 0,
                "total_size_freed": 0,
            }

        logger.info(f"Starting folder cleanup for {description}: {base_dir}")

        stats = {
            "scanned": 0,
            "deleted": 0,
            "protected": 0,
            "errors": 0,
            "total_size_freed": 0,
        }

        # PHASE 1: Remove folders with only non-importable files
        # Get all subdirectories, sorted by depth (deepest first)
        # This ensures we delete child folders before parent folders
        try:
            all_dirs = [d for d in base_dir.rglob("*") if d.is_dir()]
            # Sort by depth (deepest first) to process children before parents
            all_dirs.sort(key=lambda x: len(x.parts), reverse=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to list directories in {base_dir}: {e}")
            stats["errors"] += 1
            return stats

        logger.info(f"Found {len(all_dirs)} subdirectories to check in {description}")

        for folder in all_dirs:
            stats["scanned"] += 1

            # Skip if folder was already deleted by a previous operation
            if not folder.exists():
                continue

            # Check if safe to delete
            is_safe, reason, metadata = self._is_safe_to_delete(folder)

            if is_safe:
                # Safe to delete
                success = self._delete_folder(folder, reason)
                if success:
                    stats["deleted"] += 1
                    stats["total_size_freed"] += metadata.get("total_size", 0)
                else:
                    stats["errors"] += 1
            else:
                # Protected - contains importable files
                stats["protected"] += 1
                if metadata.get("supported_count", 0) > 0:
                    logger.debug(
                        f"Protected: {folder} - {metadata['supported_count']} importable files "
                        f"({metadata.get('other_count', 0)} other files)"
                    )

        # PHASE 2: Use existing utility to remove any truly empty directories
        # This catches folders that became empty after Phase 1, or were empty to begin with
        if not self.dry_run and base_dir.exists():
            logger.debug(f"Running final empty directory cleanup for {description}")
            try:
                cleanup_empty_directories(base_dir, base_dir)
            except Exception as e:
                logger.warning(f"Error in final empty directory cleanup: {e}")

        logger.info(
            f"Folder cleanup complete for {description}: "
            f"{stats['deleted']} deleted, {stats['protected']} protected, "
            f"{stats['errors']} errors, {stats['total_size_freed'] / (1024 * 1024):.2f} MB freed"
        )

        return stats

    def run(self) -> Dict[str, int]:
        """
        Execute folder cleanup task for both downloads and organized directories.

        Returns:
            Dict with combined cleanup statistics
        """
        mode = "DRY RUN" if self.dry_run else "LIVE"
        logger.info(f"Starting folder cleanup task ({mode})")

        # Clean downloads directory (if enabled)
        if self.enable_downloads_cleanup:
            downloads_stats = self.cleanup_directory(self.downloads_dir, "downloads")
        else:
            logger.info("Downloads cleanup is disabled - skipping")
            downloads_stats = {
                "scanned": 0,
                "deleted": 0,
                "protected": 0,
                "errors": 0,
                "total_size_freed": 0,
            }

        # Clean organized directory (if enabled)
        if self.enable_library_cleanup:
            organized_stats = self.cleanup_directory(self.library_dir, "organized")
        else:
            logger.info("Library cleanup is disabled - skipping")
            organized_stats = {
                "scanned": 0,
                "deleted": 0,
                "protected": 0,
                "errors": 0,
                "total_size_freed": 0,
            }

        # Combine statistics
        total_stats = {
            "downloads": downloads_stats,
            "organized": organized_stats,
            "total_deleted": downloads_stats["deleted"] + organized_stats["deleted"],
            "total_protected": downloads_stats["protected"] + organized_stats["protected"],
            "total_errors": downloads_stats["errors"] + organized_stats["errors"],
            "total_size_freed": downloads_stats["total_size_freed"] + organized_stats["total_size_freed"],
        }

        logger.info(
            f"Folder cleanup task complete ({mode}): "
            f"{total_stats['total_deleted']} folders deleted, "
            f"{total_stats['total_protected']} folders protected, "
            f"{total_stats['total_size_freed'] / (1024 * 1024):.2f} MB freed"
        )

        return total_stats
