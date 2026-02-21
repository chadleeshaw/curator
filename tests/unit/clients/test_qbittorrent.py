#!/usr/bin/env python3
"""
Test suite for qBittorrent Download Client
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

# Path setup handled by conftest.py

from clients.qbittorrent import QBittorrentClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    return {
        "name": "qBittorrent",
        "type": "qbittorrent",
        "api_url": "http://localhost:8090",
        "username": "admin",
        "password": "adminadmin",
        "default_category": "curator",
    }


@pytest.fixture
def client(config):
    return QBittorrentClient(config)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_initialization(config):
    """Test qBittorrent client initializes with correct values from config."""
    c = QBittorrentClient(config)

    assert c.api_url == "http://localhost:8090"
    assert c.username == "admin"
    assert c.password == "adminadmin"
    assert c.default_category == "curator"
    assert c._authenticated is False


def test_initialization_defaults():
    """Test qBittorrent client falls back to sensible defaults."""
    c = QBittorrentClient({})

    assert c.api_url == "http://localhost:8080"
    assert c.username == "admin"
    assert c.password == ""
    assert c.default_category == "curator"


def test_initialization_strips_trailing_slash():
    """Test that trailing slash is stripped from api_url."""
    c = QBittorrentClient({"api_url": "http://localhost:8090/"})
    assert c.api_url == "http://localhost:8090"


# ---------------------------------------------------------------------------
# Authentication (_login)
# ---------------------------------------------------------------------------


def test_login_success(client):
    """Test successful login stores session cookie and marks authenticated."""
    with patch.object(client._session, "post") as mock_post:
        mock_response = Mock()
        mock_response.text = "Ok."
        mock_post.return_value = mock_response

        result = client._login()

        assert result is True
        assert client._authenticated is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "username" in call_args[1]["data"]
        assert "password" in call_args[1]["data"]


def test_login_failure_wrong_credentials(client):
    """Test login failure returns False and resets authenticated flag."""
    with patch.object(client._session, "post") as mock_post:
        mock_response = Mock()
        mock_response.text = "Fails."
        mock_post.return_value = mock_response

        result = client._login()

        assert result is False
        assert client._authenticated is False


def test_login_network_error(client):
    """Test login handles network errors gracefully."""
    with patch.object(client._session, "post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        result = client._login()

        assert result is False
        assert client._authenticated is False


# ---------------------------------------------------------------------------
# _request — auth flow and re-auth on 403
# ---------------------------------------------------------------------------


def test_request_triggers_login_when_not_authenticated(client):
    """Test that _request calls _login before making the request."""
    with patch.object(client, "_login", return_value=True) as mock_login:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch.object(client._session, "get", return_value=mock_response):
            client._request("get", "/app/version")

        mock_login.assert_called_once()


def test_request_reauth_on_403(client):
    """Test that _request re-authenticates once on a 403 response."""
    client._authenticated = True

    first_response = Mock()
    first_response.status_code = 403

    second_response = Mock()
    second_response.status_code = 200
    second_response.raise_for_status = Mock()

    with patch.object(client._session, "get", side_effect=[first_response, second_response]):
        with patch.object(client, "_login", return_value=True) as mock_login:
            result = client._request("get", "/app/version")

    assert result is second_response
    mock_login.assert_called_once()


def test_request_returns_none_when_reauth_fails(client):
    """Test that _request returns None if re-auth on 403 fails."""
    client._authenticated = True

    first_response = Mock()
    first_response.status_code = 403

    with patch.object(client._session, "get", return_value=first_response):
        with patch.object(client, "_login", return_value=False):
            result = client._request("get", "/app/version")

    assert result is None


def test_request_returns_none_on_connection_error(client):
    """Test that _request returns None on ConnectionError."""
    client._authenticated = True

    with patch.object(client._session, "get", side_effect=requests.exceptions.ConnectionError("down")):
        result = client._request("get", "/app/version")

    assert result is None


def test_request_returns_none_on_timeout(client):
    """Test that _request returns None on Timeout."""
    client._authenticated = True

    with patch.object(client._session, "get", side_effect=requests.exceptions.Timeout):
        result = client._request("get", "/app/version")

    assert result is None


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


def test_submit_magnet_link_success(client):
    """Test submitting a magnet link returns the extracted hash."""
    magnet = "magnet:?xt=urn:btih:abc123def456&dn=Test+Magazine"

    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response):
        job_id = client.submit(magnet, title="Test Magazine")

    assert job_id == "abc123def456"


def test_submit_torrent_url_success(client):
    """Test submitting a .torrent URL returns None (hash unavailable)."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response):
        job_id = client.submit("https://example.com/file.torrent", title="Test")

    assert job_id is None


