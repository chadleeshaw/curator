"""
Shared pytest fixtures for services unit tests.

Provides database, session, and service instances reused across multiple test
modules to avoid copy-pasting the same setup boilerplate.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, PeriodicalTracking
from services.issue_discovery import IssueDiscoveryService


@pytest.fixture
def test_db():
    """Create a file-based SQLite test database for thread-safe testing."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def issue_discovery_service():
    """Create IssueDiscoveryService with test-friendly settings."""
    return IssueDiscoveryService(
        fuzzy_threshold=80,
        default_max_retries=1,  # 2 total attempts (initial + 1 retry)
    )


@pytest.fixture
def tracking_all():
    """PeriodicalTracking mock configured for Download All mode (track_all_editions=True)."""
    tracking = MagicMock(spec=PeriodicalTracking)
    tracking.id = 1
    tracking.title = "Test Magazine"
    tracking.country = "US"
    tracking.track_all_editions = True
    tracking.track_new_only = False
    tracking.selected_years = []
    return tracking
