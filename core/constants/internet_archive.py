"""
Internet Archive provider and client constants.

Constants for configuring and using the Internet Archive API
for searching and downloading periodicals.
"""

# Default search parameters
IA_DEFAULT_MEDIATYPE = "texts"
IA_DEFAULT_ROWS = 100
IA_DEFAULT_SORT = "date desc"

# Collections commonly containing periodicals
IA_PERIODICAL_COLLECTIONS = [
    "magazines",
    "periodicals",
    "newspaper",
    "comics",
    "pulpmagazinearchive",
]

# Preferred file formats for download (in order of preference)
IA_PREFERRED_FORMATS = ["PDF", "EPUB", "MOBI", "DJVU"]

# File format extensions mapping
IA_FORMAT_EXTENSIONS = {
    "PDF": ".pdf",
    "EPUB": ".epub",
    "MOBI": ".mobi",
    "DJVU": ".djvu",
    "Text PDF": ".pdf",
    "Image Container PDF": ".pdf",
}

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

# Provider identification
IA_PROVIDER_TYPE = "internet_archive"
IA_PROVIDER_NAME = "Internet Archive"

# Base URLs
IA_DOWNLOAD_BASE_URL = "https://archive.org/download"
IA_DETAILS_BASE_URL = "https://archive.org/details"
IA_METADATA_BASE_URL = "https://archive.org/metadata"

# Search query templates
IA_SEARCH_FIELDS = [
    "identifier",
    "title",
    "creator",
    "date",
    "description",
    "mediatype",
    "collection",
]

# Status values for tracking downloads
IA_STATUS_PENDING = "pending"
IA_STATUS_DOWNLOADING = "downloading"
IA_STATUS_COMPLETED = "completed"
IA_STATUS_FAILED = "failed"
