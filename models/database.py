import enum
import secrets
from typing import Any, Dict, Optional

import bcrypt
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator
import datetime

from core.constants.category import DEFAULT_CATEGORY
from core.constants.language import DEFAULT_LANGUAGE
from core.parsers import utc_now

Base = declarative_base()


def utcnow():
    return utc_now()


class UTCDateTime(TypeDecorator):  # pylint: disable=too-many-ancestors
    """
    SQLAlchemy TypeDecorator that ensures all datetimes are TZ-aware UTC.
    Fixes SQLite's limitation of dropping timezone metadata.
    """

    impl = DateTime
    cache_ok = True

    @property
    def python_type(self):
        return datetime.datetime

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not value.tzinfo:
                value = value.replace(tzinfo=datetime.timezone.utc)
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value

    def process_literal_param(self, value, dialect):
        return self.process_bind_param(value, dialect)

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    """Return ISO 8601 string for a datetime, or None if the datetime is None."""
    return dt.isoformat() if dt else None


class Credentials(Base):
    """Single user login credentials"""

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    api_token = Column(String(255), nullable=True, unique=True, index=True)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    def generate_api_token(self) -> str:
        self.api_token = secrets.token_urlsafe(32)
        self.updated_at = utc_now()
        return self.api_token

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "api_token": self.api_token,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class Periodical(Base):
    """Physical periodical file with metadata from filename, text extraction, and OCR."""

    __tablename__ = "periodicals"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    language = Column(String(50), nullable=True, default=DEFAULT_LANGUAGE, index=True)
    category = Column(String(100), nullable=True, default=DEFAULT_CATEGORY, index=True)
    issue_date = Column(UTCDateTime, nullable=False, index=True)
    file_path = Column(String(512), nullable=False, unique=True)
    cover_path = Column(String(512), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    parsed_metadata = Column(JSON, nullable=True)
    derived_metadata = Column(JSON, nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)
    tracking_id = Column(Integer, ForeignKey("periodical_tracking.id"), nullable=True, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "category": self.category,
            "issue_date": _iso(self.issue_date),
            "file_path": self.file_path,
            "cover_path": self.cover_path,
            "content_hash": self.content_hash,
            "parsed_metadata": self.parsed_metadata,
            "derived_metadata": self.derived_metadata,
            "extra_metadata": self.extra_metadata,
            "tracking_id": self.tracking_id,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class PeriodicalTracking(Base):
    """Tracks periodical series for automated discovery and download."""

    __tablename__ = "periodical_tracking"

    id = Column(Integer, primary_key=True)
    olid = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    language = Column(String(50), nullable=True, default="English", index=True)
    country = Column(String(50), nullable=True, index=True)
    first_publish_year = Column(Integer, nullable=True)
    total_editions_known = Column(Integer, default=0)

    track_all_editions = Column(Boolean, default=False)
    track_new_only = Column(Boolean, default=False)
    selected_editions = Column(JSON, default={})
    selected_years = Column(JSON, default=[])
    delete_from_client_on_completion = Column(Boolean, default=True)
    category = Column(String(100), nullable=True, default=DEFAULT_CATEGORY)
    download_category = Column(String(100), nullable=True)
    organization_pattern = Column(String(255), nullable=True)
    search_aliases = Column(String(512), nullable=True)

    periodical_metadata = Column(JSON, nullable=True)
    last_metadata_update = Column(UTCDateTime, nullable=True)

    last_searched = Column(UTCDateTime, nullable=True, index=True)
    search_count = Column(Integer, default=0)
    search_interval_hours = Column(Integer, default=6)

    last_cache_match = Column(UTCDateTime, nullable=True, index=True)

    total_issues_discovered = Column(Integer, default=0)
    last_discovery_count = Column(Integer, default=0)
    last_discovery_date = Column(UTCDateTime, nullable=True)

    searches_without_new_issues = Column(Integer, default=0)

    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
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
            "organization_pattern": self.organization_pattern,
            "search_aliases": self.search_aliases,
            "periodical_metadata": self.periodical_metadata,
            "last_metadata_update": _iso(self.last_metadata_update),
            "last_searched": _iso(self.last_searched),
            "search_count": self.search_count,
            "search_interval_hours": self.search_interval_hours,
            "last_cache_match": _iso(self.last_cache_match),
            "total_issues_discovered": self.total_issues_discovered,
            "last_discovery_count": self.last_discovery_count,
            "last_discovery_date": _iso(self.last_discovery_date),
            "searches_without_new_issues": self.searches_without_new_issues,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class SearchResult(Base):
    """Search results from providers before downloading"""

    __tablename__ = "search_results"

    __table_args__ = (
        UniqueConstraint(
            "fuzzy_match_group_id",
            "query",
            name="uq_search_cache_group_query",
        ),
    )

    id = Column(Integer, primary_key=True)
    provider = Column(String(100), nullable=False, index=True)
    query = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    publication_date = Column(UTCDateTime, nullable=True)
    raw_metadata = Column(JSON, nullable=True)
    fuzzy_match_group_id = Column(String(255), nullable=True, index=True)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "query": self.query,
            "title": self.title,
            "url": self.url,
            "publication_date": _iso(self.publication_date),
            "raw_metadata": self.raw_metadata,
            "fuzzy_match_group_id": self.fuzzy_match_group_id,
            "created_at": _iso(self.created_at),
            "periodical_id": self.periodical_id,
        }


class DownloadSubmission(Base):
    """Track download submissions to prevent duplicates"""

    __tablename__ = "download_submissions"

    class StatusEnum(enum.Enum):
        QUEUED = "queued"
        PENDING = "pending"
        DOWNLOADING = "downloading"
        COMPLETED = "completed"
        FAILED = "failed"
        SKIPPED = "skipped"

    id = Column(Integer, primary_key=True)
    tracking_id = Column(Integer, ForeignKey("periodical_tracking.id"), nullable=False, index=True)
    search_result_id = Column(Integer, ForeignKey("search_results.id"), nullable=True, index=True)
    job_id = Column(String(255), nullable=True, index=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)
    result_title = Column(String(255), nullable=False)
    fuzzy_match_group = Column(String(255), nullable=True, index=True)
    client_name = Column(String(100), nullable=True)
    attempt_count = Column(Integer, default=0)
    last_error = Column(String(512), nullable=True)
    extra_status = Column(String(512), nullable=True)
    file_path = Column(String(512), nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
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
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
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
    job_id = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)
    client_name = Column(String(100), nullable=False)
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True)
    search_result_id = Column(Integer, ForeignKey("search_results.id"), nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "status": self.status.value if self.status else None,
            "source_url": self.source_url,
            "client_name": self.client_name,
            "periodical_id": self.periodical_id,
            "search_result_id": self.search_result_id,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
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
        LOW = 1
        NORMAL = 5
        HIGH = 10

    id = Column(Integer, primary_key=True)
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=False, index=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    priority = Column(Integer, default=PriorityEnum.NORMAL.value, index=True)
    language = Column(String(50), nullable=True)
    attempt_count = Column(Integer, default=0)
    last_error = Column(String(512), nullable=True)
    ocr_metadata = Column(JSON, nullable=True)
    processing_time_seconds = Column(Integer, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    started_at = Column(UTCDateTime, nullable=True)
    completed_at = Column(UTCDateTime, nullable=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "periodical_id": self.periodical_id,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "language": self.language,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "ocr_metadata": self.ocr_metadata,
            "processing_time_seconds": self.processing_time_seconds,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "updated_at": _iso(self.updated_at),
        }


class DownloadStatus:
    """String constants for DiscoveredIssue.download_status."""

    DISCOVERED = "discovered"
    WANTED = "wanted"
    QUEUED = "queued"  # In Curator's internal queue, not yet sent to download client
    PENDING = "pending"  # Submitted to download client and accepted (client-side pending)
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    PERMANENTLY_FAILED = "permanently_failed"
    IGNORED = "ignored"


class DiscoveredIssue(Base):
    """
    Persistent tracking of all discovered issues from search results.

    Serves as the single source of truth for available issues and download queue.
    Replaces scattered bad file logic with unified state machine.
    """

    __tablename__ = "discovered_issues"

    __table_args__ = (Index("ix_discovered_issues_tracking_fuzzy", "tracking_id", "fuzzy_match_group"),)

    id = Column(Integer, primary_key=True)
    tracking_id = Column(Integer, ForeignKey("periodical_tracking.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False, index=True)
    normalized_title = Column(String(255), nullable=False, index=True)
    fuzzy_match_group = Column(String(255), nullable=False, index=True)

    issue_date = Column(UTCDateTime, nullable=True, index=True)
    issue_number = Column(String(50), nullable=True)
    year = Column(Integer, nullable=True, index=True)
    month = Column(Integer, nullable=True, index=True)
    language = Column(String(50), nullable=True, index=True)
    country = Column(String(50), nullable=True, index=True)

    first_seen = Column(UTCDateTime, default=utcnow, index=True)
    last_seen = Column(UTCDateTime, default=utcnow, index=True)
    times_seen = Column(Integer, default=1)

    # Download state: discovered → wanted → queued → pending → downloading → completed/failed/permanently_failed/ignored
    # queued = in Curator's internal queue; pending = submitted to and accepted by download client
    download_status = Column(String(50), nullable=False, default="discovered", index=True)
    download_priority = Column(Integer, default=50, index=True)

    latest_url = Column(String(512), nullable=True)
    latest_provider = Column(String(100), nullable=True)
    latest_pubdate = Column(UTCDateTime, nullable=True, index=True)
    search_result_ids = Column(JSON, default=list)

    current_submission_id = Column(Integer, ForeignKey("download_submissions.id"), nullable=True, index=True)
    submission_ids = Column(JSON, default=list)
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True, index=True)

    attempt_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=1)
    last_attempt = Column(UTCDateTime, nullable=True)
    last_error = Column(String(512), nullable=True)

    extra_metadata = Column(JSON, nullable=True)

    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tracking_id": self.tracking_id,
            "title": self.title,
            "normalized_title": self.normalized_title,
            "fuzzy_match_group": self.fuzzy_match_group,
            "issue_date": _iso(self.issue_date),
            "issue_number": self.issue_number,
            "year": self.year,
            "month": self.month,
            "language": self.language,
            "country": self.country,
            "first_seen": _iso(self.first_seen),
            "last_seen": _iso(self.last_seen),
            "times_seen": self.times_seen,
            "download_status": self.download_status,
            "download_priority": self.download_priority,
            "latest_url": self.latest_url,
            "latest_provider": self.latest_provider,
            "latest_pubdate": _iso(self.latest_pubdate),
            "search_result_ids": self.search_result_ids,
            "current_submission_id": self.current_submission_id,
            "submission_ids": self.submission_ids,
            "periodical_id": self.periodical_id,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "last_attempt": _iso(self.last_attempt),
            "last_error": self.last_error,
            "extra_metadata": self.extra_metadata,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class Stack(Base):
    """User-created grouping of periodicals and tracking items"""

    __tablename__ = "stacks"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(String(1024), nullable=True)
    categories = Column(JSON, nullable=True)
    cover_override_path = Column(String(512), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(UTCDateTime, default=utcnow, index=True)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "categories": self.categories or [],
            "cover_override_path": self.cover_override_path,
            "sort_order": self.sort_order,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class StackMembership(Base):
    """Associates periodicals or tracking items with a stack (one stack per item)"""

    __tablename__ = "stack_memberships"

    id = Column(Integer, primary_key=True)
    stack_id = Column(Integer, ForeignKey("stacks.id"), nullable=False, index=True)
    periodical_tracking_id = Column(
        Integer,
        ForeignKey("periodical_tracking.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True, unique=True, index=True)
    added_at = Column(UTCDateTime, default=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "stack_id": self.stack_id,
            "periodical_tracking_id": self.periodical_tracking_id,
            "periodical_id": self.periodical_id,
            "added_at": _iso(self.added_at),
        }


class ReadingProgress(Base):
    """Track reading progress for periodicals across different formats"""

    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True)
    periodical_id = Column(Integer, ForeignKey("periodicals.id"), nullable=False, index=True, unique=True)
    current_page = Column(Integer, nullable=True)
    current_chapter = Column(Integer, nullable=True)
    total_pages = Column(Integer, nullable=True)
    progress_percent = Column(Integer, nullable=True)
    last_read_at = Column(UTCDateTime, default=utcnow, index=True)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "periodical_id": self.periodical_id,
            "current_page": self.current_page,
            "current_chapter": self.current_chapter,
            "total_pages": self.total_pages,
            "progress_percent": self.progress_percent,
            "last_read_at": _iso(self.last_read_at),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
