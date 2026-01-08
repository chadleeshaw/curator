"""
File importer for processing PDFs from downloads folder.
Extracts cover art, categorizes files, and adds them to the database.
"""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.constants import (
    CATEGORY_KEYWORDS,
    DEFAULT_FUZZY_THRESHOLD,
    DUPLICATE_DATE_THRESHOLD_DAYS,
)
from core.language_utils import detect_language, generate_language_aware_olid
from core.matching import TitleMatcher
from core.pdf_utils import extract_cover_from_pdf
from core.utils import find_pdf_epub_files, hash_file_in_chunks
from core.response_models import ErrorCodes, OperationResult
from models.database import Magazine, MagazineTracking
from processor.categorizer import FileCategorizer
from processor.metadata_extractor import MetadataExtractor
from processor.organizer import FileOrganizer

logger = logging.getLogger(__name__)


class FileImporter:
    """Import and process PDF files from downloads folder"""

    def __init__(
        self,
        downloads_dir: str,
        organize_base_dir: str,
        *,
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
        organization_pattern: Optional[str] = None,
        category_prefix: str = "_",
    ):
        """
        Initialize file importer.

        Args:
            downloads_dir: Directory to monitor for new PDFs
            organize_base_dir: Base directory for organized files (_Magazines for specific magazines, _Comics, etc.)
            fuzzy_threshold: Fuzzy matching threshold (0-100) for duplicate detection
            organization_pattern: Pattern for organizing files (e.g., "_{category}/{title}/{year}/")
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
        """
        self.downloads_dir = Path(downloads_dir)
        self.organize_base_dir = Path(organize_base_dir)
        self.organization_pattern = organization_pattern
        self.category_prefix = category_prefix
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

        # Initialize specialized helpers
        self.metadata_extractor = MetadataExtractor()
        self.categorizer = FileCategorizer()
        self.organizer = FileOrganizer(
            self.organize_base_dir, category_prefix=self.category_prefix
        )

        self.organize_base_dir.mkdir(parents=True, exist_ok=True)

        for category in CATEGORY_KEYWORDS.keys():
            category_dir = self.organize_base_dir / f"{self.category_prefix}{category}"
            category_dir.mkdir(parents=True, exist_ok=True)

    def process_downloads(
        self, session: Session, organization_pattern: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scan downloads folder and process any PDFs found.

        Args:
            session: Database session
            organization_pattern: Optional custom organization pattern with tags like {category}, {title}, {year}

        Returns:
            Dict with import results in standardized format
        """
        result = OperationResult()
        result.add_count("imported", 0)
        result.add_count("failed", 0)
        result.add_count("skipped", 0)

        if not self.downloads_dir.exists():
            logger.warning(f"Downloads directory not found: {self.downloads_dir}")
            result.add_error(
                ErrorCodes.FILE_NOT_FOUND,
                f"Downloads directory not found: {self.downloads_dir}",
                retryable=False,
            )
            return result.to_dict()

        all_files = find_pdf_epub_files(self.downloads_dir, recursive=True)
        pdf_files = [f for f in all_files if f.suffix == ".pdf"]
        epub_files = [f for f in all_files if f.suffix == ".epub"]

        # Filter out files that are within the organize_dir to prevent overlap
        # This prevents scanning the same files if organize_dir is somehow nested in downloads_dir
        organize_dir_resolved = self.organize_base_dir.resolve()

        def is_in_organize_dir(file_path: Path) -> bool:
            """Check if file is within the organize directory"""
            try:
                file_resolved = file_path.resolve()
                return (
                    organize_dir_resolved in file_resolved.parents
                    or file_resolved == organize_dir_resolved
                )
            except Exception:
                return False

        pdf_files = [f for f in pdf_files if not is_in_organize_dir(f)]
        epub_files = [f for f in epub_files if not is_in_organize_dir(f)]

        all_files = pdf_files + epub_files

        if not all_files:
            logger.info(
                f"No PDF or EPUB files found in downloads folder: {self.downloads_dir}"
            )
            return result.to_dict()

        logger.info(
            f"[DOWNLOADS IMPORT] Found {len(all_files)} files to process from {self.downloads_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)"
        )

        for pdf_path in pdf_files:
            try:
                import_result = self.import_pdf(
                    pdf_path, session, organization_pattern=organization_pattern
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported: {pdf_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import {pdf_path.name}",
                        retryable=True,
                    )
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing {pdf_path.name}: {str(e)}"
                result.add_error(
                    ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True
                )
                logger.error(error_msg, exc_info=True)

        # Process EPUB files (convert to PDF first)
        for epub_path in epub_files:
            try:
                logger.info(f"Converting EPUB to PDF: {epub_path.name}")
                result.data["skipped"] += 1
                result.add_error(
                    ErrorCodes.PROCESSING_FAILED,
                    f"EPUB support coming soon: {epub_path.name}",
                    retryable=False,
                )
                logger.warning(
                    f"EPUB files not yet supported, skipping: {epub_path.name}"
                )
            except Exception as e:
                error_msg = f"Error processing EPUB {epub_path.name}: {str(e)}"
                result.add_error(
                    ErrorCodes.PROCESSING_FAILED, error_msg, retryable=False
                )
                logger.error(error_msg, exc_info=True)

        return result.to_dict()

    def import_pdf(
        self,
        pdf_path: Path,
        session: Session,
        *,
        organization_pattern: Optional[str] = None,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "all",
    ) -> bool:
        """
        Import a single PDF file.

        Args:
            pdf_path: Path to PDF file
            session: Database session
            organization_pattern: Optional custom organization pattern with tags like {category}, {title}, {year}
            auto_track: Whether to auto-create tracking records for imported periodicals
            skip_organize: If True, skip file organization and use file in place (for already-organized files)
            tracking_mode: Tracking mode - "all" (track all editions), "new" (track new only), "watch" (watch only), "none" (no tracking)

        Returns:
            True if successful, False otherwise
        """
        try:
            metadata = self.metadata_extractor.extract_from_filename(pdf_path)

            raw_title = metadata.get("title", "")

            # Step 1: Validate title before processing (Readarr-inspired)
            if not self.title_matcher.validate_before_parsing(raw_title):
                logger.warning(
                    f"Skipping invalid release title: {raw_title} (from {pdf_path.name})"
                )
                return False

            # Step 2: Clean release title (now includes formatting)
            standardized_title = self.title_matcher.clean_release_title(raw_title)
            logger.debug(f"Cleaned and formatted title: '{raw_title}' -> '{standardized_title}'")

            metadata["title"] = standardized_title

            # Detect language from filename/path
            language = detect_language(str(pdf_path))
            metadata["language"] = language

            # Calculate content hash for duplicate detection
            content_hash = hash_file_in_chunks(str(pdf_path))
            if not content_hash:
                logger.error(f"Failed to hash file {pdf_path}, skipping import")
                return False

            # First check: hash-based duplicate detection (100% accurate)
            existing_by_hash = (
                session.query(Magazine)
                .filter(Magazine.content_hash == content_hash)
                .first()
            )
            if existing_by_hash:
                logger.warning(
                    f"Duplicate detected (identical file): '{pdf_path.name}' matches existing "
                    f"'{existing_by_hash.title}' at {existing_by_hash.file_path}. Skipping import."
                )
                return False

            # Check if this is a special edition and determine the tracking title
            # Do this BEFORE duplicate checking so we compare tracking titles
            base_title, is_special_edition, special_name = (
                self.title_matcher.extract_base_title(standardized_title)
            )

            # For non-English editions, append language to tracking title
            # Always use base_title for tracking to group all issues of the same periodical
            tracking_title = base_title
            if language and language != "English":
                # Check if language is already in the title (e.g., "Wired - German")
                if not re.search(rf"\b{language}\b", tracking_title, re.IGNORECASE):
                    tracking_title = f"{tracking_title} - {language}"

            # Check for duplicates using fuzzy matching on tracking titles AND issue date
            # A duplicate is defined as: same tracking title (fuzzy match) AND same issue date (within 5 days)
            existing_magazines = session.query(Magazine).all()
            issue_date = metadata.get("issue_date")
            for existing in existing_magazines:
                is_match, score = self.title_matcher.match(
                    tracking_title, existing.title
                )
                if is_match and issue_date and existing.issue_date:
                    date_diff = abs((issue_date - existing.issue_date).days)
                    # Also check language match for duplicates
                    same_language = (existing.language == language) or (
                        not existing.language and language == "English"
                    )
                    if date_diff <= DUPLICATE_DATE_THRESHOLD_DAYS and same_language:
                        logger.warning(
                            f"Duplicate detected: '{tracking_title}' ({issue_date.strftime('%b %Y')}, {language}) matches existing "
                            f"'{existing.title}' ({existing.issue_date.strftime('%b %Y')}, {existing.language or 'English'}) "
                            f"(title score: {score}, date diff: {date_diff} days). Skipping import."
                        )
                        return False

            cover_path = self._extract_cover(pdf_path)

            category = self.categorizer.categorize(standardized_title)

            if skip_organize:
                organized_path = pdf_path
                logger.info(f"Using file in place (already organized): {pdf_path}")
            else:
                # Update metadata title to tracking_title for proper folder organization
                metadata["title"] = tracking_title
                organized_path = self.organizer.organize(
                    pdf_path, metadata, category, organization_pattern
                )

                if not organized_path:
                    return False

            # Build extra metadata, including special edition info if applicable
            extra_metadata = {
                "category": category,
                "imported_from": pdf_path.name,
                "import_date": datetime.now().isoformat(),
            }
            if is_special_edition:
                extra_metadata["special_edition"] = special_name
                extra_metadata["full_title"] = standardized_title

            magazine = Magazine(
                title=tracking_title,
                publisher=metadata.get("publisher"),
                issue_date=metadata.get("issue_date", datetime.now()),
                file_path=str(organized_path),
                cover_path=str(cover_path) if cover_path else None,
                content_hash=content_hash,
                extra_metadata=extra_metadata,
            )

            session.add(magazine)

            # Manage tracking record based on import settings

            # Generate OLID from tracking title (with language if applicable)
            olid = tracking_title.lower().replace(" ", "_").replace("-", "_")
            existing_tracking = (
                session.query(MagazineTracking)
                .filter(MagazineTracking.olid == olid)
                .first()
            )

            if auto_track:
                if not existing_tracking:
                    track_all_editions = tracking_mode == "all"
                    track_new_only = tracking_mode == "new"

                    tracking = MagazineTracking(
                        olid=olid,
                        title=tracking_title,
                        publisher=metadata.get("publisher"),
                        track_all_editions=track_all_editions,
                        track_new_only=track_new_only,
                        selected_editions={},
                        selected_years=[],
                        last_metadata_update=datetime.now(),
                    )
                    session.add(tracking)
                    logger.debug(
                        f"Will create tracking record for: {tracking_title} (mode: {tracking_mode})"
                    )

                    # If this is a special edition, add it to the selected_editions
                    if is_special_edition:
                        logger.debug(
                            f"Detected special edition '{special_name}' for: {tracking_title}"
                        )
                else:
                    existing_tracking.track_all_editions = tracking_mode == "all"
                    existing_tracking.track_new_only = tracking_mode == "new"
                    existing_tracking.last_metadata_update = datetime.now()
                    logger.debug(
                        f"Will update tracking record for: {tracking_title} (mode: {tracking_mode})"
                    )

                    # If this is a special edition, ensure it's in the selected_editions
                    if is_special_edition and special_name:
                        if existing_tracking.selected_editions is None:
                            existing_tracking.selected_editions = {}
                        # Add this special edition if not already tracked
                        if special_name not in existing_tracking.selected_editions:
                            existing_tracking.selected_editions[special_name] = True
                            logger.debug(
                                f"Added special edition '{special_name}' to tracking record: {tracking_title}"
                            )

            else:
                if existing_tracking:
                    session.delete(existing_tracking)
                    logger.debug(
                        f"Will remove tracking record for: {tracking_title} (tracking disabled)"
                    )

            session.commit()
            logger.info(f"Added to database: {standardized_title} ({category})")

            if not skip_organize:
                try:
                    parent_dir = pdf_path.parent

                    if pdf_path.exists() and pdf_path.is_file():
                        pdf_path.unlink()
                        logger.info(
                            f"Deleted original PDF from downloads: {pdf_path.name}"
                        )

                    if parent_dir != self.downloads_dir and parent_dir.is_relative_to(
                        self.downloads_dir
                    ):
                        if parent_dir.exists():
                            shutil.rmtree(parent_dir)
                            logger.info(f"Deleted download folder: {parent_dir.name}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup download files: {e}")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error importing PDF {pdf_path}: {e}", exc_info=True)
            return False

    def _extract_cover(self, pdf_path: Path) -> Optional[Path]:
        """
        Extract first page of PDF as cover image.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Path to extracted cover image, or None if failed
        """
        cover_dir = self.organize_base_dir / ".covers"
        return extract_cover_from_pdf(pdf_path, cover_dir)

    def process_organized_files(
        self, session: Session, auto_track: bool = True, tracking_mode: str = "all"
    ) -> Dict[str, Any]:
        """
        Process PDF files from organized folders (e.g., _Magazines, _Comics, _Articles, _News).
        These are files that have been manually placed or previously organized.

        Args:
            session: Database session
            auto_track: Whether to auto-create tracking records for imported periodicals
            tracking_mode: Tracking mode - "all" (track all editions), "new" (track new only), "watch" (watch only), "none" (no tracking)

        Returns:
            Dict with import results in standardized format
        """
        result = OperationResult()
        result.add_count("imported", 0)
        result.add_count("failed", 0)
        result.add_count("skipped", 0)

        if not self.organize_base_dir.exists():
            logger.warning(f"Organize directory not found: {self.organize_base_dir}")
            result.add_error(
                ErrorCodes.FILE_NOT_FOUND,
                f"Organize directory not found: {self.organize_base_dir}",
                retryable=False,
            )
            return result.to_dict()

        all_files = find_pdf_epub_files(self.organize_base_dir, recursive=True)
        pdf_files = [f for f in all_files if f.suffix == ".pdf"]

        if not pdf_files:
            logger.info(
                f"No PDF files found in organized folders: {self.organize_base_dir}"
            )
            return result.to_dict()

        logger.info(
            f"[DATA IMPORT] Found {len(pdf_files)} PDF files in organized folders to process from {self.organize_base_dir}"
        )

        for pdf_path in pdf_files:
            try:
                import_result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=None,
                    auto_track=auto_track,
                    skip_organize=True,
                    tracking_mode=tracking_mode,
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(
                        f"Successfully imported organized file: {pdf_path.name}"
                    )
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import {pdf_path.name}",
                        retryable=True,
                    )
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing organized file {pdf_path.name}: {str(e)}"
                result.add_error(
                    ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True
                )
                logger.error(error_msg, exc_info=True)

        return result.to_dict()
