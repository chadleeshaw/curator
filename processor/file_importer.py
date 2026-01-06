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

from pdf2image import convert_from_path
from sqlalchemy.orm import Session

from core.matching import TitleMatcher
from core.utils import sanitize_filename
from models.database import Magazine, MagazineTracking

logger = logging.getLogger(__name__)


class FileImporter:
    """Import and process PDF files from downloads folder"""

    # Category keywords for automatic categorization
    CATEGORIES = {
        "Magazines": [
            "magazine",
            "national geographic",
            "wired",
            "time",
            "newsweek",
            "economist",
            "pc gamer",
            "forbes",
        ],
        "Comics": ["comic", "marvel", "dc", "graphic novel", "comic book"],
        "Articles": ["article", "paper", "journal", "report"],
        "News": ["news", "daily", "newspaper"],
    }

    def __init__(
        self,
        downloads_dir: str,
        organize_base_dir: str,
        fuzzy_threshold: int = 80,
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

        # Create base directory if it doesn't exist
        self.organize_base_dir.mkdir(parents=True, exist_ok=True)

        # Create category subdirectories
        for category in self.CATEGORIES.keys():
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

        # Find all PDF and EPUB files recursively
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

        # Combine all files
        all_files = pdf_files + epub_files

        if not all_files:
            logger.info(f"No PDF or EPUB files found in downloads folder: {self.downloads_dir}")
            return results

        logger.info(f"[DOWNLOADS IMPORT] Found {len(all_files)} files to process from {self.downloads_dir} ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)")

        # Process PDF files
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
            # Extract metadata from filename (pass full path for parent folder context)
            metadata = self._extract_metadata_from_filename(pdf_path)

            # Standardize the title for consistency
            raw_title = metadata.get("title", "")
            standardized_title = self.title_matcher.standardize_title(raw_title)
            metadata["title"] = standardized_title

            # Check for duplicates using fuzzy matching on standardized titles
            existing_magazines = session.query(Magazine).all()
            for existing in existing_magazines:
                is_match, score = self.title_matcher.match(
                    standardized_title, existing.title
                )
                if is_match:
                    logger.warning(
                        f"Duplicate detected: '{standardized_title}' matches existing '{existing.title}' "
                        f"(score: {score}). Skipping import."
                    )
                    return False

            # Extract cover image
            cover_path = self._extract_cover(pdf_path)

            # Categorize the file
            category = self._categorize_file(standardized_title)

            # Organize the file (skip if already organized)
            if skip_organize:
                # Use file in place - already organized
                organized_path = pdf_path
                logger.info(f"Using file in place (already organized): {pdf_path}")
            else:
                # Organize the file to new location
                organized_path = self._organize_file(
                    pdf_path, metadata, category, organization_pattern
                )

                if not organized_path:
                    return False

            # Add to database
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
                # Create or update tracking record
                if not existing_tracking:
                    # Set tracking flags based on mode
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
                    # Update existing tracking record with new mode
                    existing_tracking.track_all_editions = tracking_mode == "all"
                    existing_tracking.track_new_only = tracking_mode == "new"
                    existing_tracking.last_metadata_update = datetime.now()
                    session.commit()
                    logger.info(f"Updated tracking record for: {standardized_title} (mode: {tracking_mode})")
            else:
                # If auto_track is disabled, remove any existing tracking record
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

    def _get_magazine_name_from_path(self, pdf_path: Path) -> Optional[str]:
        """
        Walk up the directory tree to find a suitable magazine name.
        Skips year folders (4-digit numbers) and system folders.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Magazine name from parent directories, or None if not found
        """
        system_folders = {'.', '..', 'downloads', 'data', '_Magazines', '_Comics', '_Articles', '_News',
                          'local', 'cache', 'config', 'logs'}

        # Start with immediate parent and walk up
        current = pdf_path.parent
        while current and current != current.parent:  # Stop at root
            folder_name = current.name

            # Skip system folders
            if folder_name.lower() in system_folders:
                current = current.parent
                continue

            # Skip year folders (4-digit numbers in valid year range 1900-2100)
            # This allows "2600" (the magazine) while skipping actual year folders
            if folder_name.isdigit() and len(folder_name) == 4:
                year_value = int(folder_name)
                if 1900 <= year_value <= 2100:
                    current = current.parent
                    continue

            # Found a suitable magazine name
            return folder_name

        return None

    def _extract_metadata_from_filename(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from filename and parent directory.
        Supports formats like:
        - "National Geographic - Dec2024" or "Wired Magazine December 2024"
        - "National Geographic 2000-01" (year-issue format)
        - "PC Gamer 2023-06" (year-month format)
        - "Apr2001" in folder "2600/2001/" (walks up to find "2600")

        Args:
            pdf_path: Path object to the PDF file

        Returns:
            Dict with extracted metadata
        """
        filename = pdf_path.stem  # Get filename without extension
        magazine_name = self._get_magazine_name_from_path(pdf_path)  # Get magazine name from directory tree

        metadata = {
            "title": filename,
            "publisher": None,
            "issue_date": datetime.now(),
        }

        # Pattern 1: "Title - MonYear" (e.g., "National Geographic - Dec2024")
        pattern1 = r"(.+?)\s*-\s*([A-Za-z]{3})(\d{4})"
        match = re.search(pattern1, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            month_str = match.group(2)
            year_str = match.group(3)
            try:
                # Parse month and year
                date_str = f"{month_str} {year_str}"
                metadata["issue_date"] = datetime.strptime(date_str, "%b %Y")
                return metadata
            except ValueError:
                logger.warning(
                    f"Could not parse date from filename pattern1: {filename}"
                )

        # Pattern 2: "Title Periodical Month Year" (e.g., "Wired Periodical January 2024")
        pattern2 = r"(.+?)\s+([A-Za-z]+)\s+(\d{4})"
        match = re.search(pattern2, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            month_str = match.group(2)
            year_str = match.group(3)
            try:
                date_str = f"{month_str} {year_str}"
                metadata["issue_date"] = datetime.strptime(date_str, "%B %Y")
                return metadata
            except ValueError:
                try:
                    metadata["issue_date"] = datetime.strptime(date_str, "%b %Y")
                    return metadata
                except ValueError:
                    logger.warning(
                        f"Could not parse date from filename pattern2: {filename}"
                    )

        # Pattern 3: "Title YYYY-MM" (e.g., "National Geographic 2000-01" or "PC Gamer 2024-12")
        pattern3 = r"(.+?)\s+(\d{4})-(\d{2})$"
        match = re.search(pattern3, filename)
        if match:
            metadata["title"] = match.group(1).strip()
            year_str = match.group(2)
            month_str = match.group(3)
            try:
                date_str = f"{year_str}-{month_str}-01"
                metadata["issue_date"] = datetime.strptime(date_str, "%Y-%m-%d")
                return metadata
            except ValueError:
                logger.warning(f"Could not parse year-month from filename: {filename}")

        # Pattern 4: Filename is just a date (e.g., "Apr2001", "January2015")
        # In this case, use parent directory name as the title
        # Match: MonthYear or Month Year (e.g., "Apr2001", "January 2015")
        date_only_pattern1 = r"^([A-Za-z]+)(\d{4})$"  # "Apr2001"
        date_only_pattern2 = r"^([A-Za-z]+)\s+(\d{4})$"  # "April 2001"

        match = re.search(date_only_pattern1, filename) or re.search(date_only_pattern2, filename)
        if match:
            month_str = match.group(1)
            year_str = match.group(2)
            try:
                # Try full month name first, then 3-letter abbreviation
                date_str = f"{month_str} {year_str}"
                try:
                    parsed_date = datetime.strptime(date_str, "%B %Y")
                except ValueError:
                    parsed_date = datetime.strptime(date_str, "%b %Y")

                metadata["issue_date"] = parsed_date

                # Use magazine name from directory tree as title
                if magazine_name:
                    metadata["title"] = magazine_name
                    logger.info(f"Extracted title '{magazine_name}' from directory tree for date-only filename: {filename}")
                else:
                    metadata["title"] = filename
                    logger.warning(f"Filename is date-only ({filename}) but no suitable magazine folder found")

                return metadata
            except ValueError:
                logger.warning(f"Could not parse date from date-only filename: {filename}")

        # Pattern 5: Just extract a 4-digit year anywhere in the filename
        year_match = re.search(r"(\d{4})", filename)
        if year_match:
            year_str = year_match.group(1)
            try:
                # Assume January if no month specified
                metadata["issue_date"] = datetime.strptime(
                    f"{year_str}-01-01", "%Y-%m-%d"
                )

                # If magazine name found in directory tree, use it as title
                if magazine_name:
                    metadata["title"] = magazine_name
                    logger.info(f"Extracted title '{magazine_name}' from directory tree for year-only filename: {filename}")
                else:
                    logger.info(f"Extracted year {year_str} from filename: {filename}")

                return metadata
            except ValueError:
                logger.warning(f"Could not parse year from filename: {filename}")

        logger.info(
            f"No date pattern matched in filename: {filename}, using current date"
        )
        return metadata

    def _extract_cover(self, pdf_path: Path) -> Optional[Path]:
        """
        Extract first page of PDF as cover image.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Path to extracted cover image, or None if failed
        """
        try:
            # Generate cover path
            cover_dir = self.organize_base_dir / ".covers"
            cover_dir.mkdir(parents=True, exist_ok=True)
            cover_path = cover_dir / f"{pdf_path.stem}.jpg"

            # Convert first page to image
            images = convert_from_path(
                str(pdf_path), first_page=1, last_page=1, dpi=150
            )
            if not images:
                logger.warning(f"Could not extract images from PDF: {pdf_path}")
                return None

            # Save as JPEG
            images[0].save(str(cover_path), "JPEG", quality=85)
            logger.info(f"Extracted cover: {cover_path}")
            return cover_path

        except ImportError:
            logger.warning(
                "pdf2image not available. Install with: pip install pdf2image Pillow"
            )
            return None
        except Exception as e:
            logger.error(f"Error extracting cover from {pdf_path}: {e}")
            return None

    def _categorize_file(self, title: str) -> str:
        """
        Categorize file based on title keywords.

        Args:
            title: File or periodical title

        Returns:
            Category name (default: "Magazines")
        """
        title_lower = title.lower()

        for category, keywords in self.CATEGORIES.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return category

        return "Magazines"  # Default category

    def _organize_file(
        self,
        pdf_path: Path,
        metadata: Dict[str, Any],
        category: str,
        pattern: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Move and rename PDF to organized location based on pattern.
        Available pattern tags: {category}, {title}, {year}, {month}, {day}
        Default: data/{category}/{title}/{year}/

        Args:
            pdf_path: Original PDF path
            metadata: Extracted metadata
            category: Category name
            pattern: Organization pattern with tags (optional)

        Returns:
            Path to organized file, or None if failed
        """
        try:
            # If no pattern, don't organize
            if not pattern:
                return pdf_path

            # Create organized filename: "Title - MonYear.pdf"
            title = metadata.get("title", pdf_path.stem)
            issue_date = metadata.get("issue_date", datetime.now())

            # Sanitize title for filename/folder
            safe_title = sanitize_filename(title)
            month = issue_date.strftime("%b")
            year = issue_date.strftime("%Y")
            day = issue_date.strftime("%d")
            filename = f"{safe_title} - {month}{year}.pdf"

            # Substitute tags in pattern
            target_path_str = pattern.format(
                category=category, title=safe_title, year=year, month=month, day=day
            )

            # Make absolute path from organize_base_dir
            if not target_path_str.startswith("/"):
                target_dir = self.organize_base_dir / target_path_str
            else:
                target_dir = Path(target_path_str)

            target_dir.mkdir(parents=True, exist_ok=True)

            # Target path
            target_path = target_dir / filename

            # Handle duplicates
            if target_path.exists():
                # Add timestamp to make unique
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = filename.rsplit(".", 1)
                filename = f"{name_parts[0]} ({timestamp}).pdf"
                target_path = target_dir / filename

            # Move file
            shutil.move(str(pdf_path), str(target_path))
            logger.info(f"Organized file: {target_path}")
            return target_path

        except Exception as e:
            logger.error(f"Error organizing file {pdf_path}: {e}")
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
            Dict with import results
        """
        results = {"imported": 0, "failed": 0, "skipped": 0, "errors": []}

        if not self.organize_base_dir.exists():
            logger.warning(f"Organize directory not found: {self.organize_base_dir}")
            return results

        # Recursively find all PDF files in organized folders
        pdf_files = list(self.organize_base_dir.glob("**/*.pdf"))

        if not pdf_files:
            logger.info(f"No PDF files found in organized folders: {self.organize_base_dir}")
            return results

        logger.info(f"[DATA IMPORT] Found {len(pdf_files)} PDF files in organized folders to process from {self.organize_base_dir}")

        for pdf_path in pdf_files:
            try:
                # For already-organized files, skip reorganization
                result = self.import_pdf(
                    pdf_path,
                    session,
                    organization_pattern=None,
                    auto_track=auto_track,
                    skip_organize=True,  # Files are already organized
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
