"""
File organization utilities for moving and renaming PDFs.
Handles both simple and pattern-based organization with metadata extraction.
"""

# pylint: disable=too-many-lines

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
from core.utils.files import resolve_periodical_file_path
from core.parsers import sanitize_filename, detect_country
from services.importer.sidecar import read_sidecar_file
from services.importer.matcher import TrackingMatcher
from services.cover_extractor import CoverExtractor

logger = logging.getLogger(__name__)


class FileOrganizer:
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
        from core.constants.country import ISO_COUNTRIES

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
        from core.constants.country import ISO_COUNTRIES

        cleaned_title = title.strip()

        # Remove country codes and names from the end of the title
        # Multiple passes handle malformed titles with redundant country info
        # (e.g., "Magazine US USA United States" requires 3 passes to fully clean)
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

        Examples:
            >>> _title_has_country_info("Wired USA", "US")
            True
            >>> _title_has_country_info("Time US", "US")
            True
            >>> _title_has_country_info("Magazine United States", "US")
            True
            >>> _title_has_country_info("National Geographic", "US")
            False
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

        Examples:
            >>> organizer._build_filename("Wired", 5, 12, "Dec", "2024")
            'Wired - Vol5 - No12 - Dec2024.pdf'

            >>> organizer._build_filename("Science", 385, None, None, None)
            'Science - Vol385.pdf'

            >>> organizer._build_filename("Comic", None, 123, None, None)
            'Comic - No123.pdf'

            >>> organizer._build_filename("Nature", None, None, "Jan", "2023")
            'Nature - Jan2023.pdf'
        """
        filename_parts = [safe_title]

        # Add volume if present (e.g., "Vol1")
        # Volume comes before issue number following common periodical conventions
        if volume:
            filename_parts.append(f"{VOLUME_PREFIX}{volume}")

        # Add issue number if present (e.g., "No123")
        if issue_number:
            filename_parts.append(f"{ISSUE_PREFIX}{issue_number}")

        # Add date if both month and year are present (e.g., "Dec2024")
        # This ensures consistent sorting and readability
        if month and year:
            filename_parts.append(f"{month}{year}")
        elif volume or issue_number:
            # If we have volume/issue but no date, that's okay
            pass
        else:
            # No volume, issue, or date - use "Unknown" as fallback
            filename_parts.append("Unknown")
            logger.warning(f"No date, volume, or issue number for {safe_title} - using 'Unknown'")

        # Join with separator to create final filename
        # Example: "Wired - Vol5 - No12 - Dec2024.pdf"
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
            # Check if issue_date was explicitly set (not defaulted to now())
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
                    # No date AND no volume/issue - warn and use fallback
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
                    # Has volume but no date - use volume-based pattern
                    pattern = "{category}/{title}/Vol{volume}/"
                    logger.info(f"Auto-selected volume-based organization pattern for '{title}'")
                elif not has_date and issue_number:
                    # Has issue but no date - use flat pattern (all in title folder)
                    pattern = "{category}/{title}/"
                    logger.info(f"Auto-selected flat organization pattern for '{title}'")
                elif not has_date:
                    # No date, volume, or issue - use flat pattern
                    pattern = "{category}/{title}/"
                    logger.warning(f"Using flat organization pattern for '{title}' (no metadata)")
                # else: has_date, use default pattern below

            # Build target directory
            if not pattern:
                # Default pattern: {category}/{title}/{year}/
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

        matcher = TrackingMatcher(min_score=70)  # Use 70 as minimum match threshold

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
        fixes = []  # Track what was fixed for reporting

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
                        # Already has correct tracking_id
                        skipped += 1
                else:
                    # No match found
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

    def _build_target_path_info(
        self,
        metadata: Dict[str, Any],
        category_with_prefix: str,
        pattern: Optional[str],
    ) -> Tuple[Path, str, Path]:
        """
        Build target directory, filename, and full path for a periodical.

        Centralizes path-building logic used during reorganization.

        Args:
            metadata: Dict with title, issue_date, language, issue_number, volume
            category_with_prefix: Category name with prefix (e.g., "_Magazines")
            pattern: Organization pattern or None for default

        Returns:
            Tuple of (target_dir, filename, expected_path)
        """
        safe_title = sanitize_filename(metadata["title"])
        issue_date = metadata["issue_date"]
        month = issue_date.strftime("%B")
        year = issue_date.strftime("%Y")
        day = issue_date.strftime("%d")

        filename = self._build_filename(
            safe_title,
            metadata.get("volume"),
            metadata.get("issue_number"),
            month,
            year,
        )

        if not pattern:
            target_dir = self._build_default_directory(category_with_prefix, safe_title, metadata.get("volume"), year)
        else:
            target_dir = self._build_pattern_directory(
                pattern,
                category_with_prefix,
                safe_title,
                metadata.get("language") or DEFAULT_LANGUAGE,
                year,
                month,
                day,
                metadata.get("issue_number"),
                metadata.get("volume"),
            )

        return target_dir, filename, target_dir / filename

    def scan_for_reorganization(
        self,
        category: str,
        pattern: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Scan organized directory and identify files that need reorganization.

        Looks for files in the wrong location based on current organization pattern.
        This helps clean up messy folder structures.

        Args:
            category: Category to scan (e.g., "Magazines")
            pattern: Expected organization pattern (defaults to {category}/{title}/{year}/)
            dry_run: If True, only report what would be done without making changes

        Returns:
            Dictionary with scan results and reorganization actions
        """
        category_with_prefix = f"{self.category_prefix}{category}"
        category_dir = self.library_dir / category_with_prefix

        if not category_dir.exists():
            logger.warning(f"Category directory does not exist: {category_dir}")
            return {
                "success": False,
                "error": f"Category directory not found: {category_dir}",
                "files_found": 0,
                "files_reorganized": 0,
            }

        logger.info(f"Scanning for files to reorganize in: {category_dir}")

        files_found = []
        files_reorganized = 0
        errors = []

        # Find all PDF, EPUB, CBZ, and CBR files recursively
        for file_path in category_dir.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in [".pdf", ".epub", ".cbz", ".cbr"]:
                continue

            files_found.append(str(file_path))

        logger.info(f"Found {len(files_found)} files in {category_dir}")

        return {
            "success": True,
            "category": category,
            "category_dir": str(category_dir),
            "pattern": pattern or "{category}/{title}/{year}/",
            "files_found": len(files_found),
            "files_reorganized": files_reorganized,
            "errors": errors,
            "dry_run": dry_run,
        }

    def reorganize_from_database(
        self,
        db_session: Any,
        category: str,
        pattern: Optional[str] = None,
        dry_run: bool = False,
        auto_fix_tracking: bool = True,
    ) -> Dict[str, Any]:
        """
        Reorganize files based on metadata from database.

        Scans the category folder and reorganizes files that are in the wrong location
        by looking up their metadata in the Magazine table. Uses tracking title as the
        source of truth for folder organization.

        Args:
            db_session: SQLAlchemy database session
            category: Category to reorganize (e.g., "Magazines")
            pattern: Organization pattern (defaults to {category}/{title}/{year}/)
            dry_run: If True, only report what would be done without making changes
            auto_fix_tracking: If True, auto-fix incorrect tracking_id values before reorganizing

        Returns:
            Dictionary with reorganization results including tracking_fixes if auto_fix_tracking=True
        """
        from models.database import (
            Periodical,
            PeriodicalTracking,
        )  # Import here to avoid circular dependency

        # Step 1: Auto-fix tracking IDs if enabled
        tracking_fixes = None
        if auto_fix_tracking:
            logger.info("Auto-fixing tracking_id values before reorganization...")
            tracking_fixes = self.auto_fix_tracking_ids(
                db_session=db_session,
                category=category,
                dry_run=dry_run,
            )
            if not dry_run:
                logger.info(f"Fixed {tracking_fixes['fixed']} tracking_id(s), " f"skipped {tracking_fixes['skipped']}")
            else:
                logger.info(
                    f"Would fix {tracking_fixes['fixed']} tracking_id(s), " f"skipped {tracking_fixes['skipped']}"
                )

        category_with_prefix = f"{self.category_prefix}{category}"
        category_dir = self.library_dir / category_with_prefix

        if not category_dir.exists():
            logger.warning(f"Category directory does not exist: {category_dir}")
            return {
                "success": False,
                "error": f"Category directory not found: {category_dir}",
                "files_found": 0,
                "files_reorganized": 0,
            }

        # Only log for actual operations, not dry run
        if not dry_run:
            logger.info(f"Reorganizing files in: {category_dir}")

        files_found = 0
        files_reorganized = 0
        files_skipped = 0
        errors = []
        changes = []  # Track detailed changes for preview
        old_directories = set()  # Track directories we moved files from

        # Query all magazines in this category from database
        magazines = db_session.query(Periodical).filter(Periodical.file_path.like(f"%{category_with_prefix}%")).all()

        # Only log for actual operations, not dry run
        if not dry_run:
            logger.info(f"Found {len(magazines)} magazine records in database for category {category}")

        for magazine in magazines:
            # Store original path for error messages (before any DB operations)
            original_file_path = magazine.file_path
            try:
                files_found += 1

                # Try to resolve the file path (handles environment differences like Docker paths)
                try:
                    current_path = resolve_periodical_file_path(
                        stored_path=magazine.file_path,
                        library_base_dir=self.library_dir,
                        category_prefix=self.category_prefix,
                    )
                except FileNotFoundError:
                    # Path could not be resolved - skip this file
                    logger.debug(f"File not found, skipping: {magazine.file_path}")
                    files_skipped += 1
                    continue

                # Get canonical title: prefer tracking title over magazine title
                tracking_title = self._get_tracking_title(db_session, magazine.tracking_id)
                full_title = tracking_title or magazine.title

                if tracking_title:
                    logger.debug(f"Using tracking title: {tracking_title} (magazine title was: {magazine.title})")
                else:
                    logger.debug(f"No tracking record, using magazine title: {magazine.title}")

                # Build expected path based on pattern
                metadata = {
                    "title": full_title,
                    "issue_date": magazine.issue_date,
                    "language": magazine.language or DEFAULT_LANGUAGE,
                    "issue_number": magazine.extra_metadata.get("issue_number") if magazine.extra_metadata else None,
                    "volume": magazine.extra_metadata.get("volume") if magazine.extra_metadata else None,
                }

                target_dir, filename, expected_path = self._build_target_path_info(
                    metadata, category_with_prefix, pattern
                )

                # Skip if already in correct location
                if current_path.resolve() == expected_path.resolve():
                    logger.debug(f"File already in correct location: {current_path}")
                    files_skipped += 1
                    continue

                # Only log for actual operations, not dry run
                if not dry_run:
                    logger.info(f"Reorganizing: {current_path} -> {expected_path}")

                # Track this change for preview display
                change_info = {
                    "old_path": str(current_path),
                    "new_path": str(expected_path),
                    "old_title": magazine.title,
                    "new_title": full_title,
                    "title_changed": magazine.title != full_title,
                    "old_folder": current_path.parent.name,
                    "new_folder": target_dir.name,
                }
                changes.append(change_info)

                if not dry_run:
                    # Create target directory
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Get unique target path if file exists
                    final_path = self._get_unique_target_path(target_dir, filename)

                    # Check if target path already exists in database (to avoid UNIQUE constraint error)
                    existing_record = db_session.query(Periodical).filter_by(file_path=str(final_path)).first()
                    if existing_record and existing_record.id != magazine.id:
                        logger.warning(
                            f"Target path already exists in database for different record: {final_path}. "
                            f"Skipping reorganization of {current_path}"
                        )
                        files_skipped += 1
                        continue

                    # Track old directory for cleanup
                    old_dir = current_path.parent
                    old_directories.add(old_dir)

                    # Move file
                    shutil.move(str(current_path), str(final_path))

                    # Update database with new path and title (use tracking title if available)
                    magazine.file_path = str(final_path)
                    magazine.title = full_title  # Sync to tracking title
                    db_session.commit()

                    # Also move cover if it exists
                    current_cover = current_path.with_suffix(".jpg")
                    if current_cover.exists():
                        new_cover = final_path.with_suffix(".jpg")
                        shutil.move(str(current_cover), str(new_cover))
                        magazine.cover_path = str(new_cover)
                        db_session.commit()
                        logger.info(f"Moved cover: {current_cover} -> {new_cover}")

                    logger.info(f"Reorganized: {final_path}")

                files_reorganized += 1

            except Exception as e:
                # Rollback the session to clear any pending changes
                db_session.rollback()
                error_msg = f"Error reorganizing {original_file_path}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Remove old directories (even if not empty)
        if not dry_run:
            self._cleanup_old_directories(old_directories, category_dir)

        # Also process files with sidecar metadata that aren't in the database
        sidecar_results = self._reorganize_from_sidecars(
            db_session,
            category_dir,
            category_with_prefix,
            pattern,
            dry_run,
            old_directories,
        )

        files_found += sidecar_results["files_found"]
        files_reorganized += sidecar_results["files_reorganized"]
        files_skipped += sidecar_results["files_skipped"]
        errors.extend(sidecar_results["errors"])
        # Merge sidecar changes into main changes list
        if "changes" in sidecar_results:
            changes.extend(sidecar_results["changes"])

        # Final cleanup after processing sidecar files
        if not dry_run and sidecar_results["files_reorganized"] > 0:
            self._cleanup_old_directories(old_directories, category_dir)

        result = {
            "success": True,
            "category": category,
            "category_dir": str(category_dir),
            "pattern": pattern or "{category}/{title}/{year}/",
            "files_found": files_found,
            "files_reorganized": files_reorganized,
            "files_skipped": files_skipped,
            "errors": errors,
            "changes": changes,  # Add detailed changes list
            "dry_run": dry_run,
        }

        # Add tracking fixes if auto-fix was enabled
        if tracking_fixes:
            result["tracking_fixes"] = tracking_fixes

        return result

    def _reorganize_from_sidecars(
        self,
        db_session: Any,
        category_dir: Path,
        category_with_prefix: str,
        pattern: Optional[str],
        dry_run: bool,
        old_directories: set,
    ) -> Dict[str, Any]:
        """
        Reorganize files that have sidecar metadata but aren't in the database.

        This handles downloaded files that haven't been imported yet or were
        imported but the database record was lost.

        Args:
            db_session: SQLAlchemy database session
            category_dir: Category directory to scan
            category_with_prefix: Category name with prefix (e.g., "_Magazines")
            pattern: Organization pattern
            dry_run: If True, only report what would be done
            old_directories: Set to track directories we move files from

        Returns:
            Dictionary with processing results
        """
        from models.database import Periodical

        files_found = 0
        files_reorganized = 0
        files_skipped = 0
        errors = []
        changes = []  # Track detailed changes for sidecar files

        # Find all PDF, EPUB, CBZ, and CBR files in the category directory
        for file_path in category_dir.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in [".pdf", ".epub", ".cbz", ".cbr"]:
                continue

            # Skip if file is already in database
            existing = db_session.query(Periodical).filter(Periodical.file_path == str(file_path)).first()
            if existing:
                continue  # Already handled by database reorganization

            # Check for sidecar file
            sidecar_data = read_sidecar_file(file_path)
            if not sidecar_data:
                # No sidecar, skip this file
                logger.debug(f"No sidecar found for {file_path}, skipping")
                continue

            try:
                files_found += 1

                # Extract metadata from sidecar
                tracking_title = sidecar_data.get("tracking_title")
                country = sidecar_data.get("country")
                language = sidecar_data.get("language", DEFAULT_LANGUAGE)

                if not tracking_title:
                    logger.warning(f"Sidecar missing tracking_title for {file_path}, skipping")
                    files_skipped += 1
                    continue

                # Build full title with country code (e.g., "Magazine US", "Magazine DE")
                # Use the tracking title as-is - don't append country code if title already has location info
                full_title = tracking_title

                # Only append country code if:
                # 1. Country code exists
                # 2. Title doesn't already contain common country names
                if country:
                    # Get list of country names from ISO_COUNTRIES constant
                    country_names = list(ISO_COUNTRIES.values())

                    # Check if title already has country info
                    has_country_name = any(name in tracking_title for name in country_names)

                    if not has_country_name:
                        # Title doesn't have country info, add the code
                        full_title = f"{tracking_title} {country}"

                # Parse filename to get date information
                from core.parsers.metadata import FilenameParser

                extractor = FilenameParser()
                parsed_dict = extractor.extract_from_filename(file_path)

                if not parsed_dict or not parsed_dict.get("year"):
                    logger.warning(f"Could not extract date from {file_path.name}, skipping")
                    files_skipped += 1
                    continue

                # Build issue_date from parsed metadata
                issue_date = datetime(
                    year=parsed_dict["year"],
                    month=parsed_dict.get("month", 1),
                    day=1,
                )

                # Build metadata dict
                metadata = {
                    "title": full_title,
                    "issue_date": issue_date,
                    "language": language,
                    "issue_number": parsed_dict.get("issue_number"),
                    "volume": parsed_dict.get("volume"),
                }

                target_dir, filename, expected_path = self._build_target_path_info(
                    metadata, category_with_prefix, pattern
                )

                # Skip if already in correct location
                if file_path.resolve() == expected_path.resolve():
                    logger.debug(f"File already in correct location: {file_path}")
                    files_skipped += 1
                    continue

                # Only log for actual operations, not dry run
                if not dry_run:
                    logger.info(f"Reorganizing (from sidecar): {file_path} -> {expected_path}")

                # Track this change for preview display
                change_info = {
                    "old_path": str(file_path),
                    "new_path": str(expected_path),
                    "old_title": parsed_dict.get("title", "Unknown"),
                    "new_title": full_title,
                    "title_changed": parsed_dict.get("title") != full_title,
                    "old_folder": file_path.parent.name,
                    "new_folder": target_dir.name,
                    "source": "sidecar",
                }
                changes.append(change_info)

                if not dry_run:
                    # Create target directory
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Get unique target path if file exists
                    final_path = self._get_unique_target_path(target_dir, filename)

                    # Track old directory for cleanup
                    old_dir = file_path.parent
                    old_directories.add(old_dir)

                    # Move file
                    shutil.move(str(file_path), str(final_path))

                    # Move sidecar file
                    sidecar_path = file_path.with_suffix(file_path.suffix + ".curator_meta.json")
                    if sidecar_path.exists():
                        new_sidecar = final_path.with_suffix(final_path.suffix + ".curator_meta.json")
                        shutil.move(str(sidecar_path), str(new_sidecar))

                    # Also move cover if it exists
                    current_cover = file_path.with_suffix(".jpg")
                    if current_cover.exists():
                        new_cover = final_path.with_suffix(".jpg")
                        shutil.move(str(current_cover), str(new_cover))
                        logger.info(f"Moved cover: {current_cover} -> {new_cover}")

                    logger.info(f"Reorganized (from sidecar): {final_path}")

                files_reorganized += 1

            except Exception as e:
                error_msg = f"Error reorganizing from sidecar {file_path}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        return {
            "files_found": files_found,
            "files_reorganized": files_reorganized,
            "files_skipped": files_skipped,
            "errors": errors,
            "changes": changes,  # Add detailed changes list
        }

    def _cleanup_old_directories(self, old_directories: set, base_dir: Path) -> int:
        """
        Remove old directories that we moved files from (even if they still contain other files).

        When we reorganize a PDF/EPUB, the old directory becomes obsolete and should be
        completely removed along with any leftover files (.nfo, .jpg, etc.).

        Args:
            old_directories: Set of directories we moved files from
            base_dir: Base directory to start cleanup from (for parent directory cleanup)

        Returns:
            Number of directories removed
        """
        removed_count = 0

        # First, remove the directories we moved files from
        for old_dir in old_directories:
            try:
                if old_dir.exists():
                    # Remove directory and all its contents
                    shutil.rmtree(str(old_dir))
                    logger.info(f"Removed old directory and contents: {old_dir}")
                    removed_count += 1
            except OSError as e:
                logger.warning(f"Could not remove directory {old_dir}: {e}")

        # Then, clean up any empty parent directories left behind
        # Walk bottom-up to remove nested empty dirs
        for dirpath, dirnames, filenames in os.walk(str(base_dir), topdown=False):
            dir_path = Path(dirpath)

            # Skip the base directory itself
            if dir_path == base_dir:
                continue

            # Check if directory is empty
            try:
                if not any(dir_path.iterdir()):
                    logger.info(f"Removing empty parent directory: {dir_path}")
                    dir_path.rmdir()
                    removed_count += 1
            except OSError as e:
                logger.debug(f"Could not remove directory {dir_path}: {e}")

        if removed_count > 0:
            logger.info(f"Removed {removed_count} directories during cleanup")

        return removed_count

    def _cleanup_empty_directories(self, base_dir: Path) -> int:
        """
        Remove empty directories recursively using efficient find command.

        Uses `find -type d -empty -delete` for fast cleanup of large directory trees.
        Falls back to Python implementation if find command is unavailable.

        Args:
            base_dir: Base directory to start cleanup from

        Returns:
            Number of directories removed (0 when using find command, as it doesn't return count)
        """
        try:
            import subprocess

            # Use efficient find command to remove all empty directories
            result = subprocess.run(
                ["find", str(base_dir), "-type", "d", "-empty", "-delete"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info(f"Cleaned up empty directories in {base_dir}")
                return 0  # find command doesn't return count
            else:
                # Fall back to Python implementation
                logger.debug(f"Find command failed, using Python fallback: {result.stderr}")
                return self._cleanup_empty_directories_python(base_dir)

        except FileNotFoundError:
            # find command not available (e.g., Windows), use Python implementation
            logger.debug("Find command not available, using Python fallback")
            return self._cleanup_empty_directories_python(base_dir)

    def _cleanup_empty_directories_python(self, base_dir: Path) -> int:
        """
        Python fallback for _cleanup_empty_directories.

        Args:
            base_dir: Base directory to start cleanup from

        Returns:
            Number of directories removed
        """
        removed_count = 0

        # Walk directory tree bottom-up so we can remove empty parent dirs
        for dirpath, dirnames, filenames in os.walk(str(base_dir), topdown=False):
            dir_path = Path(dirpath)

            # Skip the base directory itself
            if dir_path == base_dir:
                continue

            # Check if directory is empty (no files and no subdirs with files)
            try:
                if not any(dir_path.iterdir()):
                    logger.info(f"Removing empty directory: {dir_path}")
                    dir_path.rmdir()
                    removed_count += 1
            except OSError as e:
                logger.debug(f"Could not remove directory {dir_path}: {e}")

        if removed_count > 0:
            logger.info(f"Removed {removed_count} empty directories from {base_dir}")

        return removed_count
