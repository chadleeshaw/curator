"""
File processing and organization constants
"""

# ==============================================================================
# File Processing - Image Handling
# ==============================================================================

PIL_MAX_IMAGE_PIXELS = 200000000
"""Maximum image size in pixels for PIL (200 megapixels). Prevents decompression bomb attacks."""


# ==============================================================================
# File Processing - PDF Cover Extraction
# ==============================================================================

PDF_COVER_DPI = 150
"""DPI setting for extracting cover images from PDFs"""

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

MAX_FILENAME_LENGTH = 200
"""Maximum length for sanitized filenames"""

DEFAULT_ORGANIZATION_PATTERN = "{category}/{title}/{year}/"
"""Default pattern for organizing imported files"""

ORGANIZED_FILENAME_PATTERN = "{title} - {month}{year}"
"""Pattern for organized filenames: e.g., 'Wired - Dec2006'"""

VOLUME_PREFIX = "Vol"
"""Prefix for volume numbers in filenames (e.g., 'Vol1')"""

ISSUE_PREFIX = "No"
"""Prefix for issue numbers in filenames (e.g., 'No123')"""

ORGANIZED_FILENAME_SEPARATOR = " - "
"""Separator used in organized filenames between components"""


# ==============================================================================
# File Extensions and Types
# ==============================================================================

SUPPORTED_FILE_EXTENSIONS = {".pdf", ".epub", ".cbz", ".cbr"}
"""Set of file extensions that Curator can process"""

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
# File Hashing
# ==============================================================================

DEFAULT_HASH_CHUNK_SIZE = 8192
"""Default chunk size in bytes for reading files during hashing (8KB)"""
