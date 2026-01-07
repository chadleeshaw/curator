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
from core.matching import TitleMatcher
from core.pdf_utils import extract_cover_from_pdf
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
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
        organization_pattern: Optional[str] = None,
    ):
        """
        Initialize file importer.

        Args:
            downloads_dir: Directory to monitor for new PDFs
            organize_base_dir: Base directory for organized files (_Magazines for specific magazines, _Comics, etc.)
            fuzzy_threshold: Fuzzy matching threshold (0-100) for duplicate detection
            organization_pattern: Pattern for organizing files (e.g., "_{category}/{title}/{year}/")
        """
        self.downloads_dir = Path(downloads_dir)
        self.organize_base_dir = Path(organize_base_dir)
        self.organization_pattern = organization_pattern
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

        # Initialize specialized helpers
        self.metadata_extractor = MetadataExtractor()
        self.categorizer = FileCategorizer()
        self.organizer = FileOrganizer(self.organize_base_dir)

        self.organize_base_dir.mkdir(parents=True, exist_ok=True)

        for category in CATEGORY_KEYWORDS.keys():
            category_dir = self.organize_base_dir / f"_{category}"
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
            Dict with import results
        """
        results = {"imported": 0, "failed": 0, "errors": []}

        if not self.downloads_dir.exists():
            logger.warning(f"Downloads directory not found: {self.downloads_dir}")
            return results

        pdf_files = list(self.downloads_dir.glob("**/*.pdf"))
        epub_files = list(self.downloads_dir.glob("**/*.epub"))

        # Filter out files that are within the organize_dir to prevent overlap
        # This prevents scanning the same files if organize_dir is somehow nested in downloads_dir
        organize_dir_resolved = self.organize_base_dir.resolve()

        def is_in_organize_dir(file_path: Path) -> bool:
            """Check if file is within the organize directory"""
            try:
                file_resolved = file_path.resolve()
                return organize_dir_resolved in file_resolved.parents or file_resolved == organize_dir_resolved
            except Exception:
                return False

        pdf_files = [f for f in pdf_files if not is_in_organize_dir(f)]
        epub_files = [f for f in epub_files if not is_in_organize_dir(f)]

        all_files = pdf_files + epub_files

        if not all_files:
            logger.info(f"No PDF or EPUB files found in downloads folder: {self.downloads_dir}")
            return results

        logger.info(f"[DOWNLOADS IMPORT] Found {len(all_files)} files to process from {self.downloads_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)")

        for pdf_path in pdf_files:
            try:
                result = self.import_pdf(
                    pdf_path, session, organization_pattern=organization_pattern
                )
                if result:
                    results["imported"] += 1
                    logger.info(f"Successfully imported: {pdf_path.name}")
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Failed to import {pdf_path.name}")
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Error importing {pdf_path.name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg, exc_info=True)

        # Process EPUB files (convert to PDF first)
        for epub_path in epub_files:
            try:
                logger.info(f"Converting EPUB to PDF: {epub_path.name}")
                # TODO: Add EPUB to PDF conversion
                # For now, just log that EPUBs are found
                results["errors"].append(f"EPUB support coming soon: {epub_path.name}")
                logger.warning(f"EPUB files not yet supported, skipping: {epub_path.name}")
            except Exception as e:
                error_msg = f"Error processing EPUB {epub_path.name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg, exc_info=True)

        return results

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
            standardized_title = self.title_matcher.standardize_title(raw_title)
            metadata["title"] = standardized_title

            # Check for duplicates using fuzzy matching on standardized titles AND issue date
            # A duplicate is defined as: same title (fuzzy match) AND same issue date (within 5 days)
            existing_magazines = session.query(Magazine).all()
            issue_date = metadata.get("issue_date")
            for existing in existing_magazines:
                is_match, score = self.title_matcher.match(
                    standardized_title, existing.title
                )
                if is_match and issue_date and existing.issue_date:
                    date_diff = abs((issue_date - existing.issue_date).days)
                    if date_diff <= DUPLICATE_DATE_THRESHOLD_DAYS:
                        logger.warning(
                            f"Duplicate detected: '{standardized_title}' ({issue_date.strftime('%b %Y')}) matches existing "
                            f"'{existing.title}' ({existing.issue_date.strftime('%b %Y')}) "
                            f"(title score: {score}, date diff: {date_diff} days). Skipping import."
                        )
                        return False

            cover_path = self._extract_cover(pdf_path)

            category = self.categorizer.categorize(standardized_title)

            if skip_organize:
                organized_path = pdf_path
                logger.info(f"Using file in place (already organized): {pdf_path}")
            else:
                organized_path = self.organizer.organize(
                    pdf_path, metadata, category, organization_pattern
                )

                if not organized_path:
                    return False

            magazine = Magazine(
                title=standardized_title,
                publisher=metadata.get("publisher"),
                issue_date=metadata.get("issue_date", datetime.now()),
                file_path=str(organized_path),
                cover_path=str(cover_path) if cover_path else None,
                extra_metadata={
                    "category": category,
                    "imported_from": pdf_path.name,
                    "import_date": datetime.now().isoformat(),
                },
            )

            session.add(magazine)
            session.commit()

            logger.info(f"Added to database: {standardized_title} ({category})")

            # Manage tracking record based on import settings
            olid = standardized_title.lower().replace(" ", "_").replace("-", "_")
            existing_tracking = (
                session.query(MagazineTracking)
                .filter(MagazineTracking.olid == olid)
                .first()
            )

            if auto_track:
                if not existing_tracking:
                    track_all_editions = tracking_mode == "all"
                    track_new_only = tracking_mode == "new"
                    # watch mode means track_all_editions=False and track_new_only=False

                    tracking = MagazineTracking(
                        olid=olid,
                        title=standardized_title,
                        publisher=metadata.get("publisher"),
                        track_all_editions=track_all_editions,
                        track_new_only=track_new_only,
                        selected_editions={},
                        selected_years=[],
                        last_metadata_update=datetime.now(),
                    )
                    session.add(tracking)
                    session.commit()
                    logger.info(f"Created tracking record for: {standardized_title} (mode: {tracking_mode})")
                else:
                    existing_tracking.track_all_editions = tracking_mode == "all"
                    existing_tracking.track_new_only = tracking_mode == "new"
                    existing_tracking.last_metadata_update = datetime.now()
                    session.commit()
                    logger.info(f"Updated tracking record for: {standardized_title} (mode: {tracking_mode})")
            else:
                if existing_tracking:
                    session.delete(existing_tracking)
                    session.commit()
                    logger.info(f"Removed tracking record for: {standardized_title} (tracking disabled)")

            # Delete the original PDF from downloads folder after successful import
            # (but only if we organized/moved it)
            if not skip_organize:
                try:
                    pdf_path.unlink()
                    logger.info(f"Deleted original PDF from downloads: {pdf_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original PDF {pdf_path.name}: {e}")

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
            Dict with import results
        """
        results = {"imported": 0, "failed": 0, "skipped": 0, "errors": []}

        if not self.organize_base_dir.exists():
            logger.warning(f"Organize directory not found: {self.organize_base_dir}")
            return results

        pdf_files = list(self.organize_base_dir.glob("**/*.pdf"))

        if not pdf_files:
            logger.info(f"No PDF files found in organized folders: {self.organize_base_dir}")
            return results

        logger.info(f"[DATA IMPORT] Found {len(pdf_files)} PDF files in organized folders to process from {self.organize_base_dir}")

        for pdf_path in pdf_files:
            try:
                result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=None,
                    auto_track=auto_track,
                    skip_organize=True,
                    tracking_mode=tracking_mode,
                )
                if result:
                    results["imported"] += 1
                    logger.info(
                        f"Successfully imported organized file: {pdf_path.name}"
                    )
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Failed to import {pdf_path.name}")
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Error importing organized file {pdf_path.name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg, exc_info=True)

        return results
