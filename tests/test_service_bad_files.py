"""
Test failed download tracking and bad file detection.
Tests attempt counting, bad file filtering, and retry prevention.
"""

import sys

sys.path.insert(0, ".")

import pytest
from datetime import datetime, UTC
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services import DownloadManager
from models.database import Base, MagazineTracking, DownloadSubmission, SearchResult as DBSearchResult
from core.bases import DownloadClient


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
    client = Mock(spec=DownloadClient)
    client.name = "TestClient"
    client.submit.return_value = "test-job-123"
    client.get_status.return_value = {"status": "pending", "progress": 0}
    return client


@pytest.fixture
def download_manager(mock_download_client):
    """Create download manager with mock client"""
    return DownloadManager(
        search_providers=[],
        download_client=mock_download_client,
        fuzzy_threshold=80,
    )


class TestAttemptCounting:
    """Test that attempt_count increments on failures"""

    def test_attempt_count_increments_on_failure(self, test_db, download_manager, mock_download_client):
        """Test attempt count increases each time download fails"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create a submission
        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job-123",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/file.nzb",
            result_title="Test Issue",
            fuzzy_match_group="test-issue",
            attempt_count=1,
        )
        session.add(submission)
        session.commit()

        # Simulate failure from client
        mock_download_client.get_status.return_value = {"status": "failed", "error": "Download error"}

        # Update submission status (should increment attempt_count)
        result = download_manager.update_submission_status("job-123", session)

        assert result is not None
        assert result.status == DownloadSubmission.StatusEnum.FAILED
        assert result.attempt_count == 2
        assert result.last_error == "Download error"

        session.close()

    def test_attempt_count_starts_at_one(self, test_db, download_manager):
        """Test new submissions start with attempt_count=1"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="test-mag",
            title="Test Magazine",
        )
        session.add(tracking)
        session.commit()

        search_result = {
            "title": "Test Issue",
            "url": "http://example.com/file.nzb",
            "provider": "test",
        }

        submission = download_manager.submit_download(tracking.id, search_result, session)

        assert submission is not None
        assert submission.attempt_count == 1

        session.close()

    def test_multiple_failures_increment_count(self, test_db, download_manager, mock_download_client):
        """Test attempt count increases with each failure"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job-456",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/bad.nzb",
            result_title="Bad File",
            fuzzy_match_group="bad-file",
            attempt_count=0,
        )
        session.add(submission)
        session.commit()

        # Fail three times
        mock_download_client.get_status.return_value = {"status": "failed", "error": "Error"}

        for expected_count in [1, 2, 3]:
            result = download_manager.update_submission_status("job-456", session)
            session.refresh(submission)
            assert submission.attempt_count == expected_count

        session.close()


class TestBadFileDetection:
    """Test bad file detection and filtering"""

    def test_get_bad_files_returns_three_plus_failures(self, test_db, download_manager):
        """Test get_bad_files returns only files with 3+ failures"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        # Create submissions with different failure counts
        submissions = [
            DownloadSubmission(
                tracking_id=tracking.id,
                status=DownloadSubmission.StatusEnum.FAILED,
                source_url=f"http://example.com/file{i}.nzb",
                result_title=f"File {i}",
                fuzzy_match_group=f"file-{i}",
                attempt_count=i,
            )
            for i in [1, 2, 3, 4, 5]
        ]
        for sub in submissions:
            session.add(sub)
        session.commit()

        bad_files = download_manager.get_bad_files(session)

        assert len(bad_files) == 3  # Only 3, 4, 5
        assert all(f.attempt_count >= 3 for f in bad_files)

        session.close()

    def test_get_failed_downloads_excludes_bad_files_by_default(self, test_db, download_manager):
        """Test get_failed_downloads excludes bad files by default"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        # Create mix of failed downloads
        submissions = [
            DownloadSubmission(
                tracking_id=tracking.id,
                status=DownloadSubmission.StatusEnum.FAILED,
                source_url=f"http://example.com/file{i}.nzb",
                result_title=f"File {i}",
                fuzzy_match_group=f"file-{i}",
                attempt_count=i,
            )
            for i in [1, 2, 3, 4]
        ]
        for sub in submissions:
            session.add(sub)
        session.commit()

        failed = download_manager.get_failed_downloads(session, include_bad_files=False)

        assert len(failed) == 2  # Only 1 and 2
        assert all(f.attempt_count < 3 for f in failed)

        session.close()

    def test_get_failed_downloads_includes_bad_files_when_requested(self, test_db, download_manager):
        """Test get_failed_downloads includes bad files when include_bad_files=True"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        submissions = [
            DownloadSubmission(
                tracking_id=tracking.id,
                status=DownloadSubmission.StatusEnum.FAILED,
                source_url=f"http://example.com/file{i}.nzb",
                result_title=f"File {i}",
                fuzzy_match_group=f"file-{i}",
                attempt_count=i,
            )
            for i in [1, 2, 3, 4]
        ]
        for sub in submissions:
            session.add(sub)
        session.commit()

        failed = download_manager.get_failed_downloads(session, include_bad_files=True)

        assert len(failed) == 4  # All failed downloads

        session.close()


class TestRetryPrevention:
    """Test that bad files are not retried"""

    def test_bad_files_skipped_on_submit(self, test_db, download_manager):
        """Test submit_download skips URLs that have failed 3+ times"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        # Create a bad file record (3 failures)
        bad_submission = DownloadSubmission(
            tracking_id=tracking.id,
            status=DownloadSubmission.StatusEnum.FAILED,
            source_url="http://example.com/bad.nzb",
            result_title="Bad File",
            fuzzy_match_group="bad-file",
            attempt_count=3,
            last_error="Previous failure",
        )
        session.add(bad_submission)
        session.commit()

        # Try to submit the same URL again
        search_result = {
            "title": "Bad File Retry",
            "url": "http://example.com/bad.nzb",
            "provider": "test",
        }

        result = download_manager.submit_download(tracking.id, search_result, session)

        # Should be rejected (None)
        assert result is None

        session.close()

    def test_two_failures_still_allows_retry(self, test_db, download_manager, mock_download_client):
        """Test files with <3 failures can still be retried"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        # Create a submission with 2 failures
        previous_submission = DownloadSubmission(
            tracking_id=tracking.id,
            status=DownloadSubmission.StatusEnum.FAILED,
            source_url="http://example.com/retry.nzb",
            result_title="Retryable File",
            fuzzy_match_group="retry-file",
            attempt_count=2,
        )
        session.add(previous_submission)
        session.commit()

        # Try to submit the same URL again
        search_result = {
            "title": "Retryable File Retry",
            "url": "http://example.com/different.nzb",  # Different URL, same title pattern
            "provider": "test",
        }

        result = download_manager.submit_download(tracking.id, search_result, session)

        # Should be allowed (not None)
        assert result is not None

        session.close()

    def test_max_retries_logged(self, test_db, download_manager, mock_download_client, caplog):
        """Test that reaching max retries is logged"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.commit()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job-max",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/max.nzb",
            result_title="Max Retries File",
            fuzzy_match_group="max-file",
            attempt_count=2,
        )
        session.add(submission)
        session.commit()

        # Fail one more time to reach 3
        mock_download_client.get_status.return_value = {"status": "failed", "error": "Final error"}

        with caplog.at_level("ERROR"):
            result = download_manager.update_submission_status("job-max", session)

        assert result.attempt_count == 3
        assert "Max retries reached" in caplog.text
        assert "marking as bad file" in caplog.text

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
