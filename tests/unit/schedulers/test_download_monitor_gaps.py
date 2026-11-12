"""Gap tests for DownloadMonitor paths the folder-scan suite does not exercise.

Covers pending client updates, discovered-issue sync on client failure, orphaned
completed submissions, newline-separated Internet Archive collections, import-retry
exhaustion, and the first file-not-found miss.
"""

from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.constants.app import MAX_IMPORT_RETRIES, ORPHANED_SUBMISSION_THRESHOLD_HOURS
from core.interfaces import DownloadClient
from core.parsers import utc_now
from models.database import (
    Base,
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
    PeriodicalTracking,
)
from schedulers.download_monitor import DownloadMonitor
from services import DownloadManager

Status = DownloadSubmission.StatusEnum


@pytest.fixture
def test_db():
    """File-backed SQLite so the monitor and the test share one database."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def session(test_db):
    _, session_factory = test_db
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def downloads_dir(tmp_path):
    path = tmp_path / "downloads"
    path.mkdir()
    return path


@pytest.fixture
def download_client():
    client = Mock(spec=DownloadClient)
    client.name = "TestClient"
    client.delete.return_value = True
    return client


@pytest.fixture
def download_manager(download_client):
    return DownloadManager(
        search_providers=[],
        download_client=download_client,
        fuzzy_threshold=80,
        max_downloads=10,
    )


@pytest.fixture
def file_importer():
    importer = Mock()
    importer.import_supported_files.return_value = {"periodical_id": 1}
    importer.process_downloads.return_value = {"success": True, "data": {"imported": 0, "failed": 0}}
    return importer


@pytest.fixture
def monitor(test_db, download_manager, file_importer, downloads_dir):
    _, session_factory = test_db
    return DownloadMonitor(
        download_manager=download_manager,
        file_importer=file_importer,
        session_factory=session_factory,
        downloads_dir=downloads_dir,
    )


def _tracking(session, *, title, olid, delete_on_completion=True):
    tracking = PeriodicalTracking(
        olid=olid,
        title=title,
        language="English",
        user_id=1,
        delete_from_client_on_completion=delete_on_completion,
    )
    session.add(tracking)
    session.commit()
    return tracking


def _submission(session, tracking, **overrides):
    fields = {
        "user_id": 1,
        "tracking_id": tracking.id,
        "source_url": "http://example.com/issue.nzb",
        "result_title": tracking.title,
        "status": Status.PENDING,
        "client_name": "TestClient",
        "attempt_count": 0,
        "job_id": "job-1",
    }
    fields.update(overrides)
    submission = DownloadSubmission(**fields)
    session.add(submission)
    session.commit()
    return submission


def _issue(session, tracking, submission, download_status=DownloadStatus.PENDING):
    issue = DiscoveredIssue(
        user_id=1,
        tracking_id=tracking.id,
        title=tracking.title,
        normalized_title=tracking.title.lower(),
        fuzzy_match_group=f"gap-{tracking.id}",
        download_status=download_status,
        current_submission_id=submission.id,
        latest_url="http://example.com/issue.nzb",
        latest_provider="newsnab",
        max_retries=1,
        attempt_count=0,
    )
    session.add(issue)
    session.commit()
    return issue


def _pdf(downloads_dir, name):
    path = downloads_dir / name
    path.write_bytes(b"%PDF-1.4\ncontent")
    return path


class TestPendingStatusUpdates:
    """Client polling for submissions that are still pending or downloading."""

    def test_no_pending_downloads_reports_zero_failures(self, session, monitor, download_client):
        failed = monitor._update_pending_downloads(session)

        assert failed == 0
        download_client.delete.assert_not_called()

    def test_pending_without_job_id_fails_and_syncs_issue_without_delete(self, session, monitor, download_client):
        tracking = _tracking(session, title="Stuck Weekly", olid="OL-stuck")
        submission = _submission(session, tracking, job_id=None, status=Status.PENDING)
        issue = _issue(session, tracking, submission, DownloadStatus.PENDING)

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert failed == 1
        assert submission.status == Status.FAILED
        assert submission.last_error == "No job ID - download client never accepted this submission"
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.current_submission_id is None
        assert issue.last_error == submission.last_error
        download_client.delete.assert_not_called()

    def test_pending_status_advances_to_downloading_without_delete(
        self, session, monitor, download_manager, download_client
    ):
        tracking = _tracking(session, title="Moving Weekly", olid="OL-moving")
        submission = _submission(session, tracking, status=Status.PENDING, job_id="job-moving")
        issue = _issue(session, tracking, submission, DownloadStatus.PENDING)

        def _advance(job_id, db_session):
            assert job_id == "job-moving"
            submission.status = Status.DOWNLOADING
            db_session.commit()
            return submission

        download_manager.update_submission_status = Mock(side_effect=_advance)

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert failed == 0
        assert submission.status == Status.DOWNLOADING
        assert issue.download_status == DownloadStatus.PENDING
        download_client.delete.assert_not_called()

    def test_unknown_client_job_with_file_on_disk_is_marked_completed(
        self, session, monitor, download_manager, download_client, downloads_dir
    ):
        tracking = _tracking(session, title="Mapped Weekly", olid="OL-mapped")
        ready = _pdf(downloads_dir, "Mapped Weekly.pdf")
        submission = _submission(
            session,
            tracking,
            status=Status.DOWNLOADING,
            job_id="job-mapped",
            file_path=str(ready),
        )

        def _unknown(job_id, db_session):
            submission.status = Status.PENDING
            submission.file_path = str(ready)
            db_session.commit()
            return submission

        download_manager.update_submission_status = Mock(side_effect=_unknown)

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        assert failed == 0
        assert submission.status == Status.COMPLETED
        download_client.delete.assert_not_called()

    def test_status_update_error_leaves_submission_pending(self, session, monitor, download_manager, download_client):
        tracking = _tracking(session, title="Flaky Weekly", olid="OL-flaky")
        submission = _submission(session, tracking, status=Status.PENDING, job_id="job-flaky")
        issue = _issue(session, tracking, submission, DownloadStatus.PENDING)
        download_manager.update_submission_status = Mock(side_effect=RuntimeError("client timeout"))

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert failed == 0
        assert submission.status == Status.PENDING
        assert issue.download_status == DownloadStatus.PENDING
        download_client.delete.assert_not_called()


class TestFailedClientStatusSync:
    """A client failure must land on the linked discovered issue."""

    def test_failed_client_status_syncs_issue_and_deletes_job(
        self, session, monitor, download_manager, download_client
    ):
        tracking = _tracking(session, title="Broken Weekly", olid="OL-broken", delete_on_completion=True)
        submission = _submission(session, tracking, status=Status.DOWNLOADING, job_id="job-broken")
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        def _fail(job_id, db_session):
            submission.status = Status.FAILED
            submission.last_error = "Unpack failed"
            db_session.commit()
            return submission

        download_manager.update_submission_status = Mock(side_effect=_fail)

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert failed == 1
        assert submission.status == Status.FAILED
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.attempt_count == 1
        assert issue.current_submission_id is None
        assert issue.last_error == "Unpack failed"
        download_client.delete.assert_called_once_with("job-broken")

    def test_failed_client_status_syncs_issue_and_keeps_job_when_history_is_kept(
        self, session, monitor, download_manager, download_client
    ):
        tracking = _tracking(session, title="Kept Weekly", olid="OL-kept", delete_on_completion=False)
        submission = _submission(session, tracking, status=Status.DOWNLOADING, job_id="job-kept")
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        def _fail(job_id, db_session):
            submission.status = Status.FAILED
            submission.last_error = "CRC error"
            db_session.commit()
            return submission

        download_manager.update_submission_status = Mock(side_effect=_fail)

        failed = monitor._update_pending_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert failed == 1
        assert submission.status == Status.FAILED
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "CRC error"
        download_client.delete.assert_not_called()


class TestOrphanedCompletedSubmissions:
    """Completed rows whose client never recorded a storage path."""

    def test_old_orphan_is_skipped_and_not_deleted(self, session, monitor, download_manager, download_client):
        tracking = _tracking(session, title="Ancient Weekly", olid="OL-ancient")
        aged = utc_now() - timedelta(hours=ORPHANED_SUBMISSION_THRESHOLD_HOURS + 5)
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="job-ancient",
            file_path=None,
            updated_at=aged,
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)
        session.refresh(submission)
        assert (utc_now() - submission.updated_at).total_seconds() / 3600 > ORPHANED_SUBMISSION_THRESHOLD_HOURS
        download_manager.get_completed_downloads = Mock(return_value=[submission])

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 0
        assert submission.status == Status.SKIPPED
        assert submission.last_error.startswith("Orphaned:")
        assert issue.download_status == DownloadStatus.DOWNLOADING
        download_client.delete.assert_not_called()

    def test_recent_orphan_without_client_path_fails_and_syncs_issue(
        self, session, monitor, download_manager, download_client
    ):
        tracking = _tracking(session, title="Recent Weekly", olid="OL-recent")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="job-recent",
            file_path=None,
            attempt_count=0,
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        def _still_empty(job_id, db_session):
            submission.file_path = None
            db_session.commit()
            return submission

        download_manager.get_completed_downloads = Mock(return_value=[submission])
        download_manager.update_submission_status = Mock(side_effect=_still_empty)

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 0
        assert submission.status == Status.FAILED
        assert submission.attempt_count == 1
        assert "no storage location" in submission.last_error
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == submission.last_error
        download_client.delete.assert_not_called()

    def test_recent_orphan_without_job_id_stays_completed(self, session, monitor, download_manager, download_client):
        tracking = _tracking(session, title="Jobless Weekly", olid="OL-jobless")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id=None,
            file_path=None,
        )
        download_manager.get_completed_downloads = Mock(return_value=[submission])
        download_manager.update_submission_status = Mock()

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        assert processed == 0
        assert submission.status == Status.COMPLETED
        assert submission.last_error is None
        download_manager.update_submission_status.assert_not_called()
        download_client.delete.assert_not_called()

    def test_orphan_recovery_error_marks_failed_without_delete(
        self, session, monitor, download_manager, download_client
    ):
        tracking = _tracking(session, title="Unreachable Weekly", olid="OL-unreachable")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="job-unreachable",
            file_path=None,
            attempt_count=0,
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)
        download_manager.get_completed_downloads = Mock(return_value=[submission])
        download_manager.update_submission_status = Mock(side_effect=RuntimeError("client down"))

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 0
        assert submission.status == Status.FAILED
        assert submission.attempt_count == 1
        assert submission.last_error == "Recovery attempt failed: client down"
        assert issue.download_status == DownloadStatus.FAILED
        download_client.delete.assert_not_called()

    def test_recovered_orphan_imports_and_deletes_the_client_job(
        self, session, monitor, download_manager, download_client, file_importer, downloads_dir
    ):
        tracking = _tracking(session, title="Recovered Weekly", olid="OL-recovered", delete_on_completion=True)
        ready = _pdf(downloads_dir, "Recovered Weekly.pdf")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="job-recovered",
            file_path=None,
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        def _recover(job_id, db_session):
            submission.file_path = str(ready)
            db_session.commit()
            return submission

        download_manager.get_completed_downloads = Mock(return_value=[submission])
        download_manager.update_submission_status = Mock(side_effect=_recover)
        file_importer.import_supported_files.return_value = {"periodical_id": 42}

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 1
        assert submission.status == Status.COMPLETED
        assert submission.file_path is None
        assert issue.download_status == DownloadStatus.COMPLETED
        assert file_importer.import_supported_files.call_args.args[0] == ready
        download_client.delete.assert_called_once_with("job-recovered")


class TestInternetArchiveNewlineCollections:
    """Extracted IA archives store one path per line, including titles that contain commas."""

    def _attach_ia_client(self, download_manager):
        client = Mock()
        client.name = "Internet Archive"
        client.type = "internet_archive"
        client.delete.return_value = True
        download_manager.download_clients["internet_archive"] = client
        return client

    def test_newline_paths_import_each_file_and_delete_once(
        self, session, monitor, download_manager, download_client, file_importer, downloads_dir
    ):
        ia_client = self._attach_ia_client(download_manager)
        tracking = _tracking(session, title="Archive Bundle", olid="OL-bundle", delete_on_completion=True)
        first = _pdf(downloads_dir, "Science, Nature.pdf")
        second = _pdf(downloads_dir, "Other Issue.pdf")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="ia-bundle",
            client_name="Internet Archive",
            file_path=f"{first}\n{second}",
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)
        file_importer.import_supported_files.return_value = {"periodical_id": 9}

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        imported = [call.args[0].name for call in file_importer.import_supported_files.call_args_list]
        assert processed == 2
        assert imported == ["Science, Nature.pdf", "Other Issue.pdf"]
        assert submission.status == Status.COMPLETED
        assert submission.file_path is None
        assert issue.download_status == DownloadStatus.COMPLETED
        ia_client.delete.assert_called_once_with("ia-bundle")
        download_client.delete.assert_not_called()

    def test_newline_collection_with_no_files_fails_without_delete(
        self, session, monitor, download_manager, download_client, file_importer, downloads_dir
    ):
        ia_client = self._attach_ia_client(download_manager)
        tracking = _tracking(session, title="Empty Bundle", olid="OL-empty-bundle")
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="ia-empty",
            client_name="Internet Archive",
            file_path=f"{downloads_dir / 'Science, Nature.pdf'}\n{downloads_dir / 'Other Issue.pdf'}",
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 0
        assert submission.status == Status.FAILED
        assert submission.last_error == "All collection files failed to import"
        assert issue.download_status == DownloadStatus.FAILED
        assert issue.last_error == "All collection files failed to import"
        file_importer.import_supported_files.assert_not_called()
        ia_client.delete.assert_not_called()
        download_client.delete.assert_not_called()


class TestImportRetryExhaustion:
    """A missing file still counts toward the retry cap, and the last miss removes the client job."""

    def test_missing_file_before_the_cap_does_not_delete(self, session, monitor, download_client, downloads_dir):
        tracking = _tracking(session, title="Retry Weekly", olid="OL-retry-gap")
        submission = _submission(
            session,
            tracking,
            status=Status.FAILED,
            job_id="job-retry",
            file_path=str(downloads_dir / "gone.pdf"),
            last_error="Import/processing failed",
            attempt_count=0,
        )

        retried = monitor._retry_failed_imports(session)

        session.refresh(submission)
        assert retried == 0
        assert submission.status == Status.FAILED
        assert submission.attempt_count == 1
        download_client.delete.assert_not_called()

    def test_exhaustion_when_the_file_is_gone_deletes_the_client_job(
        self, session, monitor, download_client, downloads_dir
    ):
        tracking = _tracking(session, title="Exhausted Weekly", olid="OL-exhaust-gap", delete_on_completion=True)
        submission = _submission(
            session,
            tracking,
            status=Status.FAILED,
            job_id="job-exhaust",
            file_path=str(downloads_dir / "gone.pdf"),
            last_error="Import/processing failed",
            attempt_count=MAX_IMPORT_RETRIES - 1,
        )

        retried = monitor._retry_failed_imports(session)

        session.refresh(submission)
        assert retried == 0
        assert submission.status == Status.FAILED
        assert submission.attempt_count == MAX_IMPORT_RETRIES
        download_client.delete.assert_called_once_with("job-exhaust")


class TestFirstFileNotFoundMiss:
    """The first time a completed file is not in the downloads directory, the job stays completed."""

    def test_first_miss_stays_completed_and_does_not_delete(self, session, monitor, download_client, downloads_dir):
        tracking = _tracking(session, title="Unmapped Weekly", olid="OL-unmapped", delete_on_completion=True)
        submission = _submission(
            session,
            tracking,
            status=Status.COMPLETED,
            job_id="job-unmapped",
            file_path=str(downloads_dir / "Unmapped Weekly.pdf"),
            last_error=None,
            attempt_count=0,
        )
        issue = _issue(session, tracking, submission, DownloadStatus.DOWNLOADING)

        processed = monitor._process_completed_downloads(session)

        session.refresh(submission)
        session.refresh(issue)
        assert processed == 0
        assert submission.status == Status.COMPLETED
        assert submission.attempt_count == 0
        assert submission.last_error.startswith("File not found in downloads directory:")
        assert "Unmapped Weekly.pdf" in submission.last_error
        assert issue.download_status == DownloadStatus.DOWNLOADING
        download_client.delete.assert_not_called()
