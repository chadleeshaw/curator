import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.utils import sanitize_filename

logger = logging.getLogger(__name__)


class FileProcessor:
    """Process downloaded files and organize into standard naming convention"""

    # Pattern: {Title} - {MonYear} (e.g., "Wired Periodical - Dec2006")
    ORGANIZED_PATTERN = "{title} - {month}{year}"

    def __init__(self, organize_dir: str):
        self.organize_dir = Path(organize_dir)
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

        Args:
            source_path: Path to downloaded file
            title: Periodical title
            issue_date: Publication date
            cover_path: Optional path to cover art JPG

        Returns:
            Tuple of (pdf_path, jpg_path)
        """
        source = Path(source_path)

        # Generate filename: {Title} - {MonYear}
        month = issue_date.strftime("%b")  # Jan, Feb, Mar, etc.
        year = issue_date.strftime("%Y")

        # Sanitize title for filesystem
        safe_title = sanitize_filename(title)
        filename_base = f"{safe_title} - {month}{year}"

        pdf_path = self.organize_dir / f"{filename_base}.pdf"
        jpg_path = self.organize_dir / f"{filename_base}.jpg"

        # Move/rename PDF
        if source.suffix.lower() == ".pdf":
            try:
                source.rename(pdf_path)
                logger.info(f"Organized PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Error moving PDF: {e}")
                pdf_path = None
        else:
            logger.warning(f"Source file is not PDF: {source}")
            pdf_path = None

        # Move cover art if provided
        if cover_path and Path(cover_path).exists():
            try:
                Path(cover_path).rename(jpg_path)
                logger.info(f"Organized cover: {jpg_path}")
            except Exception as e:
                logger.error(f"Error moving cover: {e}")
                jpg_path = None

        return str(pdf_path), str(jpg_path)

    def extract_cover_from_pdf(self, pdf_path: str, output_path: str) -> bool:
        """
        Extract first page of PDF as JPG cover art.

        Args:
            pdf_path: Path to PDF file
            output_path: Where to save the cover JPG

        Returns:
            True if successful, False otherwise
        """
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
            if images:
                images[0].save(output_path, "JPEG", quality=85)
                logger.info(f"Extracted cover from PDF: {output_path}")
                return True
        except ImportError:
            logger.warning("pdf2image not installed, falling back to PyPDF2")
        except Exception as e:
            logger.warning(f"Error extracting cover from PDF: {e}")

        return False

    def parse_filename_for_metadata(self, filename: str) -> Dict[str, Any]:
        """
        Try to extract metadata from filename.

        Expected format: {Magazine Title} - {Abbr}{Year}
        Examples:
          - "Wired Magazine - Dec2006"
          - "National Geographic - Mar2023"

        Args:
            filename: Filename without extension

        Returns:
            Dict with extracted metadata (title, month, year)
        """
        # Pattern: anything - MonYear (e.g., "Wired Periodical - Dec2006")
        pattern = r"^(.+?)\s*-\s*([A-Za-z]{3})(\d{4})$"
        match = re.match(pattern, filename)

        if match:
            title, month_abbr, year = match.groups()

            # Convert month abbreviation to number
            months = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            }

            month = months.get(month_abbr.capitalize())
            if month:
                try:
                    issue_date = datetime(int(year), month, 1)
                    return {
                        "title": title.strip(),
                        "issue_date": issue_date,
                        "confidence": "high",
                    }
                except ValueError:
                    pass

        return {"confidence": "low"}
