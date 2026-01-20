"""
File organization utilities for moving and renaming PDFs.
Handles both simple and pattern-based organization with metadata extraction.
"""

# pylint: disable=too-many-lines

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.constants.country import ISO_COUNTRIES
from core.constants.files import (
    PDF_COVER_DPI_HIGH,
    PDF_COVER_QUALITY_HIGH,
    VOLUME_PREFIX,
    ISSUE_PREFIX,
    ORGANIZED_FILENAME_SEPARATOR,
)
from core.constants.language import DEFAULT_LANGUAGE
from core.utils.pdf import extract_cover_from_pdf as extract_cover_util
from core.utils.epub import extract_cover_from_epub
from core.utils.cbz import extract_cover_from_cbz, extract_cover_from_cbr
from core.parsers import sanitize_filename
from services.importer.sidecar import read_sidecar_file

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

        month = issue_date.strftime("%B")
        year = issue_date.strftime("%Y")

        safe_title = sanitize_filename(title)
        filename_base = f"{safe_title}{ORGANIZED_FILENAME_SEPARATOR}{month}{year}"

        # Preserve file extension (PDF, EPUB, CBZ, or CBR)
        extension = source.suffix.lower()
        file_path = self.organize_dir / f"{filename_base}{extension}"
        jpg_path = self.organize_dir / f"{filename_base}.jpg"

        if extension in [".pdf", ".epub", ".cbz", ".cbr"]:
            try:
                source.rename(file_path)
                logger.info(f"Organized file: {file_path}")
            except (OSError, PermissionError) as e:
                logger.error(f"Error moving file: {e}", exc_info=True)
                file_path = None
        else:
            logger.warning(f"Unsupported file type: {source} (extension: {extension})")
            file_path = None

        if cover_path and Path(cover_path).exists():
            try:
                Path(cover_path).rename(jpg_path)
                logger.info(f"Organized cover: {jpg_path}")
            except (OSError, PermissionError) as e:
                logger.error(f"Error moving cover: {e}", exc_info=True)
                jpg_path = None

        return str(file_path), str(jpg_path)

    def _build_filename(  # pylint: disable=too-many-positional-arguments
        self,
        safe_title: str,
        volume: Optional[int],
        issue_number: Optional[int],
        month: str,
        year: str,
        extension: str = ".pdf",
    ) -> str:
        """
        Build organized filename with optional volume and issue information.

        Args:
            safe_title: Sanitized title
            volume: Volume number (optional)
            issue_number: Issue number (optional)
            month: Month abbreviation (e.g., "Dec")
            year: Year (e.g., "2006")
            extension: File extension (default: ".pdf")

        Returns:
            Filename with specified extension

        Examples:
            >>> organizer._build_filename("Wired", 5, 12, "Dec", "2024")
            'Wired - Vol5 - No12 - Dec2024.pdf'

            >>> organizer._build_filename("Nature", None, None, "Jan", "2023")
            'Nature - Jan2023.pdf'

            >>> organizer._build_filename("Pride", None, None, "Jan", "2026", ".epub")
            'Pride - Jan2026.epub'
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

    def _build_pattern_directory(  # pylint: disable=too-many-positional-arguments
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
            language = metadata.get("language", DEFAULT_LANGUAGE)
            issue_number = metadata.get("issue_number")
            volume = metadata.get("volume")

            # Format date components
            safe_title = sanitize_filename(title)
            month = issue_date.strftime("%B")
            year = issue_date.strftime("%Y")
            day = issue_date.strftime("%d")

            # Preserve file extension (PDF, EPUB, CBZ, or CBR)
            extension = pdf_path.suffix.lower()

            # Build filename with preserved extension
            filename = self._build_filename(safe_title, volume, issue_number, month, year, extension)

            # Apply category prefix
            category_with_prefix = f"{self.category_prefix}{category}"

            # Build target directory
            if not pattern:
                target_dir = self._build_default_directory(category_with_prefix, safe_title, volume, year)
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
            logger.error(f"Error organizing file {pdf_path}: {e}", exc_info=True)
            return None

    def extract_cover_from_pdf(self, pdf_path: str, output_path: str) -> bool:
        """
        Extract cover from periodical file (PDF, EPUB, CBZ, or CBR).

        Args:
            pdf_path: Path to periodical file
            output_path: Where to save the cover JPG

        Returns:
            True if successful, False otherwise
        """
        file_path_obj = Path(pdf_path)
        output_path_obj = Path(output_path)
        output_dir = output_path_obj.parent
        extension = file_path_obj.suffix.lower()

        result = None

        if extension == ".pdf":
            result = extract_cover_util(
                file_path_obj,
                output_dir,
                dpi=PDF_COVER_DPI_HIGH,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".epub":
            result = extract_cover_from_epub(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".cbz":
            result = extract_cover_from_cbz(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".cbr":
            result = extract_cover_from_cbr(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        else:
            logger.warning(f"Unsupported file type for cover extraction: {extension}")
            return False

        if result:
            if result != output_path_obj:
                result.rename(output_path_obj)
            return True
        return False

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
        category_dir = self.organize_dir / category_with_prefix

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
    ) -> Dict[str, Any]:
        """
        Reorganize files based on metadata from database.

        Scans the category folder and reorganizes files that are in the wrong location
        by looking up their metadata in the Magazine table. Uses country from tracking
        record to build full title (e.g., "Magazine US", "Magazine Germany").

        Args:
            db_session: SQLAlchemy database session
            category: Category to reorganize (e.g., "Magazines")
            pattern: Organization pattern (defaults to {category}/{title}/{year}/)
            dry_run: If True, only report what would be done without making changes

        Returns:
            Dictionary with reorganization results
        """
        from models.database import (
            Magazine,
            MagazineTracking,
        )  # Import here to avoid circular dependency

        category_with_prefix = f"{self.category_prefix}{category}"
        category_dir = self.organize_dir / category_with_prefix

        if not category_dir.exists():
            logger.warning(f"Category directory does not exist: {category_dir}")
            return {
                "success": False,
                "error": f"Category directory not found: {category_dir}",
                "files_found": 0,
                "files_reorganized": 0,
            }

        logger.info(f"Reorganizing files in: {category_dir}")

        files_found = 0
        files_reorganized = 0
        files_skipped = 0
        errors = []
        old_directories = set()  # Track directories we moved files from

        # Query all magazines in this category from database
        magazines = db_session.query(Magazine).filter(Magazine.file_path.like(f"%{category_with_prefix}%")).all()

        logger.info(f"Found {len(magazines)} magazine records in database for category {category}")

        for magazine in magazines:
            # Store original path for error messages (before any DB operations)
            original_file_path = magazine.file_path
            try:
                files_found += 1
                current_path = Path(magazine.file_path)

                if not current_path.exists():
                    logger.debug(f"File not found, skipping: {current_path}")
                    files_skipped += 1
                    continue

                # Get country from tracking record if available
                country = None
                if magazine.tracking_id:
                    tracking = db_session.query(MagazineTracking).filter_by(id=magazine.tracking_id).first()
                    if tracking:
                        country = tracking.country

                # Build full title with country name (e.g., "Magazine South Africa", "Magazine Germany")
                # Use the existing title as-is - don't append country if title already has location info
                full_title = magazine.title

                # Only append country name if:
                # 1. Country code exists in tracking
                # 2. Title doesn't already end with a country code or name
                # 3. Title doesn't already contain the country name
                if country:
                    # Get country name from code (e.g., "ZA" -> "South Africa")
                    country_name = ISO_COUNTRIES.get(country)

                    if country_name:
                        # Get list of country names from ISO_COUNTRIES constant
                        country_names = list(ISO_COUNTRIES.values())

                        # Check if title already has country info
                        has_country_name = any(name in magazine.title for name in country_names)
                        has_country_code = magazine.title.endswith(f" {country}")

                        if not has_country_name and not has_country_code:
                            # Title doesn't have country info, add the country name
                            full_title = f"{magazine.title} {country_name}"

                # Build expected path based on pattern
                metadata = {
                    "title": full_title,
                    "issue_date": magazine.issue_date,
                    "language": magazine.language or DEFAULT_LANGUAGE,
                    "issue_number": magazine.extra_metadata.get("issue_number") if magazine.extra_metadata else None,
                    "volume": magazine.extra_metadata.get("volume") if magazine.extra_metadata else None,
                }

                # Build expected directory and filename
                safe_title = sanitize_filename(metadata["title"])
                issue_date = metadata["issue_date"]
                month = issue_date.strftime("%B")
                year = issue_date.strftime("%Y")
                day = issue_date.strftime("%d")

                # Build filename
                filename = self._build_filename(
                    safe_title,
                    metadata.get("volume"),
                    metadata.get("issue_number"),
                    month,
                    year,
                )

                # Build target directory
                if not pattern:
                    target_dir = self._build_default_directory(
                        category_with_prefix, safe_title, metadata.get("volume"), year
                    )
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

                expected_path = target_dir / filename

                # Skip if already in correct location
                if current_path.resolve() == expected_path.resolve():
                    logger.debug(f"File already in correct location: {current_path}")
                    files_skipped += 1
                    continue

                logger.info(f"Reorganizing: {current_path} -> {expected_path}")

                if not dry_run:
                    # Create target directory
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Get unique target path if file exists
                    final_path = self._get_unique_target_path(target_dir, filename)

                    # Check if target path already exists in database (to avoid UNIQUE constraint error)
                    existing_record = db_session.query(Magazine).filter_by(file_path=str(final_path)).first()
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

                    # Update database with new path and title
                    magazine.file_path = str(final_path)
                    magazine.title = full_title  # Update title in database to include country
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

        # Final cleanup after processing sidecar files
        if not dry_run and sidecar_results["files_reorganized"] > 0:
            self._cleanup_old_directories(old_directories, category_dir)

        return {
            "success": True,
            "category": category,
            "category_dir": str(category_dir),
            "pattern": pattern or "{category}/{title}/{year}/",
            "files_found": files_found,
            "files_reorganized": files_reorganized,
            "files_skipped": files_skipped,
            "errors": errors,
            "dry_run": dry_run,
        }

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
        from models.database import Magazine

        files_found = 0
        files_reorganized = 0
        files_skipped = 0
        errors = []

        # Find all PDF, EPUB, CBZ, and CBR files in the category directory
        for file_path in category_dir.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in [".pdf", ".epub", ".cbz", ".cbr"]:
                continue

            # Skip if file is already in database
            existing = db_session.query(Magazine).filter(Magazine.file_path == str(file_path)).first()
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
                sidecar_data.get("tracking_id")
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
                from core.parsers.metadata import MetadataExtractor

                extractor = MetadataExtractor()
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

                # Build expected directory and filename
                safe_title = sanitize_filename(metadata["title"])
                month = issue_date.strftime("%B")
                year = issue_date.strftime("%Y")
                day = issue_date.strftime("%d")

                # Build filename
                filename = self._build_filename(
                    safe_title,
                    metadata.get("volume"),
                    metadata.get("issue_number"),
                    month,
                    year,
                )

                # Build target directory
                if not pattern:
                    target_dir = self._build_default_directory(
                        category_with_prefix, safe_title, metadata.get("volume"), year
                    )
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

                expected_path = target_dir / filename

                # Skip if already in correct location
                if file_path.resolve() == expected_path.resolve():
                    logger.debug(f"File already in correct location: {file_path}")
                    files_skipped += 1
                    continue

                logger.info(f"Reorganizing (from sidecar): {file_path} -> {expected_path}")

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
