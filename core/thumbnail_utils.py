"""
Thumbnail generation utilities.
Creates optimized thumbnails for web UI display.
"""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Increase Pillow's decompression bomb limit for processing high-res covers
Image.MAX_IMAGE_PIXELS = 200000000  # 200 megapixels

# Thumbnail settings
THUMBNAIL_MAX_WIDTH = 400
THUMBNAIL_MAX_HEIGHT = 600
THUMBNAIL_QUALITY = 80


def generate_thumbnail(
    source_path: Path,
    output_dir: Path,
    max_width: int = THUMBNAIL_MAX_WIDTH,
    max_height: int = THUMBNAIL_MAX_HEIGHT,
    quality: int = THUMBNAIL_QUALITY
) -> Optional[Path]:
    """
    Generate a thumbnail from an image file.

    Args:
        source_path: Path to source image
        output_dir: Directory to save thumbnail
        max_width: Maximum thumbnail width
        max_height: Maximum thumbnail height
        quality: JPEG quality (1-100)

    Returns:
        Path to thumbnail, or None if failed
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create thumbnail path (add _thumb suffix)
        thumbnail_path = output_dir / f"{source_path.stem}_thumb.jpg"

        # Skip if thumbnail already exists and is newer than source
        if thumbnail_path.exists():
            if thumbnail_path.stat().st_mtime >= source_path.stat().st_mtime:
                return thumbnail_path

        # Open and resize image
        img = Image.open(source_path)

        # Calculate new size maintaining aspect ratio
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Save thumbnail
        img.save(str(thumbnail_path), "JPEG", quality=quality, optimize=True)
        logger.debug(f"Generated thumbnail: {thumbnail_path}")
        return thumbnail_path

    except Exception as e:
        logger.error(f"Error generating thumbnail for {source_path}: {e}")
        return None


def get_or_create_thumbnail(cover_path: Path) -> Path:
    """
    Get existing thumbnail or create one if needed.

    Args:
        cover_path: Path to full-size cover image

    Returns:
        Path to thumbnail (or original if thumbnail creation fails)
    """
    if not cover_path.exists():
        return cover_path

    # Thumbnail directory (same as covers)
    thumbnail_dir = cover_path.parent

    # Check if this is already a thumbnail
    if '_thumb' in cover_path.stem:
        return cover_path

    # Try to get or create thumbnail
    thumbnail_path = generate_thumbnail(cover_path, thumbnail_dir)

    # Return thumbnail if successful, otherwise return original
    return thumbnail_path if thumbnail_path and thumbnail_path.exists() else cover_path
