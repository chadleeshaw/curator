import enum
import secrets
from typing import Any, Dict

import bcrypt
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.ext.declarative import declarative_base

from core.constants.language import DEFAULT_LANGUAGE
from core.parsers import utc_now

Base = declarative_base()


def utcnow():
    """Return current UTC time - helper for SQLAlchemy defaults"""
    return utc_now()


class Credentials(Base):
    """Single user login credentials"""

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    api_token = Column(String(255), nullable=True, unique=True, index=True)  # For API access
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def set_password(self, password: str) -> None:
        """Hash and set the password"""
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash"""
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    def generate_api_token(self) -> str:
        """Generate a new API token"""
        self.api_token = secrets.token_urlsafe(32)
        self.updated_at = utc_now()
        return self.api_token

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Credentials to dictionary for API responses (excludes password_hash)"""
        return {
            "id": self.id,
            "username": self.username,
            # Note: password_hash intentionally excluded for security
            "api_token": self.api_token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Magazine(Base):
    """Organized periodical with metadata"""

    __tablename__ = "periodicals"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    language = Column(String(50), nullable=True, default=DEFAULT_LANGUAGE, index=True)  # Language of the edition
    issue_date = Column(DateTime, nullable=False, index=True)
    file_path = Column(String(512), nullable=False, unique=True)
    cover_path = Column(String(512), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256 hash of file content for deduplication
    extra_metadata = Column(JSON, nullable=True)  # Extra metadata from Open Library
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    tracking_id = Column(
        Integer, ForeignKey("periodical_tracking.id"), nullable=True, index=True
    )  # Link to tracking record

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Magazine to dictionary for API responses"""
        return {
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "file_path": self.file_path,
            "cover_path": self.cover_path,
            "content_hash": self.content_hash,
            "extra_metadata": self.extra_metadata,
            "tracking_id": self.tracking_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MagazineTracking(Base):
    """Track periodical series for monitoring and downloading specific editions"""

    __tablename__ = "periodical_tracking"

    id = Column(Integer, primary_key=True)
    olid = Column(
        String(50), nullable=False, index=True
    )  # Open Library ID (not unique anymore - different languages can share)
    title = Column(String(255), nullable=False, index=True)
    language = Column(String(50), nullable=True, default="English", index=True)  # Language of tracked edition
    country = Column(String(50), nullable=True, index=True)  # Country code (ISO)
    first_publish_year = Column(Integer, nullable=True)
    total_editions_known = Column(Integer, default=0)

    # Selection preferences
    track_all_editions = Column(Boolean, default=False)  # Auto-download all new editions
    track_new_only = Column(Boolean, default=False)  # Auto-download only new/future editions
    selected_editions = Column(JSON, default={})  # Dict: {olid: True/False, ...}
    selected_years = Column(JSON, default=[])  # List of years to track
    delete_from_client_on_completion = Column(
        Boolean, default=False
    )  # Delete from download client after completion or failure
    category = Column(String(100), nullable=True)  # Content category: Magazines, Comics, Articles, News
    download_category = Column(String(100), nullable=True)  # Download client category (e.g., "books", "magazines")

    # Metadata
    periodical_metadata = Column(JSON, nullable=True)  # Full metadata from Open Library
    last_metadata_update = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize MagazineTracking to dictionary for API responses"""
        return {
            "id": self.id,
            "olid": self.olid,
            "title": self.title,
            "language": self.language,
            "country": self.country,
            "first_publish_year": self.first_publish_year,
            "total_editions_known": self.total_editions_known,
            "track_all_editions": self.track_all_editions,
            "track_new_only": self.track_new_only,
            "selected_editions": self.selected_editions,
            "selected_years": self.selected_years,
            "delete_from_client_on_completion": self.delete_from_client_on_completion,
            "category": self.category,
            "download_category": self.download_category,
            "periodical_metadata": self.periodical_metadata,
            "last_metadata_update": self.last_metadata_update.isoformat() if self.last_metadata_update else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SearchResult(Base):
    """Search results from providers before downloading"""

    __tablename__ = "search_results"

    id = Column(Integer, primary_key=True)
    provider = Column(String(100), nullable=False, index=True)  # e.g., "newsnab", "rss"
    query = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    publication_date = Column(DateTime, nullable=True)
    raw_metadata = Column(JSON, nullable=True)  # Provider-specific fields as JSON
    fuzzy_match_group_id = Column(String(255), nullable=True, index=True)  # Grouping for deduplication
    created_at = Column(DateTime, default=utcnow, index=True)
    magazine_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True)  # Links to downloaded periodical

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SearchResult to dictionary for API responses"""
        return {
            "id": self.id,
            "provider": self.provider,
            "query": self.query,
            "title": self.title,
            "url": self.url,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "raw_metadata": self.raw_metadata,
            "fuzzy_match_group_id": self.fuzzy_match_group_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "magazine_id": self.magazine_id,
        }


class DownloadSubmission(Base):
    """Track download submissions to prevent duplicates"""

    __tablename__ = "download_submissions"

    class StatusEnum(enum.Enum):
        QUEUED = "queued"  # Waiting for download slot
        PENDING = "pending"  # Submitted to client, waiting for completion
        DOWNLOADING = "downloading"
        COMPLETED = "completed"
        FAILED = "failed"
        SKIPPED = "skipped"

    id = Column(Integer, primary_key=True)
    tracking_id = Column(Integer, ForeignKey("periodical_tracking.id"), nullable=False, index=True)  # Which periodical
    search_result_id = Column(
        Integer, ForeignKey("search_results.id"), nullable=True, index=True
    )  # Which search result
    job_id = Column(String(255), nullable=True, index=True)  # Client's job ID (if submitted)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)  # NZB URL or download link
    result_title = Column(String(255), nullable=False)  # Title from search result
    fuzzy_match_group = Column(String(255), nullable=True, index=True)  # For dedup grouping
    client_name = Column(String(100), nullable=True)  # Which client handled this
    attempt_count = Column(Integer, default=0)  # Number of download attempts
    last_error = Column(String(512), nullable=True)  # Last error message
    extra_status = Column(String(512), nullable=True)  # Additional status info (e.g., rate limiting)
    file_path = Column(String(512), nullable=True)  # Path where file was downloaded
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize DownloadSubmission to dictionary for API responses"""
        return {
            "id": self.id,
            "tracking_id": self.tracking_id,
            "search_result_id": self.search_result_id,
            "job_id": self.job_id,
            "status": self.status.value if self.status else None,
            "source_url": self.source_url,
            "result_title": self.result_title,
            "fuzzy_match_group": self.fuzzy_match_group,
            "client_name": self.client_name,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "extra_status": self.extra_status,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Download(Base):
    """Track downloads from clients (legacy - for backward compatibility)"""

    __tablename__ = "downloads"

    class StatusEnum(enum.Enum):
        PENDING = "pending"
        DOWNLOADING = "downloading"
        COMPLETED = "completed"
        FAILED = "failed"

    id = Column(Integer, primary_key=True)
    job_id = Column(String(255), nullable=False, unique=True, index=True)  # Client's job ID
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)  # NZB URL sent to client
    client_name = Column(String(100), nullable=False)  # Which client handled this
    magazine_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True)
    search_result_id = Column(Integer, ForeignKey("search_results.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Download to dictionary for API responses"""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "status": self.status.value if self.status else None,
            "source_url": self.source_url,
            "client_name": self.client_name,
            "magazine_id": self.magazine_id,
            "search_result_id": self.search_result_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OCRJob(Base):
    """Track OCR processing jobs for background processing with process pool"""

    __tablename__ = "ocr_jobs"

    class StatusEnum(enum.Enum):
        PENDING = "pending"
        PROCESSING = "processing"
        COMPLETED = "completed"
        FAILED = "failed"

    class PriorityEnum(enum.Enum):
        LOW = 1  # Bulk processing
        NORMAL = 5  # Regular imports
        HIGH = 10  # User-requested

    id = Column(Integer, primary_key=True)
    magazine_id = Column(Integer, ForeignKey("periodicals.id"), nullable=False, index=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    priority = Column(Integer, default=PriorityEnum.NORMAL.value, index=True)
    language = Column(String(50), nullable=True)  # OCR language hint
    attempt_count = Column(Integer, default=0)  # Number of processing attempts
    last_error = Column(String(512), nullable=True)  # Last error message
    ocr_metadata = Column(JSON, nullable=True)  # Extracted OCR metadata
    processing_time_seconds = Column(Integer, nullable=True)  # Time taken to process
    created_at = Column(DateTime, default=utcnow, index=True)
    started_at = Column(DateTime, nullable=True)  # When processing started
    completed_at = Column(DateTime, nullable=True)  # When processing completed
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize OCRJob to dictionary for API responses"""
        return {
            "id": self.id,
            "magazine_id": self.magazine_id,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "language": self.language,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "ocr_metadata": self.ocr_metadata,
            "processing_time_seconds": self.processing_time_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
