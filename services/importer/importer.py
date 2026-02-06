"""
File importer for processing PDFs from downloads folder.
Extracts cover art, categorizes files, and adds them to the database.
"""

import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session, sessionmaker

from core.constants.app import DEFAULT_FUZZY_THRESHOLD
from core.constants.category import CATEGORY_KEYWORDS
from core.constants.date import DUPLICATE_DATE_THRESHOLD_DAYS
from core.constants.errors import ErrorCodes
from core.constants.files import IMPORT_MARKER_FILE, SUPPORTED_FILE_EXTENSIONS
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
from core.utils.general import find_supported_files, hash_file_in_chunks
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
        session_factory: Optional[sessionmaker] = None,
        parallel_workers: int = 2,
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
            session_factory: SQLAlchemy session factory for parallel processing
            parallel_workers: Number of parallel workers for file processing (default: 2)
        """
        self.downloads_dir = Path(downloads_dir)
        self.library_base_dir = Path(library_base_dir)
        self.organization_pattern = organization_pattern
        self.category_prefix = category_prefix
        self._enable_text_scan = enable_text_scan
        self._session_factory = session_factory
        self._parallel_workers = max(1, parallel_workers)
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)
        self.tracking_matcher = TrackingMatcher()

        # Initialize specialized helpers
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.categorizer = FileCategorizer()
        self.organizer = FileOrganizer(self.library_base_dir, category_prefix=self.category_prefix)

        # Thread pool for CPU-intensive OCR tasks
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")

        # Thread-safe folder marker reference counting
        self._folder_marker_lock = threading.Lock()
        self._folder_marker_refs: Dict[Path, int] = defaultdict(int)

        self.library_base_dir.mkdir(parents=True, exist_ok=True)

        for category in CATEGORY_KEYWORDS.keys():
            category_dir = self.library_base_dir / f"{self.category_prefix}{category}"
            category_dir.mkdir(parents=True, exist_ok=True)

    def __del__(self):
        """Cleanup thread pool executor on deletion"""
        if hasattr(self, "_ocr_executor"):
            self._ocr_executor.shutdown(wait=False)

    def _create_import_marker(self, folder: Path) -> bool:
        """
        Create a marker file to indicate import is in progress.
        This prevents folder cleanup from deleting folders while files are being processed.

        Args:
            folder: Folder to mark as being imported

        Returns:
            True if marker was created successfully
        """
        try:
            marker_path = folder / IMPORT_MARKER_FILE
            marker_path.touch()
            logger.debug(f"Created import marker: {marker_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to create import marker for {folder}: {e}")
            return False

    def _remove_import_marker(self, folder: Path) -> None:
        """
        Remove import marker file after processing completes.

        Args:
            folder: Folder to remove marker from
        """
        try:
            marker_path = folder / IMPORT_MARKER_FILE
            if marker_path.exists():
                marker_path.unlink()
                logger.debug(f"Removed import marker: {marker_path}")
        except Exception as e:
            logger.warning(f"Failed to remove import marker for {folder}: {e}")

    def _acquire_folder_marker(self, folder: Path) -> bool:
        """
        Acquire a reference to a folder's import marker (thread-safe).
        Creates the marker file if this is the first reference.

        Args:
            folder: Folder to mark as being imported

        Returns:
            True if marker was acquired successfully
        """
        with self._folder_marker_lock:
            was_zero = self._folder_marker_refs[folder] == 0
            self._folder_marker_refs[folder] += 1

            if was_zero:
                # First reference - create the marker file
                return self._create_import_marker(folder)
            return True

    def _release_folder_marker(self, folder: Path) -> None:
        """
        Release a reference to a folder's import marker (thread-safe).
        Removes the marker file when the last reference is released.

        Args:
            folder: Folder to release marker for
        """
        with self._folder_marker_lock:
            if folder in self._folder_marker_refs:
                self._folder_marker_refs[folder] -= 1
                if self._folder_marker_refs[folder] <= 0:
                    # Last reference - remove the marker file
                    del self._folder_marker_refs[folder]
                    self._remove_import_marker(folder)

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

        # Track detailed skip/fail reasons
        skip_reasons = {
            "duplicate_hash": 0,
            "duplicate_fuzzy": 0,
            "invalid_title": 0,
            "parse_error": 0,
            "organization_failed": 0,
        }

        if not self.downloads_dir.exists():
            logger.warning(f"Downloads directory not found: {self.downloads_dir}")
            result.add_error(
                ErrorCodes.FILE_NOT_FOUND,
                f"Downloads directory not found: {self.downloads_dir}",
                retryable=False,
            )
            return result.to_dict()

        all_files = find_supported_files(self.downloads_dir, recursive=True)
        # Strip trailing quotes from suffix (for files like 'Magazine.pdf')
        pdf_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbr"]

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
        self._process_file_batch(pdf_files, "PDF", session, organization_pattern, result, skip_reasons)
        self._process_file_batch(epub_files, "EPUB", session, organization_pattern, result, skip_reasons)
        self._process_file_batch(cbz_files, "CBZ", session, organization_pattern, result, skip_reasons)
        self._process_file_batch(cbr_files, "CBR", session, organization_pattern, result, skip_reasons)

        # Log summary
        self._log_import_summary(result, skip_reasons)

        return result.to_dict()

    def _log_import_summary(self, result: OperationResult, skip_reasons: Dict[str, int]) -> None:
        """
        Log a summary of import results.

        Args:
            result: OperationResult with counts
            skip_reasons: Dictionary of skip reasons and their counts
        """
        total = result.data.get("imported", 0) + result.data.get("skipped", 0) + result.data.get("failed", 0)
        if total == 0:
            return

        logger.info("=" * 80)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total files processed: {total}")
        logger.info(f"  ✓ Successfully imported: {result.data.get('imported', 0)}")
        logger.info(f"  ⊘ Skipped: {result.data.get('skipped', 0)}")
        logger.info(f"  ✗ Failed: {result.data.get('failed', 0)}")

        # Show skip reasons if any
        if result.data.get("skipped", 0) > 0 or any(skip_reasons.values()):
            logger.info("")
            logger.info("Skip/Failure reasons:")
            for reason, count in sorted(skip_reasons.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    reason_label = {
                        "duplicate_hash": "Duplicate (content hash)",
                        "duplicate_fuzzy": "Duplicate (title/date)",
                        "invalid_title": "Invalid title",
                        "parse_error": "Parse error",
                        "organization_failed": "File organization failed",
                    }.get(reason, reason)
                    logger.info(f"  - {reason_label}: {count}")

        logger.info("=" * 80)

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
                self._cleanup_download_file(pdf_path, defer_folder_deletion=True)
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
                        f"Duplicate detected for '{pdf_path.name}': '{tracking_title}' ({parsed_issue_date.strftime('%b %Y')}, {parsed_language}) "
                        f"matches existing '{existing.title}' ({existing.issue_date.strftime('%b %Y')}, "
                        f"{existing.language or DEFAULT_LANGUAGE}) (title score: {score}, date diff: {date_diff} days). "
                        f"Skipping import."
                    )
                    if not skip_organize:
                        self._cleanup_download_file(pdf_path, defer_folder_deletion=True)
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
            metadata_discovered = False
            new_issue_date = sync_issue_date_from_derived(magazine.derived_metadata)
            if new_issue_date:
                magazine.issue_date = new_issue_date
                metadata_discovered = True
                logger.debug(f"Updated issue_date to {new_issue_date.strftime('%Y-%m')} from derived_metadata")

            # Check if text scan found volume/issue
            if scan_result.get("volume") or scan_result.get("issue_number"):
                metadata_discovered = True
                if not magazine.extra_metadata:
                    magazine.extra_metadata = {}
                if scan_result.get("volume"):
                    magazine.extra_metadata["volume"] = scan_result["volume"]
                if scan_result.get("issue_number"):
                    magazine.extra_metadata["issue_number"] = scan_result["issue_number"]

            # Flag for reorganization if we discovered new metadata
            if metadata_discovered:
                if not magazine.extra_metadata:
                    magazine.extra_metadata = {}
                magazine.extra_metadata["needs_reorganization"] = True
                magazine.extra_metadata["reorganization_reason"] = "metadata_discovered_by_text_scan"
                logger.info(f"Flagged {magazine.title} for reorganization (metadata discovered by text scan)")

            if scan_result.get("text_found"):
                logger.info(f"Enhanced {magazine.title} with metadata from text scan")

            from core.utils.db import mark_json_modified

            mark_json_modified(magazine, "parsed_metadata", "derived_metadata", "extra_metadata")
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

    def _scan_for_missing_date(
        self,
        file_path: Path,
        parsed_language: Optional[str],
    ) -> Dict[str, Any]:
        """
        Scan file for date/volume metadata BEFORE organization.

        This is used for files that have tracking context but no parseable date,
        allowing us to discover the date before organizing the file to its final location.

        Args:
            file_path: Path to the original file (not yet organized)
            parsed_language: Language from parser

        Returns:
            Dict with discovered metadata: {issue_date, year, month, volume, issue_number, source,
                                            text_scan_result, ocr_scan_result}
        """
        result = {
            "issue_date": None,
            "year": None,
            "month": None,
            "month_name": None,
            "volume": None,
            "issue_number": None,
            "source": None,
            "text_scan_result": None,  # Full text scan result for storing in DB
            "ocr_scan_result": None,  # Full OCR scan result for storing in DB
        }

        # Try text scan first (faster than OCR)
        if file_path.suffix.lower() in [".pdf", ".epub"]:
            try:
                logger.info(f"Running pre-organization text scan for {file_path.name}")
                scan_result = TextScanService.scan_document(str(file_path), language=parsed_language)
                result["text_scan_result"] = scan_result  # Store for DB

                if scan_result.get("year"):
                    from core.utils.metadata_builder import sync_issue_date_from_derived, build_derived_metadata

                    # Build derived metadata to get issue_date
                    derived = build_derived_metadata(text_scan=scan_result)
                    issue_date = sync_issue_date_from_derived(derived)

                    if issue_date:
                        result["issue_date"] = issue_date
                        result["year"] = scan_result.get("year")
                        result["month"] = scan_result.get("month")
                        # Convert month number to name for organization
                        if result["month"]:
                            from core.constants.date import MONTH_TO_NAME

                            result["month_name"] = MONTH_TO_NAME.get(result["month"])
                        result["source"] = "text_scan"
                        logger.info(
                            f"Pre-organization text scan found date: {issue_date.strftime('%Y-%m')} for {file_path.name}"
                        )

                if scan_result.get("volume"):
                    result["volume"] = scan_result["volume"]
                if scan_result.get("issue_number"):
                    result["issue_number"] = scan_result["issue_number"]

                # If we found a date, return early (no need for OCR)
                if result["issue_date"]:
                    return result

            except Exception as e:
                logger.debug(f"Pre-organization text scan failed for {file_path.name}: {e}")

        # Try OCR if text scan didn't find a date and file is PDF
        if file_path.suffix.lower() == ".pdf" and OCRService.is_available():
            try:
                logger.info(f"Running pre-organization OCR scan for {file_path.name}")
                ocr_result = OCRService.analyze_cover(str(file_path), language=parsed_language)
                result["ocr_scan_result"] = ocr_result  # Store for DB

                if ocr_result and ocr_result.get("year"):
                    from core.utils.metadata_builder import sync_issue_date_from_derived, build_derived_metadata

                    # Build derived metadata to get issue_date
                    derived = build_derived_metadata(ocr_scan=ocr_result)
                    issue_date = sync_issue_date_from_derived(derived)

                    if issue_date:
                        result["issue_date"] = issue_date
                        result["year"] = ocr_result.get("year")
                        result["month"] = ocr_result.get("month")
                        if result["month"]:
                            from core.constants.date import MONTH_TO_NAME

                            result["month_name"] = MONTH_TO_NAME.get(result["month"])
                        result["source"] = "ocr_scan"
                        logger.info(
                            f"Pre-organization OCR scan found date: {issue_date.strftime('%Y-%m')} for {file_path.name}"
                        )

                if ocr_result:
                    if ocr_result.get("volume") and not result["volume"]:
                        result["volume"] = ocr_result["volume"]
                    if ocr_result.get("issue_number") and not result["issue_number"]:
                        result["issue_number"] = ocr_result["issue_number"]

            except Exception as e:
                logger.debug(f"Pre-organization OCR scan failed for {file_path.name}: {e}")

        return result

    def _run_ocr_scan(
        self,
        magazine: Periodical,
        organized_path: Path,
        parsed_language: Optional[str],
        session: Session,
    ) -> bool:
        """
        Run OCR scan synchronously to extract date/volume metadata.

        This is used for files that need immediate date extraction (needs_date_scan)
        to avoid duplicate detection issues with fallback dates.

        Args:
            magazine: The Periodical record
            organized_path: Path to the organized file
            parsed_language: Language from parser
            session: Database session

        Returns:
            True if OCR found a date, False otherwise
        """
        if organized_path.suffix.lower() != ".pdf":
            logger.debug(f"Skipping OCR for non-PDF file: {organized_path}")
            return False

        if not OCRService.is_available():
            logger.warning("OCR service not available, cannot run immediate OCR scan")
            return False

        try:
            logger.info(f"Running immediate OCR scan for {magazine.title} to find date")

            # Run OCR directly on the PDF
            ocr_result = OCRService.analyze_cover(str(organized_path), language=parsed_language)

            if not ocr_result or not ocr_result.get("text_found"):
                logger.debug(f"OCR found no text in {organized_path.name}")
                return False

            # Store OCR scan results in parsed_metadata
            if not magazine.parsed_metadata:
                magazine.parsed_metadata = {}
            magazine.parsed_metadata["ocr_scan"] = ocr_result

            # Rebuild derived_metadata with OCR results
            from core.utils.metadata_builder import build_derived_metadata, sync_issue_date_from_derived

            magazine.derived_metadata = build_derived_metadata(
                file_scan=magazine.parsed_metadata.get("file_scan"),
                text_scan=magazine.parsed_metadata.get("text_scan"),
                ocr_scan=ocr_result,
            )

            # Sync issue_date from derived_metadata
            new_issue_date = sync_issue_date_from_derived(magazine.derived_metadata)
            found_date = False
            metadata_discovered = False

            if new_issue_date:
                magazine.issue_date = new_issue_date
                found_date = True
                metadata_discovered = True
                logger.info(f"OCR scan found date {new_issue_date.strftime('%Y-%m')} for {magazine.title}")

            # Check if OCR found volume/issue that we didn't have
            if ocr_result.get("volume") or ocr_result.get("issue_number"):
                metadata_discovered = True
                if not magazine.extra_metadata:
                    magazine.extra_metadata = {}
                if ocr_result.get("volume"):
                    magazine.extra_metadata["volume"] = ocr_result["volume"]
                if ocr_result.get("issue_number"):
                    magazine.extra_metadata["issue_number"] = ocr_result["issue_number"]

            # Flag for reorganization if we discovered new metadata
            # This allows the file to be renamed/moved later with correct metadata
            if metadata_discovered:
                if not magazine.extra_metadata:
                    magazine.extra_metadata = {}
                magazine.extra_metadata["needs_reorganization"] = True
                magazine.extra_metadata["reorganization_reason"] = "metadata_discovered_by_ocr"
                logger.info(f"Flagged {magazine.title} for reorganization (metadata discovered by OCR)")

            from core.utils.db import mark_json_modified

            mark_json_modified(magazine, "parsed_metadata", "derived_metadata", "extra_metadata")
            session.commit()

            if ocr_result.get("year"):
                logger.info(f"Enhanced {magazine.title} with metadata from immediate OCR scan")
                return found_date

            return False

        except Exception as e:
            logger.warning(f"Immediate OCR scan failed for {magazine.id}: {e}")
            return False

    # =========================================================================
    # Main Import Method
    # =========================================================================

    def import_supported_files(
        self,
        file_path: Path,
        session: Session,
        *,
        organization_pattern: Optional[str] = None,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        tracking_id: Optional[int] = None,
        skip_enhancement: bool = False,
    ) -> Dict[str, Any]:
        """
        Import a single periodical file (PDF, EPUB, CBZ, or CBR).

        Args:
            file_path: Path to periodical file
            session: Database session
            organization_pattern: Optional custom organization pattern with tags like {category}, {title}, {year}
            auto_track: Whether to auto-create tracking records for imported periodicals
            skip_organize: If True, skip file organization and use file in place (for already-library files)
            tracking_mode: Tracking mode - "all" (track all editions), "new" (track new only), "watch" (watch only), "none" (no tracking)
            use_ocr: Whether to use OCR for metadata extraction (default: True, set False for faster batch imports)
            tracking_id: Optional tracking ID to associate this file with (from DownloadSubmission)
            skip_enhancement: If True, skip cover extraction and text scanning for faster bulk imports (default: False)

        Returns:
            Dictionary with result information including magazine_id, or empty dict if failed
        """
        try:
            # Step 1: Get tracking context from sidecar and tracking record
            tracking_id, organization_pattern = self._get_tracking_context(
                file_path, tracking_id, organization_pattern, session
            )

            # Step 2: Parse file and validate
            parsed = self.parser.parse_file(file_path)
            if not self.title_matcher.validate_before_parsing(parsed.title):
                logger.warning(f"Skipping invalid release title: {parsed.title} (from {file_path.name})")
                return {"skip_reason": "invalid_title"}
            logger.debug(
                f"Parsed metadata: '{parsed.title}' - Date: {parsed.issue_date.strftime('%b %Y') if parsed.issue_date else 'None'} "
                f"(confidence: {parsed.confidence}, pattern: {parsed.matched_pattern})"
            )

            # Step 3: Calculate content hash and check for hash-based duplicates
            content_hash = hash_file_in_chunks(str(file_path))
            if not content_hash:
                logger.error(f"Failed to hash file {file_path}, skipping import", exc_info=True)
                return {"skip_reason": "parse_error"}

            if self._check_hash_duplicate(content_hash, file_path, skip_organize, session):
                return {"skip_reason": "duplicate_hash"}

            # Step 4: Determine title - use parsed title if confidence is high, otherwise fall back to tracking
            # High confidence means filename parsing succeeded well - the file might be a different
            # periodical than what was tracked (e.g., IA collection with multiple periodicals)
            # Low/medium confidence means filename is ambiguous - trust the tracking association
            needs_date_scan = False
            if tracking_id:
                target_tracking_temp = (
                    session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
                )
                if target_tracking_temp:
                    # Check if parsed title has high confidence
                    if parsed.confidence == "high" and parsed.issue_date is not None:
                        # High confidence parse - use the parsed title (might differ from tracking)
                        tracking_title = self._build_tracking_title(parsed.base_title, parsed.country, file_path)
                        logger.info(
                            f"High confidence parse for '{file_path.name}': using parsed title '{tracking_title}' "
                            f"(tracking was '{target_tracking_temp.title}')"
                        )
                    else:
                        # Low/medium confidence - fall back to tracking title
                        tracking_title = target_tracking_temp.title
                        logger.debug(
                            f"Using tracking title from sidecar: '{tracking_title}' (ID: {tracking_id}) "
                            f"for low/medium confidence parse (parsed: '{parsed.base_title}', "
                            f"confidence: {parsed.confidence})"
                        )
                    # Check if we need to force text/OCR scan to find date
                    # When we have a tracking title but couldn't parse a date from filename,
                    # we should scan the document content to try to extract date/volume info
                    date_missing = (
                        parsed.issue_date is None
                        or parsed.confidence == "low"
                        or parsed.matched_pattern == "no_match_fallback"
                    )
                    if date_missing:
                        needs_date_scan = True
                        logger.info(
                            f"File '{file_path.name}' needs date scan "
                            f"(confidence: {parsed.confidence}, pattern: {parsed.matched_pattern}). "
                            f"Will force text/OCR scan to extract date."
                        )
                else:
                    # Sidecar had invalid tracking_id, fall back to parsed title
                    logger.warning(f"Sidecar tracking_id={tracking_id} not found, using parsed title")
                    tracking_title = self._build_tracking_title(parsed.base_title, parsed.country, file_path)
            else:
                # No sidecar tracking_id, build from parsed filename
                tracking_title = self._build_tracking_title(parsed.base_title, parsed.country, file_path)

            # Step 5: Check for fuzzy duplicates
            if self._check_fuzzy_duplicate(
                tracking_title, parsed.issue_date, parsed.language, file_path, skip_organize, session
            ):
                return {"skip_reason": "duplicate_fuzzy"}

            # Step 6: Determine category and find tracking match
            category = self.categorizer.categorize(parsed.title)
            target_tracking = self._find_tracking_match(
                tracking_id, tracking_title, parsed.language, parsed.country, category, session
            )

            # Step 7: For files needing date scan, run text/OCR BEFORE organization
            # This allows us to use discovered metadata for the correct file path
            pre_scan_result = None
            if needs_date_scan and not skip_organize:
                pre_scan_result = self._scan_for_missing_date(file_path, parsed.language)
                if pre_scan_result.get("issue_date"):
                    # Update parsed metadata with discovered date for organization
                    parsed.issue_date = pre_scan_result["issue_date"]
                    parsed.year = pre_scan_result.get("year")
                    parsed.month_name = pre_scan_result.get("month_name")
                    parsed.confidence = "medium"  # Upgrade confidence since we found a date
                    logger.info(
                        f"Updated metadata from {pre_scan_result['source']}: "
                        f"date={parsed.issue_date.strftime('%Y-%m')}, year={parsed.year}"
                    )

            # Step 8: Organize file (use tracking title for folder consistency)
            organization_title = target_tracking.title if target_tracking else tracking_title

            # Extract cover unless skip_enhancement is enabled (for bulk imports)
            cover_path = None if skip_enhancement else self._extract_cover(file_path)
            should_queue_ocr = use_ocr and (cover_path or file_path) and OCRService.is_available()

            if skip_organize:
                organized_path = file_path
                logger.info(f"Using file in place (already in library): {file_path}")
            else:
                metadata = {
                    "title": organization_title,
                    "issue_date": parsed.issue_date,
                    "year": parsed.year,
                    "month_name": parsed.month_name,
                    "language": parsed.language,
                    "volume": parsed.volume,
                    "issue_number": parsed.issue_number,
                }
                organized_path = self.organizer.organize(file_path, metadata, category, organization_pattern)
                if not organized_path:
                    return {"skip_reason": "organization_failed"}

            # Step 9: Build metadata and create database record
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

            # Build extra metadata, flagging if date scan is needed
            extra_meta = build_extra_metadata(
                imported_from=file_path.name,
                import_date=datetime.now().isoformat(),
                category=category,
                import_method="auto",
            )
            if needs_date_scan and not (pre_scan_result and pre_scan_result.get("issue_date")):
                # Only flag for future date scan if pre-scan didn't find a date
                extra_meta["needs_date_scan"] = True
                extra_meta["date_scan_reason"] = "tracking_title_without_parsed_date"

            # Include pre-scan results in parsed_metadata if available
            text_scan = pre_scan_result.get("text_scan_result") if pre_scan_result else None
            ocr_scan = pre_scan_result.get("ocr_scan_result") if pre_scan_result else None

            magazine = Periodical(
                title=organization_title,
                issue_date=parsed.issue_date or datetime.now(),
                language=parsed.language or DEFAULT_LANGUAGE,
                file_path=str(organized_path),
                cover_path=str(cover_path) if cover_path else None,
                content_hash=content_hash,
                parsed_metadata=build_parsed_metadata(file_scan=file_scan, text_scan=text_scan, ocr_scan=ocr_scan),
                derived_metadata=build_derived_metadata(file_scan=file_scan, text_scan=text_scan, ocr_scan=ocr_scan),
                extra_metadata=extra_meta,
            )
            session.add(magazine)

            # Step 10: Link to existing tracking or create new one
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

            # Step 11: Run text scan for additional metadata (skip if pre-scan already ran)
            # Force text scan if needs_date_scan (even during bulk imports) to try to find date/volume
            # Otherwise skip during bulk imports for speed
            pre_scan_did_text = pre_scan_result and pre_scan_result.get("text_scan_result") is not None
            pre_scan_did_ocr = pre_scan_result and pre_scan_result.get("ocr_scan_result") is not None
            pre_scan_found_date = pre_scan_result and pre_scan_result.get("issue_date") is not None

            if not pre_scan_did_text and (not skip_enhancement or needs_date_scan):
                if needs_date_scan:
                    logger.info(f"Forcing text scan for '{organization_title}' to find missing date/volume")
                self._run_text_scan(magazine, organized_path, parsed.language, session)

            # Step 12: Run OCR if needed (skip if pre-scan already ran OCR)
            # For needs_date_scan files: run OCR synchronously to get date before next file
            # (avoids duplicate detection issues when multiple files have same fallback date)
            # For other files: queue OCR for background processing
            text_scan_result = magazine.parsed_metadata.get("text_scan", {}) if magazine.parsed_metadata else {}
            text_scan_sufficient = text_scan_result.get("has_sufficient_metadata", False)
            text_scan_found_date = text_scan_result.get("year") is not None

            # For files needing date scan, run OCR synchronously to get date immediately
            # But skip if pre-scan already did OCR or found a date
            if needs_date_scan and not text_scan_found_date and not pre_scan_found_date and not pre_scan_did_ocr:
                # Text scan didn't find date - run OCR immediately (not queued)
                # This is critical to avoid duplicate detection issues
                logger.info(f"Text scan didn't find date for '{organization_title}' - running immediate OCR scan")
                ocr_found_date = self._run_ocr_scan(magazine, organized_path, parsed.language, session)
                if not ocr_found_date:
                    logger.warning(
                        f"Could not determine date for '{organization_title}' from filename, text, or OCR. "
                        f"Using fallback date. Manual review recommended."
                    )
            elif not pre_scan_did_ocr and should_queue_ocr and not text_scan_sufficient:
                # Normal case: queue OCR for background processing
                self._queue_ocr_job(magazine, parsed.language, skip_organize, session)
            elif text_scan_sufficient or pre_scan_found_date:
                logger.info(f"Skipping OCR for '{parsed.title}' - sufficient metadata already found")

            # Step 13: Cleanup download file (defer folder deletion to batch processing)
            if not skip_organize:
                self._cleanup_download_file(file_path, defer_folder_deletion=True)

            return {"periodical_id": magazine.id}

        except Exception as e:
            session.rollback()
            logger.error(f"Error importing file {file_path}: {e}", exc_info=True)
            return {"skip_reason": "parse_error"}

    def _import_file_worker(
        self,
        file_path: Path,
        file_type: str,
        organization_pattern: Optional[str],
        *,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        skip_enhancement: bool = False,
    ) -> Dict[str, Any]:
        """
        Worker method for parallel file import.
        Creates its own database session and manages folder markers.

        Args:
            file_path: Path to file to import
            file_type: File type label for logging
            organization_pattern: Optional organization pattern
            auto_track: Whether to auto-create tracking records
            skip_organize: If True, skip file organization (for library imports)
            tracking_mode: Tracking mode for new records
            use_ocr: Whether to use OCR for metadata extraction
            skip_enhancement: If True, skip cover extraction and text scanning

        Returns:
            Dict with import result and metadata for aggregation
        """
        parent_dir = file_path.parent
        is_subfolder = parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir)

        # Acquire folder marker before processing (only for downloads, not library)
        if is_subfolder and not skip_organize:
            self._acquire_folder_marker(parent_dir)

        try:
            # Create a new session for this worker
            if self._session_factory:
                with self._session_factory() as worker_session:
                    import_result = self.import_supported_files(
                        file_path,
                        worker_session,
                        organization_pattern=organization_pattern,
                        auto_track=auto_track,
                        skip_organize=skip_organize,
                        tracking_mode=tracking_mode,
                        use_ocr=use_ocr,
                        skip_enhancement=skip_enhancement,
                    )
            else:
                # No session factory - this shouldn't happen in parallel mode
                logger.warning(f"No session factory for worker processing {file_path.name}")
                return {
                    "file_path": file_path,
                    "file_type": file_type,
                    "result": {"skip_reason": "no_session"},
                    "parent_dir": parent_dir if is_subfolder and not skip_organize else None,
                }

            return {
                "file_path": file_path,
                "file_type": file_type,
                "result": import_result,
                "parent_dir": parent_dir if is_subfolder and not skip_organize else None,
            }

        except Exception as e:
            logger.error(f"Error in worker importing {file_path.name}: {e}", exc_info=True)
            return {
                "file_path": file_path,
                "file_type": file_type,
                "result": {"skip_reason": "parse_error", "error": str(e)},
                "parent_dir": parent_dir if is_subfolder and not skip_organize else None,
            }

        finally:
            # Release folder marker after processing (only for downloads, not library)
            if is_subfolder and not skip_organize:
                self._release_folder_marker(parent_dir)

    def _process_file_batch(
        self,
        files: list,
        file_type: str,
        session: Session,
        organization_pattern: Optional[str],
        result: OperationResult,
        skip_reasons: Dict[str, int],
        *,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        skip_enhancement: bool = False,
    ) -> None:
        """
        Process a batch of files of the same type.
        Uses parallel processing when session_factory is available and multiple files exist.

        Args:
            files: List of Path objects to process
            file_type: File type label for logging (e.g., "PDF", "EPUB", "CBZ", "CBR")
            session: Database session (used for sequential processing)
            organization_pattern: Optional organization pattern
            result: OperationResult to update with counts and errors
            skip_reasons: Dictionary to track skip/failure reasons
            auto_track: Whether to auto-create tracking records
            skip_organize: If True, skip file organization (for library imports)
            tracking_mode: Tracking mode for new records
            use_ocr: Whether to use OCR for metadata extraction
            skip_enhancement: If True, skip cover extraction and text scanning
        """
        # Track folders to cleanup after processing all files
        folders_to_cleanup = set()

        # Determine if we can use parallel processing
        use_parallel = self._session_factory is not None and len(files) > 1 and self._parallel_workers > 1

        if use_parallel:
            logger.info(
                f"Processing {len(files)} {file_type} files in parallel " f"with {self._parallel_workers} workers"
            )
            self._process_files_parallel(
                files,
                file_type,
                organization_pattern,
                result,
                skip_reasons,
                folders_to_cleanup,
                auto_track=auto_track,
                skip_organize=skip_organize,
                tracking_mode=tracking_mode,
                use_ocr=use_ocr,
                skip_enhancement=skip_enhancement,
            )
        else:
            # Sequential processing (original behavior)
            self._process_files_sequential(
                files,
                file_type,
                session,
                organization_pattern,
                result,
                skip_reasons,
                folders_to_cleanup,
                auto_track=auto_track,
                skip_organize=skip_organize,
                tracking_mode=tracking_mode,
                use_ocr=use_ocr,
                skip_enhancement=skip_enhancement,
            )

        # Clean up folders after all files are processed
        # CRITICAL: Only cleanup folders that are in the downloads directory
        # and contain no remaining supported files (PDF, EPUB, CBZ, CBR)
        for folder in folders_to_cleanup:
            try:
                # Safety check: only delete folders in downloads directory
                try:
                    is_in_downloads = folder.is_relative_to(self.downloads_dir)
                except ValueError:
                    is_in_downloads = False

                if not is_in_downloads:
                    logger.debug(f"Skipping folder cleanup - not in downloads directory: {folder}")
                    continue

                if folder.exists():
                    self._safe_cleanup_download_folder(folder)
            except Exception as e:
                logger.warning(f"Failed to delete folder {folder.name}: {e}")

    def _process_files_parallel(
        self,
        files: list,
        file_type: str,
        organization_pattern: Optional[str],
        result: OperationResult,
        skip_reasons: Dict[str, int],
        folders_to_cleanup: set,
        *,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        skip_enhancement: bool = False,
    ) -> None:
        """
        Process files in parallel using ThreadPoolExecutor.

        Args:
            files: List of Path objects to process
            file_type: File type label for logging
            organization_pattern: Optional organization pattern
            result: OperationResult to update with counts and errors
            skip_reasons: Dictionary to track skip/failure reasons
            folders_to_cleanup: Set to track folders needing cleanup
            auto_track: Whether to auto-create tracking records
            skip_organize: If True, skip file organization (for library imports)
            tracking_mode: Tracking mode for new records
            use_ocr: Whether to use OCR for metadata extraction
            skip_enhancement: If True, skip cover extraction and text scanning
        """
        with ThreadPoolExecutor(max_workers=self._parallel_workers, thread_name_prefix="import") as executor:
            # Submit all files for processing
            futures = {
                executor.submit(
                    self._import_file_worker,
                    file_path,
                    file_type,
                    organization_pattern,
                    auto_track=auto_track,
                    skip_organize=skip_organize,
                    tracking_mode=tracking_mode,
                    use_ocr=use_ocr,
                    skip_enhancement=skip_enhancement,
                ): file_path
                for file_path in files
            }

            # Collect results as they complete
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    worker_result = future.result()
                    # skip_cleanup=True for library imports (skip_organize=True) - never delete library files
                    self._handle_import_result(
                        worker_result, file_type, result, skip_reasons, folders_to_cleanup, skip_cleanup=skip_organize
                    )
                except Exception as e:
                    result.data["failed"] += 1
                    skip_reasons["parse_error"] += 1
                    error_msg = f"Error importing {file_type} {file_path.name}: {str(e)}"
                    result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                    logger.error(error_msg, exc_info=True)
                    # Clean up the failed file and track folder for cleanup
                    # Only cleanup for downloads (skip_organize=False), never for library imports
                    if not skip_organize:
                        try:
                            self._cleanup_download_file(file_path, defer_folder_deletion=True)
                            parent_dir = file_path.parent
                            if parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir):
                                folders_to_cleanup.add(parent_dir)
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to cleanup {file_path.name}: {cleanup_error}")

    def _process_files_sequential(
        self,
        files: list,
        file_type: str,
        session: Session,
        organization_pattern: Optional[str],
        result: OperationResult,
        skip_reasons: Dict[str, int],
        folders_to_cleanup: set,
        *,
        auto_track: bool = True,
        skip_organize: bool = False,
        tracking_mode: str = "watch",
        use_ocr: bool = True,
        skip_enhancement: bool = False,
    ) -> None:
        """
        Process files sequentially (original behavior).

        Args:
            files: List of Path objects to process
            file_type: File type label for logging
            session: Database session
            organization_pattern: Optional organization pattern
            result: OperationResult to update with counts and errors
            skip_reasons: Dictionary to track skip/failure reasons
            folders_to_cleanup: Set to track folders needing cleanup
            auto_track: Whether to auto-create tracking records
            skip_organize: If True, skip file organization (for library imports)
            tracking_mode: Tracking mode for new records
            use_ocr: Whether to use OCR for metadata extraction
            skip_enhancement: If True, skip cover extraction and text scanning
        """
        # Track folders with active import markers (only for downloads, not library)
        folders_with_markers = set()

        # Identify unique parent folders and create import markers (only for downloads)
        if not skip_organize:
            unique_folders = set()
            for file_path in files:
                parent_dir = file_path.parent
                if parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir):
                    unique_folders.add(parent_dir)

            # Create markers for all folders being processed
            for folder in unique_folders:
                if self._create_import_marker(folder):
                    folders_with_markers.add(folder)

        for file_path in files:
            try:
                import_result = self.import_supported_files(
                    file_path,
                    session,
                    organization_pattern=organization_pattern,
                    auto_track=auto_track,
                    skip_organize=skip_organize,
                    tracking_mode=tracking_mode,
                    use_ocr=use_ocr,
                    skip_enhancement=skip_enhancement,
                )
                worker_result = {
                    "file_path": file_path,
                    "file_type": file_type,
                    "result": import_result,
                    "parent_dir": (
                        file_path.parent
                        if not skip_organize
                        and file_path.parent != self.downloads_dir
                        and file_path.parent.is_relative_to(self.downloads_dir)
                        else None
                    ),
                }
                # skip_cleanup=True for library imports (skip_organize=True) - never delete library files
                self._handle_import_result(
                    worker_result, file_type, result, skip_reasons, folders_to_cleanup, skip_cleanup=skip_organize
                )
            except Exception as e:
                result.data["failed"] += 1
                skip_reasons["parse_error"] += 1
                error_msg = f"Error importing {file_type} {file_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                # Only cleanup for downloads (skip_organize=False), never for library imports
                if not skip_organize:
                    try:
                        self._cleanup_download_file(file_path, defer_folder_deletion=True)
                        parent_dir = file_path.parent
                        if parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir):
                            folders_to_cleanup.add(parent_dir)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup {file_path.name}: {cleanup_error}")

        # Remove import markers from all processed folders
        for folder in folders_with_markers:
            self._remove_import_marker(folder)

    def _handle_import_result(
        self,
        worker_result: Dict[str, Any],
        file_type: str,
        result: OperationResult,
        skip_reasons: Dict[str, int],
        folders_to_cleanup: set,
        *,
        skip_cleanup: bool = False,
    ) -> None:
        """
        Handle the result from a file import (used by both parallel and sequential processing).

        Args:
            worker_result: Result dict from worker with file_path, result, parent_dir
            file_type: File type label for logging
            result: OperationResult to update with counts and errors
            skip_reasons: Dictionary to track skip/failure reasons
            folders_to_cleanup: Set to track folders needing cleanup
            skip_cleanup: If True, skip file cleanup (for library imports where we never delete files)
        """
        file_path = worker_result["file_path"]
        import_result = worker_result["result"]
        parent_dir = worker_result.get("parent_dir")

        if import_result and import_result.get("periodical_id"):
            result.data["imported"] += 1
            logger.info(f"Successfully imported {file_type}: {file_path.name}")
            if parent_dir:
                folders_to_cleanup.add(parent_dir)
        else:
            # Track skip reason
            skip_reason = import_result.get("skip_reason", "organization_failed") if import_result else "parse_error"
            if skip_reason in skip_reasons:
                skip_reasons[skip_reason] += 1
                result.data["skipped"] += 1
            else:
                result.data["failed"] += 1
                result.add_error(
                    ErrorCodes.IMPORT_FAILED,
                    f"Failed to import {file_type} {file_path.name}",
                    retryable=True,
                )
            logger.debug(f"Skipped {file_type} import ({skip_reason}): {file_path.name}")
            # Only cleanup files from downloads folder, never from library
            if not skip_cleanup:
                self._cleanup_download_file(file_path, defer_folder_deletion=True)
                if parent_dir:
                    folders_to_cleanup.add(parent_dir)

    def _cleanup_download_file(self, pdf_path: Path, defer_folder_deletion: bool = False) -> None:
        """
        Clean up a file from downloads folder and optionally its parent directory.
        Also removes sidecar metadata file if present.

        CRITICAL: Only deletes files that are actually in the downloads directory.
        Files in the library directory are NEVER deleted by this method.

        Args:
            pdf_path: Path to PDF file in downloads folder
            defer_folder_deletion: If True, only delete the file, not the parent folder.
                                   Used when processing multiple files from the same folder.
        """
        try:
            # CRITICAL SAFETY CHECK: Only delete files that are in the downloads directory
            # Never delete files from the library directory
            try:
                is_in_downloads = pdf_path.is_relative_to(self.downloads_dir)
            except ValueError:
                is_in_downloads = False

            if not is_in_downloads:
                logger.debug(f"Skipping cleanup - file not in downloads directory: {pdf_path}")
                return

            # Delete sidecar metadata file if it exists (only for downloads)
            delete_sidecar_file(pdf_path)

            if pdf_path.exists() and pdf_path.is_file():
                pdf_path.unlink()
                logger.info(f"Deleted file from downloads: {pdf_path.name}")

            # Cleanup parent directory only if not deferred
            if not defer_folder_deletion:
                parent_dir = pdf_path.parent
                if parent_dir != self.downloads_dir and parent_dir.is_relative_to(self.downloads_dir):
                    if parent_dir.exists():
                        self._safe_cleanup_download_folder(parent_dir)
        except Exception as e:
            logger.warning(f"Failed to cleanup download file: {e}")

    def _safe_cleanup_download_folder(self, folder: Path) -> None:
        """
        Safely clean up a download folder, preserving any remaining supported files.

        Recursively checks subdirectories bottom-up. Only removes folders and files
        when no supported files (.pdf, .epub, .cbz, .cbr) remain at any level.
        Leftover sidecar files (.nfo, .nzb, .par2, .txt, etc.) are removed when safe.

        Args:
            folder: Path to the download folder to clean up
        """
        # First, recursively clean any subdirectories bottom-up
        for child in sorted(folder.iterdir()):
            if child.is_dir():
                self._safe_cleanup_download_folder(child)

        # Now check this folder: any supported files remaining (directly)?
        remaining_supported = [
            f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
        ]

        if remaining_supported:
            logger.info(
                f"Keeping download folder (contains {len(remaining_supported)} " f"unprocessed file(s)): {folder.name}"
            )
            return

        # No supported files remain — safe to remove leftover sidecars
        for leftover in folder.iterdir():
            if leftover.is_file():
                logger.debug(f"Removing leftover download file: {leftover.name}")
                leftover.unlink()

        # Remove directory if now empty (subdirs should already be cleaned)
        if not any(folder.iterdir()):
            folder.rmdir()
            logger.info(f"Deleted empty download folder: {folder.name}")
        else:
            logger.info(f"Keeping download folder (contains remaining items): {folder.name}")

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

        # Track detailed skip/fail reasons
        skip_reasons = {
            "duplicate_hash": 0,
            "duplicate_fuzzy": 0,
            "invalid_title": 0,
            "parse_error": 0,
            "organization_failed": 0,
        }

        if not self.library_base_dir.exists():
            logger.warning(f"Library directory not found: {self.library_base_dir}")
            result.add_error(
                ErrorCodes.FILE_NOT_FOUND,
                f"Library directory not found: {self.library_base_dir}",
                retryable=False,
            )
            return result.to_dict()

        all_files = find_supported_files(self.library_base_dir, recursive=True)

        if not all_files:
            logger.info(f"No periodical files found in library folders: {self.library_base_dir}")
            return result.to_dict()

        pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower() == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower() == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix.lower() == ".cbr"]

        # Enable fast mode for bulk imports (skip cover extraction and text scanning)
        is_bulk_import = len(all_files) >= 100
        if is_bulk_import:
            logger.info(
                f"[DATA IMPORT] Bulk import mode enabled for {len(all_files)} files - "
                f"cover extraction and text scanning will be skipped for speed. "
                f"Both will be processed automatically by scheduled tasks: "
                f"covers via cover_cleanup scheduler, text scanning via auto_metadata scheduler. "
                f"Note: Schedulers may start processing files while import is still running - this is normal and efficient."
            )

        logger.info(
            f"[DATA IMPORT] Found {len(all_files)} files in library folders to process "
            f"from {self.library_base_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, "
            f"{len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
        )
        logger.info("[DATA IMPORT] OCR disabled for library imports - will run during next scheduled OCR task")

        # Process all file types using unified batch handler (supports parallel processing)
        self._process_file_batch(
            pdf_files,
            "PDF",
            session,
            None,
            result,
            skip_reasons,
            auto_track=auto_track,
            skip_organize=True,
            tracking_mode=tracking_mode,
            use_ocr=False,
            skip_enhancement=is_bulk_import,
        )
        self._process_file_batch(
            epub_files,
            "EPUB",
            session,
            None,
            result,
            skip_reasons,
            auto_track=auto_track,
            skip_organize=True,
            tracking_mode=tracking_mode,
            use_ocr=False,
            skip_enhancement=is_bulk_import,
        )
        self._process_file_batch(
            cbz_files,
            "CBZ",
            session,
            None,
            result,
            skip_reasons,
            auto_track=auto_track,
            skip_organize=True,
            tracking_mode=tracking_mode,
            use_ocr=False,
            skip_enhancement=is_bulk_import,
        )
        self._process_file_batch(
            cbr_files,
            "CBR",
            session,
            None,
            result,
            skip_reasons,
            auto_track=auto_track,
            skip_organize=True,
            tracking_mode=tracking_mode,
            use_ocr=False,
            skip_enhancement=is_bulk_import,
        )

        # Log summary
        self._log_import_summary(result, skip_reasons)

        return result.to_dict()


# Export all public items for wildcard imports
__all__ = ["FileImporter"]
