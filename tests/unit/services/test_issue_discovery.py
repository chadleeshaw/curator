"""
Test IssueDiscoveryService - Core discovery logic for Issue Discovery & Tracking system.

Tests cover:
- Recording search results (deduplication, fuzzy matching)
- Evaluating discovered issues against tracking rules
- Download failure handling and retry logic
- Priority queue generation
- Bad file detection and manual retry
"""

import sys

sys.path.insert(0, ".")

import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services import IssueDiscoveryService
from models.database import (
    Base,
    PeriodicalTracking,
    Periodical,
    DiscoveredIssue,
)


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        from pathlib import Path

        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def issue_discovery_service():
    """Create IssueDiscoveryService with default settings"""
    return IssueDiscoveryService(
        fuzzy_threshold=80,
        default_max_retries=1,  # 2 total attempts (initial + 1 retry)
    )


class TestRecordSearchResults:
    """Test recording search results and deduplication"""

    def test_record_new_issues(self, test_db, issue_discovery_service):
        """Test creating new DiscoveredIssue records"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Mock search results in correct format
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag-jan2024.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
                "size": 50 * 1024 * 1024,  # 50 MB
            },
            {
                "title": "Test Magazine February 2024",
                "url": "http://example.com/mag-feb2024.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-02-15T10:30:00Z",
                "guid": "test-guid-2",
                "size": 48 * 1024 * 1024,  # 48 MB
            },
        ]

        # Record results
        stats = issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        assert stats["new"] == 2
        assert stats["errors"] == 0

        # Check database
        issues = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).all()
        assert len(issues) == 2

        # Verify first issue
        issue1 = [i for i in issues if "January" in i.title][0]
        assert "January" in issue1.title
        assert issue1.latest_url == "http://example.com/mag-jan2024.nzb"
        assert issue1.download_status == "discovered"
        assert issue1.times_seen == 1
        assert issue1.first_seen is not None
        assert issue1.last_seen is not None

        session.close()

    def test_record_updates_existing_issues(self, test_db, issue_discovery_service):
        """Test updating times_seen and last_seen for existing issues"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # First search - create issue
        search_results_1 = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag-jan2024.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
                "size": 50 * 1024 * 1024,
            },
        ]

        stats1 = issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results_1,
            session=session,
        )
        assert stats1["new"] == 1

        # Get the created issue
        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()
        first_seen = issue.first_seen
        assert issue.times_seen == 1

        # Second search - same issue
        search_results_2 = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag-jan2024-v2.nzb",  # Different URL
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1-v2",
                "size": 50 * 1024 * 1024,
            },
        ]

        stats2 = issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results_2,
            session=session,
        )

        assert stats2["new"] == 0  # No new issues
        assert stats2["updated"] == 1  # Updated existing

        # Check database - should still have 1 issue but updated
        issues = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).all()
        assert len(issues) == 1

        issue = issues[0]
        assert issue.times_seen == 2  # Incremented
        assert issue.last_seen > first_seen  # Updated

        session.close()


class TestEvaluateDiscoveredIssues:
    """Test evaluating discovered issues against tracking rules"""

    def test_evaluate_marks_wanted_with_track_all(self, test_db, issue_discovery_service):
        """Test marking issues as wanted when track_all_editions=True"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking with track_all_editions=True
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create discovered issues using search results
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
            {
                "title": "Test Magazine February 2024",
                "url": "http://example.com/mag2.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-02-15T10:30:00Z",
                "guid": "test-guid-2",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        # Evaluate issues
        stats = issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        assert stats["wanted"] == 2
        assert stats["ignored"] == 0

        # Check database
        issues = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).all()
        for issue in issues:
            assert issue.download_status == "wanted"
            assert issue.download_priority is not None
            assert 1 <= issue.download_priority <= 100

        session.close()

    def test_evaluate_marks_completed_if_already_in_library(self, test_db, issue_discovery_service):
        """Test marking issues as completed if they're already in the library"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create magazine in library
        magazine = Periodical(
            title="Test Magazine",
            issue_date=datetime(2024, 1, 15),
            file_path="/path/to/magazine.pdf",
            tracking_id=tracking.id,
        )
        session.add(magazine)
        session.commit()

        # Create discovered issue with same date
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        # Evaluate issues
        stats = issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        # Should mark as completed (not wanted)
        assert stats["already_have"] > 0

        # Check database
        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()
        assert issue.download_status == "completed"
        assert issue.periodical_id == magazine.id

        session.close()


