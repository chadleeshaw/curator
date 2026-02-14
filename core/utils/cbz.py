"""
Comic Book Archive (CBZ/CBR) processing utilities.
Centralized CBZ/CBR cover extraction and validation logic.
"""

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

from core.constants.files import PIL_MAX_IMAGE_PIXELS, EPUB_COVER_QUALITY

logger = logging.getLogger(__name__)

# Increase Pillow's decompression bomb limit for high-res covers
Image.MAX_IMAGE_PIXELS = PIL_MAX_IMAGE_PIXELS

# Supported image extensions in comic archives
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def _convert_to_rgb(img: Image.Image) -> Image.Image:
    """
    Convert RGBA/LA/P mode images to RGB for JPEG output.

    Handles transparency by compositing onto a white background.

    Args:
        img: PIL Image in any mode

    Returns:
        PIL Image in RGB mode
    """
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        background.paste(img, mask=mask)
        return background
    return img


def validate_cbz(cbz_path: Path) -> bool:
    """
    Validate that a file is a readable CBZ (ZIP) archive.

    Args:
        cbz_path: Path to CBZ file

    Returns:
        True if CBZ appears to be valid, False otherwise
    """
    try:
        if not cbz_path.exists():
            logger.warning(f"CBZ file does not exist: {cbz_path}")
            return False

        if not zipfile.is_zipfile(cbz_path):
            logger.warning(f"File is not a valid ZIP archive: {cbz_path}")
            return False

        return True

    except Exception as e:
        logger.warning(f"CBZ validation error for {cbz_path}: {e}")
        return False


def validate_cbr(cbr_path: Path) -> bool:
    """
    Validate that a file is a readable CBR (RAR) archive.

    Args:
        cbr_path: Path to CBR file

    Returns:
        True if CBR appears to be valid, False otherwise
    """
    try:
        import rarfile

        if not cbr_path.exists():
            logger.warning(f"CBR file does not exist: {cbr_path}")
            return False

        if not rarfile.is_rarfile(cbr_path):
            logger.warning(f"File is not a valid RAR archive: {cbr_path}")
            return False

        return True

    except ImportError:
        logger.warning("rarfile not available. Install with: pip install rarfile")
        return False
    except Exception as e:
        logger.warning(f"CBR validation error for {cbr_path}: {e}")
        return False


def _get_sorted_image_files(archive, extension: str) -> list:
    """
    Get sorted list of image files from archive.

    Args:
        archive: ZipFile or RarFile object
        extension: File extension ('.cbz' or '.cbr')

    Returns:
        Sorted list of image file names
    """
    if extension == ".cbz":
        all_files = archive.namelist()
    else:  # .cbr
        all_files = [info.filename for info in archive.infolist()]

    # Filter for image files only
    image_files = [
        f for f in all_files if Path(f).suffix.lower() in IMAGE_EXTENSIONS and not Path(f).name.startswith(".")
    ]

    # Sort naturally (handle page numbers correctly)
    # Example: page1.jpg, page2.jpg, ..., page10.jpg
    image_files.sort()

    return image_files


def extract_cover_from_cbz(cbz_path: Path, output_dir: Path, quality: int = EPUB_COVER_QUALITY) -> Optional[Path]:
    """
    Extract first page/image from CBZ as cover.

    Args:
        cbz_path: Path to CBZ file
        output_dir: Directory to save cover image
        quality: JPEG quality (1-100)

    Returns:
        Path to extracted cover image, or None if failed
    """
    try:
        if not validate_cbz(cbz_path):
            logger.error(f"Invalid or corrupted CBZ file: {cbz_path}")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        # Use the source filename stem directly - the caller is responsible
        # for providing a path with a unique name (e.g., after organization)
        cover_path = output_dir / f"{cbz_path.stem}.jpg"

        with zipfile.ZipFile(cbz_path, "r") as zip_file:
            image_files = _get_sorted_image_files(zip_file, ".cbz")

            if not image_files:
                logger.warning(f"No image files found in CBZ: {cbz_path}")
                return None

            # Extract first image as cover
            first_image = image_files[0]
            logger.debug(f"Extracting cover from CBZ: {first_image}")

            image_data = zip_file.read(first_image)
            img = Image.open(BytesIO(image_data))

            # Convert RGBA/LA/P to RGB for JPEG
            img = _convert_to_rgb(img)

            img.save(str(cover_path), "JPEG", quality=quality)
            logger.info(f"Extracted CBZ cover: {cover_path}")
            return cover_path

    except Exception as e:
        logger.error(f"Error extracting cover from CBZ {cbz_path}: {e}")
        return None


def extract_cover_from_cbr(cbr_path: Path, output_dir: Path, quality: int = EPUB_COVER_QUALITY) -> Optional[Path]:
    """
    Extract first page/image from CBR as cover.

    Args:
        cbr_path: Path to CBR file
        output_dir: Directory to save cover image
        quality: JPEG quality (1-100)

    Returns:
        Path to extracted cover image, or None if failed
    """
    try:
        import rarfile

        if not validate_cbr(cbr_path):
            logger.error(f"Invalid or corrupted CBR file: {cbr_path}")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        # Use the source filename stem directly - the caller is responsible
        # for providing a path with a unique name (e.g., after organization)
        cover_path = output_dir / f"{cbr_path.stem}.jpg"

        with rarfile.RarFile(cbr_path, "r") as rar_file:
            image_files = _get_sorted_image_files(rar_file, ".cbr")

            if not image_files:
                logger.warning(f"No image files found in CBR: {cbr_path}")
                return None

            # Extract first image as cover
            first_image = image_files[0]
            logger.debug(f"Extracting cover from CBR: {first_image}")

            image_data = rar_file.read(first_image)
            img = Image.open(BytesIO(image_data))

            # Convert RGBA/LA/P to RGB for JPEG
            img = _convert_to_rgb(img)

            img.save(str(cover_path), "JPEG", quality=quality)
            logger.info(f"Extracted CBR cover: {cover_path}")
            return cover_path

    except ImportError:
        logger.warning("rarfile not available. Install with: pip install rarfile")
        return None
    except Exception as e:
        logger.error(f"Error extracting cover from CBR {cbr_path}: {e}")
        return None
