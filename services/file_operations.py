"""
File reorganization utilities for periodicals.

This module provides shared utilities for reorganizing periodical files
(PDF and cover images) across different parts of the application.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from core.constants import DEFAULT_CATEGORY
from core.parsers import sanitize_filename, utc_now

logger = logging.getLogger(__name__)


@dataclass
class FileReorganizationResult:
    """Result of a file reorganization operation"""

    success: bool
    new_pdf_path: Optional[str]
    new_cover_path: Optional[str]
    error: Optional[str] = None
    files_moved: bool = False


def reorganize_periodical_files(
    periodical,
    new_title: str,
    library_base_dir: Path,
    category_prefix: str = "_",
    should_update_database: bool = True,
) -> FileReorganizationResult:
    """
    Reorganize periodical files to match new title structure.

    Handles filename conflicts by appending timestamps.
    Moves both PDF and cover files while preserving file extensions.
    """
    try:
        from core.utils.files import strip_duplicate_suffixes

        old_pdf_path = Path(periodical.file_path)
        old_cover_path = Path(periodical.cover_path) if periodical.cover_path else None

        # Extract metadata from periodical
        category = (
            periodical.extra_metadata.get("category", DEFAULT_CATEGORY)
            if periodical.extra_metadata
            else DEFAULT_CATEGORY
        )
        issue_date = periodical.issue_date

        if not issue_date:
            return FileReorganizationResult(
                success=False,
                new_pdf_path=None,
                new_cover_path=None,
                error=f"Cannot reorganize periodical {periodical.id}: missing issue_date",
            )

        # Build new path structure
        # Strip any accumulated timestamp/counter suffixes before sanitizing
        clean_title = strip_duplicate_suffixes(new_title)
        safe_title = sanitize_filename(clean_title)
        month = issue_date.strftime("%B")
        year = issue_date.strftime("%Y")
        filename_base = f"{safe_title} - {month}{year}"

        # Preserve the original file extension instead of assuming .pdf
        file_ext = old_pdf_path.suffix if old_pdf_path.suffix else ".pdf"

        category_with_prefix = f"{category_prefix}{category}"
        target_dir = library_base_dir / category_with_prefix / safe_title / year
        target_dir.mkdir(parents=True, exist_ok=True)

        new_pdf_path = target_dir / f"{filename_base}{file_ext}"
        new_cover_path = target_dir / f"{filename_base}.jpg" if old_cover_path else None

        # Handle filename conflicts by appending timestamp with counter
        if new_pdf_path.exists() and new_pdf_path != old_pdf_path:
            timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
            filename_base_with_ts = f"{safe_title} - {month}{year} ({timestamp})"
            new_pdf_path = target_dir / f"{filename_base_with_ts}{file_ext}"

            # If the timestamped path also exists (multiple moves in the same second),
            # append an incrementing counter until we find a unique path
            counter = 1
            while new_pdf_path.exists() and new_pdf_path != old_pdf_path:
                filename_base_with_ts = f"{safe_title} - {month}{year} ({timestamp}_{counter})"
                new_pdf_path = target_dir / f"{filename_base_with_ts}{file_ext}"
                counter += 1

            if old_cover_path:
                new_cover_path = target_dir / f"{filename_base_with_ts}.jpg"

        # Check if files need to be moved
        files_moved = False

        # Move PDF file
        if old_pdf_path.exists() and new_pdf_path != old_pdf_path:
            shutil.move(str(old_pdf_path), str(new_pdf_path))
            logger.info(f"Moved PDF: {old_pdf_path} -> {new_pdf_path}")
            files_moved = True
            if should_update_database:
                periodical.file_path = str(new_pdf_path)
        elif new_pdf_path == old_pdf_path:
            if should_update_database:
                periodical.file_path = str(new_pdf_path)
        else:
            logger.warning(f"PDF file not found: {old_pdf_path}")
            return FileReorganizationResult(
                success=False,
                new_pdf_path=None,
                new_cover_path=None,
                error=f"PDF file not found: {old_pdf_path}",
            )

        # Move cover file if it exists
        if old_cover_path and old_cover_path.exists() and new_cover_path and new_cover_path != old_cover_path:
            shutil.move(str(old_cover_path), str(new_cover_path))
            logger.info(f"Moved cover: {old_cover_path} -> {new_cover_path}")
            files_moved = True
            if should_update_database:
                periodical.cover_path = str(new_cover_path)
        elif new_cover_path and should_update_database:
            periodical.cover_path = str(new_cover_path)

        return FileReorganizationResult(
            success=True,
            new_pdf_path=str(new_pdf_path),
            new_cover_path=str(new_cover_path) if new_cover_path else None,
            files_moved=files_moved,
        )

    except (OSError, shutil.Error) as e:
        logger.error(f"Error reorganizing periodical files: {e}", exc_info=True)
        return FileReorganizationResult(success=False, new_pdf_path=None, new_cover_path=None, error=str(e))


def move_files_with_cleanup(
    old_pdf_path: Path,
    new_pdf_path: Path,
    old_cover_path: Optional[Path] = None,
    new_cover_path: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Move PDF and cover files with proper error handling.

    This is a lower-level utility for moving files when you already
    have the source and target paths computed.

    Args:
        old_pdf_path: Current PDF file path
        new_pdf_path: Target PDF file path
        old_cover_path: Current cover file path (optional)
        new_cover_path: Target cover file path (optional)

    Returns:
        Tuple of (success: bool, error_message: Optional[str])

    Example:
        success, error = move_files_with_cleanup(
            Path("/old/magazine.pdf"),
            Path("/new/magazine.pdf"),
            Path("/old/magazine.jpg"),
            Path("/new/magazine.jpg")
        )
    """
    try:
        # Verify source PDF exists
        if not old_pdf_path.exists():
            return False, f"Source PDF not found: {old_pdf_path}"

        # Create target directory
        new_pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Move PDF
        if new_pdf_path != old_pdf_path:
            shutil.move(str(old_pdf_path), str(new_pdf_path))
            logger.info(f"Moved PDF: {old_pdf_path} -> {new_pdf_path}")

        # Move cover if provided
        if old_cover_path and old_cover_path.exists() and new_cover_path and new_cover_path != old_cover_path:
            shutil.move(str(old_cover_path), str(new_cover_path))
            logger.info(f"Moved cover: {old_cover_path} -> {new_cover_path}")

        return True, None

    except (OSError, shutil.Error) as e:
        logger.error(f"Error moving files: {e}", exc_info=True)
        return False, str(e)
