"""
Core file organization utilities.

Contains the main FileOrganizer class for moving and renaming PDFs.
Handles both simple and pattern-based organization with metadata extraction.
"""

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.constants.country import ISO_COUNTRIES
from core.constants.files import (
    VOLUME_PREFIX,
    ISSUE_PREFIX,
    ORGANIZED_FILENAME_SEPARATOR,
)
from core.constants.language import DEFAULT_LANGUAGE
from core.constants.title import MAX_COUNTRY_REMOVAL_PASSES
from core.parsers import sanitize_filename, detect_country
from services.importer.matcher import TrackingMatcher
from services.cover_extractor import CoverExtractor

from .cleanup import CleanupMixin
from .reorganization import ReorganizationMixin

logger = logging.getLogger(__name__)


class FileOrganizer(ReorganizationMixin, CleanupMixin):
    """Organize and rename files with metadata extraction and cover art handling"""

    # Pattern: {Title} - {MonYear} (e.g., "Wired Periodical - Dec2006")
    ORGANIZED_PATTERN = "{title} - {month}{year}"

    # Organization pattern registry
    ORGANIZATION_PATTERNS = {
        # Default: Simple year-based structure
        "default": {
            "description": "Simple category > title > year structure",
            "template": "{category}/{title}/{year}/",
            "requires_date": True,
        },
        # Volume-based: For periodicals with volume numbers but no dates
        "volume": {
            "description": "Category > title > volume structure (for series with volume numbers)",
            "template": "{category}/{title}/Vol{volume}/",
            "requires_date": False,
        },
        # Flat: All issues in title folder
        "flat": {
            "description": "Flat structure without subdirectories",
            "template": "{category}/{title}/",
            "requires_date": False,
        },
        # Volume-Year: Hybrid structure
        "volume_year": {
            "description": "Category > title > volume > year (best for academic journals)",
            "template": "{category}/{title}/Vol{volume}/{year}/",
            "requires_date": True,
        },
        # Issue-based: For numbered series without dates
        "issue": {
            "description": "Category > title > issue range (for numbered series)",
            "template": "{category}/{title}/Issues {issue_range}/",
            "requires_date": False,
        },
    }

    def __init__(self, library_dir: str, category_prefix: str = "_"):
        """
        Initialize file organizer.

        Args:
            library_dir: Base directory for library files (where organized files are stored)
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
        """
        self.library_dir = Path(library_dir)
        self.category_prefix = category_prefix
        self.library_dir.mkdir(parents=True, exist_ok=True)

    def _count_countries_in_title(self, title: str) -> int:
        """
        Count how many countries are mentioned in a title.

        This helps detect invalid titles like "Magazine US Germany" that have
        multiple country identifiers.

        Args:
            title: Magazine/periodical title to check

        Returns:
            Number of distinct countries found in the title
        """
        countries_found = set()

        # Check for each country code and name in the title
        for code, name in ISO_COUNTRIES.items():
            # Check for 2-letter code with word boundaries
            if re.search(rf"\b{re.escape(code)}\b", title, re.IGNORECASE):
                countries_found.add(code)
            # Check for full country name with word boundaries
            elif re.search(rf"\b{re.escape(name)}\b", title, re.IGNORECASE):
                countries_found.add(code)
            # Check for 3-letter codes like USA, GBR
            elif re.search(rf"\b{re.escape(code)}A\b", title, re.IGNORECASE):
                countries_found.add(code)

        return len(countries_found)

    def _strip_country_from_title(self, title: str) -> str:
        """
        Remove country codes and names from the end of a title.

        This cleans up titles like "Magazine USA", "Periodical United States",
        "Publication Australia" to just the base magazine name.

        Args:
            title: Magazine/periodical title to clean

        Returns:
            Title with country information removed
        """
        cleaned_title = title.strip()

        # Remove country codes and names from the end of the title
        # Multiple passes handle malformed titles with redundant country info
        for _ in range(MAX_COUNTRY_REMOVAL_PASSES):
            original = cleaned_title

            # Remove 2-letter country codes at end (e.g., "Magazine US")
            for code in ISO_COUNTRIES.keys():
                pattern = rf"\s+{re.escape(code)}$"
                cleaned_title = re.sub(pattern, "", cleaned_title, flags=re.IGNORECASE)

            # Remove 3-letter codes at end (e.g., "Magazine USA")
            for code in ISO_COUNTRIES.keys():
                pattern = rf"\s+{re.escape(code)}A$"
                cleaned_title = re.sub(pattern, "", cleaned_title, flags=re.IGNORECASE)

            # Remove full country names at end (e.g., "Magazine United States")
            for name in ISO_COUNTRIES.values():
                pattern = rf"\s+{re.escape(name)}$"
                cleaned_title = re.sub(pattern, "", cleaned_title, flags=re.IGNORECASE)

            # If nothing changed, we're done
            if cleaned_title == original:
                break

        return cleaned_title.strip()

    def _title_has_country_info(self, title: str, country_code: str) -> bool:
        """
        Check if title already contains country information for the specified country.

        Uses the detect_country() parser to intelligently detect country codes, names,
        and common abbreviations (USA, UK, etc.) in the title.

        Args:
            title: Magazine/periodical title to check
            country_code: 2-letter ISO country code (e.g., "US", "UK", "ZA")

        Returns:
            True if title already contains country information for this country
        """
        detected_country = detect_country(title)
        return detected_country == country_code

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

        month = issue_date.strftime("%B")
        year = issue_date.strftime("%Y")

        safe_title = sanitize_filename(title)
        filename_base = f"{safe_title}{ORGANIZED_FILENAME_SEPARATOR}{month}{year}"

        # Preserve file extension (PDF, EPUB, CBZ, or CBR)
        extension = source.suffix.lower()
        file_path = self.library_dir / f"{filename_base}{extension}"
        jpg_path = self.library_dir / f"{filename_base}.jpg"

        if extension in [".pdf", ".epub", ".cbz", ".cbr"]:
            try:
                source.rename(file_path)
                logger.info(f"Moved to library: {file_path}")
            except (OSError, PermissionError) as e:
                logger.error(f"Error moving file: {e}", exc_info=True)
                file_path = None
        else:
            logger.warning(f"Unsupported file type: {source} (extension: {extension})")
            file_path = None

        if cover_path and Path(cover_path).exists():
            try:
                Path(cover_path).rename(jpg_path)
                logger.info(f"Moved cover to library: {jpg_path}")
            except (OSError, PermissionError) as e:
                logger.error(f"Error moving cover: {e}", exc_info=True)
                jpg_path = None

        return str(file_path), str(jpg_path)

    def _build_filename(  # pylint: disable=too-many-positional-arguments
        self,
        safe_title: str,
        volume: Optional[int],
        issue_number: Optional[int],
        month: Optional[str],
        year: Optional[str],
        extension: str = ".pdf",
    ) -> str:
        """
        Build organized filename with optional volume and issue information.

        Supports files with volume/issue but no date information.

        Args:
            safe_title: Sanitized title
            volume: Volume number (optional)
            issue_number: Issue number (optional)
            month: Month abbreviation (e.g., "Dec") - optional if volume/issue present
            year: Year (e.g., "2006") - optional if volume/issue present
            extension: File extension (default: ".pdf")

        Returns:
            Filename with specified extension
        """
        filename_parts = [safe_title]

        # Add volume if present (e.g., "Vol1")
        if volume:
            filename_parts.append(f"{VOLUME_PREFIX}{volume}")

        # Add issue number if present (e.g., "No123")
        if issue_number:
            filename_parts.append(f"{ISSUE_PREFIX}{issue_number}")

        # Add date if both month and year are present (e.g., "Dec2024")
        if month and year:
            filename_parts.append(f"{month}{year}")
        elif volume or issue_number:
            # If we have volume/issue but no date, that's okay
            pass
        else:
            # No volume, issue, or date - use "Unknown" as fallback
            filename_parts.append("Unknown")
            logger.warning(f"No date, volume, or issue number for {safe_title} - using 'Unknown'")

        return f"{ORGANIZED_FILENAME_SEPARATOR.join(filename_parts)}{extension}"

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

        return self.library_dir / Path(*path_parts)

    def _resolve_path(self, path_str: str) -> Path:
        """
        Resolve relative or absolute path.

        Args:
            path_str: Path string (may start with / for absolute)

        Returns:
            Resolved Path object
        """
        if not path_str.startswith("/"):
            return self.library_dir / path_str
        return Path(path_str)

    def _build_pattern_directory(  # pylint: disable=too-many-positional-arguments
        self,
        pattern: str,
        category_with_prefix: str,
        safe_title: str,
        language: str,
        year: Optional[str],
        month: Optional[str],
        day: Optional[str],
        issue_number: Optional[int],
        volume: Optional[int],
    ) -> Path:
        """
        Build directory from pattern with tag substitution.

        Supports optional date fields - uses "Unknown" for missing year/month/day
        when they appear in the pattern.

        Args:
            pattern: Pattern string with {tags}
            category_with_prefix: Category name with prefix
            safe_title: Sanitized title
            language: Language
            year: Year (optional)
            month: Month abbreviation (optional)
            day: Day (optional)
            issue_number: Issue number (optional)
            volume: Volume number (optional)

        Returns:
            Target directory path
        """
        format_dict = {
            "category": category_with_prefix,
            "title": safe_title,
            "language": language,
            "year": year or "Unknown",
            "month": month or "Unknown",
            "day": day or "Unknown",
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
            if len(name_parts) == 2:
                filename = f"{name_parts[0]} ({timestamp}).{name_parts[1]}"
            else:
                filename = f"{filename} ({timestamp})"
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
        Automatically selects appropriate pattern when date information is missing.

        Available pattern tags:
          {category}, {title}, {year}, {month}, {day}, {language}
          {issue} - Issue number (if available)
          {volume} - Volume number (if available)

        Args:
            pdf_path: Original PDF path
            metadata: Extracted metadata
            category: Category name
            pattern: Organization pattern with tags (optional, auto-selected if not provided)

        Returns:
            Path to organized file, or None if failed
        """
        try:
            # Extract metadata
            title = metadata.get("title", pdf_path.stem)
            issue_date = metadata.get("issue_date")
            language = metadata.get("language", DEFAULT_LANGUAGE)
            issue_number = metadata.get("issue_number")
            volume = metadata.get("volume")

            # Determine if we have reliable date information
            has_date = issue_date is not None and metadata.get("year") is not None

            # Format date components (use None if no reliable date)
            safe_title = sanitize_filename(title)
            if has_date:
                month = issue_date.strftime("%B")
                year = issue_date.strftime("%Y")
                day = issue_date.strftime("%d")
            else:
                # No reliable date - check if we have volume/issue to use instead
                month = None
                year = None
                day = None
                if volume or issue_number:
                    logger.info(
                        f"No date found for '{title}', using volume/issue-based organization "
                        f"(Vol:{volume}, Issue:{issue_number})"
                    )
                else:
                    logger.warning(
                        f"No date, volume, or issue number found for '{title}' - "
                        f"file will be stored with 'Unknown' identifier"
                    )

            # Preserve file extension (PDF, EPUB, CBZ, or CBR)
            extension = pdf_path.suffix.lower()

            # Build filename with preserved extension
            filename = self._build_filename(safe_title, volume, issue_number, month, year, extension)

            # Apply category prefix
            category_with_prefix = f"{self.category_prefix}{category}"

            # Auto-select pattern if not provided
            if not pattern:
                if not has_date and volume:
                    pattern = "{category}/{title}/Vol{volume}/"
                    logger.info(f"Auto-selected volume-based organization pattern for '{title}'")
                elif not has_date and issue_number:
                    pattern = "{category}/{title}/"
                    logger.info(f"Auto-selected flat organization pattern for '{title}'")
                elif not has_date:
                    pattern = "{category}/{title}/"
                    logger.warning(f"Using flat organization pattern for '{title}' (no metadata)")

            # Build target directory
            if not pattern:
                target_dir = self._build_default_directory(category_with_prefix, safe_title, volume, year or "Unknown")
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
            logger.info(f"Moved to library: {target_path}")
            return target_path

        except Exception as e:
            logger.error(f"Error moving file to library {pdf_path}: {e}", exc_info=True)
            return None

    def extract_cover_from_pdf(self, pdf_path: str, output_path: str) -> bool:
        """
        Extract cover from periodical file (PDF, EPUB, CBZ, or CBR).

        DEPRECATED: Use CoverExtractor.extract_cover() instead.
        This method is maintained for backward compatibility.

        Args:
            pdf_path: Path to periodical file
            output_path: Where to save the cover JPG

        Returns:
            True if successful, False otherwise
        """
        return CoverExtractor.extract_cover(pdf_path, output_path)

    def auto_fix_tracking_ids(
        self,
        db_session: Any,
        category: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Auto-fix incorrect or missing tracking_id values using fuzzy title matching.

        This helps merge folders that should belong to the same tracking record
        but have incorrect or missing tracking links.

        Args:
            db_session: Database session
            category: Category to fix (None = all categories)
            dry_run: If True, only report what would be fixed

        Returns:
            Dictionary with fix results
        """
        from models.database import Periodical, PeriodicalTracking

        matcher = TrackingMatcher(min_score=70)

        # Get all tracking records for matching
        tracking_records = db_session.query(PeriodicalTracking).all()

        if not tracking_records:
            return {
                "success": True,
                "fixed": 0,
                "skipped": 0,
                "errors": [],
                "message": "No tracking records found",
            }

        # Query periodicals to check
        query = db_session.query(Periodical)
        if category:
            query = query.filter(Periodical.category == category)

        periodicals = query.all()

        fixed = 0
        skipped = 0
        errors = []
        fixes = []

        logger.info(f"Checking {len(periodicals)} periodicals for tracking_id fixes")

        for periodical in periodicals:
            try:
                # Get country from derived_metadata if available
                parsed_country = None
                if periodical.derived_metadata and "country" in periodical.derived_metadata:
                    parsed_country = periodical.derived_metadata["country"].get("value")

                # Try to find best matching tracking record
                match = matcher.find_best_match(
                    parsed_title=periodical.title,
                    tracking_records=tracking_records,
                    parsed_language=periodical.language,
                    parsed_country=parsed_country,
                    parsed_category=periodical.category,
                )

                if match and match.is_match:
                    # Check if tracking_id needs updating
                    if periodical.tracking_id != match.tracking_id:
                        old_tracking_id = periodical.tracking_id
                        old_tracking_title = None

                        if old_tracking_id:
                            old_tracking = db_session.query(PeriodicalTracking).filter_by(id=old_tracking_id).first()
                            if old_tracking:
                                old_tracking_title = old_tracking.title

                        fix_info = {
                            "periodical_id": periodical.id,
                            "title": periodical.title,
                            "old_tracking_id": old_tracking_id,
                            "old_tracking_title": old_tracking_title,
                            "new_tracking_id": match.tracking_id,
                            "new_tracking_title": match.tracking_title,
                            "match_score": match.score,
                            "match_breakdown": match.breakdown,
                        }

                        if not dry_run:
                            periodical.tracking_id = match.tracking_id
                            logger.info(
                                f"Fixed tracking_id for '{periodical.title}': "
                                f"{old_tracking_id} ({old_tracking_title}) -> "
                                f"{match.tracking_id} ({match.tracking_title}) "
                                f"[score: {match.score}]"
                            )
                        else:
                            logger.info(
                                f"[DRY RUN] Would fix tracking_id for '{periodical.title}': "
                                f"{old_tracking_id} ({old_tracking_title}) -> "
                                f"{match.tracking_id} ({match.tracking_title}) "
                                f"[score: {match.score}]"
                            )

                        fixes.append(fix_info)
                        fixed += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

            except Exception as e:
                error_msg = f"Error processing periodical {periodical.id} ('{periodical.title}'): {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Commit all tracking_id fixes in a single transaction
        if not dry_run and fixed > 0:
            try:
                db_session.commit()
                logger.info(f"Successfully committed {fixed} tracking_id fix(es)")
            except Exception as e:
                db_session.rollback()
                logger.error(f"Failed to commit tracking_id fixes: {e}")
                return {
                    "success": False,
                    "error": f"Database commit failed: {e}",
                    "fixed": 0,
                    "skipped": skipped,
                    "errors": errors + [str(e)],
                }

        return {
            "success": True,
            "fixed": fixed,
            "skipped": skipped,
            "errors": errors,
            "fixes": fixes,
            "dry_run": dry_run,
            "message": (
                f"{'Would fix' if dry_run else 'Fixed'} {fixed} tracking_id(s), "
                f"skipped {skipped}, {len(errors)} errors"
            ),
        }

    def _get_tracking_title(self, db_session: Any, tracking_id: Optional[int]) -> Optional[str]:
        """
        Get the canonical title from a tracking record.

        The tracking title is the source of truth for folder organization.
        It already includes the correct format (with country code if needed).

        Args:
            db_session: Database session
            tracking_id: Tracking record ID, or None

        Returns:
            Tracking title if found, None otherwise
        """
        if not tracking_id:
            return None

        from models.database import PeriodicalTracking

        tracking = db_session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        return tracking.title if tracking else None
