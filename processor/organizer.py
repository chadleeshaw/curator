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

from core.constants import PDF_COVER_DPI_HIGH, PDF_COVER_QUALITY_HIGH
from core.date_utils import month_abbr_to_number
from core.pdf_utils import extract_cover_from_pdf as extract_cover_util
from core.utils import sanitize_filename

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
        filename_base = f"{safe_title} - {month}{year}"

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
        Available pattern tags: {category}, {title}, {year}, {month}, {day}

        Args:
            pdf_path: Original PDF path
            metadata: Extracted metadata
            category: Category name
            pattern: Organization pattern with tags (optional)

        Returns:
            Path to organized file, or None if failed
        """
        try:
            if not pattern:
                return pdf_path

            title = metadata.get("title", pdf_path.stem)
            issue_date = metadata.get("issue_date", datetime.now())

            safe_title = sanitize_filename(title)
            month = issue_date.strftime("%b")
            year = issue_date.strftime("%Y")
            day = issue_date.strftime("%d")
            filename = f"{safe_title} - {month}{year}.pdf"

            # Apply category prefix
            category_with_prefix = f"{self.category_prefix}{category}"

            target_path_str = pattern.format(
                category=category_with_prefix, title=safe_title, year=year, month=month, day=day
            )

            if not target_path_str.startswith("/"):
                target_dir = self.organize_dir / target_path_str
            else:
                target_dir = Path(target_path_str)

            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / filename

            if target_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = filename.rsplit(".", 1)
                filename = f"{name_parts[0]} ({timestamp}).pdf"
                target_path = target_dir / filename

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

        result = extract_cover_util(
            pdf_path_obj,
            output_dir,
            dpi=PDF_COVER_DPI_HIGH,
            quality=PDF_COVER_QUALITY_HIGH
        )

        if result:
            if result != output_path_obj:
                result.rename(output_path_obj)
            return True
        return False

    def parse_filename_for_metadata(self, filename: str) -> Dict[str, Any]:
        """
        Try to extract metadata from filename.

        Expected format: {Magazine Title} - {Abbr}{Year}
        Examples:
          - "Wired Magazine - Dec2006"
          - "National Geographic - Mar2023"

        Args:
            filename: Filename without extension

        Returns:
            Dict with extracted metadata (title, month, year)
        """
        pattern = r"^(.+?)\s*-\s*([A-Za-z]{3})(\d{4})$"
        match = re.match(pattern, filename)

        if match:
            title, month_abbr, year = match.groups()

            month = month_abbr_to_number(month_abbr.capitalize())
            if month:
                try:
                    issue_date = datetime(int(year), month, 1)
                    return {
                        "title": title.strip(),
                        "issue_date": issue_date,
                        "confidence": "high",
                    }
                except ValueError:
                    pass

        return {"confidence": "low"}
