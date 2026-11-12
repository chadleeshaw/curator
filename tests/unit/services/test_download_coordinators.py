"""Behavioral tests for the download coordinators and their shared helpers.

Network and search providers are stubbed. Coordinators, the queue processor,
issue discovery, and the sqlite session are the real objects.
"""

from datetime import datetime, timezone
from threading import Lock

import pytest

from core.constants.app import MAX_DOWNLOAD_RETRIES, MAX_DOWNLOAD_RETRIES_IA, MAX_ERROR_LENGTH
from core.interfaces import DownloadClient
from core.parsers import Parser
from models.database import DiscoveredIssue, DownloadStatus, DownloadSubmission, PeriodicalTracking
from services.cache.provider_cache import NzbContentRejected
from services.download._coordinator_helpers import (
    get_active_download_count,
    get_client_for_provider,
    get_download_category,
)
from services.download.queue_coordinator import QueueCoordinator
from services.download.queue_processor import QueueProcessor
from services.download.status_coordinator import StatusCoordinator
from services.download.submission_coordinator import MANUAL_DOWNLOAD_PRIORITY, SubmissionCoordinator
from services.download.submission_service import SubmissionService
from services.issue_discovery import IssueDiscoveryService

PROVIDER_MAP = {
    "internet_archive": "internet_archive",
    "torznab": "qbittorrent",
    "newsnab": "default",
    "rss": "default",
}

ARCHIVE_URL = "https://archive.org/download/test-magazine/january.pdf"
NZB_URL = "http://example.com/january.nzb"


class _Unset:
    def __init__(self, label):
        self.label = label

    def __repr__(self):
        return self.label


_UNSET = _Unset("UNSET")
_NONE = _Unset("NONE")


class _Client(DownloadClient):
    """In-process download client. Type decides whether the NZB cache is used."""

    def __init__(
        self,
        name="SABnzbd",
        client_type="sabnzbd",
        job_id="job-1",
        status=None,
        submit_job_id=_UNSET,
        submit_error=None,
        status_error=None,
    ):
        super().__init__({"name": name, "type": client_type, "default_category": "client-default"})
        self._job_id = job_id
        self._status = dict(status or {"status": "downloading", "progress": 10})
        self._submit_job_id = submit_job_id
        self._submit_error = submit_error
        self._status_error = status_error
        self.submits = []
        self.contents = []
        self.status_calls = []

    def submit(self, url, title=None, category=None):
        self.submits.append({"url": url, "title": title, "category": category})
        if self._submit_error:
            raise self._submit_error
        if self._submit_job_id is _NONE:
            return None
        if self._submit_job_id is not _UNSET:
            return self._submit_job_id
        return self._job_id

    def submit_content(self, content, title=None, category=None):
        self.contents.append({"content": content, "title": title, "category": category})
        return f"content-{self._job_id}"

    def get_status(self, job_id):
        self.status_calls.append(job_id)
        if self._status_error:
            raise self._status_error
        return dict(self._status)

    def get_completed_downloads(self):
        return []

    def delete(self, job_id):
        return True


