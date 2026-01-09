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

        # Pattern 3b: "Title.No.XX.YYYY" or "Title No XX YYYY" (issue number format)
        # Match issue number pattern: no./no/number/issue followed by digits and year, with optional text after
        pattern3b = r"^(.+?)[\.\s]+(?:no\.?|number|issue)[\.\s]*(\d{1,3})[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
        match = re.search(pattern3b, filename, re.IGNORECASE)
        if match:
            title_part = match.group(1)
            issue_num = match.group(2)
            year_str = match.group(3)
            suffix = match.group(4) if match.group(4) else ""

            # Clean special edition markers from suffix only
            suffix_clean = re.sub(r'\b(?:special[\.\s]+edition|hybrid|magazine|digital|print)\b', '', suffix, flags=re.IGNORECASE).strip()

            # Build title from title part and cleaned suffix
            title = f"{title_part} {suffix_clean}".strip() if suffix_clean else title_part

            # Remove language codes (but not country codes like UK when part of title)
            title_clean = re.sub(r'[\.\s]+(?:de|en|fr|es|it|pt|ru|nl|pl|sv|no|fi|da|ja|ko|zh|ar)(?:[\.\s]|$)', ' ', title, flags=re.IGNORECASE)

            # Replace dots and underscores with spaces
            title_clean = title_clean.replace('.', ' ').replace('_', ' ')

            # Remove release group tags
            title_clean = re.sub(r'\[.*?\]|\(.*?\)', '', title_clean)

            # Clean trailing dashes and extra spaces
            title_clean = re.sub(r'\s*-\s*$', '', title_clean)
            title_clean = re.sub(r'\s+', ' ', title_clean).strip()

            metadata['title'] = title_clean
            metadata['publication_date'] = f"{year_str}-01-01"  # Generic Jan 1st date for issue numbers
            metadata['year'] = int(year_str)
            metadata['month_name'] = 'Jan'
            metadata['edition_number'] = int(issue_num)
            metadata['is_special_edition'] = 'special' in filename.lower() and 'edition' in filename.lower()
            logger.debug("Pattern 3b match - Issue number format")
            return metadata

        # Pattern 3c: "Title Vol.XX No.YY Season YYYY" (volume and number format)
        # Handles formats like "2600.Magazine.Vol.41.No.1.Spring.2024"
        pattern3c = r"^(.+?)[\.\s]+vol\.?[\.\s]*(\d{1,3})[\.\s]+no\.?[\.\s]*(\d{1,3})[\.\s]+(?:.+?[\.\s]+)?(\d{4})"
        match = re.search(pattern3c, filename, re.IGNORECASE)
        if match:
            title_part = match.group(1)
            volume_num = match.group(2)
            issue_num = match.group(3)
            year_str = match.group(4)

            # Clean the title
            title_clean = title_part.replace('.', ' ').replace('_', ' ')
            title_clean = re.sub(r'\s+', ' ', title_clean).strip()

            metadata['title'] = title_clean
            metadata['publication_date'] = f"{year_str}-01-01"  # Generic Jan 1st date
            metadata['year'] = int(year_str)
            metadata['month_name'] = 'Jan'
            metadata['volume'] = int(volume_num)
            metadata['edition_number'] = int(issue_num)
            metadata['is_special_edition'] = False
            logger.debug("Pattern 3c match - Volume and issue number format")
            return metadata

        # Pattern 3d: "Title Season YYYY" (seasonal magazines)
        # Handles formats like "2600.The.Hacker.Quarterly.Winter.2024"
        pattern3d = r"^(.+?)[\.\s]+(spring|summer|fall|autumn|winter)[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
        match = re.search(pattern3d, filename, re.IGNORECASE)
        if match:
            title_part = match.group(1)
            season = match.group(2)
            year_str = match.group(3)
            suffix = match.group(4) if match.group(4) else ""

            # Clean the title and suffix
            title_clean = title_part.replace('.', ' ').replace('_', ' ')

            # Remove common descriptors
            title_clean = re.sub(r'\b(?:quarterly|monthly|weekly|magazine|the|hacker)\b', ' ', title_clean, flags=re.IGNORECASE)

            # Clean suffix if present
            suffix_clean = re.sub(r'\b(?:hybrid|magazine|digital|print|quarterly|monthly)\b', '', suffix, flags=re.IGNORECASE).strip() if suffix else ""

            # Combine title and cleaned suffix
            if suffix_clean:
                title_clean = f"{title_clean} {suffix_clean}"

            # Clean up spaces
            title_clean = re.sub(r'\s+', ' ', title_clean).strip()

            # Map season to approximate month
            season_months = {
                'spring': '03',
                'summer': '06',
                'fall': '09',
                'autumn': '09',
                'winter': '12'
            }
            month = season_months.get(season.lower(), '01')

            metadata['title'] = title_clean
            metadata['publication_date'] = f"{year_str}-{month}-01"
            metadata['year'] = int(year_str)
            metadata['month_name'] = season.capitalize()
            metadata['is_special_edition'] = False
            logger.debug("Pattern 3d match - Seasonal format")
            return metadata

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
        Cleans the folder name to remove common prefixes like "Unpack", "Download", etc.

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

            # Clean the folder name to remove common download/unpack prefixes
            cleaned_name = re.sub(r'^(?:Unpack|Download|Get|Read)\s+', '', folder_name, flags=re.IGNORECASE)
            return cleaned_name

        return None