def test_submit_uses_default_category(client):
    """Test that submit uses default_category when no category is specified."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit("magnet:?xt=urn:btih:aaa111", title="Mag")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["category"] == "curator"


def test_submit_uses_explicit_category(client):
    """Test that submit uses the provided category over default."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit("magnet:?xt=urn:btih:bbb222", title="Mag", category="magazines")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["category"] == "magazines"


def test_submit_returns_none_on_failure(client):
    """Test that submit returns None when qBittorrent rejects the request."""
    mock_response = Mock()
    mock_response.text = "Fails."

    with patch.object(client, "_request", return_value=mock_response):
        job_id = client.submit("magnet:?xt=urn:btih:ccc333")

    assert job_id is None


def test_submit_returns_none_when_request_fails(client):
    """Test that submit returns None when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        job_id = client.submit("magnet:?xt=urn:btih:ddd444")

    assert job_id is None


# ---------------------------------------------------------------------------
# submit_content
# ---------------------------------------------------------------------------


def test_submit_content_success(client):
    """Test uploading a .torrent file returns None (hash unavailable after upload)."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response):
        result = client.submit_content(b"torrent-data", title="My Torrent")

    # Hash is not returned for file uploads
    assert result is None


def test_submit_content_failure(client):
    """Test that submit_content returns None on API failure."""
    mock_response = Mock()
    mock_response.text = "Fails."

    with patch.object(client, "_request", return_value=mock_response):
        result = client.submit_content(b"bad-data", title="Bad Torrent")

    assert result is None


def test_submit_content_request_failure(client):
    """Test that submit_content returns None when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        result = client.submit_content(b"data", title="Test")

    assert result is None


def test_submit_content_uses_category(client):
    """Test that submit_content passes category to _request."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"data", title="Test", category="books")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["category"] == "books"


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status_downloading(client):
    """Test get_status returns downloading status with correct progress."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "downloading", "progress": 0.45, "save_path": "/downloads/mag"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "downloading"
    assert status["progress"] == 45


def test_get_status_completed(client):
    """Test get_status returns completed status and file_path for seeding torrent."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "uploading", "progress": 1.0, "save_path": "/downloads/mag"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "completed"
    assert status["progress"] == 100
    assert status["file_path"] == "/downloads/mag"


def test_get_status_pending(client):
    """Test get_status returns pending for queued torrents."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "queuedDL", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "pending"
    assert status["progress"] == 0


def test_get_status_failed(client):
    """Test get_status returns failed for error state."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "error", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "failed"


def test_get_status_unknown_when_empty(client):
    """Test get_status returns unknown when torrent is not found."""
    mock_response = Mock()
    mock_response.json.return_value = []

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("notfound")

    assert status["status"] == "unknown"
    assert status["progress"] == 0


def test_get_status_error_when_request_fails(client):
    """Test get_status returns error when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        status = client.get_status("abc123")

    assert status["status"] == "error"
    assert status["progress"] == 0


def test_get_status_no_file_path_when_not_completed(client):
    """Test that file_path is not included when torrent is still downloading."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "downloading", "progress": 0.5, "save_path": "/downloads/mag"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert "file_path" not in status


# ---------------------------------------------------------------------------
# get_completed_downloads
# ---------------------------------------------------------------------------


def test_get_completed_downloads_returns_seeding_torrents(client):
    """Test that get_completed_downloads returns torrents in completed states."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "hash": "aaa111",
            "state": "uploading",
            "save_path": "/dl/mag1",
            "name": "Mag 1",
        },
        {
            "hash": "bbb222",
            "state": "stalledUP",
            "save_path": "/dl/mag2",
            "name": "Mag 2",
        },
        {
            "hash": "ccc333",
            "state": "downloading",
            "save_path": "/dl/mag3",
            "name": "Mag 3",
        },
    ]

    with patch.object(client, "_request", return_value=mock_response):
        downloads = client.get_completed_downloads()

    assert len(downloads) == 2
    job_ids = [d["job_id"] for d in downloads]
    assert "aaa111" in job_ids
    assert "bbb222" in job_ids
    assert "ccc333" not in job_ids


def test_get_completed_downloads_includes_title_and_path(client):
    """Test that completed downloads include title and file_path fields."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "hash": "abc123",
            "state": "uploading",
            "save_path": "/downloads/mags",
            "name": "My Magazine",
        },
    ]

    with patch.object(client, "_request", return_value=mock_response):
        downloads = client.get_completed_downloads()

    assert downloads[0]["job_id"] == "abc123"
    assert downloads[0]["file_path"] == "/downloads/mags"
    assert downloads[0]["title"] == "My Magazine"


