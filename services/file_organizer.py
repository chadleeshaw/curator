"""
File organization utilities for moving and renaming PDFs.
Handles both simple and pattern-based organization with metadata extraction.
"""

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.constants import (
    PDF_COVER_DPI_HIGH,
    PDF_COVER_QUALITY_HIGH,
    VOLUME_PREFIX,
    ISSUE_PREFIX,
    ORGANIZED_FILENAME_SEPARATOR,
)
from core.parsers import month_abbr_to_number
from core.pdf_utils import extract_cover_from_pdf as extract_cover_util
from core.parsers import sanitize_filename

logger = logging.getLogger(__name__)


class FileOrganizer:
    """Organize and rename files with metadata extraction and cover art handling"""

    # Pattern: {Title} - {MonYear} (e.g., "Wired Periodical - Dec2006")
    ORGANIZED_PATTERN = "{title} - {month}{year}"

    def __init__(self, organize_dir: str, category_prefix: str = "_"):
        """
        Initialize file organizer.

        Args:
            organize_dir: Base directory for organized files
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
        """
        self.organize_dir = Path(organize_dir)
        self.category_prefix = category_prefix
        self.organize_dir.mkdir(parents=True, exist_ok=True)

    def organize_file(
        self,
        source_path: str,
        title: str,
        issue_date: datetime,
        cover_path: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Organize file into standard naming convention with cover art.

        Simple organization to a flat directory structure.

        Args:
            source_path: Path to downloaded file
            title: Periodical title
            issue_date: Publication date
            cover_path: Optional path to cover art JPG

        Returns:
            Tuple of (pdf_path, jpg_path)

        Raises:
            FileNotFoundError: If source file doesn't exist
            ValueError: If source path is invalid or not a file
        """
        source = Path(source_path)

        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        if not source.is_file():
            raise ValueError(f"Source path is not a file: {source_path}")

        if not os.access(source, os.R_OK):
            raise ValueError(f"Source file is not readable: {source_path}")

        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        month = issue_date.strftime("%b")
        year = issue_date.strftime("%Y")

        safe_title = sanitize_filename(title)
        filename_base = f"{safe_title}{ORGANIZED_FILENAME_SEPARATOR}{month}{year}"

        pdf_path = self.organize_dir / f"{filename_base}.pdf"
        jpg_path = self.organize_dir / f"{filename_base}.jpg"

        if source.suffix.lower() == ".pdf":
            try:
                source.rename(pdf_path)
                logger.info(f"Organized PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Error moving PDF: {e}")
                pdf_path = None
        else:
            logger.warning(f"Source file is not PDF: {source}")
            pdf_path = None

        if cover_path and Path(cover_path).exists():
            try:
                Path(cover_path).rename(jpg_path)
                logger.info(f"Organized cover: {jpg_path}")
            except Exception as e:
                logger.error(f"Error moving cover: {e}")
                jpg_path = None

        return str(pdf_path), str(jpg_path)

    def _build_filename(
        self,
        safe_title: str,
        volume: Optional[int],
        issue_number: Optional[int],
        month: str,
        year: str,
    ) -> str:
        """
        Build organized filename with optional volume and issue information.

        Args:
            safe_title: Sanitized title
            volume: Volume number (optional)
            issue_number: Issue number (optional)
            month: Month abbreviation (e.g., "Dec")
            year: Year (e.g., "2006")

        Returns:
            Filename with .pdf extension
        """
        filename_parts = [safe_title]

        # Add volume if present (e.g., "Vol1")
        # Volume comes before issue number following common periodical conventions
        if volume:
            filename_parts.append(f"{VOLUME_PREFIX}{volume}")

        # Add issue number if present (e.g., "No123")
        if issue_number:
            filename_parts.append(f"{ISSUE_PREFIX}{issue_number}")

        # Add date last (e.g., "Dec2024")
        # This ensures consistent sorting and readability
        filename_parts.append(f"{month}{year}")

        # Join with separator to create final filename
        # Example: "Wired - Vol5 - No12 - Dec2024.pdf"
        return f"{ORGANIZED_FILENAME_SEPARATOR.join(filename_parts)}.pdf"

    def _build_default_directory(
        self,
        category_with_prefix: str,
        safe_title: str,
        volume: Optional[int],
        year: str,
    ) -> Path:
        """
        Build default directory structure.

        Creates: {category}/{title}/{volume}/{year}/ or {category}/{title}/{year}/

        Args:
            category_with_prefix: Category name with prefix
            safe_title: Sanitized title
            volume: Volume number (optional)
            year: Year

        Returns:
            Target directory path
        """
        path_parts = [category_with_prefix, safe_title]

        if volume:
            path_parts.append(f"{VOLUME_PREFIX}{volume}")

        path_parts.append(year)

        return self.organize_dir / Path(*path_parts)

    def _resolve_path(self, path_str: str) -> Path:
        """
        Resolve relative or absolute path.

        Args:
            path_str: Path string (may start with / for absolute)

        Returns:
            Resolved Path object
        """
        if not path_str.startswith("/"):
            return self.organize_dir / path_str
        return Path(path_str)

    def _build_pattern_directory(
        self,
        pattern: str,
        category_with_prefix: str,
        safe_title: str,
        language: str,
        year: str,
        month: str,
        day: str,
        issue_number: Optional[int],
        volume: Optional[int],
    ) -> Path:
        """
        Build directory from pattern with tag substitution.

        Args:
            pattern: Pattern string with {tags}
            category_with_prefix: Category name with prefix
            safe_title: Sanitized title
            language: Language
            year: Year
            month: Month abbreviation
            day: Day
            issue_number: Issue number (optional)
            volume: Volume number (optional)

        Returns:
            Target directory path
        """
        format_dict = {
            "category": category_with_prefix,
            "title": safe_title,
            "language": language,
            "year": year,
            "month": month,
            "day": day,
            "issue": str(issue_number) if issue_number else "",
            "volume": str(volume) if volume else "",
        }

        target_path_str = pattern.format(**format_dict)
        return self._resolve_path(target_path_str)

    def _get_unique_target_path(self, target_dir: Path, filename: str) -> Path:
        """
        Get unique target path, adding timestamp if file exists.

        Args:
            target_dir: Target directory
            filename: Filename with extension

        Returns:
            Unique target path
        """
        target_path = target_dir / filename

        if target_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name_parts = filename.rsplit(".", 1)
            filename = f"{name_parts[0]} ({timestamp}).pdf"
            target_path = target_dir / filename

        return target_path

    def organize(
        self,
        pdf_path: Path,
        metadata: Dict[str, Any],
        category: str,
        pattern: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Move and rename PDF to organized location based on pattern.

        Pattern-based organization with support for subdirectories and tags.
        Available pattern tags:
          {category}, {title}, {year}, {month}, {day}, {language}
          {issue} - Issue number (if available)
          {volume} - Volume number (if available)

        Args:
            pdf_path: Original PDF path
            metadata: Extracted metadata
            category: Category name
            pattern: Organization pattern with tags (optional, defaults to: {category}/{title}/{year}/)

        Returns:
            Path to organized file, or None if failed
        """
        try:
            # Extract metadata
            title = metadata.get("title", pdf_path.stem)
            issue_date = metadata.get("issue_date", datetime.now())
            language = metadata.get("language", "English")
            issue_number = metadata.get("issue_number")
            volume = metadata.get("volume")

            # Format date components
            safe_title = sanitize_filename(title)
            month = issue_date.strftime("%b")
            year = issue_date.strftime("%Y")
            day = issue_date.strftime("%d")

            # Build filename
            filename = self._build_filename(safe_title, volume, issue_number, month, year)

            # Apply category prefix
            category_with_prefix = f"{self.category_prefix}{category}"

            # Build target directory
            if not pattern:
                target_dir = self._build_default_directory(
                    category_with_prefix, safe_title, volume, year
                )
            else:
                target_dir = self._build_pattern_directory(
                    pattern,
                    category_with_prefix,
                    safe_title,
                    language,
                    year,
                    month,
                    day,
                    issue_number,
                    volume,
                )

            # Create directory and get unique path
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = self._get_unique_target_path(target_dir, filename)

            # Move file
            shutil.move(str(pdf_path), str(target_path))
            logger.info(f"Organized file: {target_path}")
            return target_path

        except Exception as e:
            logger.error(f"Error organizing file {pdf_path}: {e}")
            return None

    def extract_cover_from_pdf(self, pdf_path: str, output_path: str) -> bool:
        """
        Extract first page of PDF as JPG cover art.

        Args:
            pdf_path: Path to PDF file
            output_path: Where to save the cover JPG

        Returns:
            True if successful, False otherwise
        """
        pdf_path_obj = Path(pdf_path)
        output_path_obj = Path(output_path)
        output_dir = output_path_obj.parent

        result = extract_cover_util(pdf_path_obj, output_dir, dpi=PDF_COVER_DPI_HIGH, quality=PDF_COVER_QUALITY_HIGH)

        if result:
            if result != output_path_obj:
                result.rename(output_path_obj)
            return True
        return False
