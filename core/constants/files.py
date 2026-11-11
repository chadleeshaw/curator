"""
File processing and organization constants
"""

from pathlib import Path

# ==============================================================================
# File Processing - Image Handling
# ==============================================================================

PIL_MAX_IMAGE_PIXELS = 200000000
"""Maximum image size in pixels for PIL (200 megapixels). Prevents decompression bomb attacks."""


# ==============================================================================
# File Processing - PDF Cover Extraction
# ==============================================================================

PDF_COVER_DPI_LOW = 60
"""Low DPI setting for thumbnails/previews"""

PDF_COVER_DPI_HIGH = 200
"""High DPI setting for quality cover images"""

PDF_COVER_QUALITY = 50
"""JPEG quality for low resolution covers (1-100)"""

PDF_COVER_QUALITY_HIGH = 85
"""JPEG quality for high resolution covers (1-100)"""

EPUB_COVER_QUALITY = 85
"""JPEG quality for EPUB cover extraction (1-100)"""


# ==============================================================================
# File Organization
# ==============================================================================

VOLUME_PREFIX = "Vol"
"""Prefix for volume numbers in filenames (e.g., 'Vol1')"""

ISSUE_PREFIX = "No"
"""Prefix for issue numbers in filenames (e.g., 'No123')"""

ORGANIZED_FILENAME_SEPARATOR = " - "
"""Separator used in organized filenames between components"""

IMPORT_MARKER_FILE = ".importing"
"""Marker file name used to indicate import is in progress for a folder"""


# ==============================================================================
# File Extensions and Types
# ==============================================================================

SUPPORTED_FILE_EXTENSIONS = {".pdf", ".epub", ".cbz", ".cbr"}
"""Set of file extensions that Curator can process"""

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
"""Set of common image file extensions"""

BLACKLISTED_FILE_EXTENSIONS = {
    # Video files
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    # Audio files
    ".mp3",
    ".flac",
    ".wav",
    ".aac",
    ".ogg",
    ".m4a",
    # Archives (not comics)
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    # Executables
    ".exe",
    ".dll",
    ".so",
    ".bin",
    # Other
    ".txt",
    ".nfo",
    ".sfv",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
}
"""Set of file extensions to explicitly ignore during import"""


# ==============================================================================
# Temporary/Incomplete Download Patterns
# ==============================================================================

INCOMPLETE_DOWNLOAD_PATTERNS = {
    "_unpack_",  # SABnzbd unpacking prefix
    "_UNPACK_",  # SABnzbd unpacking prefix (uppercase)
    ".!qb",  # qBittorrent incomplete extension
    ".part",  # Firefox/Chrome partial downloads / IA partial downloads
    ".part.meta",  # IA resume metadata sidecar files
    ".crdownload",  # Chrome download in progress
    ".tmp",  # Generic temporary files
}
"""Set of patterns indicating incomplete/temporary downloads that should be skipped during import"""


# ==============================================================================
# File Extension Detection
# ==============================================================================

MAX_FILE_EXTENSION_LENGTH = 4
"""Maximum length for file extensions when detecting extensions in filenames"""

YEAR_STRING_LENGTH = 4
"""Length of a year string (YYYY format)"""


# ==============================================================================
# Size Conversions
# ==============================================================================

BYTES_PER_MB = 1024 * 1024
"""Bytes per megabyte, used for human-readable size formatting"""


COLLECTION_PATH_SEPARATOR = "\n"
"""Joins paths extracted from one Internet Archive archive. Titles contain commas."""


def split_collection_paths(file_path: str | None) -> list[str] | None:
    """Split an extracted collection into file paths.

    New extracts are joined with newlines. Older rows used commas. A comma
    splits only when every piece has a supported extension, so a title like
    "Science, Nature" stays one path. Returns None for a single file.
    """
    if not file_path:
        return None
    if "\n" in file_path:
        parts = [part.strip() for part in file_path.split("\n") if part.strip()]
    elif "," in file_path:
        parts = [part.strip() for part in file_path.split(",") if part.strip()]
        if not all(Path(part).suffix.lower() in SUPPORTED_FILE_EXTENSIONS for part in parts):
            return None
    else:
        return None
    if len(parts) < 2:
        return None
    return parts