def test_get_completed_downloads_returns_empty_on_request_failure(client):
    """Test that get_completed_downloads returns [] when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        downloads = client.get_completed_downloads()

    assert downloads == []


def test_get_completed_downloads_filters_by_category(client):
    """Test that get_completed_downloads includes category filter in request."""
    mock_response = Mock()
    mock_response.json.return_value = []

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.get_completed_downloads()

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["params"]["category"] == "curator"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_success(client):
    """Test that delete returns True on a successful response."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response):
        result = client.delete("abc123")

    assert result is True


def test_delete_with_files(client):
    """Test that delete passes deleteFiles=true when requested."""
    mock_response = Mock()

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.delete("abc123", delete_files=True)

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["deleteFiles"] == "true"


def test_delete_without_files(client):
    """Test that delete passes deleteFiles=false by default."""
    mock_response = Mock()

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.delete("abc123")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["deleteFiles"] == "false"


def test_delete_returns_false_when_request_fails(client):
    """Test that delete returns False when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        result = client.delete("abc123")

    assert result is False


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


def test_test_connection_success(client):
    """Test that test_connection returns success with version string."""
    mock_response = Mock()
    mock_response.text = "v5.0.4"

    with patch.object(client, "_request", return_value=mock_response):
        result = client.test_connection()

    assert result["success"] is True
    assert "v5.0.4" in result["message"]
    assert result["version"] == "v5.0.4"


def test_test_connection_failure_no_response(client):
    """Test that test_connection returns failure when _request returns None."""
    with patch.object(client, "_request", return_value=None):
        result = client.test_connection()

    assert result["success"] is False
    assert "check URL" in result["message"].lower() or "credentials" in result["message"].lower()


def test_test_connection_timeout(client):
    """Test that network errors are absorbed by _request and surfaced as None -> failure response."""
    # _request catches Timeout/ConnectionError internally and returns None;
    # test_connection then converts that None into a failure dict.
    with patch.object(client, "_request", return_value=None):
        result = client.test_connection()

    assert result["success"] is False
    assert "check" in result["message"].lower() or "credentials" in result["message"].lower()


def test_test_connection_connection_error(client):
    """Test that unexpected exceptions in test_connection are caught and returned as failure."""
    with patch.object(client, "_request", side_effect=RuntimeError("unexpected")):
        result = client.test_connection()

    assert result["success"] is False
    assert "unexpected" in result["message"].lower() or "error" in result["message"].lower()


# ---------------------------------------------------------------------------
# _resolve_hash_from_url
# ---------------------------------------------------------------------------


def test_resolve_hash_from_magnet_link(client):
    """Test that hash is correctly extracted from a magnet link."""
    magnet = "magnet:?xt=urn:btih:ABCDEF123456&dn=Some+Title&tr=http://tracker.example.com"
    result = client._resolve_hash_from_url(magnet)
    assert result == "abcdef123456"


def test_resolve_hash_returns_none_for_torrent_url(client):
    """Test that None is returned for a .torrent file URL (no hash in URL)."""
    result = client._resolve_hash_from_url("https://example.com/files/test.torrent")
    assert result is None


def test_resolve_hash_returns_none_for_malformed_magnet(client):
    """Test that None is returned for a magnet link missing the btih parameter."""
    result = client._resolve_hash_from_url("magnet:?dn=SomeTitle&tr=http://tracker.example.com")
    assert result is None


def test_resolve_hash_from_magnet_without_query_separator(client):
    """Test that hash is extracted from a magnet URI that omits the '?' separator."""
    # Some clients emit "magnet:xt=urn:btih:<hash>" without the leading "?"
    magnet = "magnet:xt=urn:btih:deadbeef1234"
    result = client._resolve_hash_from_url(magnet)
    assert result == "deadbeef1234"


# ---------------------------------------------------------------------------
# __init__ — thread-safety attributes
# ---------------------------------------------------------------------------


def test_initialization_creates_threading_lock(config):
    """Test that __init__ creates a threading.Lock for concurrent request safety."""
    import threading

    c = QBittorrentClient(config)

    assert isinstance(c._lock, type(threading.Lock()))


def test_initialization_multiple_trailing_slashes_are_stripped(config):
    """Test that multiple trailing slashes in api_url are fully stripped."""
    c = QBittorrentClient({"api_url": "http://localhost:8090///"})

    assert c.api_url == "http://localhost:8090"


# ---------------------------------------------------------------------------
# _login — edge cases
# ---------------------------------------------------------------------------


def test_login_success_with_whitespace_around_ok(client):
    """Test that login accepts 'Ok.' with surrounding whitespace in response body."""
    with patch.object(client._session, "post") as mock_post:
        mock_response = Mock()
        mock_response.text = "  Ok.  \n"
        mock_post.return_value = mock_response

        result = client._login()

    assert result is True
    assert client._authenticated is True


def test_login_failure_unexpected_response_body(client):
    """Test that any response body other than 'Ok.' is treated as a login failure."""
    with patch.object(client._session, "post") as mock_post:
        mock_response = Mock()
        mock_response.text = "Invalid credentials"
        mock_post.return_value = mock_response

        result = client._login()

    assert result is False
    assert client._authenticated is False


# ---------------------------------------------------------------------------
# _request — additional coverage
# ---------------------------------------------------------------------------


def test_request_skips_login_when_already_authenticated(client):
    """Test that _request does not call _login when already authenticated."""
    client._authenticated = True

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    with patch.object(client, "_login") as mock_login:
        with patch.object(client._session, "get", return_value=mock_response):
            client._request("get", "/app/version")

    mock_login.assert_not_called()


def test_request_returns_none_on_http_error_from_raise_for_status(client):
    """Test that _request returns None when raise_for_status raises HTTPError."""
    client._authenticated = True

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    with patch.object(client._session, "get", return_value=mock_response):
        result = client._request("get", "/app/version")

    assert result is None


def test_request_returns_none_on_generic_exception(client):
    """Test that _request returns None when an unexpected exception is raised."""
    client._authenticated = True

    with patch.object(client._session, "get", side_effect=RuntimeError("unexpected failure")):
        result = client._request("get", "/app/version")

    assert result is None


def test_request_returns_none_when_initial_login_fails(client):
    """Test that _request returns None immediately when unauthenticated and login fails."""
    assert client._authenticated is False

    with patch.object(client, "_login", return_value=False) as mock_login:
        result = client._request("get", "/app/version")

    assert result is None
    mock_login.assert_called_once()


# ---------------------------------------------------------------------------
# submit — data payload details
# ---------------------------------------------------------------------------


def test_submit_includes_rename_when_title_provided(client):
    """Test that submit adds 'rename' to the request data when a title is given."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit("magnet:?xt=urn:btih:aaa111", title="My Magazine")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["rename"] == "My Magazine"


