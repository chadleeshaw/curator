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

    def __init__(self, downloads_dir: str, organize_base_dir: str, fuzzy_threshold: int = 80, organization_pattern: Optional[str] = None):
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

    def process_downloads(self, session: Session, organization_pattern: Optional[str] = None) -> Dict[str, Any]:
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

        # Find all PDF files - both flat and nested
        pdf_files = list(self.downloads_dir.glob("*.pdf"))

        # Also look in subdirectories if configured
        pdf_files.extend(list(self.downloads_dir.glob("*/*.pdf")))

        if not pdf_files:
            logger.info("No PDF files found in downloads folder")
            return results

        logger.info(f"Found {len(pdf_files)} PDF files to process")

        for pdf_path in pdf_files:
            try:
                result = self.import_pdf(pdf_path, session, organization_pattern)
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

        return results

    def import_pdf(self, pdf_path: Path, session: Session, organization_pattern: Optional[str] = None, auto_track: bool = True) -> bool:
        """
        Import a single PDF file.

        Args:
            pdf_path: Path to PDF file
            session: Database session
            organization_pattern: Optional custom organization pattern with tags like {category}, {title}, {year}
            auto_track: Whether to auto-create tracking records for imported periodicals

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract metadata from filename
            metadata = self._extract_metadata_from_filename(pdf_path.stem)

            # Standardize the title for consistency
            raw_title = metadata.get("title", "")
            standardized_title = self.title_matcher.standardize_title(raw_title)
            metadata["title"] = standardized_title

            # Check for duplicates using fuzzy matching on standardized titles
            existing_magazines = session.query(Magazine).all()
            for existing in existing_magazines:
                is_match, score = self.title_matcher.match(standardized_title, existing.title)
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

            # Organize the file
            organized_path = self._organize_file(pdf_path, metadata, category, organization_pattern)

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

            # Also create a tracking record for this periodical if auto_track is enabled and not already tracking it
            if auto_track:
                olid = standardized_title.lower().replace(" ", "_").replace("-", "_")
                existing_tracking = session.query(MagazineTracking).filter(MagazineTracking.olid == olid).first()
                if not existing_tracking:
                    tracking = MagazineTracking(
                        olid=olid,
                        title=standardized_title,
                        publisher=metadata.get("publisher"),
                        track_all_editions=True,  # Auto-import all editions for imported periodicals
                        selected_editions={},
                        selected_years=[],
                        last_metadata_update=datetime.now(),
                    )
                    session.add(tracking)
                    session.commit()
                    logger.info(f"Created tracking record for: {standardized_title}")

            # Delete the original PDF from downloads folder after successful import
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

    def _extract_metadata_from_filename(self, filename: str) -> Dict[str, Any]:
        """
        Extract metadata from filename.
        Supports formats like:
        - "National Geographic - Dec2024" or "Wired Magazine December 2024"
        - "National Geographic 2000-01" (year-issue format)
        - "PC Gamer 2023-06" (year-month format)

        Args:
            filename: PDF filename without extension

        Returns:
            Dict with extracted metadata
        """
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
                logger.warning(f"Could not parse date from filename pattern1: {filename}")

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
                    logger.warning(f"Could not parse date from filename pattern2: {filename}")

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

        # Pattern 4: Just extract a 4-digit year anywhere in the filename
        year_match = re.search(r"(\d{4})", filename)
        if year_match:
            year_str = year_match.group(1)
            try:
                # Assume January if no month specified
                metadata["issue_date"] = datetime.strptime(f"{year_str}-01-01", "%Y-%m-%d")
                logger.info(f"Extracted year {year_str} from filename: {filename}")
                return metadata
            except ValueError:
                logger.warning(f"Could not parse year from filename: {filename}")

        logger.info(f"No date pattern matched in filename: {filename}, using current date")
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
            images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=150)
            if not images:
                logger.warning(f"Could not extract images from PDF: {pdf_path}")
                return None

            # Save as JPEG
            images[0].save(str(cover_path), "JPEG", quality=85)
            logger.info(f"Extracted cover: {cover_path}")
            return cover_path

        except ImportError:
            logger.warning("pdf2image not available. Install with: pip install pdf2image Pillow")
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

    def _organize_file(self, pdf_path: Path, metadata: Dict[str, Any], category: str, pattern: Optional[str] = None) -> Optional[Path]:
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
                category=category,
                title=safe_title,
                year=year,
                month=month,
                day=day
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

    def process_organized_files(self, session: Session, auto_track: bool = True) -> Dict[str, Any]:
        """
        Process PDF files from organized folders (e.g., _Magazines, _Comics, _Articles, _News).
        These are files that have been manually placed or previously organized.

        Args:
            session: Database session
            auto_track: Whether to auto-create tracking records for imported periodicals

        Returns:
            Dict with import results
        """
        results = {
            "imported": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }

        if not self.organize_base_dir.exists():
            logger.warning(f"Organize directory not found: {self.organize_base_dir}")
            return results

        # Recursively find all PDF files in organized folders
        pdf_files = list(self.organize_base_dir.glob("**/*.pdf"))

        if not pdf_files:
            logger.info("No PDF files found in organized folders")
            return results

        logger.info(f"Found {len(pdf_files)} PDF files in organized folders to process")

        for pdf_path in pdf_files:
            try:
                # Use stored organization pattern from config (if available)
                pattern = self.organization_pattern or "_{category}/{title}/{year}"
                result = self.import_pdf(pdf_path, session, organization_pattern=pattern, auto_track=auto_track)
                if result:
                    results["imported"] += 1
                    logger.info(f"Successfully imported organized file: {pdf_path.name}")
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Failed to import {pdf_path.name}")
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Error importing organized file {pdf_path.name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg, exc_info=True)

        return results
