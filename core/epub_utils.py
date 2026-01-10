"""
EPUB processing utilities.
Centralized EPUB cover extraction logic.
"""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def extract_cover_from_epub(
    epub_path: Path,
    output_dir: Path,
    quality: int = 85
) -> Optional[Path]:
    """
    Extract cover image from EPUB file.

    Args:
        epub_path: Path to EPUB file
        output_dir: Directory to save cover image
        quality: JPEG quality (1-100)

    Returns:
        Path to extracted cover image, or None if failed
    """
    try:
        from ebooklib import epub

        output_dir.mkdir(parents=True, exist_ok=True)
        cover_path = output_dir / f"{epub_path.stem}.jpg"

        # Read the EPUB file
        book = epub.read_epub(str(epub_path))

        # Try to get cover image
        cover_image_data = None
        cover_item = None

        # Method 1: Try to get cover via metadata
        for item in book.get_items():
            if item.get_type() == 9:  # EBOOKLIB.ITEM_COVER
                cover_item = item
                break

        # Method 2: Look for cover in metadata
        if not cover_item:
            for item in book.get_items_of_type(9):  # Cover items
                cover_item = item
                break

        # Method 3: Search for cover by name
        if not cover_item:
            for item in book.get_items():
                if item.get_type() == 9 or 'cover' in item.get_name().lower():
                    if item.media_type and item.media_type.startswith('image/'):
                        cover_item = item
                        break

        # Method 4: Try first image in the book
        if not cover_item:
            for item in book.get_items():
                if item.media_type and item.media_type.startswith('image/'):
                    cover_item = item
                    break

        if cover_item:
            cover_image_data = cover_item.get_content()

        if not cover_image_data:
            logger.warning(f"Could not extract cover from EPUB: {epub_path}")
            return None

        # Convert to JPEG if needed
        from io import BytesIO
        img = Image.open(BytesIO(cover_image_data))

        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background

        img.save(str(cover_path), "JPEG", quality=quality)
        logger.info(f"Extracted EPUB cover: {cover_path}")
        return cover_path

    except ImportError:
        logger.warning("ebooklib not available. Install with: pip install ebooklib")
        return None
    except Exception as e:
        logger.error(f"Error extracting cover from EPUB {epub_path}: {e}")
        return None