def test_submit_omits_rename_when_title_is_none(client):
    """Test that submit does not include 'rename' in the request data when title is None."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit("magnet:?xt=urn:btih:bbb222")

    call_kwargs = mock_req.call_args[1]
    assert "rename" not in call_kwargs["data"]


# ---------------------------------------------------------------------------
# submit_content — filename and data payload details
# ---------------------------------------------------------------------------


def test_submit_content_filename_uses_title(client):
    """Test that submit_content constructs the filename from the title."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"torrent-bytes", title="My Magazine Issue 42")

    call_kwargs = mock_req.call_args[1]
    filename, _content, _mime = call_kwargs["files"]["torrents"]
    assert filename == "My Magazine Issue 42.torrent"


def test_submit_content_filename_defaults_to_download_when_no_title(client):
    """Test that submit_content uses 'download.torrent' as filename when title is None."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"torrent-bytes")

    call_kwargs = mock_req.call_args[1]
    filename, _content, _mime = call_kwargs["files"]["torrents"]
    assert filename == "download.torrent"


def test_submit_content_includes_rename_when_title_provided(client):
    """Test that submit_content adds 'rename' to the data payload when title is given."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"torrent-bytes", title="Great Magazine")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["rename"] == "Great Magazine"


def test_submit_content_omits_rename_when_title_is_none(client):
    """Test that submit_content does not include 'rename' when title is None."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"torrent-bytes")

    call_kwargs = mock_req.call_args[1]
    assert "rename" not in call_kwargs["data"]


def test_submit_content_passes_correct_mime_type(client):
    """Test that submit_content passes the correct MIME type for the .torrent file."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"torrent-bytes", title="Some Title")

    call_kwargs = mock_req.call_args[1]
    _filename, _content, mime_type = call_kwargs["files"]["torrents"]
    assert mime_type == "application/x-bittorrent"


def test_submit_content_passes_raw_bytes_to_request(client):
    """Test that submit_content forwards the raw content bytes inside the files tuple."""
    mock_response = Mock()
    mock_response.text = "Ok."
    torrent_bytes = b"\x89PNG raw torrent data"

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(torrent_bytes, title="Some Title")

    call_kwargs = mock_req.call_args[1]
    _filename, content, _mime = call_kwargs["files"]["torrents"]
    assert content == torrent_bytes


