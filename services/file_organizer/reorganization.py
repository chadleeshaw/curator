"""
Reorganization utilities for file organization.

Contains mixin class with methods for reorganizing files based on
database metadata and sidecar files.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.constants.country import ISO_COUNTRIES
from core.constants.language import DEFAULT_LANGUAGE
from core.parsers import sanitize_filename
from core.utils.files import resolve_periodical_file_path
from services.importer.sidecar import read_sidecar_file

logger = logging.getLogger(__name__)


class ReorganizationMixin:
    """Mixin providing file reorganization functionality."""

    # These attributes are expected from the main class
    library_dir: Path
    category_prefix: str

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

    def _process_single_magazine_reorganization(
        self,
        magazine: Any,
        db_session: Any,
        category_with_prefix: str,
        pattern: Optional[str],
        dry_run: bool,
        old_directories: set,
    ) -> Dict[str, Any]:
        """
        Process a single magazine for reorganization.

        Args:
            magazine: Periodical database record
            db_session: SQLAlchemy database session
            category_with_prefix: Category name with prefix (e.g., "_Magazines")
            pattern: Organization pattern or None for default
            dry_run: If True, only report what would be done
            old_directories: Set to track directories we moved files from

        Returns:
            Dictionary with status: 'reorganized', 'skipped', or 'error'
        """
        # Try to resolve the file path
        try:
            current_path = resolve_periodical_file_path(
                stored_path=magazine.file_path,
                library_base_dir=self.library_dir,
                category_prefix=self.category_prefix,
            )
        except FileNotFoundError:
            logger.debug(f"File not found, skipping: {magazine.file_path}")
            return {"status": "skipped", "reason": "file_not_found"}

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

        target_dir, filename, expected_path = self._build_target_path_info(metadata, category_with_prefix, pattern)

        # Skip if already in correct location
        if current_path.resolve() == expected_path.resolve():
            logger.debug(f"File already in correct location: {current_path}")
            return {"status": "skipped", "reason": "already_correct"}

        # Build change info for preview
        change_info = {
            "old_path": str(current_path),
            "new_path": str(expected_path),
            "old_title": magazine.title,
            "new_title": full_title,
            "title_changed": magazine.title != full_title,
            "old_folder": current_path.parent.name,
            "new_folder": target_dir.name,
        }

        if dry_run:
            return {"status": "reorganized", "change": change_info}

        # Perform the actual move
        logger.info(f"Reorganizing: {current_path} -> {expected_path}")
        move_result = self._move_magazine_and_update_db(
            magazine=magazine,
            db_session=db_session,
            current_path=current_path,
            target_dir=target_dir,
            filename=filename,
            full_title=full_title,
            old_directories=old_directories,
        )

        if move_result["success"]:
            return {"status": "reorganized", "change": change_info}
        else:
            return {"status": "skipped", "reason": move_result["reason"]}

    def _move_magazine_and_update_db(
        self,
        magazine: Any,
        db_session: Any,
        current_path: Path,
        target_dir: Path,
        filename: str,
        full_title: str,
        old_directories: set,
    ) -> Dict[str, Any]:
        """
        Move a magazine file and update database records.

        Handles directory creation, unique path generation, conflict detection,
        file movement, and cover file handling.

        Args:
            magazine: Periodical database record
            db_session: SQLAlchemy database session
            current_path: Current file path
            target_dir: Target directory path
            filename: Target filename
            full_title: Title to use for the magazine
            old_directories: Set to track directories we moved files from

        Returns:
            Dictionary with success status and optional reason for failure
        """
        from models.database import Periodical

        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)

        # Get unique target path if file exists
        final_path = self._get_unique_target_path(target_dir, filename)

        # Check if target path already exists in database
        # Use no_autoflush to prevent premature flush of pending changes
        with db_session.no_autoflush:
            existing_record = db_session.query(Periodical).filter_by(file_path=str(final_path)).first()
        if existing_record and existing_record.id != magazine.id:
            logger.warning(
                f"Target path already exists in database for different record: {final_path}. "
                f"Skipping reorganization of {current_path}"
            )
            return {"success": False, "reason": "path_conflict"}

        # Track old directory for cleanup
        old_directories.add(current_path.parent)

        # Move file
        shutil.move(str(current_path), str(final_path))

        # Update database with new path and title
        magazine.file_path = str(final_path)
        magazine.title = full_title
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
        return {"success": True}

    def _build_reorganization_result(
        self,
        category: str,
        category_dir: Path,
        pattern: Optional[str],
        files_found: int,
        files_reorganized: int,
        files_skipped: int,
        errors: List[str],
        changes: List[Dict],
        dry_run: bool,
        tracking_fixes: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Build the result dictionary for reorganization operations.

        Args:
            category: Category name
            category_dir: Category directory path
            pattern: Organization pattern used
            files_found: Number of files processed
            files_reorganized: Number of files successfully reorganized
            files_skipped: Number of files skipped
            errors: List of error messages
            changes: List of change details
            dry_run: Whether this was a dry run
            tracking_fixes: Optional tracking fix results

        Returns:
            Dictionary with reorganization results
        """
        result = {
            "success": True,
            "category": category,
            "category_dir": str(category_dir),
            "pattern": pattern or "{category}/{title}/{year}/",
            "files_found": files_found,
            "files_reorganized": files_reorganized,
            "files_skipped": files_skipped,
            "errors": errors,
            "changes": changes,
            "dry_run": dry_run,
        }

        if tracking_fixes:
            result["tracking_fixes"] = tracking_fixes

        return result

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
        from models.database import Periodical

        # Step 1: Auto-fix tracking IDs if enabled
        tracking_fixes = self._run_tracking_auto_fix(db_session, category, dry_run, auto_fix_tracking)

        # Step 2: Validate category directory
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

        if not dry_run:
            logger.info(f"Reorganizing files in: {category_dir}")

        # Step 3: Process all magazines from database
        files_found, files_reorganized, files_skipped = 0, 0, 0
        errors, changes = [], []
        old_directories = set()

        magazines = db_session.query(Periodical).filter(Periodical.file_path.like(f"%{category_with_prefix}%")).all()

        if not dry_run:
            logger.info(f"Found {len(magazines)} magazine records in database for category {category}")

        for magazine in magazines:
            files_found += 1
            result = self._process_magazine_with_error_handling(
                magazine, db_session, category_with_prefix, pattern, dry_run, old_directories, errors
            )

            if result["status"] == "reorganized":
                files_reorganized += 1
                if "change" in result:
                    changes.append(result["change"])
            else:
                files_skipped += 1

        # Step 4: Cleanup old directories
        if not dry_run:
            self._cleanup_old_directories(old_directories, category_dir)

        # Step 5: Process sidecar files
        sidecar_results = self._reorganize_from_sidecars(
            db_session, category_dir, category_with_prefix, pattern, dry_run, old_directories
        )

        files_found += sidecar_results["files_found"]
        files_reorganized += sidecar_results["files_reorganized"]
        files_skipped += sidecar_results["files_skipped"]
        errors.extend(sidecar_results["errors"])
        if "changes" in sidecar_results:
            changes.extend(sidecar_results["changes"])

        # Final cleanup after sidecar processing
        if not dry_run and sidecar_results["files_reorganized"] > 0:
            self._cleanup_old_directories(old_directories, category_dir)

        # Step 6: Build and return result
        return self._build_reorganization_result(
            category,
            category_dir,
            pattern,
            files_found,
            files_reorganized,
            files_skipped,
            errors,
            changes,
            dry_run,
            tracking_fixes,
        )

    def _run_tracking_auto_fix(
        self, db_session: Any, category: str, dry_run: bool, auto_fix_tracking: bool
    ) -> Optional[Dict]:
        """Run tracking ID auto-fix if enabled and log results."""
        if not auto_fix_tracking:
            return None

        logger.info("Auto-fixing tracking_id values before reorganization...")
        tracking_fixes = self.auto_fix_tracking_ids(db_session=db_session, category=category, dry_run=dry_run)

        action = "Would fix" if dry_run else "Fixed"
        logger.info(f"{action} {tracking_fixes['fixed']} tracking_id(s), skipped {tracking_fixes['skipped']}")

        return tracking_fixes

    def _process_magazine_with_error_handling(
        self,
        magazine: Any,
        db_session: Any,
        category_with_prefix: str,
        pattern: Optional[str],
        dry_run: bool,
        old_directories: set,
        errors: List[str],
    ) -> Dict[str, Any]:
        """Process a single magazine with error handling and rollback."""
        original_file_path = magazine.file_path
        try:
            return self._process_single_magazine_reorganization(
                magazine, db_session, category_with_prefix, pattern, dry_run, old_directories
            )
        except Exception as e:
            db_session.rollback()
            error_msg = f"Error reorganizing {original_file_path}: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
            return {"status": "error"}

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
        changes = []

        # Find all PDF, EPUB, CBZ, and CBR files in the category directory
        for file_path in category_dir.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in [".pdf", ".epub", ".cbz", ".cbr"]:
                continue

            # Skip if file is already in database
            existing = db_session.query(Periodical).filter(Periodical.file_path == str(file_path)).first()
            if existing:
                continue

            # Check for sidecar file
            sidecar_data = read_sidecar_file(file_path)
            if not sidecar_data:
                logger.debug(f"No sidecar found for {file_path}, skipping")
                continue

            try:
                files_found += 1
                result = self._process_sidecar_file(
                    file_path, sidecar_data, category_with_prefix, pattern, dry_run, old_directories
                )

                if result["status"] == "reorganized":
                    files_reorganized += 1
                    if "change" in result:
                        changes.append(result["change"])
                else:
                    files_skipped += 1

            except Exception as e:
                error_msg = f"Error reorganizing from sidecar {file_path}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        return {
            "files_found": files_found,
            "files_reorganized": files_reorganized,
            "files_skipped": files_skipped,
            "errors": errors,
            "changes": changes,
        }

    def _process_sidecar_file(
        self,
        file_path: Path,
        sidecar_data: Dict,
        category_with_prefix: str,
        pattern: Optional[str],
        dry_run: bool,
        old_directories: set,
    ) -> Dict[str, Any]:
        """
        Process a single file with sidecar metadata for reorganization.

        Args:
            file_path: Path to the file
            sidecar_data: Parsed sidecar metadata
            category_with_prefix: Category name with prefix
            pattern: Organization pattern
            dry_run: If True, only report what would be done
            old_directories: Set to track directories we move files from

        Returns:
            Dictionary with status and optional change info
        """
        from core.parsers.metadata import FilenameParser

        # Extract metadata from sidecar
        tracking_title = sidecar_data.get("tracking_title")
        country = sidecar_data.get("country")
        language = sidecar_data.get("language", DEFAULT_LANGUAGE)

        if not tracking_title:
            logger.warning(f"Sidecar missing tracking_title for {file_path}, skipping")
            return {"status": "skipped", "reason": "missing_title"}

        # Build full title with country code if needed
        full_title = tracking_title
        if country:
            country_names = list(ISO_COUNTRIES.values())
            has_country_name = any(name in tracking_title for name in country_names)
            if not has_country_name:
                full_title = f"{tracking_title} {country}"

        # Parse filename to get date information
        extractor = FilenameParser()
        parsed_dict = extractor.extract_from_filename(file_path)

        if not parsed_dict or not parsed_dict.get("year"):
            logger.warning(f"Could not extract date from {file_path.name}, skipping")
            return {"status": "skipped", "reason": "no_date"}

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

        target_dir, filename, expected_path = self._build_target_path_info(metadata, category_with_prefix, pattern)

        # Skip if already in correct location
        if file_path.resolve() == expected_path.resolve():
            logger.debug(f"File already in correct location: {file_path}")
            return {"status": "skipped", "reason": "already_correct"}

        # Build change info
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

        if dry_run:
            return {"status": "reorganized", "change": change_info}

        # Perform the move
        logger.info(f"Reorganizing (from sidecar): {file_path} -> {expected_path}")

        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._get_unique_target_path(target_dir, filename)
        old_directories.add(file_path.parent)

        shutil.move(str(file_path), str(final_path))

        # Move sidecar file
        sidecar_path = file_path.with_suffix(file_path.suffix + ".curator_meta.json")
        if sidecar_path.exists():
            new_sidecar = final_path.with_suffix(final_path.suffix + ".curator_meta.json")
            shutil.move(str(sidecar_path), str(new_sidecar))

        # Move cover if exists
        current_cover = file_path.with_suffix(".jpg")
        if current_cover.exists():
            new_cover = final_path.with_suffix(".jpg")
            shutil.move(str(current_cover), str(new_cover))
            logger.info(f"Moved cover: {current_cover} -> {new_cover}")

        logger.info(f"Reorganized (from sidecar): {final_path}")
        return {"status": "reorganized", "change": change_info}
