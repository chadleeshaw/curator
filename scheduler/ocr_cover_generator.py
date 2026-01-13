"""
Scheduled task for generating high-resolution cover PNGs for OCR processing.
Runs periodically to prepare covers for OCR and clean up orphaned files.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from PIL import Image
from sqlalchemy.orm import sessionmaker

from models.database import Magazine, OCRJob
from services.ocr_queue import OCRQueueService
from services.ocr_service import OCRService

logger = logging.getLogger(__name__)


class OCRCoverGeneratorTask:
    """
    Generate high-resolution PNG covers for OCR processing.

    This task performs:
    1. Generates 300 DPI PNG files from covers for OCR processing
    2. Queues OCR jobs for magazines that need OCR
    3. Cleans up orphaned PNG files (not tied to any magazine)
    4. Removes PNG files after OCR is completed
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        organize_base_dir: str,
        config_loader=None,
    ):
        """
        Initialize OCR cover generator task.

        Args:
            session_factory: SQLAlchemy session factory
            organize_base_dir: Base directory for organized files
            config_loader: ConfigLoader instance for checking OCR enabled setting
        """
        self.session_factory = session_factory
        self.organize_base_dir = Path(organize_base_dir)
        self.config_loader = config_loader
        self.ocr_covers_dir = self.organize_base_dir / ".ocr_covers"
        self.ocr_covers_dir.mkdir(parents=True, exist_ok=True)

        # Clean up all PNG files on startup (they can be regenerated as needed)
        self._startup_cleanup()

    async def run(self) -> Dict[str, Any]:
        """
        Execute OCR cover generation task.

        Returns:
            Dict with statistics
        """
        # Check if OCR is enabled in config
        if self.config_loader:
            import_config = self.config_loader.get_import()
            if not import_config.get("enable_ocr", True):
                logger.debug("OCR is disabled in config, skipping OCR cover generation")
                return {"skipped": True, "reason": "OCR disabled in config"}

        if not OCRService.is_available():
            logger.debug("OCR service not available, skipping OCR cover generation")
            return {"skipped": True, "reason": "OCR not available"}

        logger.info("Starting OCR cover generation task")
        try:
            db_session = self.session_factory()
            try:
                # Get all magazines with covers
                # Query all magazines that have PDF files
                magazines_with_pdfs = db_session.query(Magazine).filter(
                    Magazine.file_path.isnot(None)
                ).all()

                logger.info(f"Found {len(magazines_with_pdfs)} magazines with PDF files")

                # Filter to those that exist and need OCR
                magazines_needing_ocr = []
                for mag in magazines_with_pdfs:
                    if not mag.file_path or not Path(mag.file_path).exists():
                        logger.debug(f"Skipping {mag.title}: PDF file path missing or doesn't exist")
                        continue

                    # Check if already has OCR metadata or sufficient text scan results
                    if mag.extra_metadata:
                        # Skip if OCR was already completed
                        if mag.extra_metadata.get("ocr_metadata"):
                            logger.debug(f"Skipping {mag.title}: already has OCR metadata")
                            continue

                        # Skip if text scan found text with sufficient metadata
                        text_scan = mag.extra_metadata.get("text_scan", {})
                        if text_scan.get("text_found") and text_scan.get("has_sufficient_metadata"):
                            logger.debug(f"Skipping {mag.title}: text scan found sufficient metadata")
                            continue

                    # Check if OCR job already exists
                    existing_job = db_session.query(OCRJob).filter(
                        OCRJob.magazine_id == mag.id,
                        OCRJob.status.in_([OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING])
                    ).first()

                    if existing_job:
                        logger.debug(f"Skipping {mag.title}: OCR job already exists (status: {existing_job.status.value})")
                        continue

                    magazines_needing_ocr.append(mag)

                logger.info(f"Found {len(magazines_needing_ocr)} magazines needing OCR processing")

                # Part 1: Generate high-res PNG files for OCR
                generated_count = 0
                queued_count = 0
                loop = asyncio.get_event_loop()

                for magazine in magazines_needing_ocr:
                    try:
                        # Generate high-res PNG for OCR from PDF
                        png_path = await loop.run_in_executor(
                            None,
                            self._generate_ocr_cover,
                            magazine.file_path,
                            magazine.id
                        )

                        if png_path:
                            generated_count += 1
                            logger.debug(f"Generated OCR cover for: {magazine.title}")

                            # Queue OCR job
                            ocr_job = OCRQueueService.queue_ocr_job(
                                db=db_session,
                                magazine_id=magazine.id,
                                priority=OCRJob.PriorityEnum.LOW.value,
                                language=magazine.language
                            )
                            if ocr_job:
                                queued_count += 1
                                logger.debug(f"Queued OCR job {ocr_job.id} for {magazine.title}")

                    except Exception as e:
                        logger.error(f"Error generating OCR cover for {magazine.title}: {e}")

                # Part 2: Clean up orphaned PNG files
                deleted_orphaned = await self._cleanup_orphaned_pngs(db_session)

                # Part 3: Clean up PNG files for completed OCR jobs
                deleted_completed = await self._cleanup_completed_pngs(db_session)

                if generated_count > 0 or deleted_orphaned > 0 or deleted_completed > 0:
                    msg_parts = []
                    if generated_count > 0:
                        msg_parts.append(f"generated {generated_count} OCR covers")
                    if queued_count > 0:
                        msg_parts.append(f"queued {queued_count} OCR jobs")
                    if deleted_orphaned > 0:
                        msg_parts.append(f"deleted {deleted_orphaned} orphaned PNGs")
                    if deleted_completed > 0:
                        msg_parts.append(f"deleted {deleted_completed} completed PNGs")
                    logger.info(f"OCR cover generation: {', '.join(msg_parts)}")

                return {
                    "generated_count": generated_count,
                    "queued_count": queued_count,
                    "deleted_orphaned": deleted_orphaned,
                    "deleted_completed": deleted_completed,
                }

            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"OCR cover generation error: {e}", exc_info=True)
            return {
                "generated_count": 0,
                "queued_count": 0,
                "deleted_orphaned": 0,
                "deleted_completed": 0,
                "error": str(e),
            }

    def _generate_ocr_cover(self, pdf_path: str, magazine_id: int) -> Optional[Path]:
        """
        Generate high-resolution PNG for OCR processing from PDF.

        Args:
            pdf_path: Path to the PDF file
            magazine_id: Magazine ID for naming

        Returns:
            Path to generated PNG file, or None if failed
        """
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                logger.warning(f"PDF not found: {pdf_path}")
                return None

            # Generate PNG filename
            png_filename = f"{magazine_id}_ocr.png"
            png_path = self.ocr_covers_dir / png_filename

            # Skip if already exists
            if png_path.exists():
                # Check if existing PNG is too large and needs regeneration
                try:
                    from core.constants import OCR_IMAGE_MAX_DIMENSION
                    with Image.open(png_path) as img:
                        if max(img.size) > OCR_IMAGE_MAX_DIMENSION:
                            logger.info(f"Existing OCR PNG is too large ({img.size}), regenerating: {png_path}")
                            png_path.unlink()  # Delete the old oversized PNG
                        else:
                            logger.debug(f"OCR PNG already exists: {png_path}")
                            return png_path
                except Exception as e:
                    logger.warning(f"Error checking PNG size, will regenerate: {e}")
                    png_path.unlink()  # Delete corrupted PNG

            # Extract first page from PDF at high resolution for OCR
            from core.pdf_utils import extract_cover_from_pdf
            from core.constants import PDF_COVER_DPI_OCR

            # Create temporary output directory for this extraction
            temp_output_dir = self.ocr_covers_dir
            temp_output_dir.mkdir(parents=True, exist_ok=True)

            # Extract at OCR-optimized DPI as PNG
            from pdf2image import convert_from_path

            images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_OCR, fmt='png')

            if not images:
                logger.warning(f"Failed to extract OCR PNG from: {pdf_path}")
                return None

            img = images[0]

            # Resize if too large for OCR (using optimal max dimension)
            from core.constants import OCR_IMAGE_MAX_DIMENSION
            if max(img.size) > OCR_IMAGE_MAX_DIMENSION:
                ratio = OCR_IMAGE_MAX_DIMENSION / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.debug(f"Resized OCR PNG from {images[0].size} to {new_size} for optimal OCR performance")

            # Save as PNG
            img.save(str(png_path), "PNG")

            if not png_path.exists():
                logger.warning(f"Failed to save OCR PNG: {png_path}")
                return None

            logger.debug(f"Generated high-res PNG for OCR: {png_path}")
            return png_path

        except Exception as e:
            logger.error(f"Error generating OCR cover from {pdf_path}: {e}")
            return None

    async def _cleanup_orphaned_pngs(self, db_session) -> int:
        """
        Clean up PNG files that don't have a corresponding magazine.

        Args:
            db_session: Database session

        Returns:
            Number of files deleted
        """
        try:
            deleted_count = 0

            # Get all magazine IDs
            magazine_ids = {mag.id for mag in db_session.query(Magazine.id).all()}

            # Check all PNG files in ocr_covers directory
            for png_file in self.ocr_covers_dir.glob("*_ocr.png"):
                try:
                    # Extract magazine ID from filename (e.g., "123_ocr.png" -> 123)
                    magazine_id = int(png_file.stem.replace("_ocr", ""))

                    # Delete if magazine doesn't exist
                    if magazine_id not in magazine_ids:
                        png_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted orphaned OCR PNG: {png_file}")
                except (ValueError, Exception) as e:
                    logger.debug(f"Error processing {png_file}: {e}")

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up orphaned PNGs: {e}")
            return 0

    async def _cleanup_completed_pngs(self, db_session) -> int:
        """
        Clean up PNG files for magazines that have completed OCR.

        Args:
            db_session: Database session

        Returns:
            Number of files deleted
        """
        try:
            deleted_count = 0

            # Get magazines that have OCR metadata (OCR completed)
            magazines_with_ocr = db_session.query(Magazine.id).filter(
                Magazine.extra_metadata.isnot(None)
            ).all()

            completed_ids = set()
            for mag in magazines_with_ocr:
                # Re-query to access extra_metadata properly
                magazine = db_session.query(Magazine).filter(Magazine.id == mag.id).first()
                if magazine.extra_metadata and (magazine.extra_metadata.get("ocr_metadata") or magazine.extra_metadata.get("text_metadata")):
                    completed_ids.add(magazine.id)

            # Delete PNG files for completed magazines
            for png_file in self.ocr_covers_dir.glob("*_ocr.png"):
                try:
                    magazine_id = int(png_file.stem.replace("_ocr", ""))

                    if magazine_id in completed_ids:
                        png_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted completed OCR PNG: {png_file}")
                except (ValueError, Exception) as e:
                    logger.debug(f"Error processing {png_file}: {e}")

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up completed PNGs: {e}")
            return 0

    def _startup_cleanup(self):
        """Clean up OCR PNG files on startup, except those with pending/processing OCR jobs."""
        try:
            # Get pending/processing OCR job magazine IDs
            db_session = self.session_factory()
            try:
                active_jobs = db_session.query(OCRJob.magazine_id).filter(
                    OCRJob.status.in_([OCRJob.StatusEnum.PENDING, OCRJob.StatusEnum.PROCESSING])
                ).all()

                active_magazine_ids = {job.magazine_id for job in active_jobs}

                deleted_count = 0
                for png_file in self.ocr_covers_dir.glob("*_ocr.png"):
                    try:
                        # Extract magazine ID from filename
                        magazine_id = int(png_file.stem.replace("_ocr", ""))

                        # Skip if there's an active OCR job for this magazine
                        if magazine_id in active_magazine_ids:
                            logger.debug(f"Keeping PNG for pending OCR job: {png_file}")
                            continue

                        png_file.unlink()
                        deleted_count += 1
                    except (ValueError, Exception) as e:
                        logger.debug(f"Error processing {png_file}: {e}")

                if deleted_count > 0:
                    logger.info(f"Startup cleanup: deleted {deleted_count} OCR PNG files")

            finally:
                db_session.close()

        except Exception as e:
            logger.error(f"Error during startup cleanup: {e}")