def test_submit_content_uses_default_category(client):
    """Test that submit_content falls back to default_category when none is provided."""
    mock_response = Mock()
    mock_response.text = "Ok."

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.submit_content(b"data", title="Test")

    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["data"]["category"] == "curator"


# ---------------------------------------------------------------------------
# get_status — full state-map coverage
# ---------------------------------------------------------------------------


def test_get_status_meta_download_maps_to_downloading(client):
    """Test that the 'metaDL' state maps to the 'downloading' normalized status."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "metaDL", "progress": 0.1}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "downloading"


def test_get_status_checking_dl_maps_to_downloading(client):
    """Test that the 'checkingDL' state maps to the 'downloading' normalized status."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "checkingDL", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "downloading"


def test_get_status_stalled_dl_maps_to_pending(client):
    """Test that the 'stalledDL' state maps to the 'pending' normalized status."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "stalledDL", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "pending"


def test_get_status_paused_dl_maps_to_pending(client):
    """Test that the 'pausedDL' state maps to the 'pending' normalized status."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "pausedDL", "progress": 0.3}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "pending"


def test_get_status_missing_files_maps_to_failed(client):
    """Test that the 'missingFiles' state maps to the 'failed' normalized status."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "missingFiles", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "failed"


def test_get_status_forced_up_maps_to_completed_with_file_path(client):
    """Test that the 'forcedUP' state maps to 'completed' and includes file_path."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "forcedUP", "progress": 1.0, "save_path": "/downloads/mag"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "completed"
    assert status["file_path"] == "/downloads/mag"


def test_get_status_paused_up_maps_to_completed_with_file_path(client):
    """Test that the 'pausedUP' state maps to 'completed' and includes file_path."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "pausedUP", "progress": 1.0, "save_path": "/downloads/paused"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "completed"
    assert status["file_path"] == "/downloads/paused"


def test_get_status_stopped_up_maps_to_completed_with_file_path(client):
    """Test that the 'stoppedUP' state maps to 'completed' and includes file_path."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "stoppedUP", "progress": 1.0, "save_path": "/downloads/stopped"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "completed"
    assert status["file_path"] == "/downloads/stopped"


def test_get_status_queued_up_maps_to_completed_with_file_path(client):
    """Test that the 'queuedUP' state maps to 'completed' and includes file_path."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "queuedUP", "progress": 1.0, "save_path": "/downloads/queued"}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "completed"
    assert status["file_path"] == "/downloads/queued"


def test_get_status_unmapped_state_falls_back_to_pending(client):
    """Test that an unrecognized qBittorrent state falls back to 'pending'."""
    mock_response = Mock()
    mock_response.json.return_value = [{"state": "someNewState", "progress": 0.0}]

    with patch.object(client, "_request", return_value=mock_response):
        status = client.get_status("abc123")

    assert status["status"] == "pending"


# ---------------------------------------------------------------------------
# get_completed_downloads — completed state set coverage
# ---------------------------------------------------------------------------


def test_get_completed_downloads_includes_all_completed_states(client):
    """Test that all five QBITTORRENT_COMPLETED_STATES are treated as completed."""
    from core.constants.download_clients import QBITTORRENT_COMPLETED_STATES

    torrents = [
        {"hash": f"hash{i}", "state": state, "save_path": "/dl", "name": f"Title {i}"}
        for i, state in enumerate(sorted(QBITTORRENT_COMPLETED_STATES))
    ]
    mock_response = Mock()
    mock_response.json.return_value = torrents

    with patch.object(client, "_request", return_value=mock_response):
        downloads = client.get_completed_downloads()

    assert len(downloads) == len(QBITTORRENT_COMPLETED_STATES)


def test_get_completed_downloads_includes_queued_up_state(client):
    """Test that 'queuedUP' is included — it maps to 'completed' and is in COMPLETED_STATES."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"hash": "aaa", "state": "queuedUP", "save_path": "/dl", "name": "Title"},
    ]

    with patch.object(client, "_request", return_value=mock_response):
        downloads = client.get_completed_downloads()

    assert len(downloads) == 1
    assert downloads[0]["job_id"] == "aaa"


def test_get_completed_downloads_omits_category_filter_when_default_category_is_empty(
    client,
):
    """Test that category is not included in request params when default_category is empty."""
    client.default_category = ""

    mock_response = Mock()
    mock_response.json.return_value = []

    with patch.object(client, "_request", return_value=mock_response) as mock_req:
        client.get_completed_downloads()

    call_kwargs = mock_req.call_args[1]
    assert "category" not in call_kwargs["params"]
