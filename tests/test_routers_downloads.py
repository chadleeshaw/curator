"""
Test suite for download router endpoints
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import Base, DownloadSubmission, MagazineTracking
from services import DownloadManager


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory


@pytest.fixture
def mock_download_client():
    """Create mock download client"""
    client = Mock()
    client.name = "TestClient"
    client.type = "test"
    client.submit = Mock(return_value="job_123")
    client.get_status = Mock(
        return_value={"status": "completed", "progress": 100, "file_path": "/test/path"}
    )
    return client


@pytest.fixture
def mock_search_provider():
    """Create mock search provider"""
    provider = Mock()
    provider.name = "TestProvider"
    provider.type = "test"
    provider.search = Mock(return_value=[])
    return provider


@pytest.fixture
def download_manager(mock_search_provider, mock_download_client):
    """Create download manager with mocks"""
    return DownloadManager(
        search_providers=[mock_search_provider],
        download_client=mock_download_client,
        fuzzy_threshold=80,
    )


class TestDownloadSubmission:
    """Test download submission functionality"""

    def test_submit_single_download(self, test_db, download_manager):
        """Test submitting a single download"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=False,
        )
        session.add(tracking)
        session.commit()

        # Submit download
        search_result = {
            "title": "Test Magazine Issue 1",
            "url": "http://example.com/test.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }

        submission = download_manager.submit_download(
            tracking.id, search_result, session
        )

        assert submission is not None
        assert submission.job_id == "job_123"
        assert submission.status == DownloadSubmission.StatusEnum.PENDING
        assert submission.tracking_id == tracking.id

        session.close()

    def test_submit_duplicate_prevention(self, test_db, download_manager):
        """Test that duplicate downloads are prevented"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=False,
        )
        session.add(tracking)
        session.commit()

        # Submit first download
        search_result1 = {
            "title": "Test Magazine - Dec 2023",
            "url": "http://example.com/test1.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }
        submission1 = download_manager.submit_download(
            tracking.id, search_result1, session
        )
        assert submission1 is not None

        # Try to submit similar issue (should be detected as duplicate)
        search_result2 = {
            "title": "Test Magazine December 2023",  # Similar title
            "url": "http://example.com/test2.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }
        submission2 = download_manager.submit_download(
            tracking.id, search_result2, session
        )
        assert submission2 is None  # Should be rejected as duplicate

        # Verify duplicate was recorded as SKIPPED
        skipped = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED)
            .count()
        )
        assert skipped == 1

        session.close()


class TestDownloadStatusTracking:
    """Test download status tracking"""

    def test_update_download_status(self, test_db, download_manager):
        """Test updating download status from client"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking and submission
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
        )
        session.add(tracking)
        session.flush()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_123",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/test.nzb",
            result_title="Test Issue",
            fuzzy_match_group="test-issue",
            client_name="TestClient",
        )
        session.add(submission)
        session.commit()

        # Update status
        updated = download_manager.update_submission_status("job_123", session)

        assert updated is not None
        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED
        assert updated.file_path == "/test/path"

        session.close()

    def test_get_pending_downloads(self, test_db, download_manager):
        """Test retrieving pending downloads"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = MagazineTracking(olid="test_mag", title="Test")
        session.add(tracking)
        session.flush()

        # Create mix of submissions
        pending = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/1.nzb",
            result_title="Issue 1",
            fuzzy_match_group="issue-1",
            client_name="TestClient",
        )
        downloading = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_2",
            status=DownloadSubmission.StatusEnum.DOWNLOADING,
            source_url="http://example.com/2.nzb",
            result_title="Issue 2",
            fuzzy_match_group="issue-2",
            client_name="TestClient",
        )
        completed = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_3",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/3.nzb",
            result_title="Issue 3",
            fuzzy_match_group="issue-3",
            client_name="TestClient",
            file_path="/test/job_3.pdf",
        )

        session.add_all([pending, downloading, completed])
        session.commit()

        # Get pending downloads
        active = download_manager.get_pending_downloads(session)

        assert len(active) == 2
        assert pending in active
        assert downloading in active
        assert completed not in active

        session.close()


class TestDownloadCompletion:
    """Test download completion workflow"""

    def test_get_completed_downloads(self, test_db, download_manager):
        """Test retrieving completed downloads"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking
        tracking = MagazineTracking(olid="test_mag", title="Test")
        session.add(tracking)
        session.flush()

        # Create completed downloads
        completed1 = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/1.nzb",
            result_title="Issue 1",
            fuzzy_match_group="issue-1",
            client_name="TestClient",
            file_path="/downloads/job_1.pdf",
        )
        completed2 = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_2",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/2.nzb",
            result_title="Issue 2",
            fuzzy_match_group="issue-2",
            client_name="TestClient",
            file_path="/downloads/job_2.pdf",
        )

        session.add_all([completed1, completed2])
        session.commit()

        # Get completed downloads
        completed = download_manager.get_completed_downloads(session)

        assert len(completed) == 2
        assert all(
            s.status == DownloadSubmission.StatusEnum.COMPLETED for s in completed
        )
        assert all(s.file_path is not None for s in completed)

        session.close()

    def test_mark_processed(self, test_db, download_manager):
        """Test marking download as processed"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking and completed submission
        tracking = MagazineTracking(olid="test_mag", title="Test")
        session.add(tracking)
        session.flush()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/1.nzb",
            result_title="Issue 1",
            fuzzy_match_group="issue-1",
            client_name="TestClient",
            file_path="/downloads/job_1.pdf",
        )
        session.add(submission)
        session.commit()

        # Mark as processed
        result = download_manager.mark_processed(submission.id, session)

        assert result is True
        session.refresh(submission)
        assert submission.file_path is None  # Indicates processed

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
