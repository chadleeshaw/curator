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
from models.database import Magazine, MagazineTracking, OCRJob
from services.file_organizer import FileOrganizer
from services.ocr.service import OCRService
from services.ocr.queue import OCRQueueService, _apply_scan_metadata_to_magazine
from services.text_scan_service import TextScanService

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
        enable_text_scan: bool = True,
    ):
        """
        Initialize file importer.

        Args:
            downloads_dir: Directory to monitor for new PDFs
            organize_base_dir: Base directory for organized files (_Magazines for specific magazines, _Comics, etc.)
            fuzzy_threshold: Fuzzy matching threshold (0-100) for duplicate detection
            organization_pattern: Pattern for organizing files (e.g., "_{category}/{title}/{year}/")
            category_prefix: Prefix for category folders (e.g., "_" for "_Magazines")
            enable_text_scan: Enable direct text extraction from PDF/EPUB during import
        """
        self.downloads_dir = Path(downloads_dir)
        self.organize_base_dir = Path(organize_base_dir)
        self.organization_pattern = organization_pattern
        self.category_prefix = category_prefix
        self._enable_text_scan = enable_text_scan
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)
        self.tracking_matcher = TrackingMatcher()

        # Initialize specialized helpers
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.categorizer = FileCategorizer()
        self.organizer = FileOrganizer(self.organize_base_dir, category_prefix=self.category_prefix)

        # Thread pool for CPU-intensive OCR tasks
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")

        self.organize_base_dir.mkdir(parents=True, exist_ok=True)

        for category in CATEGORY_KEYWORDS.keys():
            category_dir = self.organize_base_dir / f"{self.category_prefix}{category}"
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
        cbz_files = [f for f in cbz_files if not is_in_organize_dir(f)]
        cbr_files = [f for f in cbr_files if not is_in_organize_dir(f)]

        all_files = pdf_files + epub_files + cbz_files + cbr_files

        if not all_files:
            logger.info(f"No PDF or EPUB files found in downloads folder: {self.downloads_dir}")
            return result.to_dict()

        logger.info(
            f"[DOWNLOADS IMPORT] Found {len(all_files)} files to process from {self.downloads_dir} "
            f"({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, {len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
        )
        logger.info("[DOWNLOADS IMPORT] Text extraction enabled, OCR queued only for image-based files")

        for pdf_path in pdf_files:
            try:
                import_result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=organization_pattern,
                    use_ocr=True,
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
                    # Cleanup failed import to prevent folder clutter
                    logger.info(f"Cleaning up failed import: {pdf_path.name}")
                    self._cleanup_download_file(pdf_path)
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing {pdf_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                # Cleanup failed import to prevent folder clutter
                try:
                    self._cleanup_download_file(pdf_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup {pdf_path.name}: {cleanup_error}")

        # Process EPUB files
        for epub_path in epub_files:
            try:
                import_result = self.import_pdf(
                    epub_path,
                    session,
                    organization_pattern=organization_pattern,
                    use_ocr=True,
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported EPUB: {epub_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import EPUB {epub_path.name}",
                        retryable=True,
                    )
                    # Cleanup failed import to prevent folder clutter
                    logger.info(f"Cleaning up failed EPUB import: {epub_path.name}")
                    self._cleanup_download_file(epub_path)
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing EPUB {epub_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                # Cleanup failed import to prevent folder clutter
                try:
                    self._cleanup_download_file(epub_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup {epub_path.name}: {cleanup_error}")

        # Process CBZ files
        for cbz_path in cbz_files:
            try:
                import_result = self.import_pdf(
                    cbz_path,
                    session,
                    organization_pattern=organization_pattern,
                    use_ocr=True,
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported CBZ: {cbz_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import CBZ {cbz_path.name}",
                        retryable=True,
                    )
                    # Cleanup failed import to prevent folder clutter
                    logger.info(f"Cleaning up failed CBZ import: {cbz_path.name}")
                    self._cleanup_download_file(cbz_path)
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing CBZ {cbz_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                # Cleanup failed import to prevent folder clutter
                try:
                    self._cleanup_download_file(cbz_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup {cbz_path.name}: {cleanup_error}")

        # Process CBR files
        for cbr_path in cbr_files:
            try:
                import_result = self.import_pdf(
                    cbr_path,
                    session,
                    organization_pattern=organization_pattern,
                    use_ocr=True,
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported CBR: {cbr_path.name}")
                else:
                    result.data["failed"] += 1
                    result.add_error(
                        ErrorCodes.IMPORT_FAILED,
                        f"Failed to import CBR {cbr_path.name}",
                        retryable=True,
                    )
                    # Cleanup failed import to prevent folder clutter
                    logger.info(f"Cleaning up failed CBR import: {cbr_path.name}")
                    self._cleanup_download_file(cbr_path)
            except Exception as e:
                result.data["failed"] += 1
                error_msg = f"Error importing CBR {cbr_path.name}: {str(e)}"
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)
                # Cleanup failed import to prevent folder clutter
                try:
                    self._cleanup_download_file(cbr_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup {cbr_path.name}: {cleanup_error}")

        return result.to_dict()

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
            skip_organize: If True, skip file organization and use file in place (for already-organized files)
            tracking_mode: Tracking mode - "all" (track all editions), "new" (track new only), "watch" (watch only), "none" (no tracking)
            use_ocr: Whether to use OCR for metadata extraction (default: True, set False for faster batch imports)
            tracking_id: Optional tracking ID to associate this file with (from DownloadSubmission)

        Returns:
            Dictionary with result information including magazine_id, or empty dict if failed
        """
        try:
            # Check for sidecar metadata file first - this provides tracking context
            # that may not be available from the filename alone
            sidecar_metadata = read_sidecar_file(pdf_path)
            if sidecar_metadata and not tracking_id:
                # Use tracking_id from sidecar if not explicitly provided
                tracking_id = sidecar_metadata.get("tracking_id")
                logger.debug(
                    f"Found sidecar metadata for {pdf_path.name}: tracking_id={tracking_id}, "
                    f"tracking_title='{sidecar_metadata.get('tracking_title')}'"
                )

            # Parse file using unified parser - combines filename and filepath parsing
            parsed = self.parser.parse_file(pdf_path)

            # Step 1: Validate title before processing (already done in parser for search results)
            if not self.title_matcher.validate_before_parsing(parsed.title):
                logger.warning(f"Skipping invalid release title: {parsed.title} (from {pdf_path.name})")
                return {}

            logger.debug(f"Parsed metadata: '{parsed.title}' (confidence: {parsed.confidence})")

            # Calculate content hash for duplicate detection
            content_hash = hash_file_in_chunks(str(pdf_path))
            if not content_hash:
                logger.error(f"Failed to hash file {pdf_path}, skipping import", exc_info=True)
                return {}

            # First check: hash-based duplicate detection (100% accurate)
            # Only check if we have a valid hash (skip NULL hashes from older imports)
            existing_by_hash = (
                session.query(Magazine)
                .filter(
                    Magazine.content_hash == content_hash,
                    Magazine.content_hash.isnot(None),
                )
                .first()
            )
            if existing_by_hash:
                logger.warning(
                    f"Duplicate detected (identical file content): '{pdf_path.name}' has same SHA256 hash "
                    f"as existing '{existing_by_hash.title}' at {existing_by_hash.file_path}. "
                    f"Hash: {content_hash[:16]}... "
                    f"If these are truly different files, one may be corrupted or mislabeled. Skipping import."
                )
                # Cleanup duplicate file from downloads if not already organized
                if not skip_organize:
                    self._cleanup_download_file(pdf_path)
                return {}

            # Extract special edition info from parsed data
            base_title = parsed.base_title
            is_special_edition = parsed.is_special_edition
            special_name = parsed.special_edition_name

            # Use base_title for tracking - language is stored separately in the language field
            # This keeps titles clean and allows proper filtering by language
            # However, for regional editions (different countries), include country in title
            tracking_title = base_title

            # Include country in tracking title for regional editions
            # Regional editions should have separate tracking from the base edition
            # Only do this if the country name/code was explicitly in the original filename
            # to avoid false positives from spurious country detection
            if parsed.country and parsed.country not in ["XU", "XW", None]:
                # Import country name mapping
                country_name = ISO_COUNTRIES.get(parsed.country, parsed.country)

                # Check if country name or code was explicitly in the filename
                # Use word boundaries to avoid false matches (e.g., "TH" in "The")
                filename_lower = pdf_path.stem.lower()

                # Check for country name (e.g., "South Africa", "United Kingdom")
                country_name_in_filename = bool(re.search(rf"\b{re.escape(country_name.lower())}\b", filename_lower))

                # Check for country code with word boundaries or as separate token
                # (e.g., "UK", "ZA" but not "TH" in "The")
                country_code_in_filename = bool(re.search(rf"\b{re.escape(parsed.country.lower())}\b", filename_lower))

                country_in_filename = country_name_in_filename or country_code_in_filename

                # Only append if:
                # 1. Country was in filename
                # 2. Country name not already in title
                # 3. Country code not already in title
                if (
                    country_in_filename
                    and country_name.lower() not in base_title.lower()
                    and parsed.country.lower() not in base_title.lower()
                ):
                    tracking_title = f"{base_title} {country_name}"

            # IMPORTANT: Sanitize tracking title to ensure consistency between:
            # 1. Tracking record title (database)
            # 2. Magazine title (database)
            # 3. Folder name (filesystem)
            # This prevents issues with special characters like : / \ that are invalid in filenames
            if tracking_title:
                tracking_title = sanitize_filename(tracking_title)

            # Check for duplicates using fuzzy matching on tracking titles AND issue date
            # A duplicate is defined as: same tracking title (fuzzy match) AND same issue date (within 5 days)
            # Normalize existing titles to use full country names for consistent comparison
            existing_magazines = session.query(Magazine).all()
            for existing in existing_magazines:
                # Normalize the existing title to use full country names instead of codes
                # This ensures "Esquire US" matches "Esquire United States"
                existing_normalized = existing.title
                existing_metadata = existing.extra_metadata or {}
                existing_country = existing_metadata.get("country")

                if existing_country:
                    country_name = ISO_COUNTRIES.get(existing_country, existing_country)
                    # Replace country code with country name if it appears at the end of the title
                    if existing.title.endswith(f" {existing_country}"):
                        existing_normalized = existing.title[: -len(existing_country) - 1] + f" {country_name}"

                is_match, score = self.title_matcher.match(tracking_title, existing_normalized)
                if is_match and parsed.issue_date and existing.issue_date:
                    date_diff = abs((parsed.issue_date - existing.issue_date).days)
                    # Also check language match for duplicates
                    same_language = (existing.language == parsed.language) or (
                        not existing.language and parsed.language == DEFAULT_LANGUAGE
                    )
                    if date_diff <= DUPLICATE_DATE_THRESHOLD_DAYS and same_language:
                        logger.warning(
                            f"Duplicate detected: '{tracking_title}' ({parsed.issue_date.strftime('%b %Y')}, {parsed.language}) matches existing "
                            f"'{existing.title}' ({existing.issue_date.strftime('%b %Y')}, {existing.language or DEFAULT_LANGUAGE}) "
                            f"(title score: {score}, date diff: {date_diff} days). Skipping import."
                        )
                        # Cleanup duplicate file from downloads if not already organized
                        if not skip_organize:
                            self._cleanup_download_file(pdf_path)
                        return {}

            cover_path = self._extract_cover(pdf_path)

            # OCR will be queued for background processing instead of running inline
            # This improves import speed and allows concurrent OCR processing
            should_queue_ocr = use_ocr and (cover_path or pdf_path) and OCRService.is_available()

            category = self.categorizer.categorize(parsed.title)

            if skip_organize:
                organized_path = pdf_path
                logger.info(f"Using file in place (already organized): {pdf_path}")
            else:
                # Convert parsed data to metadata dict for organizer
                metadata = {
                    "title": tracking_title,
                    "issue_date": parsed.issue_date,
                    "year": parsed.year,
                    "month_name": parsed.month_name,
                    "language": parsed.language,
                }
                organized_path = self.organizer.organize(pdf_path, metadata, category, organization_pattern)

                if not organized_path:
                    return {}

            # Build extra metadata, including special edition info if applicable
            extra_metadata = {
                "category": category,
                "imported_from": pdf_path.name,
                "import_date": datetime.now().isoformat(),
                "confidence": parsed.confidence,
                "parse_source": parsed.parse_source,
            }
            if parsed.country:
                extra_metadata["country"] = parsed.country
            if parsed.year:
                extra_metadata["year"] = parsed.year
            if parsed.month_name:
                extra_metadata["month"] = parsed.month_name
            if parsed.issue_number:
                extra_metadata["issue_number"] = parsed.issue_number
            if parsed.volume:
                extra_metadata["volume"] = parsed.volume
            if is_special_edition:
                extra_metadata["special_edition"] = special_name
                extra_metadata["full_title"] = parsed.title

            magazine = Magazine(
                title=tracking_title,
                issue_date=parsed.issue_date or datetime.now(),
                file_path=str(organized_path),
                cover_path=str(cover_path) if cover_path else None,
                content_hash=content_hash,
                extra_metadata=extra_metadata,
            )

            session.add(magazine)

            # Manage tracking record based on import settings
            # Priority:
            # 1. If tracking_id is provided (from DownloadSubmission), use that
            # 2. Otherwise, try to match with existing tracking using the matcher
            # 3. If no match, create new tracking or leave untracked based on auto_track setting

            target_tracking = None

            if tracking_id:
                # Tracking ID provided from download submission - validate and use it
                target_tracking = session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
                if target_tracking:
                    logger.info(
                        f"Using provided tracking_id={tracking_id} ('{target_tracking.title}') for '{tracking_title}'"
                    )
                else:
                    logger.warning(f"Provided tracking_id={tracking_id} not found, will try to find best match")

            if not target_tracking:
                # Try to find best match using the tracking matcher
                all_tracking = session.query(MagazineTracking).all()
                if all_tracking:
                    match_result = self.tracking_matcher.find_best_match(
                        parsed_title=tracking_title,
                        tracking_records=all_tracking,
                        parsed_language=parsed.language,
                        parsed_country=parsed.country,
                        parsed_category=category,
                    )

                    if match_result and match_result.is_match:
                        target_tracking = (
                            session.query(MagazineTracking)
                            .filter(MagazineTracking.id == match_result.tracking_id)
                            .first()
                        )
                        logger.info(
                            f"Matched '{tracking_title}' to existing tracking '{match_result.tracking_title}' "
                            f"(ID: {match_result.tracking_id}, score: {match_result.score})"
                        )

            if target_tracking:
                # Link to existing tracking
                magazine.tracking_id = target_tracking.id
                target_tracking.last_metadata_update = datetime.now()

                # IMPORTANT: Ensure magazine title matches tracking title for consistency
                # The tracking title is the canonical name, magazine and folder should match it
                if magazine.title != target_tracking.title:
                    logger.info(
                        f"Updating magazine title to match tracking: '{magazine.title}' -> '{target_tracking.title}'"
                    )
                    magazine.title = target_tracking.title

                    # If file was already organized, reorganize it to match tracking title
                    if not skip_organize and organized_path:
                        logger.info(f"Reorganizing file to match tracking title: {target_tracking.title}")
                        try:
                            # Build new path with tracking title
                            safe_tracking_title = sanitize_filename(target_tracking.title)
                            month = (
                                parsed.issue_date.strftime("%B") if parsed.issue_date else datetime.now().strftime("%B")
                            )
                            year = (
                                parsed.issue_date.strftime("%Y") if parsed.issue_date else datetime.now().strftime("%Y")
                            )
                            filename_base = f"{safe_tracking_title} - {month}{year}"

                            category_with_prefix = f"{self.category_prefix}{category}"
                            new_target_dir = self.organize_base_dir / category_with_prefix / safe_tracking_title / year
                            new_target_dir.mkdir(parents=True, exist_ok=True)

                            new_pdf_path = new_target_dir / f"{filename_base}.pdf"

                            # Only move if paths are different
                            if organized_path != new_pdf_path:
                                # Check if target path already exists in database (UNIQUE constraint check)
                                existing_record = session.query(Magazine).filter_by(file_path=str(new_pdf_path)).first()
                                if existing_record and existing_record.id != magazine.id:
                                    logger.warning(
                                        f"Cannot reorganize magazine {magazine.id}: Target path {new_pdf_path} "
                                        f"already exists in database for magazine {existing_record.id}. "
                                        f"Keeping original path: {organized_path}"
                                    )
                                else:
                                    shutil.move(str(organized_path), str(new_pdf_path))
                                    organized_path = new_pdf_path
                                    magazine.file_path = str(new_pdf_path)
                                    logger.info(f"Moved file to match tracking title: {new_pdf_path}")

                                    # Also move cover if it exists
                                    if cover_path and cover_path.exists():
                                        new_cover_path = new_target_dir / f"{filename_base}.jpg"
                                        shutil.move(str(cover_path), str(new_cover_path))
                                        magazine.cover_path = str(new_cover_path)
                                        logger.info(f"Moved cover to match tracking title: {new_cover_path}")
                        except Exception as e:
                            logger.warning(f"Failed to reorganize file to match tracking title: {e}")
                            # Continue with import even if reorganization fails

                logger.debug(f"Linked magazine to tracking: {target_tracking.title} (ID: {target_tracking.id})")

                # IMPORTANT: DO NOT update tracking mode for existing tracking records
                # The tracking mode is a user preference that should persist
                # Only update it if explicitly provided via tracking_id from a download submission
                # This prevents imports from inadvertently changing "track all" back to "watch"
                #
                # Note: tracking_mode parameter exists for creating NEW tracking records,
                # not for updating existing ones

                # If this is a special edition, ensure it's in the selected_editions
                if is_special_edition and special_name:
                    if target_tracking.selected_editions is None:
                        target_tracking.selected_editions = {}
                    if special_name not in target_tracking.selected_editions:
                        target_tracking.selected_editions[special_name] = True
                        logger.debug(f"Added special edition '{special_name}' to tracking: {target_tracking.title}")

            elif auto_track:
                # No match found, create new tracking record
                olid = generate_olid(tracking_title)
                track_all_editions = tracking_mode == "all"
                track_new_only = tracking_mode == "new"

                new_tracking = MagazineTracking(
                    olid=olid,
                    title=tracking_title,
                    language=parsed.language,
                    country=parsed.country,
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
                logger.info(
                    f"Created new tracking record: {tracking_title} (ID: {new_tracking.id}, mode: {tracking_mode})"
                )

                # If this is a special edition, add it to the selected_editions
                if is_special_edition:
                    logger.debug(f"Detected special edition '{special_name}' for: {tracking_title}")

            session.commit()
            logger.info(f"Added to database: {parsed.title} ({category})")

            # Run direct text scanning on PDF/EPUB files (fast, synchronous)
            if organized_path.suffix.lower() in [".pdf", ".epub"]:
                try:
                    # Check if text scanning is enabled
                    enable_text_scan = getattr(self, "_enable_text_scan", True)
                    if enable_text_scan:
                        logger.debug(f"Attempting direct text extraction for {magazine.id}")

                        # Use TextScanService for direct text extraction
                        scan_result = TextScanService.scan_document(str(organized_path), language=parsed.language)

                        # Always store text scan metadata (even if no text found)
                        if not magazine.extra_metadata:
                            magazine.extra_metadata = {}
                        magazine.extra_metadata["text_scan"] = scan_result

                        # Apply text scan metadata to main magazine fields if missing
                        if scan_result.get("text_found"):
                            fields_updated = _apply_scan_metadata_to_magazine(magazine, scan_result)
                            if fields_updated:
                                logger.info(f"Enhanced {magazine.title} with metadata from text scan")

                        from sqlalchemy.orm.attributes import flag_modified

                        flag_modified(magazine, "extra_metadata")
                        session.commit()

                        if scan_result.get("text_found"):
                            has_sufficient = scan_result.get("has_sufficient_metadata", False)
                            logger.info(
                                f"Successfully extracted text metadata for {magazine.title} "
                                f"(sufficient: {has_sufficient})"
                            )
                        else:
                            logger.debug(f"No text found in {organized_path.name}")
                    else:
                        logger.debug("Text scanning disabled in config")

                except Exception as e:
                    logger.debug(f"Direct text extraction failed for {magazine.id}: {e}")

            # Queue OCR job if OCR is enabled and available
            # OCR is the highest priority metadata source (see metadata.source_priority config)
            # It should be queued regardless of whether text extraction succeeded, so that
            # OCR results can override text_scan results during metadata aggregation
            if should_queue_ocr:
                try:
                    priority = OCRJob.PriorityEnum.HIGH.value if not skip_organize else OCRJob.PriorityEnum.NORMAL.value
                    ocr_job = OCRQueueService.queue_ocr_job(
                        db=session,
                        magazine_id=magazine.id,
                        priority=priority,
                        language=parsed.language,
                    )
                    if ocr_job:
                        logger.info(f"Queued OCR job {ocr_job.id} for magazine {magazine.id}")
                except Exception as e:
                    logger.warning(f"Failed to queue OCR job for magazine {magazine.id}: {e}")

            if not skip_organize:
                self._cleanup_download_file(pdf_path)

            return {"magazine_id": magazine.id}

        except Exception as e:
            session.rollback()
            logger.error(f"Error importing PDF {pdf_path}: {e}", exc_info=True)
            return {}

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

        cover_dir = self.organize_base_dir / ".covers"
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

        if not all_files:
            logger.info(f"No periodical files found in organized folders: {self.organize_base_dir}")
            return result.to_dict()

        pdf_files = [f for f in all_files if f.suffix.lower() == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower() == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower() == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix.lower() == ".cbr"]

        logger.info(
            f"[DATA IMPORT] Found {len(all_files)} files in organized folders to process "
            f"from {self.organize_base_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs, "
            f"{len(cbz_files)} CBZs, {len(cbr_files)} CBRs)"
        )
        logger.info("[DATA IMPORT] Text extraction enabled, OCR queued only for image-based files")

        for pdf_path in all_files:
            try:
                import_result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=None,
                    auto_track=auto_track,
                    skip_organize=True,
                    tracking_mode=tracking_mode,
                    use_ocr=True,  # Enable text extraction, OCR queued only if needed
                )
                if import_result:
                    result.data["imported"] += 1
                    logger.info(f"Successfully imported organized file: {pdf_path.name}")
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
                result.add_error(ErrorCodes.PROCESSING_FAILED, error_msg, retryable=True)
                logger.error(error_msg, exc_info=True)

        return result.to_dict()


# Export all public items for wildcard imports
__all__ = ["FileImporter"]
