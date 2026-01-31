"""
Cover extraction service for periodical files.
Handles extracting cover images from PDF, EPUB, CBZ, and CBR files.
"""

import logging
from pathlib import Path

from core.constants.files import (
    PDF_COVER_DPI_HIGH,
    PDF_COVER_QUALITY_HIGH,
)
from core.utils.pdf import extract_cover_from_pdf as extract_cover_util
from core.utils.epub import extract_cover_from_epub
from core.utils.cbz import extract_cover_from_cbz, extract_cover_from_cbr

logger = logging.getLogger(__name__)


class CoverExtractor:
    """Extract cover images from various periodical file formats"""

    @staticmethod
    def extract_cover(file_path: str, output_path: str) -> bool:
        """
        Extract cover from periodical file (PDF, EPUB, CBZ, or CBR).

        Args:
            file_path: Path to periodical file
            output_path: Where to save the cover JPG

        Returns:
            True if successful, False otherwise
        """
        file_path_obj = Path(file_path)
        output_path_obj = Path(output_path)
        output_dir = output_path_obj.parent
        extension = file_path_obj.suffix.lower()

        result = None

        if extension == ".pdf":
            result = extract_cover_util(
                file_path_obj,
                output_dir,
                dpi=PDF_COVER_DPI_HIGH,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".epub":
            result = extract_cover_from_epub(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".cbz":
            result = extract_cover_from_cbz(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        elif extension == ".cbr":
            result = extract_cover_from_cbr(
                file_path_obj,
                output_dir,
                quality=PDF_COVER_QUALITY_HIGH,
            )
        else:
            logger.warning(f"Unsupported file type for cover extraction: {extension}")
            return False

        if result:
            if result != output_path_obj:
                result.rename(output_path_obj)
            return True
        return False
