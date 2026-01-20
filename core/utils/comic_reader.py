"""
Utility functions for reading CBZ/CBR comic files
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from PIL import Image

logger = logging.getLogger(__name__)


def get_sorted_image_files(archive, extension: str) -> List[str]:
    """
    Get sorted list of image files from archive.

    Args:
        archive: ZipFile or RarFile object
        extension: File extension (.cbz or .cbr)

    Returns:
        List of image filenames sorted naturally
    """
    # Get all files from archive
    if extension == ".cbz":
        all_files = archive.namelist()
    else:  # .cbr
        all_files = archive.namelist()

    # Filter for image files
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    image_files = [
        f for f in all_files if Path(f).suffix.lower() in image_extensions and not Path(f).name.startswith(".")
    ]

    # Sort naturally (1, 2, 10 instead of 1, 10, 2)
    import re

    def natural_sort_key(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

    return sorted(image_files, key=natural_sort_key)


def get_comic_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extract metadata from a CBZ/CBR file.

    Args:
        file_path: Path to the CBZ/CBR file

    Returns:
        Dictionary with metadata:
        - title: Comic title (from filename)
        - format: File format (CBZ or CBR)
        - page_count: Number of pages
        - pages: List of page filenames
    """
    try:
        extension = file_path.suffix.lower()

        if extension == ".cbz":
            import zipfile

            with zipfile.ZipFile(file_path, "r") as archive:
                pages = get_sorted_image_files(archive, extension)
        elif extension == ".cbr":
            try:
                import rarfile

                with rarfile.RarFile(file_path, "r") as archive:
                    pages = get_sorted_image_files(archive, extension)
            except ImportError:
                logger.error("rarfile not available. Install with: pip install rarfile")
                raise ImportError("rarfile not available")
        else:
            raise ValueError(f"Unsupported format: {extension}")

        return {
            "title": file_path.stem,
            "format": extension[1:].upper(),  # Remove dot, uppercase
            "page_count": len(pages),
            "pages": pages,
        }

    except Exception as e:
        logger.error(f"Failed to get comic metadata: {e}")
        raise


def get_comic_page(file_path: Path, page_index: int) -> Optional[bytes]:
    """
    Extract a specific page from a CBZ/CBR file.

    Args:
        file_path: Path to the CBZ/CBR file
        page_index: Zero-based page index

    Returns:
        Image data as bytes, or None if page not found
    """
    try:
        extension = file_path.suffix.lower()

        if extension == ".cbz":
            with zipfile.ZipFile(file_path, "r") as archive:
                pages = get_sorted_image_files(archive, extension)

                if 0 <= page_index < len(pages):
                    return archive.read(pages[page_index])

        elif extension == ".cbr":
            try:
                import rarfile

                with rarfile.RarFile(file_path, "r") as archive:
                    pages = get_sorted_image_files(archive, extension)

                    if 0 <= page_index < len(pages):
                        return archive.read(pages[page_index])
            except ImportError:
                logger.error("rarfile not available. Install with: pip install rarfile")
                raise ImportError("rarfile not available")
        else:
            raise ValueError(f"Unsupported format: {extension}")

        return None

    except Exception as e:
        logger.error(f"Failed to get comic page {page_index}: {e}")
        raise


def get_comic_page_thumbnail(file_path: Path, page_index: int, max_size: int = 150) -> Optional[bytes]:
    """
    Extract a thumbnail of a specific page from a CBZ/CBR file.

    Args:
        file_path: Path to the CBZ/CBR file
        page_index: Zero-based page index
        max_size: Maximum dimension (width or height) for thumbnail (default: 150px, reduced from 200px)

    Returns:
        Thumbnail image data as JPEG bytes, or None if page not found
    """
    try:
        # Get the full page
        page_data = get_comic_page(file_path, page_index)
        if not page_data:
            return None

        # Create thumbnail
        img = Image.open(io.BytesIO(page_data))

        # Resize maintaining aspect ratio
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Convert to RGB if needed (for formats that don't support JPEG)
        if img.mode in ("RGBA", "P", "LA"):
            # Create white background
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Save as JPEG with lower quality for faster loading
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=75, optimize=True)
        return output.getvalue()

    except Exception as e:
        logger.error(f"Failed to create thumbnail for page {page_index}: {e}")
        return None
