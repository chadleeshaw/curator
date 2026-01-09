"""
Data models for parsed metadata from various sources.
Provides type-safe, consistent structures for parsed data.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


# pylint: disable=too-many-instance-attributes
@dataclass
class ParsedMetadata:
    """
    Comprehensive metadata parsed from any source.

    This is the unified return type for all parsers.
    """
    # Core fields (always attempted to extract)
    title: str
    language: str = "English"
    country: Optional[str] = None

    # Date fields
    issue_date: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    year: Optional[int] = None
    month: Optional[int] = None
    month_name: Optional[str] = None

    # Edition/Issue fields
    issue_number: Optional[int] = None
    volume: Optional[int] = None
    edition_number: Optional[int] = None
    is_special_edition: bool = False
    special_edition_name: Optional[str] = None

    # Technical fields
    file_path: Optional[Path] = None
    original_filename: Optional[str] = None

    # Tracking fields (for deduplication)
    base_title: Optional[str] = None  # Title without special edition info
    normalized_title: Optional[str] = None  # Cleaned for matching

    # Quality/confidence
    confidence: str = "low"  # low, medium, high
    parse_source: str = "unknown"  # filename, filepath, search, download_client

    # Pattern matching info
    matched_pattern: Optional[str] = None

    # Raw data
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Derive fields after initialization"""
        if not self.base_title:
            self.base_title = self.title
        if not self.normalized_title:
            self.normalized_title = self.title.lower().strip()


@dataclass
class ParsedFilename:
    """Result of filename parsing specifically"""
    title: str
    issue_date: Optional[datetime] = None
    issue_number: Optional[int] = None
    volume: Optional[int] = None
    year: Optional[int] = None
    month_name: Optional[str] = None
    is_special_edition: bool = False
    confidence: str = "low"
    matched_pattern: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedFilepath:
    """Result of filepath/directory parsing"""
    title_from_path: Optional[str] = None
    language_from_path: Optional[str] = None
    year_from_path: Optional[int] = None
    confidence: str = "low"


@dataclass
class ParsedSearchResult:
    """Result of search result parsing (from download providers)"""
    title: str
    original_title: str
    cleaned_title: str
    base_title: str
    language: str
    country: Optional[str]
    is_special_edition: bool
    special_edition_name: Optional[str]
    publication_date: Optional[datetime]
    provider: str
    url: str
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDownloadFile:
    """Result of parsing download client file data"""
    file_path: Path
    title: str
    cleaned_title: str
    language: str
    country: Optional[str]
    issue_date: Optional[datetime]
    source: str = "download_client"
