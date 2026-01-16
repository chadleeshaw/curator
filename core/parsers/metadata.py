"""
Metadata extraction from PDF filenames and directory structure.
Handles various filename patterns and infers titles from parent directories.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.constants import MAX_VALID_YEAR, MIN_VALID_YEAR, MONTH_TO_NUMBER, NUMBER_TO_MONTH, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


def parse_month(month_str: str) -> Optional[int]:
    """
    Parse a month string to its number (1-12).

    Args:
        month_str: Month name or abbreviation (e.g., "January", "Jan", "jan")

    Returns:
        Month number (1-12) or None if not recognized
    """
    if not month_str:
        return None

    month_lower = month_str.lower().strip()
    return MONTH_TO_NUMBER.get(month_lower)


def parse_multi_month(month_str: str) -> Tuple[Optional[int], str]:
    """
    Parse a month string that may contain multiple months (e.g., "June/July").

    Args:
        month_str: Month string, possibly multi-month format

    Returns:
        Tuple of (first_month_number, display_string)
        first_month_number is None if not parseable
    """
    if not month_str:
        return None, ""

    month_str = month_str.strip()

    # Check for multi-month separators
    for sep in ["/", "-", "&"]:
        if sep in month_str:
            parts = month_str.split(sep)
            first_month = parts[0].strip()
            month_num = parse_month(first_month)
            if month_num:
                # Normalize display: "Jun/Jul" -> "June/July"
                normalized_parts = []
                for part in parts:
                    part = part.strip()
                    part_num = parse_month(part)
                    if part_num:
                        # Convert to full month name
                        normalized_parts.append(NUMBER_TO_MONTH[part_num])
                    else:
                        # Keep original if not recognized
                        normalized_parts.append(part.capitalize())
                return month_num, "/".join(normalized_parts)

    # Single month - convert to full name
    month_num = parse_month(month_str)
    if month_num:
        return month_num, NUMBER_TO_MONTH[month_num]
    return None, month_str.capitalize()


def clean_title(title: str, remove_descriptors: bool = False) -> str:
    """
    Clean a title string by removing common artifacts.

    Args:
        title: Raw title string
        remove_descriptors: If True, also remove words like "magazine", "quarterly"

    Returns:
        Cleaned title string
    """
    # Replace dots and underscores with spaces
    cleaned = title.replace(".", " ").replace("_", " ")

    # Remove release group tags [xxx] and (xxx)
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned)

    # Remove language codes (but not country codes like UK)
    cleaned = re.sub(
        r"[\s]+(?:de|en|fr|es|it|pt|ru|nl|pl|sv|no|fi|da|ja|ko|zh|ar)(?:[\s]|$)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    if remove_descriptors:
        cleaned = re.sub(
            r"\b(?:quarterly|monthly|weekly|magazine|the|hacker|hybrid|digital|print)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    # NOTE: Do NOT remove "Special Edition" here - it needs to be preserved
    # for title_matcher.extract_base_title() to detect special editions properly

    # Clean trailing dashes and normalize whitespace
    cleaned = re.sub(r"\s*-\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


class MetadataExtractor:
    """Extract metadata from PDF filenames and directory structure."""

    def __init__(self):
        """Initialize metadata extractor with system folder list."""
        self.system_folders = {
            ".", "..", "downloads", "data", "local", "cache", "config", "logs", "app",
            "_Magazines", "_Comics", "_Articles", "_News",
        }
        # Add language folders (should be skipped when extracting periodical names)
        self.system_folders.update(lang.lower() for lang in SUPPORTED_LANGUAGES)

    def extract_from_filename(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from filename and parent directory.

        Supports formats like:
        - "Title - Jun/Jul2024" (multi-month)
        - "National Geographic - Dec2024" (month-year)
        - "Title.January.2024" (dot-separated)
        - "Title 2024-01" (ISO format)
        - "Title No.405 2024" (issue number)
        - "Title Winter 2024" (seasonal)

        Args:
            pdf_path: Path object to the PDF file

        Returns:
            Dict with extracted metadata (title, issue_date, etc.)
        """
        filename = pdf_path.stem
        magazine_name = self.get_title_from_path(pdf_path)

        # Default metadata
        metadata: Dict[str, Any] = {
            "title": filename,
            "issue_date": datetime.now(),
        }

        # Try each pattern in order of specificity
        result = (
            self._try_multi_month_pattern(filename, metadata)
            or self._try_dash_month_year_pattern(filename, metadata)
            or self._try_dot_separated_pattern(filename, metadata)
            or self._try_space_month_year_pattern(filename, metadata)
            or self._try_iso_date_pattern(filename, metadata)
            or self._try_issue_number_pattern(filename, metadata)
            or self._try_volume_issue_pattern(filename, metadata)
            or self._try_seasonal_pattern(filename, metadata)
            or self._try_date_only_pattern(filename, metadata, magazine_name)
            or self._try_year_only_pattern(filename, metadata, magazine_name)
        )

        if result:
            return result

        logger.info(f"No date pattern matched in filename: {filename}, using current date")
        return metadata

    def _try_multi_month_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: Multi-month periods like "Title - June/July 2024" or "Title Jun/Jul2024".
        """
        # Handles: "Title - Jun/Jul2024", "Title June/July 2024", "Title - December/January 2024"
        pattern = r"(.+?)\s*[-–]?\s*([A-Za-z]+)[/\-&]([A-Za-z]+)\s*(\d{4})"
        match = re.search(pattern, filename)

        if not match:
            return None

        title = match.group(1).strip()
        month1_str = match.group(2)
        month2_str = match.group(3)
        year_str = match.group(4)

        month1_num = parse_month(month1_str)
        if not month1_num:
            return None

        year = int(year_str)
        metadata["title"] = clean_title(title)
        metadata["issue_date"] = datetime(year, month1_num, 1)
        metadata["year"] = year
        metadata["month_name"] = f"{month1_str.capitalize()}/{month2_str.capitalize()}"

        logger.info(f"Extracted multi-month: {metadata['month_name']} {year}")
        return metadata

    def _try_dash_month_year_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title - MonYear" (e.g., "National Geographic - Dec2024").
        Also handles: "Title-Month.Year" (e.g., "Esquire.Africa-August.2023").
        """
        # Try with year directly after month (no separator)
        pattern = r"(.+?)\s*-\s*([A-Za-z]{3,9})(\d{4})"
        match = re.search(pattern, filename)

        # Also try with dot or space before year
        if not match:
            pattern = r"(.+?)\s*-\s*([A-Za-z]{3,9})[\.\s]+(\d{4})"
            match = re.search(pattern, filename)

        if not match:
            return None

        title = match.group(1).strip()
        month_str = match.group(2)
        year_str = match.group(3)

        month_num, normalized_month = parse_multi_month(month_str)
        if not month_num:
            return None

        year = int(year_str)
        metadata["title"] = clean_title(title)
        metadata["issue_date"] = datetime(year, month_num, 1)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        return metadata

    def _try_dot_separated_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title.Month.Year" (e.g., "Wired.January.2024").
        """
        pattern = r"^([^.]+)\.(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.(\d{4})"
        match = re.search(pattern, filename, re.IGNORECASE)

        if not match:
            return None

        title = match.group(1)
        month_str = match.group(2)
        year_str = match.group(3)

        month_num, normalized_month = parse_multi_month(month_str)
        if not month_num:
            return None

        year = int(year_str)
        metadata["title"] = clean_title(title)
        metadata["issue_date"] = datetime(year, month_num, 1)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        logger.info(f"Extracted '{metadata['title']}' {month_str} {year_str} from dot-separated filename")
        return metadata

    def _try_space_month_year_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Month Year" (e.g., "Wired January 2024").
        """
        pattern = r"(.+?)\s+([A-Za-z]+)\s+(\d{4})"
        match = re.search(pattern, filename)

        if not match:
            return None

        title = match.group(1).strip()
        month_str = match.group(2)
        year_str = match.group(3)

        month_num, normalized_month = parse_multi_month(month_str)
        if not month_num:
            return None

        year = int(year_str)
        metadata["title"] = clean_title(title)
        metadata["issue_date"] = datetime(year, month_num, 1)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        return metadata

    def _try_iso_date_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title YYYY-MM" (e.g., "PC Gamer 2024-12").
        """
        pattern = r"(.+?)\s+(\d{4})-(\d{2})$"
        match = re.search(pattern, filename)

        if not match:
            return None

        title = match.group(1).strip()
        year_str = match.group(2)
        month_str = match.group(3)

        try:
            metadata["title"] = clean_title(title)
            metadata["issue_date"] = datetime(int(year_str), int(month_str), 1)
            return metadata
        except ValueError:
            logger.warning(f"Invalid ISO date in filename: {filename}")
            return None

    def _try_issue_number_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title No.XXX YYYY" (e.g., "PC Gamer No.405 2024").
        """
        pattern = r"^(.+?)[\.\s]+(?:no\.?|number|issue)[\.\s]*(\d{1,3})[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
        match = re.search(pattern, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1)
        issue_num = match.group(2)
        year_str = match.group(3)
        suffix = match.group(4) or ""

        # Build and clean title
        title = f"{title_part} {suffix}".strip() if suffix else title_part
        title_clean = clean_title(title)

        year = int(year_str)
        metadata["title"] = title_clean
        metadata["issue_date"] = datetime(year, 1, 1)
        metadata["year"] = year
        metadata["month_name"] = "January"
        metadata["edition_number"] = int(issue_num)
        metadata["is_special_edition"] = "special" in filename.lower() and "edition" in filename.lower()

        logger.debug("Pattern match - Issue number format")
        return metadata

    def _try_volume_issue_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Vol.XX No.YY YYYY" (e.g., "2600.Magazine.Vol.41.No.1.2024").
        """
        pattern = r"^(.+?)[\.\s]+vol\.?[\.\s]*(\d{1,3})[\.\s]+no\.?[\.\s]*(\d{1,3})[\.\s]+(?:.+?[\.\s]+)?(\d{4})"
        match = re.search(pattern, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1)
        volume_num = match.group(2)
        issue_num = match.group(3)
        year_str = match.group(4)

        year = int(year_str)
        metadata["title"] = clean_title(title_part)
        metadata["issue_date"] = datetime(year, 1, 1)
        metadata["year"] = year
        metadata["month_name"] = "January"
        metadata["volume"] = int(volume_num)
        metadata["edition_number"] = int(issue_num)
        metadata["is_special_edition"] = False

        logger.debug("Pattern match - Volume and issue number format")
        return metadata

    def _try_seasonal_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Season YYYY" (e.g., "2600 Winter 2024").
        """
        pattern = r"^(.+?)[\.\s]+(spring|summer|fall|autumn|winter)[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
        match = re.search(pattern, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1)
        season = match.group(2).lower()
        year_str = match.group(3)
        suffix = match.group(4) or ""

        # Build and clean title
        title = f"{title_part} {suffix}".strip() if suffix else title_part
        title_clean = clean_title(title, remove_descriptors=True)

        year = int(year_str)
        month = MONTH_TO_NUMBER.get(season, 1)

        metadata["title"] = title_clean
        metadata["issue_date"] = datetime(year, month, 1)
        metadata["year"] = year
        metadata["month_name"] = season.capitalize()
        metadata["is_special_edition"] = False

        logger.debug("Pattern match - Seasonal format")
        return metadata

    def _try_date_only_pattern(
        self, filename: str, metadata: Dict[str, Any], magazine_name: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Pattern: Filename is just a date (e.g., "Apr2001", "January 2015").
        """
        # Try "Apr2001" format
        pattern1 = r"^([A-Za-z]+)(\d{4})$"
        # Try "April 2001" format
        pattern2 = r"^([A-Za-z]+)\s+(\d{4})$"

        match = re.search(pattern1, filename) or re.search(pattern2, filename)
        if not match:
            return None

        month_str = match.group(1)
        year_str = match.group(2)

        month_num = parse_month(month_str)
        if not month_num:
            return None

        year = int(year_str)
        metadata["issue_date"] = datetime(year, month_num, 1)
        metadata["year"] = year
        metadata["month_name"] = month_str.capitalize()

        if magazine_name:
            metadata["title"] = magazine_name
            logger.info(f"Extracted title '{magazine_name}' from directory for date-only filename: {filename}")
        else:
            metadata["title"] = filename
            logger.warning(f"Filename is date-only ({filename}) but no suitable magazine folder found")

        return metadata

    def _try_year_only_pattern(
        self, filename: str, metadata: Dict[str, Any], magazine_name: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Pattern: Just extract a 4-digit year from the filename.
        """
        match = re.search(r"(\d{4})", filename)
        if not match:
            return None

        year_str = match.group(1)
        year = int(year_str)

        # Validate it's a reasonable year
        if not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            return None

        metadata["issue_date"] = datetime(year, 1, 1)

        if magazine_name:
            metadata["title"] = magazine_name
            logger.info(f"Extracted title '{magazine_name}' from directory for year-only filename: {filename}")
        else:
            logger.info(f"Extracted year {year_str} from filename: {filename}")

        return metadata

    def get_title_from_path(self, pdf_path: Path) -> Optional[str]:
        """
        Walk up the directory tree to find a suitable magazine name.

        Skips year folders (4-digit numbers) and system folders.
        Cleans the folder name to remove common prefixes.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Magazine name from parent directories, or None if not found
        """
        current = pdf_path.parent

        while current and current != current.parent:
            folder_name = current.name

            # Skip system folders
            if folder_name.lower() in self.system_folders:
                current = current.parent
                continue

            # Skip year folders (but allow magazine names like "2600")
            if folder_name.isdigit() and len(folder_name) == 4:
                year_value = int(folder_name)
                if MIN_VALID_YEAR <= year_value <= MAX_VALID_YEAR:
                    current = current.parent
                    continue

            # Clean common download/unpack prefixes
            cleaned = re.sub(
                r"^(?:Unpack|Download|Get|Read)\s+",
                "",
                folder_name,
                flags=re.IGNORECASE,
            )
            return cleaned

        return None
