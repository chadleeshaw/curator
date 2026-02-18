"""
Metadata extraction from PDF filenames and directory structure.
Handles various filename patterns and infers titles from parent directories.
"""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.constants.date import (
    MAX_VALID_YEAR,
    MIN_VALID_YEAR,
    MONTH_TO_NUMBER,
    NUMBER_TO_MONTH,
)
from core.constants.files import MAX_FILE_EXTENSION_LENGTH, YEAR_STRING_LENGTH
from core.constants.language import SUPPORTED_LANGUAGES
from core.constants.validation import ANTI_PERIODICAL_PATTERNS
from core.constants.patterns import (
    DATE_PATTERN_ABBR_MONTH_YEAR,
    DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY,
    DATE_PATTERN_FULL_MONTH_YEAR,
    DATE_PATTERN_ISO_FULL,
    DATE_PATTERN_ISO_MONTH,
    DATE_PATTERN_MONTH_YEAR_NUMERIC,
    DATE_PATTERN_MULTI_MONTH,
    DATE_PATTERN_MULTI_MONTH_NUMERIC,
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
    TITLE_PATTERN_DASH_MONTH_DOT_YEAR,
    TITLE_PATTERN_DASH_MONTH_YEAR,
    TITLE_PATTERN_DOT_SEPARATED,
    TITLE_PATTERN_ISO_DATE,
    TITLE_PATTERN_ISSUE_NUMBER,
    TITLE_PATTERN_YEAR_NUMERIC_MONTH,
    TITLE_PATTERN_ISSUE_ONLY,
    TITLE_SUFFIX_ISSUE_NUMBER,
    TITLE_PATTERN_LEADING_ISSUE,
    TITLE_PATTERN_SEASONAL,
    TITLE_PATTERN_SPACE_MONTH_ONLY,
    TITLE_PATTERN_SPACE_MONTH_YEAR,
    TITLE_PATTERN_TIMESTAMP_ID,
    TITLE_PATTERN_VOLUME_ISSUE,
    TITLE_PATTERN_VOLUME_ONLY,
)
from core.parsers.date import parse_month, parse_multi_month, parse_numeric_month_range
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

    def extract_from_nzb_title(self, nzb_title: str) -> Optional[Dict[str, Any]]:
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
            Returns None if title matches anti-periodical patterns (movies/TV/audiobooks)
        """
        original_title = nzb_title

        # EARLY CHECK: Reject non-periodical content (movies, TV shows, audiobooks) FIRST
        if self._has_anti_periodical_patterns(nzb_title):
            logger.debug(f"Rejecting '{nzb_title}': Contains anti-periodical patterns (likely movie/TV/audiobook)")
            return None

        # Preprocess: Remove file extension if present (but preserve years like "2021")
        nzb_title = self._preprocess_title(nzb_title)

        # Initialize metadata dictionary
        metadata = self._initialize_metadata()

        # Pre-check: Extract numeric multi-month and ISO dates BEFORE normalization
        # These patterns would be destroyed by dot-to-space conversion
        numeric_month_data = self._extract_numeric_multi_month(nzb_title)
        iso_date_data = self._extract_iso_date(nzb_title)
        month_issue_year_data = self._extract_month_issue_year(nzb_title)

        # Normalize delimiters: dots, underscores → spaces (but keep dashes)
        remaining_text = self._normalize_delimiters(nzb_title)

        # Remove pre-detected ISO date from remaining text
        if iso_date_data:
            pattern_to_remove = f"{iso_date_data['year']} {iso_date_data['month']:02d}"
            remaining_text = remaining_text.replace(pattern_to_remove, "", 1)
            remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
            logger.debug(f"Removed ISO date from remaining text, left with: '{remaining_text}'")

        # Extract release metadata (group, quality, country, language, edition)
        remaining_text = self._extract_release_metadata(nzb_title, remaining_text, metadata)

        # Extract dates from various formats
        remaining_text = self._extract_dates(
            remaining_text, metadata, numeric_month_data, iso_date_data, month_issue_year_data
        )

        # Extract volume and issue numbers (AFTER dates to avoid conflicts)
        remaining_text = self._extract_volume_issue(remaining_text, metadata)

        # What remains is the title - clean it up
        metadata["title"] = self._extract_title_from_remaining(remaining_text, original_title)

        # Calculate confidence score
        metadata["confidence"] = self._calculate_confidence(metadata)

        logger.debug(f"Extracted NZB metadata from '{original_title}': {metadata}")
        return metadata

    def _preprocess_title(self, nzb_title: str) -> str:
        """Remove file extension if present (but preserve years like '2021')."""
        if "." not in nzb_title:
            return nzb_title

        parts = nzb_title.rsplit(".", 1)
        last_part = parts[-1]
        # Check if it's a likely extension (≤4 chars), but NOT a year (4 digits between 1900-2100)
        is_extension = len(last_part) <= MAX_FILE_EXTENSION_LENGTH
        is_year = (
            last_part.isdigit()
            and len(last_part) == YEAR_STRING_LENGTH
            and MIN_VALID_YEAR <= int(last_part) <= MAX_VALID_YEAR
        )
        if is_extension and not is_year:
            return parts[0]
        return nzb_title

    def _initialize_metadata(self) -> Dict[str, Any]:
        """Initialize metadata dictionary with default values."""
        return {
            "title": None,
            "year": None,
            "month": None,
            "month_name": None,
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

    def _extract_numeric_multi_month(self, nzb_title: str) -> Optional[Dict[str, Any]]:
        """
        Extract numeric multi-month patterns BEFORE normalization.
        Handles cases like '11.10' which would be destroyed by dot-to-space conversion.
        """
        numeric_month_match = re.search(DATE_PATTERN_MULTI_MONTH_NUMERIC, nzb_title)
        if not numeric_month_match:
            return None

        title_part = numeric_month_match.group(1).strip()
        month1_str = numeric_month_match.group(2)
        month2_str = numeric_month_match.group(3)
        year_str = numeric_month_match.group(4)
        year = int(year_str)
        month_num, display_string = parse_numeric_month_range(month1_str, month2_str)

        if month_num and MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            logger.debug(f"Pre-detected numeric multi-month: {display_string} {year} from '{title_part}'")
            return {
                "month": month_num,
                "month_name": display_string,
                "year": year,
                "issue_date": datetime(year, month_num, 1, tzinfo=UTC),
                "title_part": title_part,
                "month1": month1_str,
                "month2": month2_str,
            }
        return None

    def _extract_iso_date(self, nzb_title: str) -> Optional[Dict[str, Any]]:
        """
        Extract ISO date formats from ORIGINAL text (before dot normalization destroys them).
        Handles '2023.09' which becomes '2023 09' after normalization.
        """
        iso_month_match = re.search(DATE_PATTERN_ISO_MONTH, nzb_title)
        if not iso_month_match:
            return None

        year, month = int(iso_month_match.group(1)), int(iso_month_match.group(2))
        if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12:
            logger.debug(f"Pre-detected ISO month: {NUMBER_TO_MONTH.get(month)} {year}")
            return {
                "year": year,
                "month": month,
                "month_name": NUMBER_TO_MONTH.get(month),
                "issue_date": datetime(year, month, 1, tzinfo=UTC),
                "match_text": iso_month_match.group(),
            }
        return None

    def _extract_month_issue_year(self, nzb_title: str) -> Optional[Dict[str, Any]]:
        """
        Extract Month.Issue.Year format from ORIGINAL text (before dot normalization).
        Handles formats like 'October.25.2013' which becomes 'October 25 2013' after normalization.
        """
        from core.parsers.date import parse_month

        # Pattern: MonthName.Number.Year
        pattern = r"\b([A-Za-z]+)\.?(\d{1,3})\.?(\d{4})\b"
        match = re.search(pattern, nzb_title, re.IGNORECASE)
        if not match:
            return None

        month_str = match.group(1)
        issue_num = int(match.group(2))
        year = int(match.group(3))
        month_num = parse_month(month_str)

        if month_num and MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= issue_num <= 999:
            logger.debug(f"Pre-detected Month.Issue.Year: {month_str} (Issue {issue_num}), {year}")
            return {
                "year": year,
                "month": month_num,
                "month_name": NUMBER_TO_MONTH.get(month_num),
                "issue": issue_num,
                "issue_date": datetime(year, month_num, 1, tzinfo=UTC),
                "match_text": match.group(),
            }
        return None

    def _normalize_delimiters(self, nzb_title: str) -> str:
        """Normalize delimiters: dots, underscores → spaces (but keep dashes)."""
        return nzb_title.replace(".", " ").replace("_", " ")

    def _extract_release_metadata(self, nzb_title: str, remaining_text: str, metadata: Dict[str, Any]) -> str:
        """Extract release group, quality, country, language, and edition from title."""
        # Extract release group (from end)
        for pattern in NZB_RELEASE_GROUP_PATTERNS:
            match = re.search(pattern, nzb_title, re.IGNORECASE)
            if match:
                metadata["release_group"] = match.group(1)
                end_pos = remaining_text.rfind(match.group(1))
                if end_pos != -1:
                    remaining_text = remaining_text[:end_pos].strip()
                break

        # Extract quality indicators (search in ORIGINAL before normalization)
        for pattern in NZB_QUALITY_PATTERNS:
            match = re.search(pattern, nzb_title, re.IGNORECASE)
            if match:
                quality_text = match.group(1).replace(".", " ")
                metadata["quality"] = quality_text
                quality_normalized = quality_text.lower().replace(" ", " ")
                for word in quality_normalized.split():
                    remaining_text = re.sub(
                        rf"\b{re.escape(word)}\b",
                        "",
                        remaining_text,
                        flags=re.IGNORECASE,
                    )
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Extract country/region
        for pattern in NZB_COUNTRY_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                country = match.group(1)
                metadata["country"] = "USA" if country.upper() in ["US", "USA"] else country.upper()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Extract language
        for pattern in NZB_LANGUAGE_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["language"] = match.group(1).capitalize()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        # Extract edition/variant
        for pattern in NZB_EDITION_PATTERNS:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["edition"] = match.group(1).capitalize()
                remaining_text = remaining_text[: match.start()] + remaining_text[match.end() :]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                break

        return remaining_text

    def _extract_dates(
        self,
        remaining_text: str,
        metadata: Dict[str, Any],
        numeric_month_data: Optional[Dict[str, Any]],
        iso_date_data: Optional[Dict[str, Any]],
        month_issue_year_data: Optional[Dict[str, Any]],
    ) -> str:
        """
        Extract dates from various formats.
        Tries multiple patterns in order of specificity.
        """
        # Format 0a: Use pre-detected numeric multi-month if found
        if numeric_month_data:
            remaining_text = self._apply_numeric_multi_month(remaining_text, metadata, numeric_month_data)
            return remaining_text

        # Format 0b: Use pre-detected Month.Issue.Year if found
        if month_issue_year_data:
            metadata["year"] = month_issue_year_data["year"]
            metadata["month"] = month_issue_year_data["month"]
            metadata["month_name"] = month_issue_year_data["month_name"]
            metadata["issue"] = month_issue_year_data["issue"]
            metadata["issue_date"] = month_issue_year_data["issue_date"]
            # Remove the matched text from remaining_text
            remaining_text = remaining_text.replace(month_issue_year_data["match_text"].replace(".", " "), "", 1)
            remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
            logger.debug(
                f"Used pre-detected Month.Issue.Year: {month_issue_year_data['month_name']} Issue {month_issue_year_data['issue']}, {month_issue_year_data['year']}"
            )
            return remaining_text

        # Format 1: Numeric multi-month in remaining text
        remaining_text, extracted = self._try_numeric_multi_month_pattern(remaining_text, metadata)
        if extracted:
            return remaining_text

        # Format 2: ISO full date (2024.01.20 or 2024-01-20)
        remaining_text, extracted = self._try_iso_full_date_pattern(remaining_text, metadata)
        if extracted:
            return remaining_text

        # Format 3-5: Month name/abbreviation with year patterns
        remaining_text, extracted = self._try_month_name_patterns(remaining_text, metadata)
        if extracted:
            return remaining_text

        # Format 6: ISO month format - use pre-detected if available
        if iso_date_data:
            self._apply_iso_date_data(metadata, iso_date_data)
            return remaining_text

        # Format 7: ISO month format in remaining text
        remaining_text, extracted = self._try_iso_month_pattern(remaining_text, metadata)
        if extracted:
            return remaining_text

        # Format 8: Numeric month-year (01-2024 or 1/2024)
        remaining_text, extracted = self._try_numeric_month_year_pattern(remaining_text, metadata)
        if extracted:
            return remaining_text

        # Format 9: Just a year (2024) - LAST to avoid false matches
        remaining_text, _ = self._try_year_only_pattern(remaining_text, metadata)
        return remaining_text

    def _apply_numeric_multi_month(
        self,
        remaining_text: str,
        metadata: Dict[str, Any],
        numeric_month_data: Dict[str, Any],
    ) -> str:
        """Apply pre-detected numeric multi-month data and remove from text."""
        metadata["year"] = numeric_month_data["year"]
        metadata["month"] = numeric_month_data["month"]
        metadata["month_name"] = numeric_month_data["month_name"]
        metadata["issue_date"] = numeric_month_data["issue_date"]

        m1 = numeric_month_data["month1"]
        m2 = numeric_month_data["month2"]
        year = str(numeric_month_data["year"])

        patterns_to_try = [
            rf"\b{m1}\s+{m2}\s+{year}\b",
            rf"\b{m1}/{m2}\s+{year}\b",
            rf"\b{m1}-{m2}\s+{year}\b",
        ]

        for pattern in patterns_to_try:
            new_text = re.sub(pattern, "", remaining_text, count=1)
            if new_text != remaining_text:
                remaining_text = new_text
                break

        remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
        logger.debug(f"Used pre-detected numeric multi-month: {numeric_month_data['month_name']} {year}")
        return remaining_text

    def _try_numeric_multi_month_pattern(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try to match numeric multi-month pattern in remaining text."""
        match = re.search(DATE_PATTERN_MULTI_MONTH_NUMERIC, remaining_text)
        if not match:
            return remaining_text, False

        title_part = match.group(1)
        month1_str = match.group(2)
        month2_str = match.group(3)
        year_str = match.group(4)
        year = int(year_str)
        month_num, display_string = parse_numeric_month_range(month1_str, month2_str)

        if not month_num or not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            return remaining_text, False

        metadata["year"] = year
        metadata["month"] = month_num
        metadata["month_name"] = display_string
        metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
        remaining_text = remaining_text[: match.start()] + title_part + remaining_text[match.end() :]
        remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
        logger.debug(f"Extracted numeric multi-month: {display_string} {year}")
        return remaining_text, True

    def _try_iso_full_date_pattern(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try to match ISO full date pattern (2024.01.20 or 2024-01-20)."""
        match = re.search(DATE_PATTERN_ISO_FULL, remaining_text)
        if not match:
            return remaining_text, False

        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

        if not (MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12 and 1 <= day <= 31):
            return remaining_text, False

        metadata["year"] = year
        metadata["month"] = month
        metadata["month_name"] = NUMBER_TO_MONTH.get(month)
        metadata["day"] = day
        metadata["issue_date"] = datetime(year, month, day, tzinfo=UTC)
        remaining_text = self._remove_match_and_cleanup(remaining_text, match)
        return remaining_text, True

    def _try_month_name_patterns(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try month name patterns in order: full, abbreviated, no boundaries."""
        patterns = [
            (DATE_PATTERN_FULL_MONTH_YEAR, "full month name"),
            (DATE_PATTERN_ABBR_MONTH_YEAR, "abbreviated month"),
            (
                DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY,
                "abbreviated month (no boundary)",
            ),
        ]

        for pattern, pattern_name in patterns:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if not match:
                continue

            month_str = match.group(1)
            year_str = match.group(2)
            month_num = parse_month(month_str)
            year = int(year_str)

            if not month_num or not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                continue

            metadata["year"] = year
            metadata["month"] = month_num
            metadata["month_name"] = NUMBER_TO_MONTH.get(month_num)
            metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
            remaining_text = self._remove_match_and_cleanup(remaining_text, match)
            return remaining_text, True

        return remaining_text, False

    def _apply_iso_date_data(self, metadata: Dict[str, Any], iso_date_data: Dict[str, Any]) -> None:
        """Apply pre-detected ISO date data to metadata."""
        metadata["year"] = iso_date_data["year"]
        metadata["month"] = iso_date_data["month"]
        metadata["month_name"] = iso_date_data["month_name"]
        metadata["issue_date"] = iso_date_data["issue_date"]
        logger.debug(f"Used pre-detected ISO date: {iso_date_data['month_name']} {iso_date_data['year']}")

    def _try_iso_month_pattern(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try to match ISO month format (2024-01 or 2024.01)."""
        match = re.search(DATE_PATTERN_ISO_MONTH, remaining_text)
        if not match:
            return remaining_text, False

        year = int(match.group(1))
        month = int(match.group(2))

        if not (MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12):
            return remaining_text, False

        metadata["year"] = year
        metadata["month"] = month
        metadata["month_name"] = NUMBER_TO_MONTH.get(month)
        metadata["issue_date"] = datetime(year, month, 1, tzinfo=UTC)
        remaining_text = self._remove_match_and_cleanup(remaining_text, match)
        return remaining_text, True

    def _try_numeric_month_year_pattern(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try to match numeric month-year (01-2024 or 1/2024)."""
        match = re.search(DATE_PATTERN_MONTH_YEAR_NUMERIC, remaining_text)
        if not match:
            return remaining_text, False

        month = int(match.group(1))
        year = int(match.group(2))

        if not (MIN_VALID_YEAR <= year <= MAX_VALID_YEAR and 1 <= month <= 12):
            return remaining_text, False

        metadata["year"] = year
        metadata["month"] = month
        metadata["month_name"] = NUMBER_TO_MONTH.get(month)
        metadata["issue_date"] = datetime(year, month, 1, tzinfo=UTC)
        remaining_text = self._remove_match_and_cleanup(remaining_text, match)
        return remaining_text, True

    def _try_year_only_pattern(self, remaining_text: str, metadata: Dict[str, Any]) -> tuple:
        """Try to match year-only pattern (2024) - LAST to avoid false matches."""
        match = re.search(DATE_PATTERN_YEAR_ONLY, remaining_text)
        if not match:
            return remaining_text, False

        year = int(match.group(1))
        if not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            return remaining_text, False

        metadata["year"] = year
        metadata["month"] = 1  # Default to January
        metadata["issue_date"] = datetime(year, 1, 1, tzinfo=UTC)
        remaining_text = self._remove_match_and_cleanup(remaining_text, match)
        return remaining_text, True

    def _remove_match_and_cleanup(self, text: str, match) -> str:
        """Remove matched pattern from text and cleanup whitespace."""
        text = text[: match.start()] + text[match.end() :]
        return re.sub(r"\s+", " ", text).strip()

    def _extract_volume_issue(self, remaining_text: str, metadata: Dict[str, Any]) -> str:
        """Extract volume and issue numbers from remaining text."""
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

        # If no issue found yet, check for bare trailing numbers (likely issue numbers)
        # This handles cases like "Magazine 13 December 2023" where 13 is the issue number
        # Only do this if we successfully extracted a month (to avoid false positives)
        if metadata.get("issue") is None and metadata.get("month") is not None:
            match = re.search(r"\b(\d{1,3})\s*$", remaining_text)
            if match:
                metadata["issue"] = int(match.group(1))
                remaining_text = remaining_text[: match.start()]
                remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
                logger.debug(f"Extracted bare trailing issue number: {metadata['issue']}")

        return remaining_text

    def _extract_title_from_remaining(self, remaining_text: str, original_title: str) -> str:
        """Clean up remaining text and extract title."""
        # Clean up remaining text
        remaining_text = re.sub(r"\s+", " ", remaining_text).strip()
        remaining_text = re.sub(r"^[-\s]+|[-\s]+$", "", remaining_text).strip()  # Remove leading/trailing dashes
        remaining_text = re.sub(r"\s*-\s*$", "", remaining_text).strip()  # Remove trailing dash with spaces
        remaining_text = re.sub(r"--+", "-", remaining_text).strip()  # Collapse multiple dashes
        remaining_text = re.sub(
            TITLE_CLEANUP_TRAILING_DASH_DIGITS, "", remaining_text
        ).strip()  # Remove trailing dash+digits
        remaining_text = re.sub(
            TITLE_CLEANUP_TRAILING_SPACE_DIGITS, "", remaining_text
        ).strip()  # Remove trailing space+digits

        if remaining_text:
            return clean_title(remaining_text)
        # Fallback to original if everything was extracted
        return clean_title(original_title)

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
        # Strip leading and trailing quotes from filename (for files like 'Magazine.pdf')
        filename = pdf_path.stem.strip("'")

        # Strip old "Unknown" placeholder that was used when date/volume/issue was missing
        # This handles existing files like "Title - Unknown.pdf"
        filename = re.sub(r"\s*-\s*Unknown\s*$", "", filename, flags=re.IGNORECASE)

        magazine_name = self.get_title_from_path(pdf_path)

        # Default metadata
        metadata: Dict[str, Any] = {
            "title": filename,
            "issue_date": datetime.now(),
        }

        # Detect NZB-style filenames (multiple dots, typical format: "Title.Country.-.Month.Year")
        # Try NZB parser first for these complex filenames as it's more robust
        is_nzb_style = filename.count(".") >= 2 or ("-" in filename and "." in filename)
        if is_nzb_style:
            logger.debug(f"Detected NZB-style filename, trying NZB parser first: {filename}")
            nzb_result = self.extract_from_nzb_title(filename)
            # Check if result is None (rejected as non-periodical)
            if nzb_result is None:
                logger.debug(f"NZB parser rejected '{filename}' as non-periodical content")
                # Don't return None here - fall through to try standard patterns
                # (in case the anti-pattern check was a false positive)
            # Use NZB result if it has medium/high confidence
            elif nzb_result.get("confidence") in ["medium", "high"]:
                logger.debug(f"NZB parsing succeeded with {nzb_result['confidence']} confidence")
                # Convert NZB metadata format to standard metadata format
                nzb_result["pattern"] = "nzb_style"
                if nzb_result.get("issue_date"):
                    return nzb_result
                # If no issue_date but has year/month, construct it
                if nzb_result.get("year") and nzb_result.get("month"):
                    nzb_result["issue_date"] = datetime(nzb_result["year"], nzb_result["month"], 1, tzinfo=UTC)
                    return nzb_result
            else:
                logger.debug("NZB parsing failed or low confidence, falling back to standard patterns")

        # Try each pattern in order of specificity
        # First try patterns that include dates (preferred)
        # Then try volume/issue patterns without dates (will trigger needs_date_scan)
        result = (
            self._try_multi_month_pattern(filename, metadata)
            or self._try_dash_month_year_pattern(filename, metadata)
            or self._try_dot_separated_pattern(filename, metadata)
            or self._try_space_month_year_pattern(filename, metadata)
            or self._try_iso_date_pattern(filename, metadata)
            or self._try_issue_number_pattern(filename, metadata)
            or self._try_volume_issue_pattern(filename, metadata)
            or self._try_seasonal_pattern(filename, metadata)
            or self._try_timestamp_id_pattern(filename, metadata)
            or self._try_date_only_pattern(filename, metadata, magazine_name)
            or self._try_year_numeric_month_pattern(filename, metadata)
            or self._try_year_only_filename_pattern(filename, metadata, magazine_name)
            # Patterns without dates - volume/issue only (will need date scan)
            or self._try_leading_issue_pattern(filename, metadata)
            or self._try_volume_only_pattern(filename, metadata)
            or self._try_issue_only_pattern(filename, metadata)
        )

        if result:
            return result

        # Final fallback: Try enhanced NZB-style parsing for other complex filenames
        logger.info(f"Standard patterns failed, trying NZB-style parsing: {filename}")
        nzb_result = self.extract_from_nzb_title(filename)

        # Check if result is None (rejected as non-periodical)
        if nzb_result is None:
            logger.info(f"NZB parser rejected '{filename}' as non-periodical content, using fallback metadata")
            return metadata

        # Only use NZB result if it has medium/high confidence
        if nzb_result.get("confidence") in ["medium", "high"]:
            logger.info(f"NZB parsing succeeded with {nzb_result['confidence']} confidence")
            # Convert NZB metadata format to standard metadata format
            nzb_result["pattern"] = "nzb_style_fallback"
            if nzb_result.get("issue_date"):
                return nzb_result
            # If no issue_date but has year/month, construct it
            if nzb_result.get("year") and nzb_result.get("month"):
                nzb_result["issue_date"] = datetime(nzb_result["year"], nzb_result["month"], 1, tzinfo=UTC)
                return nzb_result

        logger.info(f"No date pattern matched in filename: {filename}, using current date")
        metadata["pattern"] = "no_match_fallback"
        return metadata

    def _try_multi_month_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: Multi-month periods like "Title - June/July 2024" or "Title Jun/Jul2024"
        or numeric formats like "Title 11.10 2019" (meaning Oct/Nov 2019).
        """
        # Try alphabetic multi-month first: "Title - Jun/Jul2024", "Title June/July 2024"
        match = re.search(DATE_PATTERN_MULTI_MONTH, filename)

        if match:
            title = match.group(1).strip()
            month1_str = match.group(2)
            month2_str = match.group(3)
            year_str = match.group(4)

            month1_num = parse_month(month1_str)
            if not month1_num:
                return None

            year = int(year_str)
            metadata["title"] = clean_title(title)
            metadata["issue_date"] = datetime(year, month1_num, 1, tzinfo=UTC)
            metadata["year"] = year
            metadata["month_name"] = f"{month1_str.capitalize()}/{month2_str.capitalize()}"
            metadata["pattern"] = "multi_month"

            logger.info(f"Extracted multi-month: {metadata['month_name']} {year}")
            return metadata

        # Try numeric multi-month: "Title 11.10 2019", "Title 05/06 2023"
        match = re.search(DATE_PATTERN_MULTI_MONTH_NUMERIC, filename)

        if match:
            title = match.group(1).strip()
            month1_str = match.group(2)
            month2_str = match.group(3)
            year_str = match.group(4)

            month_num, display_string = parse_numeric_month_range(month1_str, month2_str)
            if not month_num:
                return None

            year = int(year_str)
            metadata["title"] = clean_title(title)
            metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
            metadata["year"] = year
            metadata["month_name"] = display_string
            metadata["pattern"] = "multi_month_numeric"

            logger.info(f"Extracted numeric multi-month: {metadata['month_name']} {year}")
            return metadata

        return None

    def _try_dash_month_year_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title - MonYear" (e.g., "National Geographic - Dec2024").
        Also handles: "Title-Month.Year" (e.g., "Esquire.Africa-August.2023").

        IMPORTANT: Strips month names from title to prevent folders with embedded dates
        """
        # Try with year directly after month (no separator)
        match = re.search(TITLE_PATTERN_DASH_MONTH_YEAR, filename)

        # Also try with dot or space before year
        if not match:
            match = re.search(TITLE_PATTERN_DASH_MONTH_DOT_YEAR, filename)

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
        metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        metadata["pattern"] = "dash_month_year"
        return metadata

    def _try_dot_separated_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title.Month.Year" (e.g., "Wired.January.2024").
        """
        match = re.search(TITLE_PATTERN_DOT_SEPARATED, filename, re.IGNORECASE)

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
        metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        metadata["pattern"] = "dot_separated"
        logger.info(f"Extracted '{metadata['title']}' {month_str} {year_str} from dot-separated filename")
        return metadata

    def _try_space_month_year_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Month Year" (e.g., "Wired January 2024").
        Also handles: "Title Month" (year defaults to current).

        IMPORTANT: Strips month names from title to prevent folders like "Esquire Us February"
        """
        # First try with year: "Title Month Year"
        match = re.search(TITLE_PATTERN_SPACE_MONTH_YEAR, filename)

        has_year = True
        if not match:
            # Try without year: "Title Month" (use current year)
            match = re.search(TITLE_PATTERN_SPACE_MONTH_ONLY, filename)
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
        metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = normalized_month
        metadata["pattern"] = "space_month_year"
        return metadata

    def _try_iso_date_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title YYYY-MM" (e.g., "PC Gamer 2024-12").
        """
        match = re.search(TITLE_PATTERN_ISO_DATE, filename)

        if not match:
            return None

        title = match.group(1).strip()
        year_str = match.group(2)
        month_str = match.group(3)

        try:
            year = int(year_str)
            month_num = int(month_str)
            metadata["title"] = clean_title(title)
            metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
            metadata["year"] = year
            metadata["month_name"] = NUMBER_TO_MONTH.get(month_num, "")
            metadata["pattern"] = "iso_date"
            return metadata
        except ValueError:
            logger.warning(f"Invalid ISO date in filename: {filename}")
            return None

    def _try_issue_number_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title No.XXX YYYY" (e.g., "PC Gamer No.405 2024").
        """
        match = re.search(TITLE_PATTERN_ISSUE_NUMBER, filename, re.IGNORECASE)

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
        metadata["issue_date"] = datetime(year, 1, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = "January"
        metadata["edition_number"] = int(issue_num)
        metadata["is_special_edition"] = "special" in filename.lower() and "edition" in filename.lower()
        metadata["pattern"] = "issue_number"

        logger.debug("Pattern match - Issue number format")
        return metadata

    def _try_volume_issue_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Vol.XX No.YY YYYY" (e.g., "2600.Magazine.Vol.41.No.1.2024").
        """
        match = re.search(TITLE_PATTERN_VOLUME_ISSUE, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1)
        volume_num = match.group(2)
        issue_num = match.group(3)
        year_str = match.group(4)

        year = int(year_str)
        metadata["title"] = clean_title(title_part)
        metadata["issue_date"] = datetime(year, 1, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = "January"
        metadata["volume"] = int(volume_num)
        metadata["edition_number"] = int(issue_num)
        metadata["is_special_edition"] = False
        metadata["pattern"] = "volume_issue"

        logger.debug("Pattern match - Volume and issue number format")
        return metadata

    def _try_seasonal_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Season YYYY" (e.g., "2600 Winter 2024").
        """
        match = re.search(TITLE_PATTERN_SEASONAL, filename, re.IGNORECASE)

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
        metadata["issue_date"] = datetime(year, month, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = season.capitalize()
        metadata["is_special_edition"] = False
        metadata["pattern"] = "seasonal"

        logger.debug("Pattern match - Seasonal format")
        return metadata

    def _try_volume_only_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title Vol.XXX" without year (e.g., "Magazine Vol.260").

        For magazines that use volume numbering without dates.
        Returns metadata with volume but NO issue_date (caller should handle missing date).
        """
        match = re.search(TITLE_PATTERN_VOLUME_ONLY, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1).strip()
        volume_num = match.group(2)
        suffix = match.group(3) or ""

        # Clean up title - remove leading numbers if they match the volume
        title_clean = re.sub(r"^\d+\s*-\s*", "", title_part)
        title_clean = clean_title(title_clean)

        # Check if suffix is an issue number (e.g., "No304", "No.304", "Issue 5", "#42")
        issue_match = re.match(TITLE_SUFFIX_ISSUE_NUMBER, suffix, re.IGNORECASE) if suffix else None
        if issue_match:
            # Store as edition_number metadata, don't append to title
            metadata["edition_number"] = int(issue_match.group(1))
            logger.debug(f"Extracted issue number {metadata['edition_number']} from suffix '{suffix}'")
        elif suffix and not re.match(r"^[A-Z][a-z]+\s+[A-Z]", suffix):  # Skip "Bridgette B" style
            # Build suffix into title if it's meaningful (not just a name/descriptor)
            title_clean = f"{title_clean} {clean_title(suffix)}"

        metadata["title"] = title_clean
        metadata["volume"] = int(volume_num)
        metadata["issue_date"] = None  # No date - should trigger needs_date_scan
        metadata["pattern"] = "volume_only"

        logger.debug(f"Pattern match - Volume only format: {title_clean} Vol.{volume_num} (no date)")
        return metadata

    def _try_issue_only_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title No.XXX" or "Title Issue XXX" without year.

        For magazines that use issue numbering without dates.
        Returns metadata with issue number but NO issue_date (caller should handle missing date).
        """
        match = re.search(TITLE_PATTERN_ISSUE_ONLY, filename, re.IGNORECASE)

        if not match:
            return None

        title_part = match.group(1).strip()
        issue_num = match.group(2)
        suffix = match.group(3) or ""

        # Clean up title
        title_clean = clean_title(title_part)

        metadata["title"] = title_clean
        metadata["edition_number"] = int(issue_num)
        metadata["issue_date"] = None  # No date - should trigger needs_date_scan
        metadata["pattern"] = "issue_only"

        logger.debug(f"Pattern match - Issue only format: {title_clean} #{issue_num} (no date)")
        return metadata

    def _try_leading_issue_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "XXX - Title - Vol.XXX - Suffix" (leading issue number).

        For files like "260 - Magazine - Vol.260 - Cover Model".
        Returns metadata with volume/issue but NO issue_date (caller should handle missing date).
        """
        match = re.search(TITLE_PATTERN_LEADING_ISSUE, filename, re.IGNORECASE)

        if not match:
            return None

        issue_num = match.group(1)
        title_part = match.group(2).strip()
        volume_str = match.group(3)  # Now captured directly from pattern
        suffix = match.group(4) or ""

        # Extract volume number if present
        volume_num = int(volume_str) if volume_str else None

        title_clean = clean_title(title_part.strip())

        metadata["title"] = title_clean
        metadata["edition_number"] = int(issue_num)
        if volume_num:
            metadata["volume"] = volume_num
        metadata["issue_date"] = None  # No date - should trigger needs_date_scan
        metadata["pattern"] = "leading_issue"

        logger.debug(
            f"Pattern match - Leading issue format: #{issue_num} {title_clean}"
            f"{f' Vol.{volume_num}' if volume_num else ''} (no date)"
        )
        return metadata

    def _try_timestamp_id_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title (YYYYMMDD_HHMMSS)" - download client timestamp identifiers.

        Handles filenames like "Magazine (20260205_235420)" where the parenthesized
        portion is a unique download timestamp, not editorial metadata.
        Extracts the title and full date (year + month) from the timestamp.
        """
        match = re.search(TITLE_PATTERN_TIMESTAMP_ID, filename)
        if not match:
            return None

        title = match.group(1).strip()
        year_str = match.group(2)
        month_str = match.group(3)

        year = int(year_str)
        month = int(month_str)

        if not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            return None
        if not 1 <= month <= 12:
            return None

        metadata["title"] = clean_title(title)
        metadata["issue_date"] = datetime(year, month, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = NUMBER_TO_MONTH.get(month, "")
        metadata["pattern"] = "timestamp_id"

        logger.info(
            f"Extracted title '{metadata['title']}' and low-confidence date {year}-{month:02d} "
            f"from import timestamp filename: {filename}"
        )
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
        metadata["issue_date"] = datetime(year, month_num, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = month_str.capitalize()
        metadata["pattern"] = "date_only"

        if magazine_name:
            metadata["title"] = magazine_name
            logger.info(f"Extracted title '{magazine_name}' from directory for date-only filename: {filename}")
        else:
            metadata["title"] = filename
            logger.warning(f"Filename is date-only ({filename}) but no suitable magazine folder found")

        return metadata

    def _try_year_numeric_month_pattern(self, filename: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pattern: "Title YYYY MM" (e.g., "Magazine 2017 12").

        Handles filenames where a 4-digit year is followed by a space and a 1-2 digit
        numeric month. Must appear at the end of the filename.
        """
        match = re.search(TITLE_PATTERN_YEAR_NUMERIC_MONTH, filename)
        if not match:
            return None

        title = match.group(1).strip()
        year_str = match.group(2)
        month_str = match.group(3)

        year = int(year_str)
        month = int(month_str)

        # Validate year and month
        if not MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
            return None
        if not 1 <= month <= 12:
            return None

        title_clean = clean_title(title)
        if not title_clean or len(title_clean) < 2:
            return None

        metadata["title"] = title_clean
        metadata["issue_date"] = datetime(year, month, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["month_name"] = NUMBER_TO_MONTH.get(month, "")
        metadata["pattern"] = "year_numeric_month"

        logger.info(f"Extracted title '{metadata['title']}' and date {year}-{month:02d} " f"from filename: {filename}")
        return metadata

    def _try_year_only_filename_pattern(
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

        metadata["issue_date"] = datetime(year, 1, 1, tzinfo=UTC)
        metadata["year"] = year
        metadata["pattern"] = "year_only"

        # Try to extract title from text before the year in the filename
        text_before_year = filename[: match.start(1)].strip()
        # Clean separators from end of title portion
        text_before_year = re.sub(r"[\s\-_\.]+$", "", text_before_year).strip()

        if text_before_year and len(text_before_year) >= 2:
            metadata["title"] = clean_title(text_before_year)
            logger.info(f"Extracted title '{metadata['title']}' and year {year_str} from filename: {filename}")
        elif magazine_name:
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
            if folder_name.isdigit() and len(folder_name) == YEAR_STRING_LENGTH:
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

    def _has_anti_periodical_patterns(self, title: str) -> bool:
        """
        Check if title contains anti-patterns indicating non-periodical content.

        Anti-patterns include:
        - Video quality/resolution: 1080p, 4k, BluRay, WEB-DL, etc.
        - Video codecs: x264, x265, HEVC, XviD, etc.
        - Audio codecs: AAC, DTS, DD5.1, etc.
        - TV show indicators: S01E01, Season 1, Episode 2, etc.
        - Movie/film keywords
        - Audiobook indicators
        - Release group tags common in video releases

        This check is performed EARLY to quickly reject obvious non-periodical content
        (movies, TV shows, audiobooks) before doing expensive parsing.

        Args:
            title: Title string to check

        Returns:
            True if anti-patterns found (NOT a periodical), False otherwise
        """
        # Normalize dots, underscores, and dashes to spaces for better pattern matching
        # This catches patterns in NZB-style titles like "Movie.Name.2024.1080p.BluRay.x264"
        normalized_title = title.replace(".", " ").replace("_", " ").replace("-", " ")
        title_lower = normalized_title.lower()

        for pattern in ANTI_PERIODICAL_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                logger.debug(f"Found anti-periodical pattern in '{title}': matches '{pattern}'")
                return True

        return False
