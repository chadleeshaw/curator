"""
Scheduled task for cleaning up orphaned covers and generating missing ones.
Runs periodically to maintain cover image consistency.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from models.database import Magazine
from services.ocr_service import OCRService

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
                ocr_updated_count = 0
                for magazine in periodicals_without_covers:
                    file_path = Path(magazine.file_path)
                    if not file_path.exists():
                        continue

                    # Extract cover from PDF or EPUB
                    cover_path = self.file_importer._extract_cover(file_path)
                    if cover_path:
                        magazine.cover_path = str(cover_path)
                        generated_count += 1
                        logger.debug(
                            f"Generated missing cover for: {magazine.title}"
                        )

                        # Run OCR on the newly generated cover
                        if OCRService.is_available():
                            try:
                                logger.debug(f"Running OCR on newly generated cover: {cover_path}")
                                ocr_metadata = OCRService.analyze_cover(str(cover_path))
                                if ocr_metadata.get('text_found'):
                                    # Update extra_metadata with OCR findings
                                    if magazine.extra_metadata is None:
                                        magazine.extra_metadata = {}
                                    magazine.extra_metadata["ocr_metadata"] = {
                                        "detected_text": ocr_metadata.get('detected_text', '')[:500],
                                        "ocr_issue_number": ocr_metadata.get('issue_number'),
                                        "ocr_year": ocr_metadata.get('year'),
                                        "ocr_month": ocr_metadata.get('month'),
                                        "ocr_volume": ocr_metadata.get('volume'),
                                        "ocr_special_edition": ocr_metadata.get('special_edition', False)
                                    }
                                    ocr_updated_count += 1
                                    logger.info(f"OCR metadata added for: {magazine.title}")
                            except Exception as ocr_error:
                                logger.warning(f"OCR failed for {magazine.title}: {ocr_error}")

                # Part 3: Run OCR on existing covers that don't have OCR metadata
                ocr_scanned_count = 0
                if OCRService.is_available():
                    for magazine in periodicals_with_covers:
                        # Check if magazine already has OCR metadata
                        if (magazine.extra_metadata
                                and magazine.extra_metadata.get('ocr_metadata')):
                            continue

                        # Run OCR on existing cover
                        try:
                            logger.debug(f"Running OCR on existing cover: {magazine.cover_path}")
                            ocr_metadata = OCRService.analyze_cover(str(magazine.cover_path))
                            if ocr_metadata.get('text_found'):
                                # Update extra_metadata with OCR findings
                                if magazine.extra_metadata is None:
                                    magazine.extra_metadata = {}
                                magazine.extra_metadata["ocr_metadata"] = {
                                    "detected_text": ocr_metadata.get('detected_text', '')[:500],
                                    "ocr_issue_number": ocr_metadata.get('issue_number'),
                                    "ocr_year": ocr_metadata.get('year'),
                                    "ocr_month": ocr_metadata.get('month'),
                                    "ocr_volume": ocr_metadata.get('volume'),
                                    "ocr_special_edition": ocr_metadata.get('special_edition', False)
                                }
                                ocr_scanned_count += 1
                                logger.info(f"OCR metadata added to existing cover: {magazine.title}")
                        except Exception as ocr_error:
                            logger.warning(f"OCR failed for existing cover {magazine.title}: {ocr_error}")

                if generated_count > 0 or ocr_scanned_count > 0:
                    db_session.commit()
                    msg_parts = []
                    if generated_count > 0:
                        msg_parts.append(f"Generated {generated_count} missing covers")
                    if ocr_updated_count > 0:
                        msg_parts.append(f"added OCR to {ocr_updated_count} new covers")
                    if ocr_scanned_count > 0:
                        msg_parts.append(f"scanned {ocr_scanned_count} existing covers")
                    logger.info(f"Cleanup covers: {', '.join(msg_parts)}")

                return {
                    "deleted_count": deleted_count,
                    "generated_count": generated_count,
                    "ocr_updated_count": ocr_updated_count,
                    "ocr_scanned_count": ocr_scanned_count
                }

            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Cover cleanup error: {e}", exc_info=True)
            return {
                "deleted_count": 0,
                "generated_count": 0,
                "ocr_updated_count": 0,
                "ocr_scanned_count": 0,
                "error": str(e)
            }
