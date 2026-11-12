"""Old metadata rows are rewritten into the current columns."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, DiscoveredIssue, Periodical, PeriodicalTracking
from models.migrations.data import (
    migrate_discovered_issues_provider,
    migrate_metadata_structure,
    run_data_migrations,
)


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        db_path = handle.name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    try:
        yield engine, sessionmaker(bind=engine)
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


def test_an_old_periodical_gains_parsed_metadata(test_db):
    _, session_factory = test_db
    session = session_factory()
    magazine = Periodical(
        user_id=1,
        title="City Paper",
        issue_date=datetime(2024, 1, 1),
        file_path="/library/city.pdf",
        parsed_metadata=None,
        extra_metadata={"parse_source": "file", "year": 2024, "month": "January", "issue_number": "12"},
    )
    session.add(magazine)
    session.commit()

    assert migrate_metadata_structure(session) == 1
    session.refresh(magazine)
    assert magazine.parsed_metadata["file_scan"]["year"] == 2024
    assert magazine.parsed_metadata["file_scan"]["issue_number"] == "12"
    assert migrate_metadata_structure(session) == 0
    session.close()


def test_a_display_provider_name_becomes_the_routing_type(test_db):
    _, session_factory = test_db
    session = session_factory()
    tracking = PeriodicalTracking(olid="city", title="City Paper", user_id=1)
    session.add(tracking)
    session.commit()
    issue = DiscoveredIssue(
        user_id=1,
        tracking_id=tracking.id,
        title="City Paper",
        normalized_title="city paper",
        fuzzy_match_group="city-paper",
        download_status="discovered",
        latest_provider="IA",
    )
    session.add(issue)
    session.commit()

    assert migrate_discovered_issues_provider(session) == 1
    session.refresh(issue)
    assert issue.latest_provider == "internet_archive"
    assert migrate_discovered_issues_provider(session) == 0
    session.close()


def test_run_data_migrations_reports_both_counts(test_db):
    _, session_factory = test_db
    session = session_factory()
    counts = run_data_migrations(session)
    assert counts == {"metadata_structure": 0, "discovered_issues_provider": 0}
    session.close()
