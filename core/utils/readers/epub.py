"""
EPUB reader utilities for extracting and serving chapters.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Patterns to filter out from filenames and chapter titles
EXCLUDE_PATTERNS = [
    "wrap",
    "nav",
    "toc",
    "cover",
    "titlepage",
    "copyright",
    "blank",
    "license",
    "gutenberg",
    "legal",
    "colophon",
]

# Patterns to filter out from content (boilerplate, licensing)
EXCLUDE_CONTENT_PATTERNS = [
    "project gutenberg",
    "start of the project gutenberg",
    "end of the project gutenberg",
    "pg-boilerplate",
    "*** start of",
    "*** end of",
]


def _filter_epub_items(book, title: str) -> List[Tuple[int, Any, str]]:
    """
    Filter EPUB items and return list of (original_index, item, chapter_title).

    Args:
        book: EPUB book object
        title: Book title for duplicate detection

    Returns:
        List of tuples: (original_index, item, chapter_title)
    """
    from bs4 import BeautifulSoup

    filtered = []
    seen_titles = {}

    for idx, item in enumerate(book.get_items_of_type(9)):  # ITEM_DOCUMENT
        # Get filename for filtering
        filename = item.get_name().lower()

        # Skip files matching exclude patterns
        if any(pattern in filename for pattern in EXCLUDE_PATTERNS):
            continue

        # Try to extract a better title from the HTML content
        chapter_title = None
        content_text = ""
        try:
            content = item.get_content()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(content, "html.parser")

            # Get text content for pattern matching
            content_text = soup.get_text().lower()

            # Skip if content contains boilerplate/licensing patterns
            if any(pattern in content_text for pattern in EXCLUDE_CONTENT_PATTERNS):
                continue

            # Look for title in h1, h2, or title tag
            for tag in ["h1", "h2", "title"]:
                element = soup.find(tag)
                if element and element.get_text().strip():
                    chapter_title = element.get_text().strip()
                    break
        except Exception:
            pass

        # Fall back to filename-based title if extraction failed
        if not chapter_title:
            chapter_title = item.get_name().split("/")[-1].replace(".xhtml", "").replace(".html", "").title()

        # Skip if chapter title matches exclude patterns too
        chapter_title_lower = chapter_title.lower()
        if any(pattern in chapter_title_lower for pattern in EXCLUDE_PATTERNS):
            continue

        # Handle duplicate titles by checking if it's in the first few chapters
        # If the title is the book title and it's early in the book, call it "Contents"
        if chapter_title == title and idx < 5:
            # First occurrence of book title in early chapters is likely TOC
            if chapter_title not in seen_titles:
                chapter_title = "Contents"
                seen_titles[title] = True

        filtered.append((idx, item, chapter_title))

    return filtered


def get_epub_metadata(epub_path: Path) -> Dict[str, Any]:
    """
    Extract metadata from EPUB file.

    Args:
        epub_path: Path to EPUB file

    Returns:
        Dictionary with metadata (title, author, chapters)
    """
    try:
        from ebooklib import epub

        book = epub.read_epub(str(epub_path))

        # Get basic metadata
        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else epub_path.stem

        author = book.get_metadata("DC", "creator")
        author = author[0][0] if author else "Unknown"

        # Get filtered chapters
        filtered_items = _filter_epub_items(book, title)
        chapters = [chapter_title for _, _, chapter_title in filtered_items]

        return {
            "title": title,
            "author": author,
            "chapters": chapters,
            "total_chapters": len(chapters),
        }

    except ImportError:
        logger.warning("ebooklib not available. Install with: pip install ebooklib")
        return {
            "title": epub_path.stem,
            "author": "Unknown",
            "chapters": [],
            "total_chapters": 0,
            "error": True,
        }
    except Exception as e:
        logger.error(f"Error reading EPUB metadata from {epub_path}: {e}")
        return {
            "title": epub_path.stem,
            "author": "Unknown",
            "chapters": [],
            "total_chapters": 0,
            "error": True,
        }


def get_epub_chapter(epub_path: Path, chapter_index: int, magazine_id: Optional[int] = None) -> Optional[str]:
    """
    Extract a specific chapter from EPUB as HTML.

    Args:
        epub_path: Path to EPUB file
        chapter_index: Zero-based chapter index (into filtered chapter list)
        magazine_id: Magazine ID for rewriting image URLs (optional)

    Returns:
        Chapter HTML content with rewritten image URLs, or None if failed
    """
    try:
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(str(epub_path))

        # Get book title for filtering
        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else epub_path.stem

        # Get filtered items with original indices
        filtered_items = _filter_epub_items(book, title)

        if chapter_index < 0 or chapter_index >= len(filtered_items):
            logger.warning(f"Chapter index {chapter_index} out of range (0-{len(filtered_items) - 1})")
            return None

        # Get the item using the filtered list (which preserves original indices)
        original_index, item, chapter_title = filtered_items[chapter_index]
        content = item.get_content()

        # Decode bytes to string
        if isinstance(content, bytes):
            content = content.decode("utf-8")

        # Rewrite image URLs to point to our image serving endpoint
        if magazine_id:
            soup = BeautifulSoup(content, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    # Convert relative path to API endpoint
                    # Remove any directory paths, just use the filename
                    filename = src.split("/")[-1]
                    img["src"] = f"/api/periodicals/{magazine_id}/epub/image/{filename}"

            content = str(soup)

        return content

    except ImportError:
        logger.warning("ebooklib not available. Install with: pip install ebooklib")
        return None
    except Exception as e:
        logger.error(f"Error extracting chapter {chapter_index} from {epub_path}: {e}")
        return None


def get_epub_image(epub_path: Path, image_name: str) -> Optional[bytes]:
    """
    Extract a specific image from EPUB.

    Args:
        epub_path: Path to EPUB file
        image_name: Name of the image file (e.g., 'cover.jpg')

    Returns:
        Image data as bytes, or None if not found
    """
    try:
        from ebooklib import epub

        book = epub.read_epub(str(epub_path))

        # Search through all items for the image
        for item in book.get_items():
            item_name = item.get_name()
            # Match by filename (ignore directory structure)
            if item_name.split("/")[-1] == image_name:
                return item.get_content()

        logger.warning(f"Image '{image_name}' not found in EPUB")
        return None

    except ImportError:
        logger.warning("ebooklib not available. Install with: pip install ebooklib")
        return None
    except Exception as e:
        logger.error(f"Error extracting image '{image_name}' from {epub_path}: {e}")
        return None
