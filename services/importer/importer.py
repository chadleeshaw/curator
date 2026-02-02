"""
File importer for processing PDFs from downloads folder.
Extracts cover art, categorizes files, and adds them to the database.
"""

import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.constants.app import DEFAULT_FUZZY_THRESHOLD
from core.constants.category import CATEGORY_KEYWORDS
from core.constants.date import DUPLICATE_DATE_THRESHOLD_DAYS
from core.constants.errors import ErrorCodes
from core.constants.language import DEFAULT_LANGUAGE
from core.parsers.country import ISO_COUNTRIES
from core.utils.general import generate_olid
from core.parsers import sanitize_filename
from core.parsers import TitleMatcher, FileCategorizer, Parser
from services.importer.matcher import TrackingMatcher
from services.importer.sidecar import read_sidecar_file, delete_sidecar_file
from core.utils.pdf import extract_cover_from_pdf
from core.utils.epub import extract_cover_from_epub
from core.utils.cbz import extract_cover_from_cbz, extract_cover_from_cbr
from core.utils.general import find_pdf_epub_files, hash_file_in_chunks
from services.response_models import OperationResult
from models.database import Periodical, PeriodicalTracking, OCRJob
from services.file_organizer import FileOrganizer
from services.ocr.service import OCRService
from services.ocr.queue import OCRQueueService
from services.text_scan_service import TextScanService

logger = logging.getLogger(__name__)