class TestDownloadFailureHandling:
    """Test download failure handling and retry logic"""

    def test_handle_download_failure_retry(self, test_db, issue_discovery_service):
        """Test marking failed downloads for retry"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create discovered issue
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        # Mark as wanted
        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()
        original_priority = issue.download_priority

        # Handle failure (first attempt)
        new_status = issue_discovery_service.handle_download_failure(
            issue_id=issue.id,
            error_message="Download failed",
            session=session,
        )

        assert new_status == "failed"

        # Check database
        issue = session.query(DiscoveredIssue).filter_by(id=issue.id).first()
        assert issue.download_status == "failed"
        assert issue.attempt_count == 1
        assert issue.download_priority < original_priority  # Priority reduced
        assert issue.last_error == "Download failed"

        session.close()

    def test_handle_download_failure_permanently_failed_after_max_retries(self, test_db, issue_discovery_service):
        """Test marking as permanently_failed after exceeding max_retries"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create discovered issue
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()

        # Default max_retries is 1, so after 2 attempts it should be permanently_failed
        # First failure
        issue_discovery_service.handle_download_failure(
            issue_id=issue.id,
            error_message="First failure",
            session=session,
        )

        # Second failure - exceeds max_retries
        new_status = issue_discovery_service.handle_download_failure(
            issue_id=issue.id,
            error_message="Second failure",
            session=session,
        )

        assert new_status == "permanently_failed"

        # Check database
        issue = session.query(DiscoveredIssue).filter_by(id=issue.id).first()
        assert issue.download_status == "permanently_failed"
        assert issue.attempt_count == 2
        assert issue.download_priority == 0  # Priority set to 0 for bad files

        session.close()


class TestDownloadQueue:
    """Test priority queue generation"""

    def test_get_download_queue_returns_priority_order(self, test_db, issue_discovery_service):
        """Test queue returns wanted issues in priority order"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create discovered issues
        search_results = [
            {
                "title": "Test Magazine Jan 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
            {
                "title": "Test Magazine Feb 2024",
                "url": "http://example.com/mag2.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-02-15T10:30:00Z",
                "guid": "test-guid-2",
            },
            {
                "title": "Test Magazine Mar 2024",
                "url": "http://example.com/mag3.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-03-15T10:30:00Z",
                "guid": "test-guid-3",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        # Manually adjust priorities for testing
        issues = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).all()
        issues[0].download_priority = 90  # High
        issues[1].download_priority = 60  # Medium
        issues[2].download_priority = 30  # Low
        session.commit()

        # Get queue
        queue = issue_discovery_service.get_download_queue(session, limit=10)

        assert len(queue) == 3
        # Check priority order (highest first)
        assert queue[0].download_priority == 90
        assert queue[1].download_priority == 60
        assert queue[2].download_priority == 30

        session.close()

    def test_get_download_queue_excludes_non_wanted_statuses(self, test_db, issue_discovery_service):
        """Test queue only includes wanted and failed issues"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create issues
        search_results = [
            {
                "title": f"Test Magazine Issue {i}",
                "url": f"http://example.com/mag{i}.nzb",
                "provider": "TestProvider",
                "pubdate": f"2024-0{i + 1}-15T10:30:00Z",
                "guid": f"test-guid-{i}",
            }
            for i in range(5)
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        # Mark some as wanted, leave others as discovered
        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        # Manually set different statuses
        issues = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).all()
        issues[0].download_status = "wanted"  # Should be in queue
        issues[1].download_status = "failed"  # Should be in queue
        issues[2].download_status = "completed"  # Should NOT be in queue
        issues[3].download_status = "permanently_failed"  # Should NOT be in queue
        issues[4].download_status = "ignored"  # Should NOT be in queue
        session.commit()

        # Get queue
        queue = issue_discovery_service.get_download_queue(session, limit=10)

        # Should only include "wanted" and "failed" statuses
        assert len(queue) == 2
        assert all(issue.download_status in ["wanted", "failed"] for issue in queue)

        session.close()


class TestRetryPermanentlyFailed:
    """Test manual retry of permanently failed issues"""

    def test_retry_permanently_failed_resets_to_wanted(self, test_db, issue_discovery_service):
        """Test retrying a bad file resets it to wanted status"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create discovered issue
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()

        # Mark as permanently_failed
        issue.download_status = "permanently_failed"
        issue.attempt_count = 5
        issue.last_error = "Import failed"
        issue.download_priority = 0
        session.commit()

        # Retry bad file
        success = issue_discovery_service.retry_permanently_failed(
            issue_id=issue.id,
            session=session,
            reset_attempts=True,
        )

        assert success is True

        # Check database
        issue = session.query(DiscoveredIssue).filter_by(id=issue.id).first()
        assert issue.download_status == "wanted"
        assert issue.attempt_count == 0  # Reset
        assert issue.download_priority == 50  # Reset to default
        assert issue.last_error is None

        session.close()

    def test_retry_permanently_failed_fails_if_not_permanently_failed(self, test_db, issue_discovery_service):
        """Test retrying non-permanently_failed issue fails"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create wanted issue
        search_results = [
            {
                "title": "Test Magazine January 2024",
                "url": "http://example.com/mag1.nzb",
                "provider": "TestProvider",
                "pubdate": "2024-01-15T10:30:00Z",
                "guid": "test-guid-1",
            },
        ]

        issue_discovery_service.record_search_results(
            tracking_id=tracking.id,
            search_results=search_results,
            session=session,
        )

        issue_discovery_service.evaluate_discovered_issues(
            tracking_id=tracking.id,
            session=session,
        )

        issue = session.query(DiscoveredIssue).filter_by(tracking_id=tracking.id).first()

        # Try to retry (should fail - not permanently_failed)
        success = issue_discovery_service.retry_permanently_failed(
            issue_id=issue.id,
            session=session,
        )

        assert success is False

        # Check database - status unchanged
        issue = session.query(DiscoveredIssue).filter_by(id=issue.id).first()
        assert issue.download_status == "wanted"

        session.close()
