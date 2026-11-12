"""DownloadManager paths that only the coordinator tests were exercising.

The client is in-process. Search providers are stubbed except where the test
is about what search_periodical_issues itself returns. Status assertions are
read back from sqlite.
"""

from datetime import datetime, timezone

import pytest

from core.constants.app import MAX_DOWNLOAD_RETRIES
from core.interfaces import DownloadClient, SearchProvider, SearchResult
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
    PeriodicalTracking,
)
from services.download.search_service import _result_has_requested_language
from services.download_manager import DownloadManager

JANUARY = datetime(2024, 1, 15, tzinfo=timezone.utc)
FEBRUARY = datetime(2024, 2, 15, tzinfo=timezone.utc)


class _Client(DownloadClient):
    def __init__(self, job_id="job-1", error=None, status=None, statuses=None):
        super().__init__({"name": "MockClient", "type": "sabnzbd"})
        self.job_id = job_id
        self.error = error
        self.status = status or {"status": "downloading", "progress": 0}
        self.statuses = statuses or {}
        self.submitted_urls = []

    def submit(self, url, title=None, category=None):
        self.submitted_urls.append({"url": url, "title": title, "category": category})
        if self.error:
            raise self.error
        return self.job_id

    def submit_content(self, content, title=None, category=None):
        return f"content-{self.job_id}"

    def get_status(self, job_id):
        status = self.statuses.get(job_id, self.status)
        if isinstance(status, Exception):
            raise status
        return dict(status)

    def get_completed_downloads(self):
        return []

    def delete(self, job_id):
        return True


class _Provider(SearchProvider):
    def __init__(self, results=None, error=None, rate_limited=False, name="Indexer"):
        super().__init__({"name": name, "type": "newsnab"})
        self._results = list(results or [])
        self._error = error
        self._rate_limited = rate_limited
        self.calls = []

    @property
    def is_rate_limited(self):
        return self._rate_limited

    def search(self, query, category=None, aliases=None):
        self.calls.append({"query": query, "category": category, "aliases": list(aliases or [])})
        if self._error:
            raise self._error
        return list(self._results)


class _DatedSearch:
    """Search results that still carry the issue date in the title."""

    def __init__(self, results):
        self.results = results
        self.titles = []

    def search_periodical_issues(self, periodical_title, session, aliases=None):
        self.titles.append(periodical_title)
        return list(self.results)


@pytest.fixture
def session(test_db):
    _, session_factory = test_db
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _manager(client=None, providers=None, max_downloads=10):
    return DownloadManager(
        search_providers=list(providers or []),
        download_client=client or _Client(),
        max_downloads=max_downloads,
    )


def _tracking(session, title="Gardening World", **kwargs):
    tracking = PeriodicalTracking(
        user_id=1,
        olid=title.lower().replace(" ", "-"),
        title=title,
        track_all_editions=kwargs.pop("track_all_editions", True),
        **kwargs,
    )
    session.add(tracking)
    session.commit()
    return tracking


def _issue(session, tracking, title, status=DownloadStatus.WANTED, url="http://example.com/issue.nzb", **kwargs):
    issue = DiscoveredIssue(
        user_id=1,
        tracking_id=tracking.id,
        title=title,
        normalized_title=title.lower(),
        fuzzy_match_group=kwargs.pop("fuzzy_match_group", f"group-{title}"),
        issue_date=kwargs.pop("issue_date", JANUARY),
        download_status=status,
        download_priority=kwargs.pop("download_priority", 50),
        latest_url=kwargs.pop("latest_url", url),
        latest_provider=kwargs.pop("latest_provider", "newsnab"),
        max_retries=kwargs.pop("max_retries", 1),
        attempt_count=kwargs.pop("attempt_count", 0),
        last_error=kwargs.pop("last_error", None),
    )
    session.add(issue)
    session.commit()
    return issue