class FileImporter:
    """Import and process PDF files from downloads folder"""

    def __init__(
        self,
        downloads_dir: str,
        library_base_dir: str,
        *,
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
        organization_pattern: Optional[str] = None,
        category_prefix: str = "_",
        enable_text_scan: bool = True,
    ):
        """
        Initialize file importer.

        Args:
            downloads_dir: Directory to monitor for new PDFs
            library_base_dir: Base directory for library files (_Magazines for specific magazines, _Comics, etc.)
            fuzzy_threshold: Fuzzy matching threshold (0-100) for duplicate detection
            organization_pattern: Pattern for organizing files (e.g., "_{category}/{title}/{year}/")
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
            enable_text_scan: Enable direct text extraction from PDF/EPUB during import
        """
        self.downloads_dir = Path(downloads_dir)
        self.library_base_dir = Path(library_base_dir)
        self.organization_pattern = organization_pattern
        self.category_prefix = category_prefix
        self._enable_text_scan = enable_text_scan
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)
        self.tracking_matcher = TrackingMatcher()

        # Initialize specialized helpers
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.categorizer = FileCategorizer()
        self.organizer = FileOrganizer(self.library_base_dir, category_prefix=self.category_prefix)

        # Thread pool for CPU-intensive OCR tasks
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")

        self.library_base_dir.mkdir(parents=True, exist_ok=True)

        for category in CATEGORY_KEYWORDS.keys():
            category_dir = self.library_base_dir / f"{self.category_prefix}{category}"
            category_dir.mkdir(parents=True, exist_ok=True)

    def __del__(self):
        """Cleanup thread pool executor on deletion"""
        if hasattr(self, "_ocr_executor"):
            self._ocr_executor.shutdown(wait=False)

    def process_downloads(self, session: Session, organization_pattern: Optional[str] = None) -> Dict[str, Any]:
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
        cbz_files = [f for f in all_files if f.suffix == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix == ".cbr"]

        # Filter out files that are within the library_dir to prevent overlap
        # This prevents scanning the same files if library_dir is somehow nested in downloads_dir
        library_dir_resolved = self.library_base_dir.resolve()

        def is_in_library_dir(file_path: Path) -> bool:
            """Check if file is within the library directory"""
            try:
                file_resolved = file_path.resolve()
                return library_dir_resolved in file_resolved.parents or file_resolved == library_dir_resolved
            except Exception:
                return False

        pdf_files = [f for f in pdf_files if not is_in_library_dir(f)]
        epub_files = [f for f in epub_files if not is_in_library_dir(f)]
        cbz_files = [f for f in cbz_files if not is_in_library_dir(f)]
        cbr_files = [f for f in cbr_files if not is_in_library_dir(f)]

        all_files = pdf_files + epub_files + cbz_files + cbr_files

        if not all_files:
            logger.info(f"No PDF or EPUB files found in downloads folder: {self.downloads_dir}")
            return result.to_dict()

        logger.info(
            f"[DOWNLOADS IMPORT] Found {len(all_files)} files to process from {self.downloads_dir} "
            f"({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, {len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
        )
        logger.info("[DOWNLOADS IMPORT] Text extraction enabled, OCR queued only for image-based files")

        # Process all file types using unified handler
        self._process_file_batch(pdf_files, "PDF", session, organization_pattern, result)
        self._process_file_batch(epub_files, "EPUB", session, organization_pattern, result)
        self._process_file_batch(cbz_files, "CBZ", session, organization_pattern, result)
        self._process_file_batch(cbr_files, "CBR", session, organization_pattern, result)

        return result.to_dict()

    # =========================================================================
    # Import Helper Methods
    # =========================================================================

    def _get_tracking_context(
        self,
        pdf_path: Path,
        tracking_id: Optional[int],
        organization_pattern: Optional[str],
        session: Session,
    ) -> tuple[Optional[int], Optional[str]]:
        """
        Get tracking context from sidecar file and tracking record.

        Args:
            pdf_path: Path to the file being imported
            tracking_id: Explicitly provided tracking ID (or None)
            organization_pattern: Explicitly provided organization pattern (or None)
            session: Database session

        Returns:
            Tuple of (tracking_id, organization_pattern) with values from sidecar/tracking if available
        """
        # Check for sidecar metadata file first
        sidecar_metadata = read_sidecar_file(pdf_path)
        if sidecar_metadata and not tracking_id:
            tracking_id = sidecar_metadata.get("tracking_id")
            logger.debug(
                f"Found sidecar metadata for {pdf_path.name}: tracking_id={tracking_id}, "
                f"tracking_title='{sidecar_metadata.get('tracking_title')}'"
            )

        # Check if tracking record has a custom organization pattern
        if tracking_id and not organization_pattern:
            tracking_record = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
            if tracking_record and tracking_record.organization_pattern:
                organization_pattern = tracking_record.organization_pattern
                logger.debug(
                    f"Using per-periodical organization pattern for tracking_id={tracking_id}: {organization_pattern}"
                )

        return tracking_id, organization_pattern

    def _check_hash_duplicate(self, content_hash: str, pdf_path: Path, skip_organize: bool, session: Session) -> bool:
        """
        Check if file already exists in library by content hash.

        Args:
            content_hash: SHA256 hash of file content
            pdf_path: Path to the file being imported
            skip_organize: Whether to skip cleanup on duplicate
            session: Database session

        Returns:
            True if duplicate found (caller should skip import), False otherwise
        """
        existing_by_hash = (
            session.query(Periodical)
            .filter(
                Periodical.content_hash == content_hash,
                Periodical.content_hash.isnot(None),
            )
            .first()
        )
        if existing_by_hash:
            logger.info(f"File already in library: '{pdf_path.name}' (matches existing file by content hash)")
            if not skip_organize:
                self._cleanup_download_file(pdf_path)
            return True
        return False

    def _build_tracking_title(self, base_title: str, parsed_country: Optional[str], pdf_path: Path) -> str:
        """
        Build tracking title, appending country code for regional editions.

        Args:
            base_title: Base title from parser
            parsed_country: Country code from parser (or None)
            pdf_path: Original file path (for checking if country was in filename)

        Returns:
            Tracking title (with country code appended if applicable)
        """
        tracking_title = base_title

        # Skip if no country or universal/worldwide codes
        if not parsed_country or parsed_country in ["XU", "XW"]:
            return sanitize_filename(tracking_title) if tracking_title else tracking_title

        country_code = parsed_country
        filename_lower = pdf_path.stem.lower()
        country_name = ISO_COUNTRIES.get(parsed_country, parsed_country)

        # Check if country was explicitly in the filename
        country_name_in_filename = bool(re.search(rf"\b{re.escape(country_name.lower())}\b", filename_lower))
        country_code_in_filename = bool(re.search(rf"\b{re.escape(parsed_country.lower())}\b", filename_lower))
        country_in_filename = country_name_in_filename or country_code_in_filename

        # Append country code if it was in filename and not already in title
        if (
            country_in_filename
            and country_name.lower() not in base_title.lower()
            and parsed_country.lower() not in base_title.lower()
        ):
            tracking_title = f"{base_title} {country_code}"

        # Sanitize to ensure consistency between DB and filesystem
        return sanitize_filename(tracking_title) if tracking_title else tracking_title

    def _check_fuzzy_duplicate(
        self,
        tracking_title: str,
        parsed_issue_date: Optional[datetime],
        parsed_language: Optional[str],
        pdf_path: Path,
        skip_organize: bool,
        session: Session,
    ) -> bool:
        """
        Check for duplicate using fuzzy title matching and issue date.

        Args:
            tracking_title: Normalized tracking title
            parsed_issue_date: Issue date from parser
            parsed_language: Language from parser
            pdf_path: Path to file being imported
            skip_organize: Whether to skip cleanup on duplicate
            session: Database session

        Returns:
            True if duplicate found (caller should skip import), False otherwise
        """
        existing_magazines = session.query(Periodical).all()

        for existing in existing_magazines:
            # Normalize existing title for comparison
            existing_normalized = existing.title
            existing_metadata = existing.extra_metadata or {}
            existing_country = existing_metadata.get("country")

            if existing_country:
                country_name = ISO_COUNTRIES.get(existing_country, existing_country)
                if existing.title.endswith(f" {existing_country}"):
                    existing_normalized = existing.title[: -len(existing_country) - 1] + f" {country_name}"

            is_match, score = self.title_matcher.match(tracking_title, existing_normalized)

            if is_match and parsed_issue_date and existing.issue_date:
                date_diff = abs((parsed_issue_date - existing.issue_date).days)
                same_language = (existing.language == parsed_language) or (
                    not existing.language and parsed_language == DEFAULT_LANGUAGE
                )

                if date_diff <= DUPLICATE_DATE_THRESHOLD_DAYS and same_language:
                    logger.warning(
                        f"Duplicate detected: '{tracking_title}' ({parsed_issue_date.strftime('%b %Y')}, {parsed_language}) "
                        f"matches existing '{existing.title}' ({existing.issue_date.strftime('%b %Y')}, "
                        f"{existing.language or DEFAULT_LANGUAGE}) (title score: {score}, date diff: {date_diff} days). "
                        f"Skipping import."
                    )
                    if not skip_organize:
                        self._cleanup_download_file(pdf_path)
                    return True

        return False

    def _find_tracking_match(
        self,
        tracking_id: Optional[int],
        tracking_title: str,
        parsed_language: Optional[str],
        parsed_country: Optional[str],
        category: str,
        session: Session,
    ) -> Optional[PeriodicalTracking]:
        """
        Find the best matching tracking record.

        Args:
            tracking_id: Explicitly provided tracking ID (or None)
            tracking_title: Normalized tracking title
            parsed_language: Language from parser
            parsed_country: Country from parser
            category: Categorized category
            session: Database session

        Returns:
            Matching PeriodicalTracking record or None
        """
        target_tracking = None

        if tracking_id:
            target_tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
            if target_tracking:
                logger.info(
                    f"Using provided tracking_id={tracking_id} ('{target_tracking.title}') for '{tracking_title}'"
                )
            else:
                logger.warning(f"Provided tracking_id={tracking_id} not found, will try to find best match")

        if not target_tracking:
            all_tracking = session.query(PeriodicalTracking).all()
            if all_tracking:
                match_result = self.tracking_matcher.find_best_match(
                    parsed_title=tracking_title,
                    tracking_records=all_tracking,
                    parsed_language=parsed_language,
                    parsed_country=parsed_country,
                    parsed_category=category,
                )

                if match_result and match_result.is_match:
                    target_tracking = (
                        session.query(PeriodicalTracking)
                        .filter(PeriodicalTracking.id == match_result.tracking_id)
                        .first()
                    )
                    logger.info(
                        f"Matched '{tracking_title}' to existing tracking '{match_result.tracking_title}' "
                        f"(ID: {match_result.tracking_id}, score: {match_result.score})"
                    )

        return target_tracking

    def _link_or_create_tracking(
        self,
        magazine: Periodical,
        target_tracking: Optional[PeriodicalTracking],
        tracking_title: str,
        parsed_language: Optional[str],
        parsed_country: Optional[str],
        category: str,
        is_special_edition: bool,
        special_name: Optional[str],
        auto_track: bool,
        tracking_mode: str,
        session: Session,
    ) -> None:
        """
        Link magazine to existing tracking or create new tracking record.

        Args:
            magazine: The Periodical record to link
            target_tracking: Existing tracking match (or None)
            tracking_title: Normalized tracking title
            parsed_language: Language from parser
            parsed_country: Country from parser
            category: Categorized category
            is_special_edition: Whether this is a special edition
            special_name: Name of special edition (if applicable)
            auto_track: Whether to auto-create tracking records
            tracking_mode: Tracking mode for new records
            session: Database session
        """
        if target_tracking:
            magazine.tracking_id = target_tracking.id
            target_tracking.last_metadata_update = datetime.now()

            # Synchronize language between tracking and periodical
            if target_tracking.language:
                magazine.language = target_tracking.language
                logger.debug(
                    f"Synchronized language to '{target_tracking.language}' from tracking for: {target_tracking.title}"
                )
            elif parsed_language:
                target_tracking.language = parsed_language
                magazine.language = parsed_language
                logger.debug(
                    f"Set tracking and periodical language to '{parsed_language}' for: {target_tracking.title}"
                )

            logger.debug(f"Linked magazine to tracking: {target_tracking.title} (ID: {target_tracking.id})")

            # Add special edition to selected_editions if applicable
            if is_special_edition and special_name:
                if target_tracking.selected_editions is None:
                    target_tracking.selected_editions = {}
                if special_name not in target_tracking.selected_editions:
                    target_tracking.selected_editions[special_name] = True
                    logger.debug(f"Added special edition '{special_name}' to tracking: {target_tracking.title}")

        elif auto_track:
            olid = generate_olid(tracking_title)
            track_all_editions = tracking_mode == "all"
            track_new_only = tracking_mode == "new"

            new_tracking = PeriodicalTracking(
                olid=olid,
                title=tracking_title,
                language=parsed_language,
                country=parsed_country,
                category=category,
                track_all_editions=track_all_editions,
                track_new_only=track_new_only,
                selected_editions={},
                selected_years=[],
                last_metadata_update=datetime.now(),
            )
            session.add(new_tracking)
            session.flush()
            magazine.tracking_id = new_tracking.id
            logger.info(f"Created new tracking record: {tracking_title} (ID: {new_tracking.id}, mode: {tracking_mode})")

            if is_special_edition:
                logger.debug(f"Detected special edition '{special_name}' for: {tracking_title}")

    def _run_text_scan(
        self, magazine: Periodical, organized_path: Path, parsed_language: Optional[str], session: Session
    ) -> None:
        """
        Run direct text extraction on the imported file.

        Args:
            magazine: The Periodical record
            organized_path: Path to the organized file
            parsed_language: Language from parser
            session: Database session
        """
        if organized_path.suffix.lower() not in [".pdf", ".epub"]:
            return

        enable_text_scan = getattr(self, "_enable_text_scan", True)
        if not enable_text_scan:
            logger.debug("Text scanning disabled in config")
            return

        try:
            logger.debug(f"Attempting direct text extraction for {magazine.id}")
            scan_result = TextScanService.scan_document(str(organized_path), language=parsed_language)

            # Store text scan metadata
            if not magazine.parsed_metadata:
                magazine.parsed_metadata = {}
            magazine.parsed_metadata["text_scan"] = scan_result

            # Rebuild derived_metadata with text scan results
            from core.utils.metadata_builder import build_derived_metadata, sync_issue_date_from_derived

            magazine.derived_metadata = build_derived_metadata(
                file_scan=magazine.parsed_metadata.get("file_scan"),
                text_scan=scan_result,
                ocr_scan=magazine.parsed_metadata.get("ocr_scan"),
            )

            # Sync issue_date from derived_metadata
            new_issue_date = sync_issue_date_from_derived(magazine.derived_metadata)
            if new_issue_date:
                magazine.issue_date = new_issue_date
                logger.debug(f"Updated issue_date to {new_issue_date.strftime('%Y-%m')} from derived_metadata")

            if scan_result.get("text_found"):
                logger.info(f"Enhanced {magazine.title} with metadata from text scan")

            from core.utils.db import mark_json_modified

            mark_json_modified(magazine, "parsed_metadata", "derived_metadata")
            session.commit()

            if scan_result.get("text_found"):
                has_sufficient = scan_result.get("has_sufficient_metadata", False)
                logger.info(f"Successfully extracted text metadata for {magazine.title} (sufficient: {has_sufficient})")
            else:
                logger.debug(f"No text found in {organized_path.name}")

        except Exception as e:
            logger.debug(f"Direct text extraction failed for {magazine.id}: {e}")

    def _queue_ocr_job(
        self,
        magazine: Periodical,
        parsed_language: Optional[str],
        skip_organize: bool,
        session: Session,
    ) -> None:
        """
        Queue OCR job for background processing.

        Args:
            magazine: The Periodical record
            parsed_language: Language from parser
            skip_organize: Whether this was a skip_organize import
            session: Database session
        """
        try:
            priority = OCRJob.PriorityEnum.HIGH.value if not skip_organize else OCRJob.PriorityEnum.NORMAL.value
            ocr_job = OCRQueueService.queue_ocr_job(
                db=session,
                periodical_id=magazine.id,
                priority=priority,
                language=parsed_language,
            )
            if ocr_job:
                logger.info(f"Queued OCR job {ocr_job.id} for magazine {magazine.id}")
        except Exception as e:
            logger.warning(f"Failed to queue OCR job for magazine {magazine.id}: {e}")

    # =========================================================================
    # Main Import Method
    # =========================================================================

    def import_pdf(
        self,
        pdf_path: Path,
        session: Session,
        *,
        organization_pattern: Optional[str] = None,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        tracking_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Import a single PDF file.

        Args:
            pdf_path: Path to PDF file
            session: Database session
            organization_pattern: Optional custom organization pattern with tags like {category}, {title}, {year}
            auto_track: Whether to auto-create tracking records for imported periodicals
            skip_organize: If True, skip file organization and use file in place (for already-library files)
            tracking_mode: Tracking mode - "all" (track all editions), "new" (track new only), "watch" (watch only), "none" (no tracking)
            use_ocr: Whether to use OCR for metadata extraction (default: True, set False for faster batch imports)
            tracking_id: Optional tracking ID to associate this file with (from DownloadSubmission)

        Returns:
            Dictionary with result information including magazine_id, or empty dict if failed
        """
        try:
            # Step 1: Get tracking context from sidecar and tracking record
            tracking_id, organization_pattern = self._get_tracking_context(
                pdf_path, tracking_id, organization_pattern, session
            )

            # Step 2: Parse file and validate
            parsed = self.parser.parse_file(pdf_path)
            if not self.title_matcher.validate_before_parsing(parsed.title):
                logger.warning(f"Skipping invalid release title: {parsed.title} (from {pdf_path.name})")
                return {}
            logger.debug(f"Parsed metadata: '{parsed.title}' (confidence: {parsed.confidence})")

            # Step 3: Calculate content hash and check for hash-based duplicates
            content_hash = hash_file_in_chunks(str(pdf_path))
            if not content_hash:
                logger.error(f"Failed to hash file {pdf_path}, skipping import", exc_info=True)
                return {}

            if self._check_hash_duplicate(content_hash, pdf_path, skip_organize, session):
                return {}

            # Step 4: Build tracking title with country code if applicable
            tracking_title = self._build_tracking_title(parsed.base_title, parsed.country, pdf_path)

            # Step 5: Check for fuzzy duplicates
            if self._check_fuzzy_duplicate(
                tracking_title, parsed.issue_date, parsed.language, pdf_path, skip_organize, session
            ):
                return {}

            # Step 6: Determine category and find tracking match
            category = self.categorizer.categorize(parsed.title)
            target_tracking = self._find_tracking_match(
                tracking_id, tracking_title, parsed.language, parsed.country, category, session
            )

            # Step 7: Organize file (use tracking title for folder consistency)
            organization_title = target_tracking.title if target_tracking else tracking_title
            cover_path = self._extract_cover(pdf_path)
            should_queue_ocr = use_ocr and (cover_path or pdf_path) and OCRService.is_available()

            if skip_organize:
                organized_path = pdf_path
                logger.info(f"Using file in place (already in library): {pdf_path}")
            else:
                metadata = {
                    "title": organization_title,
                    "issue_date": parsed.issue_date,
                    "year": parsed.year,
                    "month_name": parsed.month_name,
                    "language": parsed.language,
                }
                organized_path = self.organizer.organize(pdf_path, metadata, category, organization_pattern)
                if not organized_path:
                    return {}

            # Step 8: Build metadata and create database record
            from core.utils.metadata_builder import (
                build_file_scan,
                build_parsed_metadata,
                build_derived_metadata,
                build_extra_metadata,
            )

            file_scan = build_file_scan(parsed)
            if parsed.is_special_edition:
                file_scan["special_edition_name"] = parsed.special_edition_name
                file_scan["is_special_edition"] = True

            magazine = Periodical(
                title=organization_title,
                issue_date=parsed.issue_date or datetime.now(),
                language=parsed.language or DEFAULT_LANGUAGE,
                file_path=str(organized_path),
                cover_path=str(cover_path) if cover_path else None,
                content_hash=content_hash,
                parsed_metadata=build_parsed_metadata(file_scan=file_scan),
                derived_metadata=build_derived_metadata(file_scan=file_scan),
                extra_metadata=build_extra_metadata(
                    imported_from=pdf_path.name,
                    import_date=datetime.now().isoformat(),
                    category=category,
                    import_method="auto",
                ),
            )
            session.add(magazine)

            # Step 9: Link to existing tracking or create new one
            self._link_or_create_tracking(
                magazine=magazine,
                target_tracking=target_tracking,
                tracking_title=tracking_title,
                parsed_language=parsed.language,
                parsed_country=parsed.country,
                category=category,
                is_special_edition=parsed.is_special_edition,
                special_name=parsed.special_edition_name,
                auto_track=auto_track,
                tracking_mode=tracking_mode,
                session=session,
            )

            session.commit()
            logger.info(f"Added to database: {parsed.title} ({category})")

            # Step 10: Run text scan for additional metadata
            self._run_text_scan(magazine, organized_path, parsed.language, session)

            # Step 11: Queue OCR job for background processing
            if should_queue_ocr:
                self._queue_ocr_job(magazine, parsed.language, skip_organize, session)

            # Step 12: Cleanup download file
            if not skip_organize:
                self._cleanup_download_file(pdf_path)

            return {"periodical_id": magazine.id}

        except Exception as e:
            session.rollback()
            logger.error(f"Error importing PDF {pdf_path}: {e}", exc_info=True)
            return {}

    def _process_file_batch(
        self,
        files: list,
        file_type: str,
        session: Session,
        organization_pattern: Optional[str],
        result: OperationResult,
    ) -> None:
        """
        Process a batch of files of the same type.

        Args:
            files: List of Path objects to process
            file_type: File type label for logging (e.g., "PDF", "EPUB", "CBZ", "CBR")
            session: Database session
            organization_pattern: Optional organization pattern
            result: OperationResult to update with counts and errors
        """
        for file_path in files:
            try:
                import_result = self.import_pdf(
                    file_path,
                    session,
                    organization_pattern=organization_pattern,
                    use_ocr=True,
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported {file_type}: {file_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import {file_type} {file_path.name}",
                        retryable=True,
                    )
                    logger.info(f"Cleaning up failed {file_type} import: {file_path.name}")
                    self._cleanup_download_file(file_path)
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing {file_type} {file_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                try:
                    self._cleanup_download_file(file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup {file_path.name}: {cleanup_error}")

    def _cleanup_download_file(self, pdf_path: Path) -> None:
        """
        Clean up a file from downloads folder and its parent directory.
        Also removes sidecar metadata file if present.

        This removes the entire download directory (e.g., the SABnzbd/NZBGet folder)
        including any leftover files like .nzb, .par2, .nfo, etc.

        Args:
            pdf_path: Path to PDF file in downloads folder
        """
        try:
            # Delete sidecar metadata file if it exists
            delete_sidecar_file(pdf_path)

            if pdf_path.exists() and pdf_path.is_file():
                pdf_path.unlink()
                logger.info(f"Deleted file from downloads: {pdf_path.name}")

            # Cleanup parent directory (including any leftover files) if within downloads
            parent_dir = pdf_path.parent
            if parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir):
                if parent_dir.exists():
                    # Remove directory and all its contents (e.g., .nzb, .par2, .nfo files)
                    shutil.rmtree(parent_dir)
                    logger.info(f"Deleted download folder and contents: {parent_dir.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup download file: {e}")

    def _extract_cover(self, file_path: Path) -> Optional[Path]:
        """
        Extract cover image from PDF or EPUB file.
        Uses higher DPI when OCR is available for better text extraction.

        Args:
            file_path: Path to PDF or EPUB file

        Returns:
            Path to extracted cover image, or None if failed
        """
        from core.constants.files import PDF_COVER_QUALITY_HIGH
        from core.constants.ocr import PDF_COVER_DPI_OCR

        cover_dir = self.library_base_dir / ".covers"
        extension = file_path.suffix.lower()

        if extension == ".pdf":
            # Use higher DPI for OCR if available
            if OCRService.is_available():
                return extract_cover_from_pdf(
                    file_path,
                    cover_dir,
                    dpi=PDF_COVER_DPI_OCR,
                    quality=PDF_COVER_QUALITY_HIGH,
                )
            return extract_cover_from_pdf(file_path, cover_dir)
        elif extension == ".epub":
            return extract_cover_from_epub(file_path, cover_dir)
        elif extension == ".cbz":
            return extract_cover_from_cbz(file_path, cover_dir)
        elif extension == ".cbr":
            return extract_cover_from_cbr(file_path, cover_dir)
        else:
            logger.warning(f"Unsupported file type for cover extraction: {file_path.suffix}")
            return None

    def process_organized_files(
        self, session: Session, auto_track: bool = True, tracking_mode: str = "all"
    ) -> Dict[str, Any]:
        """
        Process PDF files from library folders (e.g., _Magazines, _Comics, _Articles, _News).
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

        if not self.library_base_dir.exists():
            logger.warning(f"Library directory not found: {self.library_base_dir}")
            result.add_error(
                ErrorCodes.FILE_NOT_FOUND,
                f"Library directory not found: {self.library_base_dir}",
                retryable=False,
            )
            return result.to_dict()

        all_files = find_pdf_epub_files(self.library_base_dir, recursive=True)

        if not all_files:
            logger.info(f"No periodical files found in library folders: {self.library_base_dir}")
            return result.to_dict()

        pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower() == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower() == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix.lower() == ".cbr"]

        logger.info(
            f"[DATA IMPORT] Found {len(all_files)} files in library folders to process "
            f"from {self.library_base_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, "
            f"{len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
        )
        logger.info("[DATA IMPORT] OCR disabled for library imports - will run during next scheduled OCR task")

        for pdf_path in all_files:
            try:
                import_result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=None,
                    auto_track=auto_track,
                    skip_organize=True,
                    tracking_mode=tracking_mode,
                    use_ocr=False,  # Don't queue OCR during library imports
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported library file: {pdf_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import {pdf_path.name}",
                        retryable=True,
                    )
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing library file {pdf_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)

        return result.to_dict()


# Export all public items for wildcard imports
__all__ = ["FileImporter"]
