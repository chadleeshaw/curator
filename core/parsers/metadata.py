"""
Metadata extraction from PDF filenames and directory structure.
Handles various filename patterns and infers titles from parent directories.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.constants.date import (
    MAX_VALID_YEAR,
    MIN_VALID_YEAR,
    MONTH_TO_NUMBER,
)
from core.constants.language import SUPPORTED_LANGUAGES
from core.constants.patterns import (
    DATE_PATTERN_ABBR_MONTH_YEAR,
    DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY,
    DATE_PATTERN_FULL_MONTH_YEAR,
    DATE_PATTERN_ISO_FULL,
    DATE_PATTERN_ISO_MONTH,
    DATE_PATTERN_MONTH_YEAR_NUMERIC,
    DATE_PATTERN_YEAR_ONLY,
    NZB_COUNTRY_PATTERNS,
    NZB_EDITION_PATTERNS,
    NZB_ISSUE_PATTERN,
    NZB_LANGUAGE_PATTERNS,
    NZB_QUALITY_PATTERNS,
    NZB_RELEASE_GROUP_PATTERNS,
    NZB_VOLUME_PATTERN,
    TITLE_CLEANUP_TRAILING_DASH_DIGITS,
    TITLE_CLEANUP_TRAILING_SPACE_DIGITS,
)
from core.parsers.date import parse_month, parse_multi_month
from core.utils.text import clean_title

logger = logging.getLogger(__name__)


class FilenameParser:
    """Extract metadata from PDF filenames and directory structure."""

    def __init__(self):
        """Initialize metadata extractor with system folder list."""
        self.system_folders = {
            ".",
            "..",
            "downloads",
            "data",
            "local",
            "cache",
            "config",
            "logs",
            "app",
            "_Magazines",
            "_Comics",
            "_Articles",
            "_News",
        }
        # Add language folders (should be skipped when extracting periodical names)
        self.system_folders.update(lang.lower() for lang in SUPPORTED_LANGUAGES)

    def extract_from_nzb_title(self, nzb_title: str) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from NZB-style filename.

        Handles complex patterns like:
        - Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2
        - National.Geographic-2024-01-HQ.PDF
        - PC.Gamer.UK.Issue.389.February.2024.pdf
        - The.Economist.2024.01.20.pdf
        - TIME.V202.N25.2023.pdf

        Args:
            nzb_title: NZB title or complex filename string

        Returns:
            Dict with extracted metadata including confidence score
        """
        original_title = nzb_title

        # Remove file extension if present
        if "." in nzb_title:
            parts = nzb_title.rsplit(".", 1)
            if len(parts[-1]) <= 4:  # Likely an extension
                nzb_title = parts[0]

        # Initialize metadata dictionary
        metadata: Dict[str, Any] = {
            "title": None,
            "year": None,
            "month": None,
            "day": None,
            "volume": None,
            "issue": None,
            "country": None,
            "language": None,
            "edition": None,
            "release_group": None,
            "quality": None,
            "confidence": "low",
            "issue_date": None,
        }

        # Normalize delimiters: dots, underscores → spaces (but keep dashes)
        normalized = nzb_title.replace(".", " ").replace("_", " ")
        remaining_text = normalized

        # Step 1: Extract release group (from end)
        for pattern in NZB_RELEASE_GROUP_PATTERNS:
            match = re.search(pattern, nzb_title, re.IGNORECASE)
            if match:
                metadata["release_group"] = match.group(1)
                # Remove from remaining text
                end_pos = remaining_text.rfind(match.group(1))
                if end_pos != -1:
                    remaining_text = remaining_text[:end_pos].strip()
                break

        # Step 2: Extract quality indicators (search in ORIGINAL before normalization)
        for pattern in NZB_QUALITY_PATTERNS:
            match = re.search(pattern, nzb_title, re.IGNORECASE)
            if match:
                quality_text = match.group(1).replace(".", " ")
                metadata["quality"] = quality_text
                # Remove from remaining text (normalized version)
                # Replace dots with spaces in the matched quality text to find it in normalized
                quality_normalized = quality_text.lower().replace(" ", " ")
                # Try to find and remove quality keywords from remaining text
                for word in quality_normalized.split():
                    remaining_text = re.sub(
                        rf"\b{re.escape(word)}\b",
                        "",
                        remaining_text,
                        flags=re.IGNORECASE,
                    )
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Step 3: Extract country/region
        for pattern in NZB_COUNTRY_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                country = match.group(1)
                # Special handling for "US" vs "USA"
                if country.upper() in ["US", "USA"]:
                    metadata["country"] = "USA"
                else:
                    metadata["country"] = country.upper()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Step 4: Extract language
        for pattern in NZB_LANGUAGE_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["language"] = match.group(1).capitalize()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Step 5: Extract edition/variant
        for pattern in NZB_EDITION_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["edition"] = match.group(1).capitalize()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Step 6: Extract dates FIRST (before volume/issue to avoid conflicts)
        # This prevents "Jan2024" from being parsed as "issue 2024"
        date_extracted = False

        # Format 1: ISO full date (2024.01.20 or 2024-01-20)
        if not date_extracted:
            match = re.search(DATE_PATTERN_ISO_FULL, remaining_text)
            if match:
                year, month, day = (
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
                if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12 and 1 <= day <= 31:
                    metadata["year"] = year
                    metadata["month"] = month
                    metadata["day"] = day
                    metadata["issue_date"] = datetime(year, month, day)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 2: Full month name with year (January 2024)
        if not date_extracted:
            match = re.search(DATE_PATTERN_FULL_MONTH_YEAR, remaining_text, re.IGNORECASE)
            if match:
                month_str, year_str = match.group(1), match.group(2)
                month_num = parse_month(month_str)
                year = int(year_str)
                if month_num and MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                    metadata["year"] = year
                    metadata["month"] = month_num
                    metadata["issue_date"] = datetime(year, month_num, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 3: Abbreviated month with year (Jan 2024, Jan2024)
        if not date_extracted:
            match = re.search(DATE_PATTERN_ABBR_MONTH_YEAR, remaining_text, re.IGNORECASE)
            if match:
                month_str, year_str = match.group(1), match.group(2)
                month_num = parse_month(month_str)
                year = int(year_str)
                if month_num and MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                    metadata["year"] = year
                    metadata["month"] = month_num
                    metadata["issue_date"] = datetime(year, month_num, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 3b: Abbreviated month with year, no word boundaries (Jan2024 in middle of string)
        if not date_extracted:
            match = re.search(DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY, remaining_text, re.IGNORECASE)
            if match:
                month_str, year_str = match.group(1), match.group(2)
                month_num = parse_month(month_str)
                year = int(year_str)
                if month_num and MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                    metadata["year"] = year
                    metadata["month"] = month_num
                    metadata["issue_date"] = datetime(year, month_num, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 4: ISO month format (2024-01 or 2024.01)
        if not date_extracted:
            match = re.search(DATE_PATTERN_ISO_MONTH, remaining_text)
            if match:
                year, month = int(match.group(1)), int(match.group(2))
                if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12:
                    metadata["year"] = year
                    metadata["month"] = month
                    metadata["issue_date"] = datetime(year, month, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 5: Numeric month-year (01-2024 or 1/2024) - check BEFORE year-only
        if not date_extracted:
            match = re.search(DATE_PATTERN_MONTH_YEAR_NUMERIC, remaining_text)
            if match:
                month, year = int(match.group(1)), int(match.group(2))
                if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12:
                    metadata["year"] = year
                    metadata["month"] = month
                    metadata["issue_date"] = datetime(year, month, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Format 6: Just a year (2024) - LAST to avoid false matches
        if not date_extracted:
            match = re.search(DATE_PATTERN_YEAR_ONLY, remaining_text)
            if match:
                year = int(match.group(1))
                if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                    metadata["year"] = year
                    metadata["month"] = 1  # Default to January
                    metadata["issue_date"] = datetime(year, 1, 1)
                    remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                    date_extracted = True

        # Step 7: Extract volume and issue numbers (AFTER dates to avoid conflicts)
        # Volume patterns: Vol.12, Volume 5, V202
        match = re.search(NZB_VOLUME_PATTERN, remaining_text, re.IGNORECASE)
        if match:
            metadata["volume"] = int(match.group(1))
            remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
            remaining_text = re.sub(r"\s+", " ", remaining_text).strip()

        # Issue patterns: Issue 389, No. 25, N25, #45
        match = re.search(NZB_ISSUE_PATTERN, remaining_text, re.IGNORECASE)
        if match:
            issue_num = match.group(1) or match.group(2)
            metadata["issue"] = int(issue_num)
            remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
            remaining_text = re.sub(r"\s+", " ", remaining_text).strip()

        # Step 8: What remains is the title
        # Clean up remaining text before using as title
        remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
        remaining_text = re.sub(r"^[-\s]+|[-\s]+$", "", remaining_text).strip()  # Remove leading/trailing dashes
        remaining_text = re.sub(r"\s*-\s*$", "", remaining_text).strip()  # Remove trailing dash with spaces
        remaining_text = re.sub(r"--+", "-", remaining_text).strip()  # Collapse multiple dashes
        remaining_text = re.sub(
            TITLE_CLEANUP_TRAILING_DASH_DIGITS, "", remaining_text
        ).strip()  # Remove trailing dash+digits (e.g., "-01")
        remaining_text = re.sub(
            TITLE_CLEANUP_TRAILING_SPACE_DIGITS, "", remaining_text
        ).strip()  # Remove trailing space+digits (e.g., " 01")

        if remaining_text:
            metadata["title"] = clean_title(remaining_text)
        else:
            # Fallback to original if everything was extracted
            metadata["title"] = clean_title(original_title)

        # Step 9: Calculate confidence score
        metadata["confidence"] = self._calculate_confidence(metadata)

        logger.debug(f"Extracted NZB metadata from '{original_title}': {metadata}")
        return metadata

    def _calculate_confidence(self, metadata: Dict[str, Any]) -> str:
        """
        Calculate confidence level based on extracted metadata.

        Scoring:
        - Core components: title (2 pts), year (2 pts), month (2 pts)
        - Additional: volume/issue (1 pt), country (1 pt), quality (1 pt)

        Returns:
            "high" (6+ pts), "medium" (4-5 pts), or "low" (0-3 pts)
        """
        score = 0

        # Core components
        if metadata.get("title"):
            score += 2
        if metadata.get("year"):
            score += 2
        if metadata.get("month"):
            score += 2

        # Additional components
        if metadata.get("volume") or metadata.get("issue"):
            score += 1
        if metadata.get("country"):
            score += 1
        if metadata.get("quality"):
            score += 1

        if score >= 6:
            return "high"
        elif score >= 4:
            return "medium"
        else:
            return "low"

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

        # Fallback: Try enhanced NZB-style parsing for complex filenames
        logger.info(f"Standard patterns failed, trying NZB-style parsing: {filename}")
        nzb_result = self.extract_from_nzb_title(filename)

        # Only use NZB result if it has medium/high confidence
        if nzb_result.get("confidence") in ["medium", "high"]:
            logger.info(f"NZB parsing succeeded with {nzb_result['confidence']} confidence")
            # Convert NZB metadata format to standard metadata format
            if nzb_result.get("issue_date"):
                return nzb_result
            # If no issue_date but has year/month, construct it
            if nzb_result.get("year") and nzb_result.get("month"):
                nzb_result["issue_date"] = datetime(nzb_result["year"], nzb_result["month"], 1)
                return nzb_result

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

        IMPORTANT: Strips month names from title to prevent folders with embedded dates
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
        cleaned = clean_title(title)

        # Additional safety: Remove trailing month names from title
        # This catches cases where pattern matched too greedily or filename had redundant month
        for month_name in MONTH_TO_NUMBER.keys():
            # Use word boundary to avoid removing parts of words
            pattern_to_remove = rf"\b{re.escape(month_name)}\b\s*$"
            cleaned = re.sub(pattern_to_remove, "", cleaned, flags=re.IGNORECASE).strip()

        metadata["title"] = cleaned
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
        Also handles: "Title Month" (year defaults to current).

        IMPORTANT: Strips month names from title to prevent folders like "Hustler Us February"
        """
        # First try with year: "Title Month Year"
        pattern = r"(.+?)\s+([A-Za-z]+)\s+(\d{4})"
        match = re.search(pattern, filename)

        has_year = True
        if not match:
            # Try without year: "Title Month" (use current year)
            pattern = r"(.+?)\s+([A-Za-z]+)$"
            match = re.search(pattern, filename)
            has_year = False

        if not match:
            return None

        title = match.group(1).strip()
        month_str = match.group(2)
        year = int(match.group(3)) if has_year else datetime.now().year

        # Validate that this is actually a month name (not part of title)
        month_num, normalized_month = parse_multi_month(month_str)
        if not month_num:
            return None

        # Clean the title and strip any trailing month names that may have been captured
        cleaned = clean_title(title)

        # Additional safety: Remove trailing month names from title
        # This catches cases where pattern matched too greedily
        for month_name in MONTH_TO_NUMBER.keys():
            # Use word boundary to avoid removing parts of words
            pattern_to_remove = rf"\b{re.escape(month_name)}\b\s*$"
            cleaned = re.sub(pattern_to_remove, "", cleaned, flags=re.IGNORECASE).strip()

        metadata["title"] = cleaned
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
