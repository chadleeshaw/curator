import enum
from datetime import datetime

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

Base = declarative_base()


class Credentials(Base):
    """Single user login credentials"""

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password: str):
        """Hash and set the password"""
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash"""
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )


class Magazine(Base):
    """Organized periodical with metadata"""

    __tablename__ = "periodicals"

    id = Column(Integer, primary_key=True)
    issn = Column(String(20), nullable=True, index=True)  # ISBN/ISSN identifier
    title = Column(String(255), nullable=False, index=True)
    publisher = Column(String(255), nullable=True)
    issue_date = Column(DateTime, nullable=False, index=True)
    file_path = Column(String(512), nullable=False, unique=True)
    cover_path = Column(String(512), nullable=True)
    extra_metadata = Column(JSON, nullable=True)  # Extra metadata from Open Library
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MagazineTracking(Base):
    """Track periodical series for monitoring and downloading specific editions"""

    __tablename__ = "periodical_tracking"

    id = Column(Integer, primary_key=True)
    olid = Column(
        String(50), nullable=False, unique=True, index=True
    )  # Open Library ID
    title = Column(String(255), nullable=False, index=True)
    publisher = Column(String(255), nullable=True)
    issn = Column(String(20), nullable=True, index=True)
    first_publish_year = Column(Integer, nullable=True)
    total_editions_known = Column(Integer, default=0)

    # Selection preferences
    track_all_editions = Column(
        Boolean, default=False
    )  # Auto-download all new editions
    track_new_only = Column(
        Boolean, default=False
    )  # Auto-download only new/future editions
    selected_editions = Column(JSON, default={})  # Dict: {olid: True/False, ...}
    selected_years = Column(JSON, default=[])  # List of years to track

    # Metadata
    periodical_metadata = Column(JSON, nullable=True)  # Full metadata from Open Library
    last_metadata_update = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    fuzzy_match_group_id = Column(
        String(255), nullable=True, index=True
    )  # Grouping for deduplication
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    magazine_id = Column(
        Integer, ForeignKey("periodicals.id"), nullable=True
    )  # Links to downloaded periodical


class DownloadSubmission(Base):
    """Track download submissions to prevent duplicates"""

    __tablename__ = "download_submissions"

    class StatusEnum(enum.Enum):
        PENDING = "pending"
        DOWNLOADING = "downloading"
        COMPLETED = "completed"
        FAILED = "failed"
        SKIPPED = "skipped"

    id = Column(Integer, primary_key=True)
    tracking_id = Column(
        Integer, ForeignKey("periodical_tracking.id"), nullable=False, index=True
    )  # Which periodical
    search_result_id = Column(
        Integer, ForeignKey("search_results.id"), nullable=True, index=True
    )  # Which search result
    job_id = Column(
        String(255), nullable=True, index=True
    )  # Client's job ID (if submitted)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)  # NZB URL or download link
    result_title = Column(String(255), nullable=False)  # Title from search result
    fuzzy_match_group = Column(
        String(255), nullable=True, index=True
    )  # For dedup grouping
    client_name = Column(String(100), nullable=True)  # Which client handled this
    attempt_count = Column(Integer, default=0)  # Number of download attempts
    last_error = Column(String(512), nullable=True)  # Last error message
    file_path = Column(String(512), nullable=True)  # Path where file was downloaded
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Download(Base):
    """Track downloads from clients (legacy - for backward compatibility)"""

    __tablename__ = "downloads"

    class StatusEnum(enum.Enum):
        PENDING = "pending"
        DOWNLOADING = "downloading"
        COMPLETED = "completed"
        FAILED = "failed"

    id = Column(Integer, primary_key=True)
    job_id = Column(
        String(255), nullable=False, unique=True, index=True
    )  # Client's job ID
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, index=True)
    source_url = Column(String(512), nullable=False)  # NZB URL sent to client
    client_name = Column(String(100), nullable=False)  # Which client handled this
    magazine_id = Column(Integer, ForeignKey("periodicals.id"), nullable=True)
    search_result_id = Column(Integer, ForeignKey("search_results.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
