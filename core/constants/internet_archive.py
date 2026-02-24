"""
Internet Archive provider and client constants.

Constants for configuring and using the Internet Archive API
for searching and downloading periodicals.
"""

from core.constants.validation import COLLECTION_INDICATOR_WORDS

# Default search parameters
IA_DEFAULT_ROWS = 500
IA_DEFAULT_SORT = "-downloads"  # Sort by most downloaded (most popular) first

# Map Curator categories to specific IA collections
# When a category is specified, only search relevant collections
IA_CATEGORY_COLLECTION_MAP = {
    "Magazines": ["magazines", "periodicals", "americana", "pulpmagazinearchive"],
    "Comics": ["comics"],
    "Graphic Novels": ["comics"],
    "Books": ["americana"],
    "Documents": ["americana", "periodicals"],
}

# Preferred file formats for download (in order of preference)
# PDF is most common for magazines; EPUB for modern digital publications
# ZIP/GZIP for collection archives containing multiple files
IA_PREFERRED_FORMATS = ["PDF", "EPUB", "ZIP", "GZIP"]

# Text PDF variants - these have embedded OCR text, preferred for text scanning
# Order matters: most preferred first
IA_TEXT_PDF_FORMATS = ["Text PDF", "Searchable PDF"]

# Collection/archive formats (contain multiple files)
IA_COLLECTION_FORMATS = ["ZIP", "TAR", "GZIP", "RAR"]

# Formats that need extraction after download
IA_EXTRACTABLE_EXTENSIONS = {
    ".zip": "zip",
    ".gz": "gzip",
    ".tar": "tar",
    ".tar.gz": "tar.gz",
    ".tgz": "tar.gz",
    ".rar": "rar",
}

# Keywords that indicate a collection archive (case-insensitive)
# Canonical list lives in validation.COLLECTION_INDICATOR_WORDS
IA_COLLECTION_KEYWORDS = sorted(COLLECTION_INDICATOR_WORDS)

# Rate limiting
IA_DEFAULT_REQUEST_DELAY = 1.0  # Seconds between API requests
IA_DEFAULT_MAX_REQUESTS_PER_MINUTE = 15
IA_DOWNLOAD_TIMEOUT = 300  # 5 minutes for large files
IA_SEARCH_TIMEOUT = 30  # 30 seconds for search queries

# Download settings
IA_DEFAULT_MAX_CONCURRENT_DOWNLOADS = 3
IA_DOWNLOAD_CHUNK_SIZE = 8192  # 8KB chunks for streaming downloads
IA_DOWNLOAD_RETRY_ATTEMPTS = 3
IA_DOWNLOAD_RETRY_DELAY = 5  # Seconds between retry attempts

# Resume settings
IA_DOWNLOAD_RESUME_ENABLED = True  # Enable HTTP Range-based resume for partial downloads
IA_PART_META_EXTENSION = ".part.meta"  # Sidecar metadata file for resume state

# Provider identification
IA_PROVIDER_TYPE = "internet_archive"

# Base URLs
IA_DOWNLOAD_BASE_URL = "https://archive.org/download"
IA_COMPRESS_BASE_URL = "https://archive.org/compress"

# Search query templates
IA_SEARCH_FIELDS = [
    "identifier",
    "title",
    "creator",
    "date",
    "description",
    "mediatype",
    "collection",
    "format",
    "item_count",
]

# Status values for tracking downloads
IA_STATUS_PENDING = "pending"
IA_STATUS_DOWNLOADING = "downloading"
IA_STATUS_COMPLETED = "completed"
IA_STATUS_FAILED = "failed"
