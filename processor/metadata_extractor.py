"""
Metadata extraction from PDF filenames and directory structure.
Handles various filename patterns and infers titles from parent directories.
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.constants import MAX_VALID_YEAR, MIN_VALID_YEAR

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extract metadata from PDF filenames and directory structure"""

    def __init__(self):
        """Initialize metadata extractor"""
        self.system_folders = {
            '.',
            '..',
            'downloads',
            'data',
            '_Magazines',
            '_Comics',
            '_Articles',
            '_News',
            'local',
            'cache',
            'config',
            'logs',
            'app',
            # Language folders (should be skipped when extracting periodical names)
            'english',
            'spanish',
            'french',
            'german',
            'italian',
            'portuguese',
            'dutch',
            'russian',
            'chinese',
            'japanese',
            'korean',
        }

    def extract_from_filename(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from filename and parent directory.

        Supports formats like:
        - "National Geographic - Dec2024" or "Wired Magazine December 2024"
        - "National Geographic 2000-01" (year-issue format)
        - "PC Gamer 2023-06" (year-month format)
        - "Apr2001" in folder "2600/2001/" (walks up to find "2600")

        Args:
            pdf_path: Path object to the PDF file

        Returns:
            Dict with extracted metadata (title, publisher, issue_date)
        """
        filename = pdf_path.stem
        magazine_name = self.get_title_from_path(pdf_path)

        metadata = {
            "title": filename,
            "publisher": None,
            "issue_date": datetime.now(),
        }

        # Pattern 1: "Title - MonYear" (e.g., "National Geographic - Dec2024")
        pattern1 = r"(.+?)\s*-\s*([A-Za-z]{3})(\d{4})"
        match = re.search(pattern1, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            month_str = match.group(2)
            year_str = match.group(3)
            try:
                date_str = f"{month_str} {year_str}"
                metadata["issue_date"] = datetime.strptime(date_str, "%b %Y")
                return metadata
            except ValueError:
                logger.warning(
                    f"Could not parse date from filename pattern1: {filename}"
                )

        # Pattern 1b: "Title.Month.Year" with dots (e.g. "Wired.Jan.2024")
        # This handles release group naming conventions
        pattern1b = r"^([^.]+)\.(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.(\d{4})"
        match = re.search(pattern1b, filename, re.IGNORECASE)
        if match:
            metadata["title"] = match.group(1).replace(".", " ").strip()
            month_str = match.group(2)
            year_str = match.group(3)
            try:
                date_str = f"{month_str} {year_str}"
                try:
                    metadata["issue_date"] = datetime.strptime(date_str, "%B %Y")
                except ValueError:
                    metadata["issue_date"] = datetime.strptime(date_str, "%b %Y")
                logger.info(f"Extracted '{metadata['title']}' {month_str} {year_str} from dot-separated filename")
                return metadata
            except ValueError:
                logger.warning(
                    f"Could not parse date from filename pattern1b: {filename}"
                )

        # Pattern 2: "Title Periodical Month Year" (e.g., "Wired Periodical January 2024")
        pattern2 = r"(.+?)\s+([A-Za-z]+)\s+(\d{4})"
        match = re.search(pattern2, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            month_str = match.group(2)
            year_str = match.group(3)
            try:
                date_str = f"{month_str} {year_str}"
                metadata["issue_date"] = datetime.strptime(date_str, "%B %Y")
                return metadata
            except ValueError:
                try:
                    metadata["issue_date"] = datetime.strptime(date_str, "%b %Y")
                    return metadata
                except ValueError:
                    logger.warning(
                        f"Could not parse date from filename pattern2: {filename}"
                    )

        # Pattern 3: "Title YYYY-MM" (e.g., "National Geographic 2000-01" or "PC Gamer 2024-12")
        pattern3 = r"(.+?)\s+(\d{4})-(\d{2})$"
        match = re.search(pattern3, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            year_str = match.group(2)
            month_str = match.group(3)
            try:
                date_str = f"{year_str}-{month_str}-01"
                metadata["issue_date"] = datetime.strptime(date_str, "%Y-%m-%d")
                return metadata
            except ValueError:
                logger.warning(f"Could not parse year-month from filename: {filename}")

        # Pattern 4: Filename is just a date (e.g., "Apr2001", "January2015")
        date_only_pattern1 = r"^([A-Za-z]+)(\d{4})$"  # "Apr2001"
        date_only_pattern2 = r"^([A-Za-z]+)\s+(\d{4})$"  # "April 2001"

        match = re.search(date_only_pattern1, filename) or re.search(
            date_only_pattern2, filename
        )
        if match:
            month_str = match.group(1)
            year_str = match.group(2)
            try:
                date_str = f"{month_str} {year_str}"
                try:
                    parsed_date = datetime.strptime(date_str, "%B %Y")
                except ValueError:
                    parsed_date = datetime.strptime(date_str, "%b %Y")

                metadata["issue_date"] = parsed_date

                if magazine_name:
                    metadata["title"] = magazine_name
                    logger.info(
                        f"Extracted title '{magazine_name}' from directory tree for date-only filename: {filename}"
                    )
                else:
                    metadata["title"] = filename
                    logger.warning(
                        f"Filename is date-only ({filename}) but no suitable magazine folder found"
                    )

                return metadata
            except ValueError:
                logger.warning(f"Could not parse date from date-only filename: {filename}")

        # Pattern 5: Just extract a 4-digit year anywhere in the filename
        year_match = re.search(r"(\d{4})", filename)
        if year_match:
            year_str = year_match.group(1)
            try:
                metadata["issue_date"] = datetime.strptime(
                    f"{year_str}-01-01", "%Y-%m-%d"
                )

                if magazine_name:
                    metadata["title"] = magazine_name
                    logger.info(
                        f"Extracted title '{magazine_name}' from directory tree for year-only filename: {filename}"
                    )
                else:
                    logger.info(f"Extracted year {year_str} from filename: {filename}")

                return metadata
            except ValueError:
                logger.warning(f"Could not parse year from filename: {filename}")

        logger.info(
            f"No date pattern matched in filename: {filename}, using current date"
        )
        return metadata

    def get_title_from_path(self, pdf_path: Path) -> Optional[str]:
        """
        Walk up the directory tree to find a suitable magazine name.

        Skips year folders (4-digit numbers) and system folders.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Magazine name from parent directories, or None if not found
        """
        current = pdf_path.parent
        while current and current != current.parent:
            folder_name = current.name

            if folder_name.lower() in self.system_folders:
                current = current.parent
                continue

            # This allows "2600" (the magazine) while skipping actual year folders
            if folder_name.isdigit() and len(folder_name) == 4:
                year_value = int(folder_name)
                if MIN_VALID_YEAR <= year_value <= MAX_VALID_YEAR:
                    current = current.parent
                    continue

            return folder_name

        return None