def _submission(session, tracking, status, job_id="job-1", attempt_count=0, **kwargs):
    submission = DownloadSubmission(
        user_id=1,
        tracking_id=tracking.id,
        result_title=kwargs.pop("result_title", "Gardening World January 2024"),
        source_url=kwargs.pop("source_url", "http://example.com/january.nzb"),
        status=status,
        job_id=job_id,
        client_name=kwargs.pop("client_name", "MockClient"),
        attempt_count=attempt_count,
        fuzzy_match_group=kwargs.pop("fuzzy_match_group", "gardening-world-january-2024"),
    )
    session.add(submission)
    session.commit()
    return submission


def _hit(title, url, when):
    return SearchResult(title=title, url=url, provider="newsnab", publication_date=when)


def _dated_result(title, url, when):
    return {
        "title": title,
        "original_title": title,
        "url": url,
        "provider": "newsnab",
        "publication_date": when,
        "raw_metadata": {},
    }


class TestSearchPeriodicalIssues:
    def test_aliases_are_forwarded_and_the_language_suffix_filters(self, session):
        provider = _Provider(
            results=[
                _hit("Gardening World January 2024", "http://example.com/en.nzb", JANUARY),
                _hit("Gardening World January 2024 French", "http://example.com/fr.nzb", JANUARY),
                _hit(
                    "Gardening World March 2024.mp4",
                    "http://example.com/video.nzb",
                    datetime(2024, 3, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        limited = _Provider(
            results=[_hit("Gardening World April 2024", "http://example.com/late.nzb", JANUARY)],
            rate_limited=True,
            name="Limited",
        )
        manager = _manager(providers=[provider, limited])

        results = manager.search_periodical_issues("Gardening World - French", session, aliases=["Monde Jardin"])

        assert provider.calls == [{"query": "Gardening World", "category": None, "aliases": ["Monde Jardin"]}]
        assert limited.calls == []
        assert [item["original_title"] for item in results] == ["Gardening World January 2024 French"]
        assert results[0]["url"] == "http://example.com/fr.nzb"
        assert results[0]["raw_metadata"]["date_precision"] == "month"

    def test_a_country_name_does_not_pass_the_language_filter(self, session):
        """France, Japan, and Holland are countries. French, 日本語, and Nederlands are languages."""
        cases = (
            ("French", "France", "French"),
            ("Japanese", "Japan", "日本語"),
            ("Dutch", "Holland", "Nederlands"),
        )
        for language, country, word in cases:
            kept = f"Gardening World January 2024 {word}"
            dropped = f"Gardening World January 2024 {country}"
            provider = _Provider(
                results=[
                    _hit(dropped, "http://example.com/country.nzb", JANUARY),
                    _hit(kept, "http://example.com/language.nzb", JANUARY),
                ]
            )
            manager = _manager(providers=[provider])

            results = manager.search_periodical_issues(f"Gardening World - {language}", session)

            assert [item["original_title"] for item in results] == [kept]

    def test_a_provider_error_leaves_the_other_provider_results(self, session):
        broken = _Provider(error=RuntimeError("indexer down"), name="Broken")
        healthy = _Provider(
            results=[_hit("Gardening World February 2024", "http://example.com/feb.nzb", FEBRUARY)], name="Healthy"
        )
        manager = _manager(providers=[broken, healthy])

        results = manager.search_periodical_issues("Gardening World", session)

        assert len(results) == 1
        assert results[0]["original_title"] == "Gardening World February 2024"
        assert results[0]["publication_date"] == FEBRUARY
        assert broken.calls and healthy.calls

    def test_an_exe_title_is_returned_because_search_does_not_apply_the_blacklist(self, session):
        provider = _Provider(
            results=[
                _hit(
                    "Gardening World March 2024.exe",
                    "http://example.com/march.nzb",
                    datetime(2024, 3, 1, tzinfo=timezone.utc),
                )
            ]
        )
        manager = _manager(providers=[provider])

        results = manager.search_periodical_issues("Gardening World", session)

        assert len(results) == 1
        assert results[0]["original_title"].endswith(".exe")
        assert results[0]["title"] == "Gardening World"


def test_language_filter_matches_language_names_not_country_names():
    rejected = (
        ("French", "France"),
        ("German", "Deutschland"),
        ("Spanish", "España"),
        ("Italian", "Italia"),
        ("Dutch", "Holland"),
        ("Polish", "Polska"),
        ("Japanese", "Japan"),
        ("Chinese", "China"),
        ("Korean", "Korea"),
    )
    accepted = (
        ("French", "French"),
        ("French", "Français"),
        ("French", "Francais"),
        ("Japanese", "Japanese"),
        ("Japanese", "日本語"),
        ("Dutch", "Dutch"),
        ("Dutch", "Nederlands"),
    )
    for language, word in rejected:
        title = f"Gardening World January 2024 {word}"
        assert _result_has_requested_language("English", title, language) is False
    for language, word in accepted:
        title = f"Gardening World January 2024 {word}"
        assert _result_has_requested_language("English", title, language) is True


class TestDownloadAllPeriodicalIssues:
    def test_real_search_results_are_not_recorded(self, session):
        """Search stores the cleaned title, which no longer contains the issue date.

        Discovery then rejects every row, so a real search submits nothing.
        """
        provider = _Provider(
            results=[
                _hit("Gardening World January 2024", "http://example.com/jan.nzb", JANUARY),
                _hit("Gardening World February 2024", "http://example.com/feb.nzb", FEBRUARY),
            ]
        )
        client = _Client()
        manager = _manager(client, providers=[provider])
        tracking = _tracking(session)
        found = manager.search_periodical_issues(tracking.title, session)
        assert {item["original_title"] for item in found} == {
            "Gardening World January 2024",
            "Gardening World February 2024",
        }
        assert {item["title"] for item in found} == {"Gardening World"}

        stats = manager.download_all_periodical_issues(tracking.id, session)

        assert stats == {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}
        assert client.submitted_urls == []
        assert session.query(DiscoveredIssue).count() == 0
        assert session.query(DownloadSubmission).count() == 0

    def test_dated_titles_submit_one_issue_and_queue_the_rest(self, session):
        client = _Client(job_id="job-feb")
        manager = _manager(client, max_downloads=1)
        manager.search_service = _DatedSearch(
            [
                _dated_result("Gardening World January 2024", "http://example.com/jan.nzb", JANUARY),
                _dated_result("Gardening World February 2024", "http://example.com/feb.nzb", FEBRUARY),
            ]
        )
        tracking = _tracking(session, download_category="newsstand")

        stats = manager.download_all_periodical_issues(tracking.id, session)

        assert stats["submitted"] == 1
        assert stats["queued"] == 1
        assert stats["skipped"] == 0
        assert stats["failed"] == 0
        assert len(client.submitted_urls) == 1
        assert client.submitted_urls[0]["category"] == "newsstand"
        statuses = {row.status for row in session.query(DownloadSubmission).all()}
        assert statuses == {DownloadSubmission.StatusEnum.PENDING, DownloadSubmission.StatusEnum.QUEUED}
        issues = session.query(DiscoveredIssue).all()
        assert {issue.download_status for issue in issues} == {DownloadStatus.PENDING, DownloadStatus.QUEUED}
        pending = next(issue for issue in issues if issue.download_status == DownloadStatus.PENDING)
        queued = next(issue for issue in issues if issue.download_status == DownloadStatus.QUEUED)
        assert pending.current_submission_id is not None
        assert queued.current_submission_id is not None
        assert pending.attempt_count == 0

    def test_missing_tracking_and_an_empty_search_submit_nothing(self, session):
        client = _Client()
        manager = _manager(client, providers=[_Provider(results=[])])
        tracking = _tracking(session)

        missing = manager.download_all_periodical_issues(9999, session)
        empty = manager.download_all_periodical_issues(tracking.id, session)

        assert missing == {"submitted": 0, "skipped": 0, "failed": 0}
        assert empty == {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}
        assert client.submitted_urls == []
        assert session.query(DownloadSubmission).count() == 0


class TestDownloadSingleIssue:
    def test_a_requested_issue_is_submitted_and_marked_pending(self, session):
        client = _Client(job_id="job-single")
        manager = _manager(client)
        tracking = _tracking(session, download_category="newsstand")
        search_result = _dated_result("Gardening World January 2024", "http://example.com/jan.nzb", JANUARY)

        submission = manager.download_single_issue(tracking.id, search_result, session)

        session.refresh(submission)
        issue = session.query(DiscoveredIssue).one()
        assert submission.status == DownloadSubmission.StatusEnum.PENDING
        assert submission.job_id == "job-single"
        assert submission.attempt_count == 1
        assert submission.client_name == "MockClient"
        assert client.submitted_urls == [
            {
                "url": "http://example.com/jan.nzb",
                "title": issue.title,
                "category": "newsstand",
            }
        ]
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == submission.id
        assert issue.latest_url == "http://example.com/jan.nzb"
        assert issue.date_precision == "month"

    def test_a_blacklisted_title_is_submitted_by_the_manual_fallback(self, session):
        """record_search_results rejects the extension, then the manual path submits it anyway."""
        client = _Client(job_id="job-exe")
        manager = _manager(client)
        tracking = _tracking(session)
        search_result = _dated_result(
            "Gardening World January 2024.exe",
            "http://example.com/bad.nzb",
            JANUARY,
        )

        submission = manager.download_single_issue(tracking.id, search_result, session)

        issue = session.query(DiscoveredIssue).one()
        assert submission.status == DownloadSubmission.StatusEnum.PENDING
        assert submission.source_url == "http://example.com/bad.nzb"
        assert client.submitted_urls[0]["url"] == "http://example.com/bad.nzb"
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.title.endswith(".exe")
        assert issue.last_error is None


class TestSubmissionGuards:
    def test_a_blacklisted_extension_is_permanently_failed_without_a_client_call(self, session):
        client = _Client()
        manager = _manager(client)
        tracking = _tracking(session)
        issue = _issue(session, tracking, "Gardening World January 2024.exe")

        result = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert result is None
        assert client.submitted_urls == []
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.last_error == "Blacklisted file extension"
        assert session.query(DownloadSubmission).count() == 0

    def test_a_missing_url_fails_the_issue(self, session):
        client = _Client()
        manager = _manager(client)
        tracking = _tracking(session)
        issue = _issue(session, tracking, "Gardening World January 2024", latest_url=None)

        result = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert result is None
        assert client.submitted_urls == []
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "Missing URL"
        assert issue.current_submission_id is None
        assert session.query(DownloadSubmission).count() == 0

    def test_a_permanently_failed_issue_is_left_unchanged(self, session):
        client = _Client()
        manager = _manager(client)
        tracking = _tracking(session)
        issue = _issue(
            session,
            tracking,
            "Gardening World January 2024",
            status=DownloadStatus.PERMANENTLY_FAILED,
            last_error="indexer rejected it",
            attempt_count=4,
        )

        result = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert result is None
        assert client.submitted_urls == []
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.last_error == "indexer rejected it"
        assert issue.attempt_count == 4
        assert session.query(DownloadSubmission).count() == 0

    def test_the_issue_is_queued_when_the_active_limit_is_full(self, session):
        client = _Client()
        manager = _manager(client, max_downloads=1)
        tracking = _tracking(session)
        _submission(session, tracking, DownloadSubmission.StatusEnum.PENDING, job_id="job-active")
        issue = _issue(session, tracking, "Gardening World February 2024", url="http://example.com/feb.nzb")

        queued = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert queued.status == DownloadSubmission.StatusEnum.QUEUED
        assert queued.job_id is None
        assert queued.client_name == "MockClient"
        assert queued.source_url == "http://example.com/feb.nzb"
        assert issue.download_status == DownloadStatus.QUEUED
        assert issue.current_submission_id == queued.id
        assert client.submitted_urls == []
        assert session.query(DownloadSubmission).count() == 2

    def test_a_queued_submission_does_not_consume_a_slot(self, session):
        client = _Client(job_id="job-open")
        manager = _manager(client, max_downloads=1)
        tracking = _tracking(session)
        _submission(session, tracking, DownloadSubmission.StatusEnum.QUEUED, job_id=None)
        issue = _issue(session, tracking, "Gardening World February 2024", url="http://example.com/feb.nzb")

        submitted = manager.submit_from_discovered_issue(issue.id, session)

        session.refresh(issue)
        assert submitted.status == DownloadSubmission.StatusEnum.PENDING
        assert submitted.job_id == "job-open"
        assert issue.download_status == DownloadStatus.PENDING
        assert client.submitted_urls[0]["url"] == "http://example.com/feb.nzb"


class TestSubmitDiscoveredBatch:
    def test_only_the_open_slots_are_submitted(self, session):
        client = _Client(job_id="job-batch")
        manager = _manager(client, max_downloads=1)
        tracking = _tracking(session)
        first = _issue(
            session, tracking, "Gardening World January 2024", url="http://example.com/jan.nzb", download_priority=10
        )
        second = _issue(
            session,
            tracking,
            "Gardening World February 2024",
            url="http://example.com/feb.nzb",
            download_priority=90,
            fuzzy_match_group="group-february",
        )

        submitted = manager.submit_discovered_batch(session, manager.issue_discovery_service)

        session.refresh(first)
        session.refresh(second)
        assert submitted == 1
        assert len(client.submitted_urls) == 1
        assert client.submitted_urls[0]["url"] == "http://example.com/feb.nzb"
        assert second.download_status == DownloadStatus.PENDING
        assert first.download_status == DownloadStatus.WANTED
        assert first.current_submission_id is None
        assert session.query(DownloadSubmission).count() == 1

    def test_a_full_queue_submits_nothing(self, session):
        client = _Client()
        manager = _manager(client, max_downloads=1)
        tracking = _tracking(session)
        _submission(session, tracking, DownloadSubmission.StatusEnum.DOWNLOADING, job_id="job-busy")
        issue = _issue(session, tracking, "Gardening World January 2024")

        submitted = manager.submit_discovered_batch(session, manager.issue_discovery_service)

        session.refresh(issue)
        assert submitted == 0
        assert client.submitted_urls == []
        assert issue.download_status == DownloadStatus.WANTED
        assert session.query(DownloadSubmission).count() == 1


class TestRetryAndStatus:
    def test_retry_resubmits_a_failed_download(self, session):
        client = _Client(job_id="job-retry")
        manager = _manager(client)
        tracking = _tracking(session, download_category="newsstand")
        failed = _submission(
            session,
            tracking,
            DownloadSubmission.StatusEnum.FAILED,
            job_id="job-old",
            attempt_count=1,
            source_url="http://example.com/retry.nzb",
        )

        outcome = manager.retry_submission(failed.id, session)

        session.refresh(failed)
        assert outcome["success"] is True
        assert outcome["job_id"] == "job-retry"
        assert outcome["message"] == "Retry submitted (attempt 2)"
        assert failed.status == DownloadSubmission.StatusEnum.PENDING
        assert failed.job_id == "job-retry"
        assert failed.last_error is None
        assert client.submitted_urls == [
            {
                "url": "http://example.com/retry.nzb",
                "title": failed.result_title,
                "category": "newsstand",
            }
        ]

    def test_retry_rejects_a_submission_past_the_default_budget(self, session):
        client = _Client(job_id="job-should-not-run")
        manager = _manager(client)
        tracking = _tracking(session)
        failed = _submission(
            session,
            tracking,
            DownloadSubmission.StatusEnum.FAILED,
            job_id="job-old",
            attempt_count=MAX_DOWNLOAD_RETRIES + 1,
        )

        outcome = manager.retry_submission(failed.id, session)

        session.refresh(failed)
        assert outcome["success"] is False
        assert "failed 2 times" in outcome["message"]
        assert failed.status == DownloadSubmission.StatusEnum.FAILED
        assert failed.job_id == "job-old"
        assert client.submitted_urls == []

    def test_retry_rejects_a_missing_row_and_a_pending_row(self, session):
        client = _Client()
        manager = _manager(client)
        tracking = _tracking(session)
        pending = _submission(session, tracking, DownloadSubmission.StatusEnum.PENDING, job_id="job-live")

        missing = manager.retry_submission(9999, session)
        active = manager.retry_submission(pending.id, session)

        session.refresh(pending)
        assert missing == {"success": False, "message": "Submission not found"}
        assert active["success"] is False
        assert "pending" in active["message"]
        assert pending.status == DownloadSubmission.StatusEnum.PENDING
        assert client.submitted_urls == []

    def test_update_submission_status_stores_completion_failure_and_a_client_error(self, session):
        client = _Client(
            statuses={
                "job-done": {"status": "completed", "file_path": "/downloads/Gardening World January 2024.pdf"},
                "job-bad": {"status": "failed", "error": "checksum mismatch"},
                "job-wait": {"status": "downloading", "rate_limited": True, "message": "slow down", "wait_time": 30},
                "job-err": RuntimeError("client down"),
            }
        )
        manager = _manager(client)
        tracking = _tracking(session)
        done = _submission(session, tracking, DownloadSubmission.StatusEnum.PENDING, job_id="job-done")
        bad = _submission(
            session,
            tracking,
            DownloadSubmission.StatusEnum.DOWNLOADING,
            job_id="job-bad",
            result_title="Gardening World February 2024",
            source_url="http://example.com/feb.nzb",
            fuzzy_match_group="group-february",
        )
        waiting = _submission(
            session,
            tracking,
            DownloadSubmission.StatusEnum.DOWNLOADING,
            job_id="job-wait",
            attempt_count=0,
            result_title="Gardening World March 2024",
            source_url="http://example.com/mar.nzb",
            fuzzy_match_group="group-march",
        )
        broken = _submission(
            session,
            tracking,
            DownloadSubmission.StatusEnum.PENDING,
            job_id="job-err",
            result_title="Gardening World April 2024",
            source_url="http://example.com/apr.nzb",
            fuzzy_match_group="group-april",
        )
        issue = _issue(session, tracking, "Gardening World January 2024", status=DownloadStatus.PENDING)
        issue.current_submission_id = done.id
        session.commit()

        missing = manager.update_submission_status("missing-job", session)
        completed = manager.update_submission_status("job-done", session)
        failed = manager.update_submission_status("job-bad", session)
        limited = manager.update_submission_status("job-wait", session)
        errored = manager.update_submission_status("job-err", session)

        session.refresh(done)
        session.refresh(bad)
        session.refresh(waiting)
        session.refresh(broken)
        session.refresh(issue)
        assert missing is None
        assert completed.status == DownloadSubmission.StatusEnum.COMPLETED
        assert completed.file_path == "/downloads/Gardening World January 2024.pdf"
        assert completed.attempt_count == 0
        assert failed.status == DownloadSubmission.StatusEnum.FAILED
        assert failed.attempt_count == 1
        assert failed.last_error == "checksum mismatch"
        assert limited.status == DownloadSubmission.StatusEnum.PENDING
        assert limited.extra_status == "slow down"
        assert limited.last_error == "slow down"
        assert limited.attempt_count == 0
        assert errored.status == DownloadSubmission.StatusEnum.FAILED
        assert errored.attempt_count == 1
        assert errored.last_error == "client down"
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == done.id
