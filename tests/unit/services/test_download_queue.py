"""
Test download queuing behavior in submit_from_discovered_issue().

Tests cover:
- Items beyond the concurrent download limit get QUEUED submission records
- DiscoveredIssue status is updated to "queued" when at limit
- Queue processor can pick up QUEUED submissions
"""

import pytest
from datetime import datetime, UTC

from core.interfaces import DownloadClient
from models.database import (
    DiscoveredIssue,
    DownloadSubmission,
    PeriodicalTracking,
    DownloadStatus,
)
from services.download_manager import DownloadManager


class MockDownloadClient(DownloadClient):
    """Mock download client for testing"""

    def __init__(self):
        super().__init__({"name": "MockClient", "type": "download_client"})
        self.submitted = []
        self.submitted_content = []

    def submit(self, url, title=None, category=None):
        self.submitted.append({"url": url, "title": title, "category": category})
        return f"mock_job_{len(self.submitted)}"

    def submit_content(self, content, title=None, category=None):
        self.submitted_content.append({"content": content, "title": title, "category": category})
        return f"mock_content_job_{len(self.submitted_content)}"

    def get_status(self, job_id):
        return {"status": "completed", "progress": 100}

    def get_completed_downloads(self):
        return []

    def delete(self, job_id):
        return True


@pytest.fixture
def mock_client():
    return MockDownloadClient()


def _create_tracking(session, title="Test Magazine"):
    """Helper to create a tracking record"""
    tracking = PeriodicalTracking(
        title=title,
        olid=title.lower().replace(" ", "_"),
        language="en",
        user_id=1,
    )
    session.add(tracking)
    session.commit()
    return tracking


def _create_discovered_issue(
    session,
    tracking_id,
    title,
    url="http://example.com/test.nzb",
    status=DownloadStatus.WANTED,
):
    """Helper to create a DiscoveredIssue"""
    issue = DiscoveredIssue(
        tracking_id=tracking_id,
        title=title,
        normalized_title=title.lower(),
        fuzzy_match_group=title.lower().replace(" ", "_"),
        issue_date=datetime(2024, 1, 1, tzinfo=UTC),
        download_status=status,
        latest_url=url,
        latest_provider="newsnab",
        user_id=1,
    )
    session.add(issue)
    session.commit()
    return issue


def _create_active_submission(session, tracking_id, title, status=DownloadSubmission.StatusEnum.PENDING):
    """Helper to create an active submission to fill up the download limit"""
    submission = DownloadSubmission(
        tracking_id=tracking_id,
        result_title=title,
        source_url=f"http://example.com/{title.lower().replace(' ', '_')}.nzb",
        status=status,
        job_id=f"job_{title.lower().replace(' ', '_')}",
        client_name="MockClient",
        user_id=1,
    )
    session.add(submission)
    session.commit()
    return submission


