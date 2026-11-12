"""Indexer error pages must not be cached or handed to the download client."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from clients.qbittorrent import QBittorrentClient
from core.parsers.date import utc_now
from models.cache import NzbCache
from models.database import DownloadStatus, PeriodicalTracking
from services.cache.provider_cache import NzbCacheService, NzbContentRejected
from services.download.nzb_submit import submit_with_nzb_content
from services.download.queue_processor import release_linked_issue
from services.download_manager import DownloadManager

ERROR_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<error code="101" description="This API endpoint has been retired. '
    'Update your indexer URL from nzb.su to nzb.life."/>'
)
DOWNLOAD_URL = "http://prowlarr.local/1/download?apikey=secret&link=xyz"


class _ContentClient:
    """Has its own submit_content, so the cache path runs instead of URL submit."""

    def __init__(self):
        self.name = "SABnzbd"
        self.submitted_url = None
        self.submitted_content = None

    def submit(self, url, title=None, category=None):
        self.submitted_url = url
        return "url-job"

    def submit_content(self, content, title=None, category=None):
        self.submitted_content = content
        return "content-job"


def _response(body):
    response = MagicMock()
    response.text = body
    response.raise_for_status = MagicMock()
    return response


class TestNzbContentRejected:
    def test_error_xml_is_not_cached(self, tmp_path):
        service = NzbCacheService(cache_db_path=str(tmp_path / "cache.db"))

        with patch("services.cache.provider_cache.httpx.get", return_value=_response(ERROR_XML)):
            with pytest.raises(NzbContentRejected, match="retired"):
                service.get_nzb_content(DOWNLOAD_URL)

        session = service._session_factory()
        try:
            assert session.query(NzbCache).count() == 0
        finally:
            session.close()

    def test_cached_error_page_is_deleted_and_not_refetched(self, tmp_path):
        service = NzbCacheService(cache_db_path=str(tmp_path / "cache.db"))
        session = service._session_factory()
        session.add(NzbCache(download_url=DOWNLOAD_URL, nzb_content=ERROR_XML, cached_at=utc_now()))
        session.commit()
        session.close()

        with patch("services.cache.provider_cache.httpx.get") as mock_get:
            with pytest.raises(NzbContentRejected, match="retired"):
                service.get_nzb_content(DOWNLOAD_URL)

        mock_get.assert_not_called()
        session = service._session_factory()
        try:
            assert session.query(NzbCache).count() == 0
        finally:
            session.close()

    def test_http_status_error_is_rejected(self, tmp_path):
        service = NzbCacheService(cache_db_path=str(tmp_path / "cache.db"))
        response = _response("")
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        with patch("services.cache.provider_cache.httpx.get", return_value=response):
            with pytest.raises(NzbContentRejected, match="HTTP 404"):
                service.get_nzb_content(DOWNLOAD_URL)

    def test_submit_does_not_fall_back_to_the_url(self):
        client = _ContentClient()
        cache = Mock()
        cache.get_nzb_content.side_effect = NzbContentRejected("retired")

        with pytest.raises(NzbContentRejected, match="retired"):
            submit_with_nzb_content(
                client,
                DOWNLOAD_URL,
                "Issue",
                nzb_cache_service=cache,
            )

        assert client.submitted_url is None
        assert client.submitted_content is None


class TestTorrentGrabsSkipTheNzbCache:
    """qBittorrent implements submit_content, but a .torrent URL is not an NZB."""

    def test_qbittorrent_torrent_url_is_submitted_by_url(self, test_db):
        torrent_url = "http://prowlarr.local/1/download/issue.torrent?apikey=secret"
        client = QBittorrentClient(
            {
                "name": "qBittorrent",
                "type": "qbittorrent",
                "api_url": "http://localhost:8090",
                "username": "admin",
                "password": "secret",
            }
        )
        cache = Mock()
        cache.get_nzb_content.side_effect = NzbContentRejected("response is not NZB XML")
        _, session_factory = test_db
        session = session_factory()
        tracking = PeriodicalTracking(olid="weekly", title="City Paper", track_all_editions=True, user_id=1)
        session.add(tracking)
        session.commit()
        manager = DownloadManager(
            search_providers=[],
            download_client=client,
            download_clients={"qbittorrent": client},
            nzb_cache_service=cache,
        )

        with patch.object(client, "submit", return_value="abc123") as submit:
            submission = manager._submit_to_client(
                tracking.id,
                {"title": "City Paper 2024-01-07", "url": torrent_url, "provider": "torznab"},
                session,
            )

        assert submission is not None
        assert submission.job_id == "abc123"
        assert submission.client_name == "qBittorrent"
        cache.get_nzb_content.assert_not_called()
        submit.assert_called_once()
        assert submit.call_args.kwargs["url"] == torrent_url
        session.close()


class TestReleaseLinkedIssue:
    def test_queued_issue_fails_without_counting_an_attempt(self):
        issue = SimpleNamespace(
            download_status=DownloadStatus.QUEUED,
            last_error=None,
            current_submission_id=7,
            attempt_count=0,
        )
        session = Mock()
        session.query.return_value.filter.return_value.first.return_value = issue

        release_linked_issue(session, SimpleNamespace(id=7), "Indexer did not return an NZB: retired")

        assert issue.download_status == DownloadStatus.FAILED
        assert issue.attempt_count == 0
        assert issue.current_submission_id is None
        assert "retired" in issue.last_error

    def test_completed_issue_is_left_alone(self):
        issue = SimpleNamespace(
            download_status=DownloadStatus.COMPLETED,
            last_error=None,
            current_submission_id=7,
            attempt_count=1,
        )
        session = Mock()
        session.query.return_value.filter.return_value.first.return_value = issue

        release_linked_issue(session, SimpleNamespace(id=7), "Indexer did not return an NZB: retired")

        assert issue.download_status == DownloadStatus.COMPLETED
        assert issue.current_submission_id == 7
        assert issue.attempt_count == 1