class _Cache:
    def __init__(self, content="<nzb>cached</nzb>", error=None):
        self.content = content
        self.error = error
        self.urls = []

    def get_nzb_content(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.content


class _Search:
    def __init__(self, results):
        self.results = results
        self.titles = []

    def search_periodical_issues(self, periodical_title, session):
        self.titles.append(periodical_title)
        return list(self.results)


class _FailingCommit:
    """Real session whose Nth commit raises, so a swallowed commit is observable."""

    def __init__(self, session, fail_on):
        self._session = session
        self.fail_on = fail_on
        self.commits = 0

    def commit(self):
        self.commits += 1
        if self.commits == self.fail_on:
            raise RuntimeError("sync commit failed")
        return self._session.commit()

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture
def session(test_db):
    _, session_factory = test_db
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _clients():
    sab = _Client(name="SABnzbd", client_type="sabnzbd", job_id="job-1")
    qbt = _Client(name="qBittorrent", client_type="qbittorrent", job_id="torrent-job")
    ia = _Client(name="Internet Archive", client_type="internet_archive", job_id="ia-job")
    return sab, qbt, ia, {"default": sab, "qbittorrent": qbt, "internet_archive": ia}


def _tracking(session, title="Test Magazine", download_category=None):
    tracking = PeriodicalTracking(
        olid=title.lower().replace(" ", "-"),
        title=title,
        user_id=1,
        track_all_editions=True,
        download_category=download_category,
    )
    session.add(tracking)
    session.commit()
    return tracking


def _issue(
    session,
    tracking,
    *,
    title=None,
    url=NZB_URL,
    provider="newsnab",
    status=DownloadStatus.WANTED,
    submission_id=None,
    max_retries=1,
    attempt_count=0,
    last_error=None,
    priority=50,
    fuzzy_group="group-january-2024",
):
    title = title or f"{tracking.title} January 2024"
    issue = DiscoveredIssue(
        user_id=1,
        tracking_id=tracking.id,
        title=title,
        normalized_title=title.lower(),
        fuzzy_match_group=fuzzy_group,
        download_status=status,
        latest_url=url,
        latest_provider=provider,
        current_submission_id=submission_id,
        max_retries=max_retries,
        attempt_count=attempt_count,
        last_error=last_error,
        download_priority=priority,
    )
    session.add(issue)
    session.commit()
    return issue


def _row(
    session,
    tracking,
    *,
    title="Existing download",
    url=NZB_URL,
    status=DownloadSubmission.StatusEnum.PENDING,
    job_id="job-existing",
    client_name="SABnzbd",
    attempt_count=0,
    fuzzy_group=None,
    created_at=None,
    last_error=None,
    extra_status=None,
    file_path=None,
):
    row = DownloadSubmission(
        user_id=1,
        tracking_id=tracking.id,
        result_title=title,
        source_url=url,
        status=status,
        job_id=job_id,
        client_name=client_name,
        attempt_count=attempt_count,
        fuzzy_match_group=fuzzy_group,
        last_error=last_error,
        extra_status=extra_status,
        file_path=file_path,
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    session.commit()
    return row


def _submission(clients, **kwargs):
    return SubmissionCoordinator(
        download_clients=clients,
        provider_client_map=dict(PROVIDER_MAP),
        nzb_cache_service=kwargs.get("cache"),
        max_downloads=kwargs.get("max_downloads", 10),
        default_category=kwargs.get("default_category", "magazines"),
        parser=Parser(),
        submission_service=SubmissionService(),
        issue_discovery_service=kwargs.get("discovery") or IssueDiscoveryService(),
        slot_lock=Lock(),
        search_service=kwargs.get("search"),
    )


def _queue(clients, processor, max_downloads=10):
    return QueueCoordinator(
        download_clients=clients,
        provider_client_map=dict(PROVIDER_MAP),
        max_downloads=max_downloads,
        queue_processor=processor,
        slot_lock=Lock(),
    )


def _status(clients, *, cache=None, default_category="magazines"):
    return StatusCoordinator(
        download_clients=clients,
        nzb_cache_service=cache,
        default_category=default_category,
        submission_service=SubmissionService(),
    )


def _result(title="Test Magazine January 2024", url=NZB_URL, provider="newsnab", pubdate="2024-01-15T10:30:00Z"):
    return {"title": title, "url": url, "provider": provider, "pubdate": pubdate, "guid": title}


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


class TestCoordinatorHelpers:
    def test_torznab_routes_to_qbittorrent_even_for_an_archive_url(self):
        sab, qbt, ia, clients = _clients()

        chosen = get_client_for_provider(clients, PROVIDER_MAP, "torznab", ARCHIVE_URL)

        assert chosen is qbt
        assert chosen is not ia
        assert chosen is not sab

    def test_missing_qbittorrent_falls_back_to_the_default_client(self):
        sab = _Client()

        assert get_client_for_provider({"default": sab}, PROVIDER_MAP, "torznab") is sab

    def test_archive_org_url_selects_the_internet_archive_client(self):
        sab, _, ia, clients = _clients()

        chosen = get_client_for_provider(clients, PROVIDER_MAP, "rss", ARCHIVE_URL)

        assert chosen is ia
        assert chosen is not sab

    def test_ia_scheme_selects_the_internet_archive_client(self):
        _, _, ia, clients = _clients()

        assert get_client_for_provider(clients, PROVIDER_MAP, "rss", "ia:test-magazine") is ia

    def test_archive_org_without_an_ia_client_stays_on_the_default(self):
        sab = _Client()

        chosen = get_client_for_provider({"default": sab}, PROVIDER_MAP, "rss", ARCHIVE_URL)

        assert chosen is sab

    def test_unknown_provider_uses_the_default_client(self):
        sab, qbt, _, clients = _clients()

        assert get_client_for_provider(clients, PROVIDER_MAP, "unknown", NZB_URL) is sab
        assert get_client_for_provider(clients, PROVIDER_MAP, "newsnab") is sab
        assert qbt is not sab

    def test_internet_archive_provider_does_not_need_a_url(self):
        sab, _, ia, clients = _clients()

        assert get_client_for_provider(clients, PROVIDER_MAP, "internet_archive") is ia
        assert ia is not sab

    def test_a_missing_default_client_raises_key_error(self):
        _, qbt, _, _ = _clients()

        with pytest.raises(KeyError):
            get_client_for_provider({"qbittorrent": qbt}, PROVIDER_MAP, "newsnab")

    def test_queue_coordinator_uses_the_same_client_routing(self):
        sab, qbt, ia, clients = _clients()
        coordinator = _queue({"default": sab, "qbittorrent": qbt, "internet_archive": ia}, QueueProcessor(sab))

        assert coordinator._get_client_for_provider("torznab") is qbt
        assert coordinator._get_client_for_provider("rss", ARCHIVE_URL) is ia
        assert coordinator._get_client_for_provider("rss", NZB_URL) is sab

    def test_active_count_includes_only_pending_and_downloading(self, session):
        tracking = _tracking(session)
        counted = {
            DownloadSubmission.StatusEnum.PENDING,
            DownloadSubmission.StatusEnum.DOWNLOADING,
        }
        ignored = {
            DownloadSubmission.StatusEnum.QUEUED,
            DownloadSubmission.StatusEnum.COMPLETED,
            DownloadSubmission.StatusEnum.FAILED,
            DownloadSubmission.StatusEnum.SKIPPED,
        }
        for status in counted | ignored:
            _row(session, tracking, title=status.value, status=status, job_id=status.value)

        sab = _Client()
        queue = _queue({"default": sab}, QueueProcessor(sab))
        submission = _submission({"default": sab})

        assert get_active_download_count(session) == 2
        assert queue._get_active_download_count(session) == 2
        assert submission._get_active_download_count(session) == 2

    def test_tracking_category_beats_the_default(self, session):
        tracking = _tracking(session, download_category="newsstand")

        assert get_download_category(tracking.id, session, "magazines") == "newsstand"

    def test_blank_tracking_category_uses_the_default(self, session):
        tracking = _tracking(session, download_category="")

        assert get_download_category(tracking.id, session, "magazines") == "magazines"

    def test_unknown_tracking_uses_the_default(self, session):
        assert get_download_category(99999, session, "magazines") == "magazines"

    def test_no_configured_category_returns_none(self, session):
        tracking = _tracking(session)

        assert get_download_category(tracking.id, session, None) is None
        assert get_download_category(99999, session, None) is None


# --------------------------------------------------------------------------
# Queue coordinator
# --------------------------------------------------------------------------


class TestQueueCoordinator:
    def test_process_queue_submits_in_age_order_and_marks_the_issue_pending(self, test_db, session):
        tracking = _tracking(session, download_category="newsstand")
        earlier = _row(
            session,
            tracking,
            title="Earlier issue",
            url="http://example.com/earlier.nzb",
            status=DownloadSubmission.StatusEnum.QUEUED,
            job_id=None,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        later = _row(
            session,
            tracking,
            title="Later issue",
            url="http://example.com/later.nzb",
            status=DownloadSubmission.StatusEnum.QUEUED,
            job_id=None,
            created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        linked = _issue(
            session,
            tracking,
            title="Earlier issue",
            status=DownloadStatus.QUEUED,
            submission_id=earlier.id,
            fuzzy_group="group-earlier",
        )
        _issue(
            session,
            tracking,
            title="Later issue",
            status=DownloadStatus.DISCOVERED,
            fuzzy_group="group-later",
        )
        sab = _Client()
        processor = QueueProcessor(sab, max_downloads=5)
        coordinator = _queue({"default": sab}, processor, max_downloads=5)

        result = coordinator.process_queue(session, submission_coordinator=None)

        assert result["submitted"] == 2
        assert result["errors"] == []
        assert [call["title"] for call in sab.submits] == ["Earlier issue", "Later issue"]
        assert sab.submits[0]["category"] == "newsstand"
        assert sab.submits[0]["url"] == "http://example.com/earlier.nzb"
        assert not coordinator._slot_lock.locked()

        fresh = test_db[1]()
        try:
            stored_issue = fresh.get(DiscoveredIssue, linked.id)
            stored_earlier = fresh.get(DownloadSubmission, earlier.id)
            stored_later = fresh.get(DownloadSubmission, later.id)
            unlinked = fresh.query(DiscoveredIssue).filter_by(fuzzy_match_group="group-later").one()
            assert stored_issue.download_status == DownloadStatus.PENDING
            assert stored_issue.current_submission_id == earlier.id
            assert stored_earlier.status == DownloadSubmission.StatusEnum.PENDING
            assert stored_earlier.job_id == "job-1"
            assert stored_later.status == DownloadSubmission.StatusEnum.PENDING
            assert unlinked.download_status == DownloadStatus.DISCOVERED
        finally:
            fresh.close()

    def test_process_queue_at_capacity_leaves_the_queued_issue_alone(self, session):
        tracking = _tracking(session)
        _row(session, tracking, title="Busy", status=DownloadSubmission.StatusEnum.DOWNLOADING)
        queued = _row(
            session,
            tracking,
            title="Waiting",
            status=DownloadSubmission.StatusEnum.QUEUED,
            job_id=None,
        )
        issue = _issue(
            session,
            tracking,
            title="Waiting",
            status=DownloadStatus.QUEUED,
            submission_id=queued.id,
            fuzzy_group="group-waiting",
        )
        sab = _Client()
        coordinator = _queue({"default": sab}, QueueProcessor(sab, max_downloads=1), max_downloads=1)

        result = coordinator.process_queue(session, submission_coordinator=None)

        assert result["submitted"] == 0
        assert result["checked"] == 0
        assert result.get("promoted_submissions", []) == []
        assert sab.submits == []
        session.refresh(issue)
        session.refresh(queued)
        assert issue.download_status == DownloadStatus.QUEUED
        assert queued.status == DownloadSubmission.StatusEnum.QUEUED
        assert queued.job_id is None

    def test_a_failed_sync_commit_is_swallowed_and_the_issue_stays_queued(self, test_db):
        session = test_db[1]()
        gated = None
        try:
            tracking = _tracking(session, download_category="newsstand")
            queued = _row(
                session,
                tracking,
                title="Promoted issue",
                status=DownloadSubmission.StatusEnum.QUEUED,
                job_id=None,
            )
            issue = _issue(
                session,
                tracking,
                title="Promoted issue",
                status=DownloadStatus.QUEUED,
                submission_id=queued.id,
                fuzzy_group="group-promoted",
            )
            sab = _Client()
            processor = QueueProcessor(sab, max_downloads=5)
            coordinator = _queue({"default": sab}, processor, max_downloads=5)
            # The processor commits the promotion first. The coordinator's sync commit is next.
            gated = _FailingCommit(test_db[1](), fail_on=2)

            result = coordinator.process_queue(gated, submission_coordinator=None)

            assert result["submitted"] == 1
            assert result["errors"] == []
            assert gated.commits == 2
            inner = gated._session
            assert inner.get(DiscoveredIssue, issue.id).download_status == DownloadStatus.PENDING
            inner.rollback()
            inner.expire_all()
            assert inner.get(DiscoveredIssue, issue.id).download_status == DownloadStatus.QUEUED
            stored = inner.get(DownloadSubmission, queued.id)
            assert stored.status == DownloadSubmission.StatusEnum.PENDING
            assert stored.job_id == "job-1"
            assert sab.submits[0]["category"] == "newsstand"
        finally:
            session.close()
            if gated is not None:
                gated._session.close()

    def test_batch_submits_only_the_open_slots_in_priority_order(self, session):
        tracking = _tracking(session)
        first = _issue(
            session,
            tracking,
            title="Test Magazine January 2024",
            priority=80,
            fuzzy_group="group-jan",
            url="http://example.com/jan.nzb",
        )
        second = _issue(
            session,
            tracking,
            title="Test Magazine February 2024",
            priority=10,
            fuzzy_group="group-feb",
            url="http://example.com/feb.nzb",
        )
        sab, _, _, clients = _clients()
        discovery = IssueDiscoveryService()
        submission = _submission(clients, discovery=discovery, max_downloads=1)
        coordinator = _queue(clients, QueueProcessor(sab, max_downloads=1), max_downloads=1)

        submitted = coordinator.submit_discovered_batch(session, discovery, submission)

        assert submitted == 1
        assert len(sab.submits) == 1
        assert sab.submits[0]["title"] == first.title
        assert sab.submits[0]["url"] == first.latest_url
        session.refresh(first)
        session.refresh(second)
        assert first.download_status == DownloadStatus.PENDING
        assert first.current_submission_id is not None
        assert second.download_status == DownloadStatus.WANTED
        assert session.query(DownloadSubmission).count() == 1

    def test_batch_returns_zero_when_no_slot_is_open(self, session):
        tracking = _tracking(session)
        _row(session, tracking, status=DownloadSubmission.StatusEnum.PENDING)
        issue = _issue(session, tracking)
        sab, _, _, clients = _clients()
        discovery = IssueDiscoveryService()
        submission = _submission(clients, discovery=discovery, max_downloads=1)
        coordinator = _queue(clients, QueueProcessor(sab), max_downloads=1)

        assert coordinator.submit_discovered_batch(session, discovery, submission) == 0

        assert sab.submits == []
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.WANTED
        assert session.query(DownloadSubmission).count() == 1

    def test_batch_returns_zero_when_nothing_is_wanted(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, status=DownloadStatus.DISCOVERED)
        sab, _, _, clients = _clients()
        discovery = IssueDiscoveryService()
        submission = _submission(clients, discovery=discovery)
        coordinator = _queue(clients, QueueProcessor(sab))

        assert coordinator.submit_discovered_batch(session, discovery, submission) == 0

        assert sab.submits == []
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.DISCOVERED

    def test_batch_continues_after_a_submission_error(self, session):
        tracking = _tracking(session)
        broken = _issue(
            session,
            tracking,
            title="Test Magazine January 2024",
            priority=80,
            fuzzy_group="group-jan",
            url="http://example.com/jan.nzb",
        )
        healthy = _issue(
            session,
            tracking,
            title="Test Magazine February 2024",
            priority=10,
            fuzzy_group="group-feb",
            url="http://example.com/feb.nzb",
        )
        sab, _, _, clients = _clients()
        discovery = IssueDiscoveryService()
        submission = _submission(clients, discovery=discovery, max_downloads=5)
        original = submission.submit_from_discovered_issue

        def flaky(issue_id, db):
            row = db.get(DiscoveredIssue, issue_id)
            if row.id == broken.id:
                raise RuntimeError("submit exploded")
            return original(issue_id, db)

        submission.submit_from_discovered_issue = flaky
        coordinator = _queue(clients, QueueProcessor(sab), max_downloads=5)

        submitted = coordinator.submit_discovered_batch(session, discovery, submission)

        assert submitted == 1
        assert len(sab.submits) == 1
        assert sab.submits[0]["title"] == healthy.title
        session.refresh(broken)
        session.refresh(healthy)
        assert broken.download_status == DownloadStatus.WANTED
        assert healthy.download_status == DownloadStatus.PENDING
        assert healthy.current_submission_id is not None


# --------------------------------------------------------------------------
# Status coordinator
# --------------------------------------------------------------------------


class TestStatusCoordinator:
    def _pending(self, session, client_name="SABnzbd", **kwargs):
        tracking = _tracking(session, download_category=kwargs.pop("download_category", None))
        row = _row(
            session,
            tracking,
            status=kwargs.pop("status", DownloadSubmission.StatusEnum.PENDING),
            client_name=client_name,
            job_id=kwargs.pop("job_id", "job-1"),
            **kwargs,
        )
        return tracking, row

    def test_downloading_status_is_stored_and_keeps_the_existing_path(self, session):
        _, row = self._pending(
            session,
            extra_status="Rate limited, waiting 30s",
            file_path="/keep.pdf",
            attempt_count=2,
        )
        sab = _Client(status={"status": "downloading", "progress": 40})
        updated = _status({"default": sab}).update_submission_status("job-1", session)

        assert updated.id == row.id
        assert updated.status == DownloadSubmission.StatusEnum.DOWNLOADING
        assert updated.file_path == "/keep.pdf"
        assert updated.extra_status is None
        assert updated.attempt_count == 2
        assert sab.status_calls == ["job-1"]

    def test_completed_status_stores_the_file_path(self, session):
        _, row = self._pending(session, extra_status="Rate limited, waiting 30s", attempt_count=1)
        sab = _Client(status={"status": "completed", "progress": 100, "file_path": "/library/issue.pdf"})

        updated = _status({"default": sab}).update_submission_status(row.job_id, session)

        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED
        assert updated.file_path == "/library/issue.pdf"
        assert updated.extra_status is None
        assert updated.attempt_count == 1
        assert updated.last_error is None

    def test_failed_status_increments_attempts_and_leaves_the_issue_unchanged(self, session):
        tracking, row = self._pending(session, attempt_count=1, job_id="job-failed")
        issue = _issue(
            session,
            tracking,
            status=DownloadStatus.DOWNLOADING,
            submission_id=row.id,
            max_retries=1,
            attempt_count=0,
        )
        sab = _Client(status={"status": "failed", "error": "corrupt nzb"})

        updated = _status({"default": sab}).update_submission_status("job-failed", session)

        assert updated.status == DownloadSubmission.StatusEnum.FAILED
        assert updated.attempt_count == 2
        assert updated.last_error == "corrupt nzb"
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.DOWNLOADING
        assert issue.attempt_count == 0
        assert issue.last_error is None

    def test_error_status_without_a_message_uses_unknown_error(self, session):
        self._pending(session, job_id="job-error")
        sab = _Client(status={"status": "error"})

        updated = _status({"default": sab}).update_submission_status("job-error", session)

        assert updated.status == DownloadSubmission.StatusEnum.FAILED
        assert updated.last_error == "Unknown error"
        assert updated.attempt_count == 1

    def test_unknown_client_status_becomes_a_failure(self, session):
        self._pending(session, job_id="job-missing")
        sab = _Client(status={"status": "unknown"})

        updated = _status({"default": sab}).update_submission_status("job-missing", session)

        assert updated.status == DownloadSubmission.StatusEnum.FAILED
        assert updated.last_error == "Job no longer exists in download client"
        assert updated.attempt_count == 1

    def test_an_unrecognized_client_status_is_stored_as_pending(self, session):
        self._pending(session, status=DownloadSubmission.StatusEnum.DOWNLOADING, job_id="job-paused")
        sab = _Client(status={"status": "paused", "progress": 0})

        updated = _status({"default": sab}).update_submission_status("job-paused", session)

        assert updated.status == DownloadSubmission.StatusEnum.PENDING
        assert updated.attempt_count == 0
        assert updated.last_error is None

    def test_rate_limit_keeps_the_submission_pending_without_counting_an_attempt(self, session):
        _, row = self._pending(
            session,
            status=DownloadSubmission.StatusEnum.DOWNLOADING,
            attempt_count=3,
            job_id="job-limited",
        )
        sab = _Client(status={"status": "downloading", "rate_limited": True, "wait_time": 30})

        updated = _status({"default": sab}).update_submission_status(row.job_id, session)

        assert updated.status == DownloadSubmission.StatusEnum.PENDING
        assert updated.attempt_count == 3
        assert updated.last_error == "Rate limited, waiting 30s"
        assert updated.extra_status == "Rate limited, waiting 30s"

    def test_explicit_rate_limit_message_is_stored(self, session):
        self._pending(session, job_id="job-slow")
        sab = _Client(status={"rate_limited": True, "wait_time": 5, "message": "slow down", "status": "pending"})

        updated = _status({"default": sab}).update_submission_status("job-slow", session)

        assert updated.status == DownloadSubmission.StatusEnum.PENDING
        assert updated.last_error == "slow down"
        assert updated.extra_status == "slow down"

    def test_missing_job_returns_none(self, session):
        sab = _Client()

        assert _status({"default": sab}).update_submission_status("missing-job", session) is None
        assert sab.status_calls == []

    def test_client_status_error_marks_the_submission_failed(self, session):
        self._pending(session, attempt_count=2, job_id="job-boom")
        sab = _Client(status_error=RuntimeError("client exploded"))

        updated = _status({"default": sab}).update_submission_status("job-boom", session)

        assert updated.status == DownloadSubmission.StatusEnum.FAILED
        assert updated.attempt_count == 3
        assert updated.last_error == "client exploded"

    def test_status_is_read_from_the_named_client(self, session):
        self._pending(session, client_name="qBittorrent", job_id="torrent-job")
        sab = _Client(name="SABnzbd", status={"status": "failed", "error": "wrong client"})
        qbt = _Client(
            name="qBittorrent",
            client_type="qbittorrent",
            status={"status": "completed", "file_path": "/torrents/issue.pdf"},
        )

        updated = _status({"default": sab, "qbittorrent": qbt}).update_submission_status("torrent-job", session)

        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED
        assert updated.file_path == "/torrents/issue.pdf"
        assert qbt.status_calls == ["torrent-job"]
        assert sab.status_calls == []

    def test_unknown_client_name_falls_back_to_the_default_client(self, session):
        self._pending(session, client_name="retired-client", job_id="job-1")
        sab = _Client(status={"status": "downloading", "progress": 5})
        other = _Client(name="qBittorrent", client_type="qbittorrent", status={"status": "failed", "error": "nope"})

        updated = _status({"default": sab, "qbittorrent": other}).update_submission_status("job-1", session)

        assert updated.status == DownloadSubmission.StatusEnum.DOWNLOADING
        assert sab.status_calls == ["job-1"]
        assert other.status_calls == []

    def test_retry_uses_cached_nzb_for_sabnzbd_and_skips_it_for_qbittorrent(self, session):
        tracking = _tracking(session, download_category="newsstand")
        sab_row = _row(
            session,
            tracking,
            title="Usenet issue",
            url="http://indexer.example/nzb/1",
            status=DownloadSubmission.StatusEnum.FAILED,
            client_name="SABnzbd",
            job_id="old-sab",
            attempt_count=1,
            last_error="checksum",
        )
        qbt_row = _row(
            session,
            tracking,
            title="Torrent issue",
            url="http://indexer.example/download/1",
            status=DownloadSubmission.StatusEnum.SKIPPED,
            client_name="qBittorrent",
            job_id="old-torrent",
            attempt_count=0,
            last_error="skipped",
        )
        cache = _Cache("<nzb>cached</nzb>")
        sab = _Client(name="SABnzbd", client_type="sabnzbd", job_id="sab-job")
        qbt = _Client(name="qBittorrent", client_type="qbittorrent", job_id="qbt-job")
        coordinator = _status({"default": sab, "qbittorrent": qbt}, cache=cache, default_category="magazines")

        sab_result = coordinator.retry_submission(sab_row.id, session)
        qbt_result = coordinator.retry_submission(qbt_row.id, session)

        assert sab_result["success"] is True
        assert sab_result["job_id"] == "content-sab-job"
        assert sab_result["message"] == "Retry submitted (attempt 2)"
        assert cache.urls == ["http://indexer.example/nzb/1"]
        assert sab.submits == []
        assert sab.contents[0]["content"] == "<nzb>cached</nzb>"
        assert sab.contents[0]["category"] == "newsstand"
        assert sab.contents[0]["title"] == "Usenet issue"
        session.refresh(sab_row)
        assert sab_row.status == DownloadSubmission.StatusEnum.PENDING
        assert sab_row.job_id == "content-sab-job"
        assert sab_row.last_error is None
        assert sab_row.attempt_count == 1

        assert qbt_result["success"] is True
        assert qbt_result["job_id"] == "qbt-job"
        assert qbt_result["message"] == "Retry submitted (attempt 1)"
        assert qbt.contents == []
        assert qbt.submits[0]["url"] == "http://indexer.example/download/1"
        assert qbt.submits[0]["category"] == "newsstand"
        assert cache.urls == ["http://indexer.example/nzb/1"]
        session.refresh(qbt_row)
        assert qbt_row.status == DownloadSubmission.StatusEnum.PENDING
        assert qbt_row.attempt_count == 0

    def test_retry_uses_the_default_category_when_tracking_has_none(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            status=DownloadSubmission.StatusEnum.FAILED,
            attempt_count=0,
            job_id="old",
            last_error="nope",
        )
        sab = _Client(job_id="fresh-job")

        result = _status({"default": sab}, default_category="magazines").retry_submission(row.id, session)

        assert result == {
            "success": True,
            "message": "Retry submitted (attempt 1)",
            "job_id": "fresh-job",
        }
        assert sab.submits[0]["category"] == "magazines"
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.PENDING
        assert row.last_error is None

    def test_retry_of_a_missing_submission_returns_failure(self, session):
        result = _status({"default": _Client()}).retry_submission(99999, session)

        assert result == {"success": False, "message": "Submission not found"}

    def test_retry_rejects_a_submission_that_is_not_failed_or_skipped(self, session):
        _, row = self._pending(session, status=DownloadSubmission.StatusEnum.DOWNLOADING, job_id="live")
        sab = _Client()

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result == {"success": False, "message": "Cannot retry submission with status: downloading"}
        assert sab.submits == []
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.DOWNLOADING
        assert row.job_id == "live"

    def test_linked_issue_retry_budget_is_used_instead_of_the_default(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            status=DownloadSubmission.StatusEnum.FAILED,
            attempt_count=MAX_DOWNLOAD_RETRIES,
            job_id="old",
            fuzzy_group="different-group",
        )
        _issue(
            session,
            tracking,
            submission_id=row.id,
            max_retries=4,
            fuzzy_group="issue-group",
        )
        sab = _Client(job_id="allowed")

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result["success"] is True
        assert result["job_id"] == "allowed"
        assert sab.submits

    def test_fuzzy_group_issue_can_reject_a_retry(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            status=DownloadSubmission.StatusEnum.FAILED,
            attempt_count=1,
            job_id="old",
            fuzzy_group="same-group",
        )
        _issue(session, tracking, max_retries=0, fuzzy_group="same-group", attempt_count=1)
        sab = _Client()

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result == {
            "success": False,
            "message": "Cannot retry: file has failed 1 times (max 1)",
        }
        assert sab.submits == []
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.FAILED
        assert row.job_id == "old"

    @pytest.mark.parametrize(
        ("attempts", "allowed"),
        [(MAX_DOWNLOAD_RETRIES_IA, True), (MAX_DOWNLOAD_RETRIES_IA + 1, False)],
    )
    def test_archive_org_url_uses_the_internet_archive_retry_budget(self, session, attempts, allowed):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            url=ARCHIVE_URL,
            status=DownloadSubmission.StatusEnum.FAILED,
            attempt_count=attempts,
            job_id="old-ia",
        )
        sab = _Client(job_id="retried-ia")

        result = _status({"default": sab}).retry_submission(row.id, session)

        session.refresh(row)
        if allowed:
            assert result["success"] is True
            assert result["job_id"] == "retried-ia"
            assert row.status == DownloadSubmission.StatusEnum.PENDING
            assert len(sab.submits) == 1
        else:
            assert result == {
                "success": False,
                "message": f"Cannot retry: file has failed {attempts} times (max {MAX_DOWNLOAD_RETRIES_IA + 1})",
            }
            assert sab.submits == []
            assert row.status == DownloadSubmission.StatusEnum.FAILED
            assert row.job_id == "old-ia"

    def test_default_retry_budget_rejects_the_attempt_past_the_limit(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            url="http://example.com/file.nzb",
            status=DownloadSubmission.StatusEnum.FAILED,
            attempt_count=MAX_DOWNLOAD_RETRIES + 1,
            job_id="old",
        )
        sab = _Client()

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result["success"] is False
        assert result["message"] == (
            f"Cannot retry: file has failed {MAX_DOWNLOAD_RETRIES + 1} times (max {MAX_DOWNLOAD_RETRIES + 1})"
        )
        assert sab.submits == []

    def test_retry_reports_a_client_rejection(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            status=DownloadSubmission.StatusEnum.FAILED,
            client_name="SABnzbd",
            job_id="old-job",
            attempt_count=0,
            last_error="checksum",
        )
        sab = _Client(submit_job_id=_NONE)

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result == {"success": False, "message": "Download client SABnzbd rejected submission"}
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.FAILED
        assert row.job_id == "old-job"
        assert row.last_error == "checksum"
        assert len(sab.submits) == 1

    def test_retry_reports_a_client_exception(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            status=DownloadSubmission.StatusEnum.FAILED,
            job_id="old-job",
            attempt_count=0,
        )
        sab = _Client(submit_error=RuntimeError("down"))

        result = _status({"default": sab}).retry_submission(row.id, session)

        assert result == {"success": False, "message": "Error: down"}
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.FAILED
        assert row.job_id == "old-job"

    def test_retry_reports_an_indexer_rejection(self, session):
        tracking = _tracking(session)
        row = _row(
            session,
            tracking,
            url="http://indexer.example/nzb/rejected",
            status=DownloadSubmission.StatusEnum.FAILED,
            client_name="SABnzbd",
            job_id="old-job",
            attempt_count=0,
        )
        cache = _Cache(error=NzbContentRejected("not an nzb"))
        sab = _Client(name="SABnzbd", client_type="sabnzbd")

        result = _status({"default": sab}, cache=cache).retry_submission(row.id, session)

        assert result == {"success": False, "message": "Error: not an nzb"}
        assert cache.urls == [row.source_url]
        assert sab.submits == []
        assert sab.contents == []
        session.refresh(row)
        assert row.status == DownloadSubmission.StatusEnum.FAILED
        assert row.job_id == "old-job"
        assert row.attempt_count == 0

    def test_issue_status_stub_does_not_change_the_issue(self, session):
        tracking = _tracking(session)
        row = _row(session, tracking)
        issue = _issue(session, tracking, status=DownloadStatus.DOWNLOADING, submission_id=row.id)
        coordinator = _status({"default": _Client()})

        coordinator._update_discovered_issue_status(row, session)

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.DOWNLOADING
        assert issue.current_submission_id == row.id


# --------------------------------------------------------------------------
# Submission coordinator
# --------------------------------------------------------------------------


class TestSubmissionCoordinator:
    def test_submit_from_discovered_issue_uses_the_tracking_category(self, session):
        tracking = _tracking(session, download_category="newsstand")
        issue = _issue(session, tracking, url=NZB_URL, provider="newsnab")
        sab, _, _, clients = _clients()

        result = _submission(clients, default_category="magazines").submit_from_discovered_issue(issue.id, session)

        assert result is not None
        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert result.job_id == "job-1"
        assert result.client_name == "SABnzbd"
        assert result.attempt_count == 1
        assert result.result_title == issue.title
        assert result.source_url == NZB_URL
        assert sab.submits == [{"url": NZB_URL, "title": issue.title, "category": "newsstand"}]
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == result.id
        assert issue.submission_ids == [result.id]
        assert issue.attempt_count == 1
        assert issue.last_attempt is not None

    def test_submit_uses_the_default_category_when_tracking_has_none(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking)
        sab, _, _, clients = _clients()

        result = _submission(clients, default_category="magazines").submit_from_discovered_issue(issue.id, session)

        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert sab.submits[0]["category"] == "magazines"

    def test_submit_omits_the_category_when_none_is_configured(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking)
        sab, _, _, clients = _clients()

        _submission(clients, default_category=None).submit_from_discovered_issue(issue.id, session)

        assert sab.submits[0]["category"] is None

    def test_sabnzbd_submit_uses_cached_nzb_content(self, session):
        tracking = _tracking(session, download_category="newsstand")
        issue = _issue(session, tracking, provider="newsnab", url="http://indexer.example/nzb/9")
        cache = _Cache("<nzb>cached</nzb>")
        sab, _, _, clients = _clients()

        result = _submission(clients, cache=cache).submit_from_discovered_issue(issue.id, session)

        assert result.job_id == "content-job-1"
        assert result.client_name == "SABnzbd"
        assert cache.urls == ["http://indexer.example/nzb/9"]
        assert sab.submits == []
        assert sab.contents == [{"content": "<nzb>cached</nzb>", "title": issue.title, "category": "newsstand"}]

    def test_qbittorrent_submit_skips_the_nzb_cache(self, session):
        tracking = _tracking(session, download_category="newsstand")
        url = "http://indexer.example/download/9"
        issue = _issue(session, tracking, provider="torznab", url=url, title="Test Magazine January 2024")
        cache = _Cache("<nzb>cached</nzb>")
        sab, qbt, _, clients = _clients()

        result = _submission(clients, cache=cache).submit_from_discovered_issue(issue.id, session)

        assert result.job_id == "torrent-job"
        assert result.client_name == "qBittorrent"
        assert cache.urls == []
        assert qbt.contents == []
        assert sab.submits == []
        assert sab.contents == []
        assert qbt.submits == [{"url": url, "title": issue.title, "category": "newsstand"}]

    def test_cache_lookup_error_falls_back_to_the_url(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, url="http://indexer.example/nzb/fallback")
        cache = _Cache(error=RuntimeError("cache down"))
        sab, _, _, clients = _clients()

        result = _submission(clients, cache=cache).submit_from_discovered_issue(issue.id, session)

        assert result.job_id == "job-1"
        assert cache.urls == [issue.latest_url]
        assert sab.contents == []
        assert sab.submits[0]["url"] == issue.latest_url

    def test_indexer_rejection_is_stored_as_a_counted_failure(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, url="http://indexer.example/nzb/bad", attempt_count=0)
        cache = _Cache(error=NzbContentRejected("not an nzb"))
        sab, _, _, clients = _clients()

        result = _submission(clients, cache=cache).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert sab.submits == []
        assert sab.contents == []
        assert session.query(DownloadSubmission).count() == 0
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.attempt_count == 1
        assert issue.last_error == "not an nzb"
        assert issue.last_attempt is not None

    def test_archive_org_url_under_capacity_uses_the_internet_archive_client(self, session):
        tracking = _tracking(session, download_category="newsstand")
        issue = _issue(session, tracking, provider="rss", url=ARCHIVE_URL)
        sab, _, ia, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result.client_name == "Internet Archive"
        assert result.job_id == "ia-job"
        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert ia.submits == [{"url": ARCHIVE_URL, "title": issue.title, "category": "newsstand"}]
        assert sab.submits == []

    def test_archive_org_issue_queued_at_the_limit_is_later_sent_to_the_default_client(self, session):
        tracking = _tracking(session, download_category="newsstand")
        _row(session, tracking, title="Filler", status=DownloadSubmission.StatusEnum.PENDING)
        issue = _issue(session, tracking, provider="rss", url=ARCHIVE_URL, title="Test Magazine March 2024")
        sab, _, ia, clients = _clients()
        submission = _submission(clients, max_downloads=1)

        queued = submission.submit_from_discovered_issue(issue.id, session)

        assert queued.status == DownloadSubmission.StatusEnum.QUEUED
        assert queued.client_name == "SABnzbd"
        assert queued.job_id is None
        assert sab.submits == []
        assert ia.submits == []
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.QUEUED

        filler = session.query(DownloadSubmission).filter_by(result_title="Filler").one()
        filler.status = DownloadSubmission.StatusEnum.COMPLETED
        session.commit()
        processor = QueueProcessor(sab, max_downloads=1, download_clients=clients)
        result = _queue(clients, processor, max_downloads=1).process_queue(session, submission)

        assert result["submitted"] == 1
        assert ia.submits == []
        assert sab.submits == [{"url": ARCHIVE_URL, "title": issue.title, "category": "newsstand"}]
        session.refresh(queued)
        session.refresh(issue)
        assert queued.status == DownloadSubmission.StatusEnum.PENDING
        assert queued.job_id == "job-1"
        assert queued.client_name == "SABnzbd"
        assert issue.download_status == DownloadStatus.PENDING

    def test_blacklisted_extension_is_permanently_failed_without_contacting_the_client(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, title="Test Magazine January 2024.mp4", attempt_count=0)
        sab, _, _, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert sab.submits == []
        assert session.query(DownloadSubmission).count() == 0
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.last_error == "Blacklisted file extension"
        assert issue.attempt_count == 0

    def test_uppercase_blacklisted_extension_is_rejected(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, title="Test Magazine January 2024.MP4")
        sab, _, _, clients = _clients()

        assert _submission(clients).submit_from_discovered_issue(issue.id, session) is None

        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert sab.submits == []

    def test_missing_url_fails_the_issue(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, url=None, attempt_count=2)
        sab, _, _, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert sab.submits == []
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "Missing URL"
        assert issue.attempt_count == 2

    def test_permanently_failed_issue_is_left_unchanged(self, session):
        tracking = _tracking(session)
        issue = _issue(
            session,
            tracking,
            status=DownloadStatus.PERMANENTLY_FAILED,
            attempt_count=3,
            last_error="bad file",
        )
        sab, _, _, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert sab.submits == []
        assert session.query(DownloadSubmission).count() == 0
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PERMANENTLY_FAILED
        assert issue.last_error == "bad file"
        assert issue.attempt_count == 3

    def test_client_rejection_fails_the_issue_without_a_submission_row(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, attempt_count=0)
        sab = _Client(name="SABnzbd", client_type="sabnzbd", submit_job_id=_NONE)

        result = _submission({"default": sab}).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert len(sab.submits) == 1
        assert session.query(DownloadSubmission).count() == 0
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "Client SABnzbd rejected submission"
        assert issue.attempt_count == 1
        assert issue.current_submission_id is None

    def test_submit_exception_is_truncated_and_counted(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, attempt_count=0)
        sab = _Client(submit_error=RuntimeError("E" * 600))

        result = _submission({"default": sab}).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert session.query(DownloadSubmission).count() == 0
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "E" * MAX_ERROR_LENGTH
        assert len(issue.last_error) == MAX_ERROR_LENGTH
        assert issue.attempt_count == 1

    def test_missing_discovered_issue_returns_none(self, session):
        sab, _, _, clients = _clients()

        assert _submission(clients).submit_from_discovered_issue(99999, session) is None
        assert sab.submits == []

    @pytest.mark.parametrize(
        "status",
        [DownloadStatus.PENDING, DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING],
    )
    def test_active_issue_with_a_submission_is_not_submitted_again(self, session, status):
        tracking = _tracking(session)
        existing = _row(session, tracking, status=DownloadSubmission.StatusEnum.PENDING, job_id="already")
        issue = _issue(
            session,
            tracking,
            status=status,
            submission_id=existing.id,
            attempt_count=2,
        )
        sab, _, _, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result is None
        assert sab.submits == []
        session.refresh(issue)
        assert issue.download_status == status
        assert issue.current_submission_id == existing.id
        assert issue.attempt_count == 2
        assert session.query(DownloadSubmission).count() == 1

    def test_pending_issue_with_no_submission_id_is_submitted_again(self, session):
        tracking = _tracking(session)
        issue = _issue(session, tracking, status=DownloadStatus.PENDING, submission_id=None, attempt_count=4)
        sab, _, _, clients = _clients()

        result = _submission(clients).submit_from_discovered_issue(issue.id, session)

        assert result is not None
        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert len(sab.submits) == 1
        session.refresh(issue)
        assert issue.current_submission_id == result.id
        assert issue.attempt_count == 5
        assert session.query(DownloadSubmission).count() == 1

    def test_issue_is_queued_when_the_active_limit_is_reached(self, session):
        tracking = _tracking(session)
        _row(session, tracking, title="Active", status=DownloadSubmission.StatusEnum.DOWNLOADING)
        issue = _issue(session, tracking, provider="torznab", url="http://indexer.example/download/queued")
        sab, qbt, _, clients = _clients()

        result = _submission(clients, max_downloads=1).submit_from_discovered_issue(issue.id, session)

        assert result.status == DownloadSubmission.StatusEnum.QUEUED
        assert result.job_id is None
        assert result.client_name == "qBittorrent"
        assert result.attempt_count == 0
        assert sab.submits == []
        assert qbt.submits == []
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.QUEUED
        assert issue.current_submission_id == result.id
        assert issue.submission_ids == [result.id]

    def test_a_queued_submission_does_not_consume_a_download_slot(self, session):
        tracking = _tracking(session)
        _row(session, tracking, title="Only queued", status=DownloadSubmission.StatusEnum.QUEUED, job_id=None)
        issue = _issue(session, tracking, fuzzy_group="group-new", title="Test Magazine February 2024")
        sab, _, _, clients = _clients()

        result = _submission(clients, max_downloads=1).submit_from_discovered_issue(issue.id, session)

        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert result.job_id == "job-1"
        assert len(sab.submits) == 1
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PENDING

    def test_download_single_issue_submits_the_recorded_issue(self, session):
        tracking = _tracking(session, download_category="newsstand")
        sab, _, _, clients = _clients()
        search_result = _result()

        result = _submission(clients).download_single_issue(tracking.id, search_result, session)

        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert result.job_id == "job-1"
        assert result.client_name == "SABnzbd"
        assert sab.submits == [{"url": NZB_URL, "title": "Test Magazine January 2024", "category": "newsstand"}]
        issue = session.query(DiscoveredIssue).one()
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == result.id
        assert issue.download_priority == MANUAL_DOWNLOAD_PRIORITY
        assert issue.submission_ids == [result.id]
        assert issue.latest_url == NZB_URL

    def test_download_single_issue_does_not_submit_an_in_flight_issue_again(self, session):
        tracking = _tracking(session)
        sab, _, _, clients = _clients()
        coordinator = _submission(clients)
        search_result = _result()
        first = coordinator.download_single_issue(tracking.id, search_result, session)

        second = coordinator.download_single_issue(tracking.id, search_result, session)

        assert first is not None
        assert second is None
        assert len(sab.submits) == 1
        assert session.query(DownloadSubmission).count() == 1
        issue = session.query(DiscoveredIssue).one()
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == first.id

    def test_download_single_issue_resubmits_a_completed_issue(self, session):
        tracking = _tracking(session)
        sab, _, _, clients = _clients()
        coordinator = _submission(clients)
        search_result = _result()
        first = coordinator.download_single_issue(tracking.id, search_result, session)
        issue = session.query(DiscoveredIssue).one()
        issue.download_status = DownloadStatus.COMPLETED
        issue.attempt_count = 4
        issue.last_error = "old failure"
        issue.download_priority = 5
        session.commit()

        second = coordinator.download_single_issue(tracking.id, search_result, session)

        assert second is not None
        assert second.id != first.id
        assert second.status == DownloadSubmission.StatusEnum.PENDING
        assert len(sab.submits) == 2
        session.refresh(issue)
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == second.id
        assert issue.attempt_count == 1
        assert issue.last_error is None
        assert issue.download_priority == MANUAL_DOWNLOAD_PRIORITY
        assert session.query(DownloadSubmission).count() == 2

    def test_download_single_issue_falls_back_when_the_title_does_not_match(self, session):
        tracking = _tracking(session, download_category="newsstand")
        sab, _, _, clients = _clients()
        search_result = _result(title="Gardening World January 2024", url="http://example.com/garden.nzb")

        result = _submission(clients).download_single_issue(tracking.id, search_result, session)

        assert result is not None
        assert result.status == DownloadSubmission.StatusEnum.PENDING
        assert result.result_title == "Gardening World January 2024"
        assert result.source_url == "http://example.com/garden.nzb"
        assert sab.submits[0]["title"] == "Gardening World January 2024"
        assert sab.submits[0]["category"] == "newsstand"
        issue = session.query(DiscoveredIssue).one()
        assert issue.title == "Gardening World January 2024"
        assert issue.download_status == DownloadStatus.PENDING
        assert issue.current_submission_id == result.id
        assert issue.user_id == 1

    def test_manual_fallback_records_a_failed_submission_when_the_client_returns_none(self, session):
        tracking = _tracking(session)
        sab = _Client(submit_job_id=_NONE)
        search_result = _result(title="Gardening World January 2024", url="http://example.com/garden.nzb")

        result = _submission({"default": sab}).download_single_issue(tracking.id, search_result, session)

        assert result is None
        stored = session.query(DownloadSubmission).one()
        assert stored.status == DownloadSubmission.StatusEnum.FAILED
        assert stored.last_error == "Client SABnzbd rejected submission"
        assert stored.attempt_count == 1
        assert stored.result_title == "Gardening World January 2024"
        assert session.query(DiscoveredIssue).count() == 0

    def test_queue_issue_for_batch_always_queues_and_skips_an_active_issue(self, session):
        tracking = _tracking(session)
        sab, _, _, clients = _clients()
        coordinator = _submission(clients, max_downloads=10)
        search_result = _result()

        queued = coordinator.queue_issue_for_batch(tracking.id, search_result, session)
        duplicate = coordinator.queue_issue_for_batch(tracking.id, search_result, session)
        rejected = coordinator.queue_issue_for_batch(
            tracking.id,
            _result(title="Gardening World January 2024"),
            session,
        )

        assert queued.status == DownloadSubmission.StatusEnum.QUEUED
        assert queued.job_id is None
        assert queued.client_name == "SABnzbd"
        assert duplicate is None
        assert rejected is None
        assert sab.submits == []
        assert session.query(DownloadSubmission).count() == 1
        issue = session.query(DiscoveredIssue).one()
        assert issue.download_status == DownloadStatus.QUEUED
        assert issue.current_submission_id == queued.id
        assert issue.download_priority == MANUAL_DOWNLOAD_PRIORITY

    def test_download_all_submits_one_issue_and_queues_the_rest(self, session):
        tracking = _tracking(session, download_category="newsstand")
        sab, _, _, clients = _clients()
        search = _Search(
            [
                _result(title="Test Magazine January 2024", url="http://example.com/jan.nzb"),
                _result(
                    title="Test Magazine February 2024",
                    url="http://example.com/feb.nzb",
                    pubdate="2024-02-15T10:30:00Z",
                ),
            ]
        )
        coordinator = _submission(clients, max_downloads=1, search=search)

        results = coordinator.download_all_periodical_issues(tracking.id, session)

        assert search.titles == ["Test Magazine"]
        assert results["submitted"] == 1
        assert results["queued"] == 1
        assert results["skipped"] == 0
        assert results["failed"] == 0
        assert len(sab.submits) == 1
        assert sab.submits[0]["category"] == "newsstand"
        statuses = {row.status for row in session.query(DownloadSubmission).all()}
        assert statuses == {
            DownloadSubmission.StatusEnum.PENDING,
            DownloadSubmission.StatusEnum.QUEUED,
        }
        issues = session.query(DiscoveredIssue).all()
        assert {issue.download_status for issue in issues} == {DownloadStatus.PENDING, DownloadStatus.QUEUED}

    def test_download_all_reports_a_missing_tracking_record(self, session):
        sab, _, _, clients = _clients()

        result = _submission(clients).download_all_periodical_issues(99999, session)

        assert result == {"submitted": 0, "skipped": 0, "failed": 0}
        assert sab.submits == []

    def test_download_all_without_a_search_service_submits_nothing(self, session):
        tracking = _tracking(session)
        sab, _, _, clients = _clients()

        result = _submission(clients, search=None).download_all_periodical_issues(tracking.id, session)

        assert result == {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}
        assert sab.submits == []
        assert session.query(DiscoveredIssue).count() == 0
        assert session.query(DownloadSubmission).count() == 0

    def test_download_all_counts_a_client_rejection_as_skipped(self, session):
        tracking = _tracking(session)
        sab = _Client(submit_job_id=_NONE)
        search = _Search([_result()])

        results = _submission({"default": sab}, search=search).download_all_periodical_issues(tracking.id, session)

        assert results == {"submitted": 0, "skipped": 1, "failed": 0, "errors": []}
        assert len(sab.submits) == 1
        assert session.query(DownloadSubmission).count() == 0
        issue = session.query(DiscoveredIssue).one()
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "Client SABnzbd rejected submission"
        assert issue.attempt_count == 1