class TestSubmitFromDiscoveredIssueQueuing:
    """Test that submit_from_discovered_issue creates QUEUED records when at download limit"""

    def test_creates_queued_submission_when_at_limit(self, test_db, mock_client):
        """When at max_downloads, should create a QUEUED submission record instead of returning None"""
        _, session_factory = test_db
        session = session_factory()

        tracking = _create_tracking(session)

        # Create 10 active (PENDING) submissions to fill the limit
        for i in range(10):
            _create_active_submission(session, tracking.id, f"Active Download {i}")

        # Create a discovered issue that should be queued
        issue = _create_discovered_issue(session, tracking.id, "New Issue - January 2024")

        manager = DownloadManager(
            search_providers=[],
            download_client=mock_client,
            max_downloads=10,
        )

        result = manager.submit_from_discovered_issue(issue.id, session)

        # Should return a submission, not None
        assert result is not None, "Expected QUEUED submission, got None"
        assert result.status == DownloadSubmission.StatusEnum.QUEUED

        # Client should NOT have been called (we're at capacity)
        assert len(mock_client.submitted) == 0

        session.close()

    def test_discovered_issue_status_updated_to_queued(self, test_db, mock_client):
        """DiscoveredIssue.download_status should be set to 'queued' when submission is queued"""
        _, session_factory = test_db
        session = session_factory()

        tracking = _create_tracking(session)

        for i in range(10):
            _create_active_submission(session, tracking.id, f"Active Download {i}")

        issue = _create_discovered_issue(session, tracking.id, "Queued Issue - February 2024")

        manager = DownloadManager(
            search_providers=[],
            download_client=mock_client,
            max_downloads=10,
        )

        submission = manager.submit_from_discovered_issue(issue.id, session)

        # Refresh the issue from DB
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.QUEUED
        assert issue.current_submission_id == submission.id
        assert submission.id in (issue.submission_ids or [])

        session.close()

    def test_submits_directly_when_under_limit(self, test_db, mock_client):
        """When under max_downloads, should submit directly (PENDING status)"""
        _, session_factory = test_db
        session = session_factory()

        tracking = _create_tracking(session)
        issue = _create_discovered_issue(session, tracking.id, "Direct Issue - March 2024")

        manager = DownloadManager(
            search_providers=[],
            download_client=mock_client,
            max_downloads=10,
        )

        result = manager.submit_from_discovered_issue(issue.id, session)

        assert result is not None
        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert len(mock_client.submitted) == 1

        session.close()

    def test_multiple_issues_queued_beyond_limit(self, test_db, mock_client):
        """Multiple issues submitted beyond the limit should all get QUEUED records"""
        _, session_factory = test_db
        session = session_factory()

        tracking = _create_tracking(session)

        # Fill up the limit
        for i in range(10):
            _create_active_submission(session, tracking.id, f"Active Download {i}")

        # Submit 5 more issues - all should be QUEUED
        queued_submissions = []
        for i in range(5):
            issue = _create_discovered_issue(
                session,
                tracking.id,
                f"Overflow Issue {i} - 2024",
                url=f"http://example.com/overflow_{i}.nzb",
            )

            manager = DownloadManager(
                search_providers=[],
                download_client=mock_client,
                max_downloads=10,
            )

            result = manager.submit_from_discovered_issue(issue.id, session)
            queued_submissions.append(result)

        # All 5 should have QUEUED submissions
        for sub in queued_submissions:
            assert sub is not None, "Expected QUEUED submission, got None"
            assert sub.status == DownloadSubmission.StatusEnum.QUEUED

        # Verify 5 QUEUED records exist in DB
        queued_count = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.QUEUED)
            .count()
        )
        assert queued_count == 5

        # Client should NOT have been called for any of these
        assert len(mock_client.submitted) == 0

        session.close()

    def test_queue_processor_picks_up_queued_submissions(self, test_db, mock_client):
        """Queue processor should find and submit QUEUED records when capacity opens up"""
        _, session_factory = test_db
        session = session_factory()

        tracking = _create_tracking(session)

        # Create a QUEUED submission (simulating what our fix does)
        issue = _create_discovered_issue(session, tracking.id, "Queued Issue")

        manager = DownloadManager(
            search_providers=[],
            download_client=mock_client,
            max_downloads=10,
        )

        # Fill limit and queue one
        for i in range(10):
            _create_active_submission(session, tracking.id, f"Active Download {i}")

        submission = manager.submit_from_discovered_issue(issue.id, session)
        assert submission is not None
        assert submission.status == DownloadSubmission.StatusEnum.QUEUED

        # Now "complete" all active downloads by changing their status
        active_subs = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
            .all()
        )
        for sub in active_subs:
            sub.status = DownloadSubmission.StatusEnum.COMPLETED
        session.commit()

        # Run queue processor
        result = manager.queue_processor.process_queue(session)

        assert result["submitted"] == 1

        # Refresh submission - should now be PENDING
        session.refresh(submission)
        assert submission.status == DownloadSubmission.StatusEnum.PENDING

        session.close()
