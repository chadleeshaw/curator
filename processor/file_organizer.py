"""
File organization utilities for moving and renaming PDFs.
Handles pattern-based organization with support for tags like {category}, {title}, {year}.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.utils import sanitize_filename

logger = logging.getLogger(__name__)


class FileOrganizer:
    """Organize and rename files based on patterns"""

    def __init__(self, organize_base_dir: Path):
        """
        Initialize file organizer.

        Args:
            organize_base_dir: Base directory for organized files
        """
        self.organize_base_dir = organize_base_dir

    def organize(
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
            if not pattern:
                return pdf_path

            # Create organized filename: "Title - MonYear.pdf"
            title = metadata.get("title", pdf_path.stem)
            issue_date = metadata.get("issue_date", datetime.now())

            safe_title = sanitize_filename(title)
            month = issue_date.strftime("%b")
            year = issue_date.strftime("%Y")
            day = issue_date.strftime("%d")
            filename = f"{safe_title} - {month}{year}.pdf"

            target_path_str = pattern.format(
                category=category, title=safe_title, year=year, month=month, day=day
            )

            if not target_path_str.startswith("/"):
                target_dir = self.organize_base_dir / target_path_str
            else:
                target_dir = Path(target_path_str)

            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / filename

            if target_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = filename.rsplit(".", 1)
                filename = f"{name_parts[0]} ({timestamp}).pdf"
                target_path = target_dir / filename

            shutil.move(str(pdf_path), str(target_path))
            logger.info(f"Organized file: {target_path}")
            return target_path

        except Exception as e:
            logger.error(f"Error organizing file {pdf_path}: {e}")
            return None
