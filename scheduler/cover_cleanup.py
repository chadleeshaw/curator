"""
Scheduled task for cleaning up orphaned covers and generating missing ones.
Runs periodically to maintain cover image consistency.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from models.database import Magazine

logger = logging.getLogger(__name__)


class CoverCleanupTask:
    """
    Clean up orphaned cover files and generate missing covers.

    This task performs two main functions:
    1. Deletes orphaned covers (cover files on disk not tied to any periodical)
    2. Generates missing covers (extracts covers for periodicals that don't have one)
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        organize_base_dir: str,
        file_importer,
    ):
        """
        Initialize cover cleanup task.

        Args:
            session_factory: SQLAlchemy session factory
            organize_base_dir: Base directory for organized files
            file_importer: FileImporter instance for extracting covers
        """
        self.session_factory = session_factory
        self.organize_base_dir = Path(organize_base_dir)
        self.file_importer = file_importer

    async def run(self) -> dict:
        """
        Execute cover cleanup task.

        Returns:
            Dict with deleted_count and generated_count
        """
        try:
            db_session = self.session_factory()
            try:
                # Get all periodicals
                all_periodicals = db_session.query(Magazine).all()
                periodicals_with_covers = [
                    m
                    for m in all_periodicals
                    if m.cover_path and Path(m.cover_path).exists()
                ]
                periodicals_without_covers = [
                    m
                    for m in all_periodicals
                    if m.file_path
                    and (not m.cover_path or not Path(m.cover_path).exists())
                ]

                db_cover_paths = {
                    str(Path(m.cover_path).resolve())
                    for m in periodicals_with_covers
                }

                # Find all cover files on disk
                covers_dir = self.organize_base_dir / ".covers"
                covers_dir.mkdir(parents=True, exist_ok=True)

                # Part 1: Delete orphaned covers
                deleted_count = 0
                if covers_dir.exists():
                    # Get absolute paths of all cover files on disk
                    cover_files = set(str(f.resolve()) for f in covers_dir.glob("*.jpg"))
                    orphaned_covers = cover_files - db_cover_paths

                    for orphan_path in orphaned_covers:
                        try:
                            Path(orphan_path).unlink()
                            deleted_count += 1
                            logger.debug(f"Deleted orphaned cover: {orphan_path}")
                        except Exception as e:
                            logger.error(
                                f"Error deleting orphaned cover {orphan_path}: {e}"
                            )

                    if deleted_count > 0:
                        logger.info(
                            f"Cleanup covers: Deleted {deleted_count} orphaned cover files"
                        )

                # Part 2: Generate missing covers
                generated_count = 0
                for magazine in periodicals_without_covers:
                    pdf_path = Path(magazine.file_path)
                    if not pdf_path.exists():
                        continue

                    # Extract cover from PDF
                    cover_path = self.file_importer._extract_cover(pdf_path)
                    if cover_path:
                        magazine.cover_path = str(cover_path)
                        generated_count += 1
                        logger.debug(
                            f"Generated missing cover for: {magazine.title}"
                        )

                if generated_count > 0:
                    db_session.commit()
                    logger.info(
                        f"Cleanup covers: Generated {generated_count} missing covers"
                    )

                return {
                    "deleted_count": deleted_count,
                    "generated_count": generated_count
                }

            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Cover cleanup error: {e}", exc_info=True)
            return {"deleted_count": 0, "generated_count": 0, "error": str(e)}
