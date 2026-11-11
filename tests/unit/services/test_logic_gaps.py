"""Correct behavior for the discovery and download state bugs.

A neighboring month is a different issue. One accepted download plus one
client failure stays retryable. A submission that never reaches the client
does not leave its issue queued or pending. An indexer error is not sent to
the download client and is not submitted again until the URL changes.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from core.interfaces import DownloadClient
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
    OCRJob,
    Periodical,
    PeriodicalTracking,
)
from schedulers.download_monitor import DownloadMonitor
from services.cache.provider_cache import NzbCacheService, NzbContentRejected
from services.download.nzb_submit import submit_with_nzb_content
from services.download.queue_processor import QueueProcessor
from services.download_manager import DownloadManager
from services.issue_discovery import IssueDiscoveryService
from services.ocr.queue import OCRQueueService

DOWNLOAD_URL = "http://prowlarr.local/1/download?apikey=secret&link=xyz"


class _Client(DownloadClient):
    def __init__(self, job_id="job-1", error=None):
        super().__init__({"name": "MockClient", "type": "sabnzbd"})
        self.job_id = job_id
        self.error = error
        self.submitted_urls = []

    def submit(self, url, title=None, category=None):
        if self.error:
            raise self.error
        self.submitted_urls.append(url)
        return self.job_id

    def submit_content(self, content, title=None, category=None):
        return f"content-{self.job_id}"

    def get_status(self, job_id):
        return {"status": "downloading", "progress": 0}

    def get_completed_downloads(self):
        return []

    def delete(self, job_id):
        return True


class _UrlClient:
    """Own submit_content, so a cache result is used instead of the URL."""

    def __init__(self):
        self.submitted_url = None

    def submit(self, url, title=None, category=None):
        self.submitted_url = url
        return "url-job"

    def submit_content(self, content, title=None, category=None):
        return "content-job"


def _tracking(session, title="Test Magazine"):
    tracking = PeriodicalTracking(
        olid=title.lower().replace(" ", "-"),
        title=title,
        track_all_editions=True,
        user_id=1,
    )
    session.add(tracking)
    session.commit()
    return tracking


def _library_issue(session, tracking, month, year=2024):
    magazine = Periodical(
        title=tracking.title,
        issue_date=datetime(year, month, 15),
        file_path=f"/library/{tracking.title}-{year}-{month}.pdf",
        tracking_id=tracking.id,
        user_id=1,
    )
    session.add(magazine)
    session.commit()
    return magazine


def _discovered(session, tracking, month, year=2024, status=DownloadStatus.DISCOVERED):
    issue = DiscoveredIssue(
        user_id=1,
        tracking_id=tracking.id,
        title=f"{tracking.title} {year}-{month:02d}",
        normalized_title=f"{tracking.title} {year}-{month:02d}".lower(),
        fuzzy_match_group=f"group-{year}-{month:02d}",
        issue_date=datetime(year, month, 1),
        download_status=status,
        download_priority=50,
        latest_url=f"http://example.com/{year}-{month:02d}.nzb",
        latest_provider="newsnab",
        max_retries=1,
        attempt_count=0,
    )
    session.add(issue)
    session.commit()
    return issue


def _queued_pair(session, tracking):
    submission = DownloadSubmission(
        user_id=1,
        tracking_id=tracking.id,
        result_title="Queued issue",
        source_url="http://example.com/queued.nzb",
        status=DownloadSubmission.StatusEnum.QUEUED,
        client_name="MockClient",
    )
    session.add(submission)
    session.commit()
    issue = _discovered(session, tracking, 3, status=DownloadStatus.QUEUED)
    issue.current_submission_id = submission.id
    session.commit()
    return issue, submission


class TestNeighboringMonthIsADifferentIssue:
    def test_february_is_wanted_when_january_is_in_the_library(self, test_db, issue_discovery_service):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        owned = _library_issue(session, tracking, 1)
        february = _discovered(session, tracking, 2)
        december = _discovered(session, tracking, 12, year=2023)

        stats = issue_discovery_service.evaluate_discovered_issues(tracking.id, session)

        session.refresh(february)
        session.refresh(december)
        assert stats["already_have"] == 0
        assert stats["wanted"] == 2
        assert february.download_status == DownloadStatus.WANTED
        assert february.periodical_id is None
        assert december.download_status == DownloadStatus.WANTED
        assert december.periodical_id != owned.id

        session.close()

    def test_the_same_month_is_already_in_the_library(self, test_db, issue_discovery_service):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        owned = _library_issue(session, tracking, 1)
        january = _discovered(session, tracking, 1)

        stats = issue_discovery_service.evaluate_discovered_issues(tracking.id, session)

        session.refresh(january)
        assert stats["already_have"] == 1
        assert january.download_status == DownloadStatus.COMPLETED
        assert january.periodical_id == owned.id
        session.close()


class TestClientFailureUsesOneAttempt:
    def test_the_first_client_failure_can_be_retried(self, test_db, issue_discovery_service):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        issue = _discovered(session, tracking, 6, status=DownloadStatus.WANTED)
        manager = DownloadManager(
            search_providers=[],
            download_client=_Client(),
            max_downloads=10,
            issue_discovery_service=issue_discovery_service,
        )

        submission = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert submission is not None
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.attempt_count == 0

        status = issue_discovery_service.handle_download_failure(issue.id, "Download failed", session)
        session.refresh(issue)
        assert status == DownloadStatus.FAILED
        assert issue.attempt_count == 1

        resubmitted = manager.submit_from_discovered_issue(issue.id, session)
        session.refresh(issue)
        assert resubmitted is not None
        assert issue.attempt_count == 1

        status = issue_discovery_service.handle_download_failure(issue.id, "Download failed again", session)
        session.refresh(issue)
        assert status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.attempt_count == 2
        session.close()


class TestFailedSubmissionReleasesTheIssue:
    def test_a_missing_job_id_does_not_leave_the_issue_queued(self, test_db):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        issue, submission = _queued_pair(session, tracking)
        processor = QueueProcessor(_Client(job_id=None), max_downloads=10)

        processor.process_queue(session)

        session.refresh(issue)
        session.refresh(submission)
        assert submission.status == DownloadSubmission.StatusEnum.FAILED
        assert issue.download_status != DownloadStatus.QUEUED
        assert issue.current_submission_id is None
        assert issue.attempt_count == 1
        assert issue.download_status == DownloadStatus.FAILED
        session.close()

    def test_a_second_client_rejection_is_permanent(self, test_db):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        issue, submission = _queued_pair(session, tracking)
        issue.attempt_count = 1
        session.commit()
        processor = QueueProcessor(_Client(job_id=None), max_downloads=10)

        processor.process_queue(session)

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.current_submission_id is None
        session.close()

    def test_a_submit_exception_does_not_leave_the_issue_queued(self, test_db):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        issue, submission = _queued_pair(session, tracking)
        processor = QueueProcessor(_Client(error=RuntimeError("client down")), max_downloads=10)

        processor.process_queue(session)

        session.refresh(issue)
        session.refresh(submission)
        assert submission.status == DownloadSubmission.StatusEnum.FAILED
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.current_submission_id is None
        session.close()

    def test_a_missing_tracking_record_does_not_leave_the_issue_queued(self, test_db):
        _, session_factory = test_db
        session = session_factory()
        submission = DownloadSubmission(
            user_id=1,
            tracking_id=999,
            result_title="Queued issue",
            source_url="http://example.com/queued.nzb",
            status=DownloadSubmission.StatusEnum.QUEUED,
            client_name="MockClient",
        )
        session.add(submission)
        session.commit()
        issue = DiscoveredIssue(
            user_id=1,
            tracking_id=999,
            title="Queued issue",
            normalized_title="queued issue",
            fuzzy_match_group="queued-issue",
            download_status=DownloadStatus.QUEUED,
            latest_url="http://example.com/queued.nzb",
            current_submission_id=submission.id,
            max_retries=1,
            attempt_count=0,
        )
        session.add(issue)
        session.commit()
        processor = QueueProcessor(_Client(), max_downloads=10)

        processor.process_queue(session)

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.current_submission_id is None
        session.close()


class TestOrphanedCompletionFailsTheIssue:
    def test_a_completed_download_with_no_file_fails_the_issue(self, test_db, tmp_path):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        submission = DownloadSubmission(
            user_id=1,
            tracking_id=tracking.id,
            result_title="Finished with no file",
            source_url="http://example.com/done.nzb",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            job_id="job-orphan",
            client_name="MockClient",
            file_path=None,
        )
        session.add(submission)
        session.commit()
        issue = _discovered(session, tracking, 4, status=DownloadStatus.PENDING)
        issue.current_submission_id = submission.id
        session.commit()

        download_manager = Mock()
        download_manager.update_submission_status.return_value = submission
        monitor = DownloadMonitor(
            download_manager,
            MagicMock(),
            session_factory,
            str(tmp_path),
            issue_discovery_service=IssueDiscoveryService(default_max_retries=1),
        )

        assert monitor._handle_orphaned_submission(submission, session) is None

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.attempt_count == 1
        assert issue.current_submission_id is None
        session.close()


class TestDeadIndexerUrlIsNotSentToTheClient:
    def test_an_http_status_error_is_not_submitted_by_url(self, tmp_path):
        service = NzbCacheService(cache_db_path=str(tmp_path / "cache.db"))
        response = MagicMock()
        response.text = ""
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        client = _UrlClient()

        with patch("services.cache.provider_cache.httpx.get", return_value=response):
            with pytest.raises(NzbContentRejected):
                submit_with_nzb_content(client, DOWNLOAD_URL, "Issue", nzb_cache_service=service)

        assert client.submitted_url is None

    def test_a_network_error_can_still_fall_back_to_the_url(self, tmp_path):
        service = NzbCacheService(cache_db_path=str(tmp_path / "cache.db"))
        client = _UrlClient()

        with patch("services.cache.provider_cache.httpx.get", side_effect=httpx.ConnectError("down")):
            job_id = submit_with_nzb_content(client, DOWNLOAD_URL, "Issue", nzb_cache_service=service)

        assert job_id == "url-job"
        assert client.submitted_url == DOWNLOAD_URL

    def test_a_rejected_nzb_is_not_queued_again_until_the_url_changes(self, test_db, issue_discovery_service):
        _, session_factory = test_db
        session = session_factory()
        tracking = _tracking(session)
        issue = _discovered(session, tracking, 7, status=DownloadStatus.WANTED)
        cache = Mock()
        cache.get_nzb_content.side_effect = NzbContentRejected("retired")
        manager = DownloadManager(
            search_providers=[],
            download_client=_Client(),
            max_downloads=10,
            nzb_cache_service=cache,
            issue_discovery_service=issue_discovery_service,
        )

        assert manager.submit_from_discovered_issue(issue.id, session) is None

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.attempt_count == 0
        assert issue.id not in {item.id for item in issue_discovery_service.get_download_queue(session)}

        issue.latest_url = "http://example.com/fresh.nzb"
        issue.download_status = DownloadStatus.WANTED
        session.commit()
        assert issue.id in {item.id for item in issue_discovery_service.get_download_queue(session)}
        session.close()


class TestOcrTimeoutCountsAsAnAttempt:
    def test_a_repeated_timeout_stops(self, test_db, tmp_path, monkeypatch):
        _, session_factory = test_db
        session = session_factory()
        pdf_path = tmp_path / "issue.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        magazine = Periodical(
            title="Test Magazine",
            issue_date=datetime(2024, 1, 1),
            file_path=str(pdf_path),
            user_id=1,
        )
        session.add(magazine)
        session.commit()
        job = OCRJob(periodical_id=magazine.id, status=OCRJob.StatusEnum.PENDING, attempt_count=0)
        session.add(job)
        session.commit()

        def timeout(jobs, timeout=120):
            return {job["periodical_id"]: "timeout" for job in jobs}

        monkeypatch.setattr("services.ocr.queue._generate_pngs_parallel", timeout)
        monkeypatch.setattr("services.ocr.queue.ConfigLoader", MagicMock())
        service = OCRQueueService()

        service.process_queue(session, batch_size=1, max_retries=2)
        session.refresh(job)
        assert job.status == OCRJob.StatusEnum.PENDING
        assert job.attempt_count == 1

        service.process_queue(session, batch_size=1, max_retries=2)
        session.refresh(job)
        assert job.status == OCRJob.StatusEnum.FAILED
        assert job.attempt_count == 2
        assert job.last_error == "OCR image generation timed out"
        session.close()
