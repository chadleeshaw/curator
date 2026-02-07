#!/usr/bin/env python3
"""
Test suite for NZBGet Download Client

Tests aligned with official NZBGet API docs:
  - listgroups: https://nzbget.com/documentation/api/listgroups
  - history: https://nzbget.com/documentation/api/history
  - append: https://nzbget.com/documentation/api/append
  - editqueue: https://nzbget.com/documentation/api/editqueue
"""

from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from clients.nzbget import NZBGetClient


# --- Initialization tests ---


def test_nzbget_initialization():
    """Test NZBGet client initialization"""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    assert client.name == "nzbget"
    assert client.type == "download_client"
    assert client.api_url == "http://localhost:6789"
    assert client.username == "nzbget"
    assert client.password == "test-password"


def test_nzbget_missing_password():
    """Test that NZBGet raises error without password"""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
    }

    try:
        NZBGetClient(config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "password" in str(e)


def test_nzbget_defaults():
    """Test NZBGet default values"""
    config = {
        "name": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    assert client.api_url == "http://localhost:6789"  # Default
    assert client.username == "nzbget"  # Default
    assert client.password == "test-password"


# --- Submit tests ---


def test_nzbget_submit():
    """Test submitting NZB URL — Filename and Content params are in correct order"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 123  # NZBID returned as number

        job_id = client.submit("https://example.com/nzb/test.nzb", title="Test Magazine")

        assert job_id == "123"
        mock_api.assert_called_once()

        # Verify append params: (Filename, Content/URL, Category, Priority, AddToTop, AddPaused)
        call_args = mock_api.call_args[0]
        assert call_args[0] == "append"
        params = call_args[1]
        assert params[0] == "Test Magazine.nzb"  # Filename (display name with .nzb extension)
        assert params[1] == "https://example.com/nzb/test.nzb"  # Content (URL to fetch)
        assert params[2] == ""  # Category (empty)
        assert params[3] == 50  # Priority (high)
        assert params[4] is False  # AddToTop
        assert params[5] is False  # AddPaused


def test_nzbget_submit_with_category():
    """Test submitting NZB with category"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 456

        job_id = client.submit("https://example.com/nzb/test.nzb", title="Test Magazine", category="books")

        assert job_id == "456"
        # Verify category was passed in correct position (index 2)
        params = mock_api.call_args[0][1]
        assert params[2] == "books"


def test_nzbget_submit_failure():
    """Test failed NZB submission to NZBGet (returns 0)"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 0  # 0 or negative means failure

        job_id = client.submit("https://example.com/nzb/test.nzb")

        assert job_id is None


def test_nzbget_submit_title_sanitization():
    """Test that titles with path separators are sanitized"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 100

        client.submit("https://example.com/nzb", title="Bad/Path\\Name")

        params = mock_api.call_args[0][1]
        filename = params[0]
        assert "/" not in filename.replace(".nzb", "")
        assert "\\" not in filename.replace(".nzb", "")


# --- get_status queue tests (listgroups API) ---


def test_nzbget_get_status_downloading():
    """Test DOWNLOADING status — uses DownloadedSizeMB/FileSizeMB (both in MiB)"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "DOWNLOADING",
                "NZBName": "Test Magazine",
                "DownloadedSizeMB": 500,  # 500 MiB downloaded
                "FileSizeMB": 1024,  # 1024 MiB total
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "downloading"
        assert status["progress"] == 48  # 500/1024 * 100
        assert status["size"] == 1024


def test_nzbget_get_status_queued():
    """Test QUEUED status from listgroups — item waiting in queue"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "QUEUED",
                "NZBName": "Test Magazine",
                "DownloadedSizeMB": 0,
                "FileSizeMB": 1024,
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "pending"
        assert status["progress"] == 0


def test_nzbget_get_status_paused():
    """Test PAUSED status from listgroups"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "PAUSED",
                "NZBName": "Test Magazine",
                "DownloadedSizeMB": 200,
                "FileSizeMB": 1024,
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "pending"


def test_nzbget_get_status_post_processing():
    """Test post-processing statuses from listgroups (UNPACKING, REPAIRING, etc.)"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    for pp_status in ["PP_QUEUED", "UNPACKING", "REPAIRING", "VERIFYING_SOURCES", "EXECUTING_SCRIPT", "PP_FINISHED"]:
        with patch.object(client, "_api_call") as mock_api:
            mock_api.return_value = [
                {
                    "NZBID": 123,
                    "Status": pp_status,
                    "NZBName": "Test Magazine",
                    "DownloadedSizeMB": 1024,
                    "FileSizeMB": 1024,
                    "PostInfoText": "Verifying file myfile.rar",
                }
            ]

            status = client.get_status("123")

            assert status["status"] == "downloading", f"Expected 'downloading' for {pp_status}"
            assert "extra_status" in status


def test_nzbget_get_status_fetching():
    """Test FETCHING status from listgroups (NZB being fetched from URL)"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "FETCHING",
                "NZBName": "Test Magazine",
                "DownloadedSizeMB": 0,
                "FileSizeMB": 0,
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "downloading"


# --- get_status history tests (history API) ---


def test_nzbget_get_status_completed_from_history():
    """Test SUCCESS/* items found in history after leaving queue"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        # First call: listgroups returns empty (item left queue)
        # Second call: history returns the completed item
        mock_api.side_effect = [
            [],  # listgroups
            [
                {
                    "NZBID": 123,
                    "Status": "SUCCESS/ALL",
                    "Name": "Test Magazine",
                    "DestDir": "/downloads/test",
                    "FinalDir": "/library/test",
                }
            ],  # history
        ]

        status = client.get_status("123")

        assert status["status"] == "completed"
        assert status["progress"] == 100
        assert status["file_path"] == "/library/test"  # FinalDir preferred over DestDir


def test_nzbget_get_status_completed_destdir_fallback():
    """Test completed item uses DestDir when FinalDir is empty"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = [
            [],  # listgroups
            [
                {
                    "NZBID": 123,
                    "Status": "SUCCESS/UNPACK",
                    "Name": "Test Magazine",
                    "DestDir": "/downloads/test",
                    "FinalDir": "",
                }
            ],  # history
        ]

        status = client.get_status("123")

        assert status["status"] == "completed"
        assert status["file_path"] == "/downloads/test"


def test_nzbget_get_status_failed_from_history():
    """Test FAILURE/* items found in history"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = [
            [],  # listgroups
            [
                {
                    "NZBID": 123,
                    "Status": "FAILURE/UNPACK",
                    "Name": "Test Magazine",
                    "UnpackStatus": "FAILURE",
                }
            ],  # history
        ]

        status = client.get_status("123")

        assert status["status"] == "failed"
        assert status["progress"] == 0
        assert "error" in status
        assert "unpack" in status["error"].lower()


def test_nzbget_get_status_encrypted_from_history():
    """Test PASSWORD detection via UnpackStatus field in history items"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = [
            [],  # listgroups
            [
                {
                    "NZBID": 123,
                    "Status": "WARNING/PASSWORD",
                    "Name": "Test Magazine",
                    "UnpackStatus": "PASSWORD",
                }
            ],  # history
        ]

        status = client.get_status("123")

        assert status["status"] == "failed"
        assert status["encrypted"] is True
        assert "password" in status["error"].lower()


def test_nzbget_get_status_deleted_from_history():
    """Test DELETED/* items in history"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = [
            [],  # listgroups
            [
                {
                    "NZBID": 123,
                    "Status": "DELETED/HEALTH",
                    "Name": "Test Magazine",
                }
            ],  # history
        ]

        status = client.get_status("123")

        assert status["status"] == "failed"
        assert "health" in status["error"].lower()


def test_nzbget_get_status_unknown():
    """Test getting download status for job not in queue or history"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = [
            [],  # listgroups — empty
            [],  # history — empty
        ]

        status = client.get_status("999")

        assert status["status"] == "unknown"
        assert status["progress"] == 0


# --- get_completed_downloads tests ---


def test_nzbget_get_completed_downloads():
    """Test getting completed downloads from history (not listgroups queue)"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "SUCCESS/ALL",
                "Name": "Magazine 1",
                "NZBName": "magazine1.nzb",
                "DestDir": "/downloads/mag1",
                "FinalDir": "",
            },
            {
                "NZBID": 124,
                "Status": "SUCCESS/UNPACK",
                "Name": "Magazine 2",
                "NZBName": "magazine2.nzb",
                "DestDir": "/downloads/mag2",
                "FinalDir": "/library/mag2",
            },
            {
                "NZBID": 125,
                "Status": "FAILURE/UNPACK",  # Not completed — should be excluded
                "Name": "Magazine 3",
                "DestDir": "/downloads/mag3",
            },
        ]

        downloads = client.get_completed_downloads()

        # Verify history API was called (not listgroups)
        mock_api.assert_called_once_with("history", [False])
        assert len(downloads) == 2
        assert downloads[0]["job_id"] == "123"
        assert downloads[0]["title"] == "Magazine 1"
        assert downloads[0]["file_path"] == "/downloads/mag1"  # DestDir (FinalDir empty)
        assert downloads[1]["job_id"] == "124"
        assert downloads[1]["title"] == "Magazine 2"
        assert downloads[1]["file_path"] == "/library/mag2"  # FinalDir preferred


# --- Delete tests ---


def test_nzbget_delete():
    """Test deleting a job — tries queue first with v18+ editqueue signature"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = True

        result = client.delete("123")

        assert result is True
        # v18+ editqueue: (Command, Param, IDs) — no Offset parameter
        mock_api.assert_called_once_with("editqueue", ["GroupFinalDelete", "", [123]])


def test_nzbget_delete_from_history():
    """Test deleting a job found in history (not queue)"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        # First call (queue delete) fails, second call (history delete) succeeds
        mock_api.side_effect = [False, True]

        result = client.delete("123")

        assert result is True
        assert mock_api.call_count == 2
        # Second call should be HistoryFinalDelete
        mock_api.assert_called_with("editqueue", ["HistoryFinalDelete", "", [123]])


def test_nzbget_delete_not_found():
    """Test deleting job that's not in queue or history"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = False

        result = client.delete("999")

        assert result is False
        assert mock_api.call_count == 2  # Tried both queue and history


# --- API call tests ---


def test_nzbget_api_call_json_rpc():
    """Test NZBGet JSON-RPC API call format"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch("clients.nzbget.requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"result": 123, "error": None}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = client._api_call("append", ["name.nzb", "https://example.com/nzb", "", 50, False, False])

        # Verify JSON-RPC format
        call_args = mock_post.call_args
        assert call_args[1]["json"]["jsonrpc"] == "2.0"
        assert call_args[1]["json"]["method"] == "append"
        assert result == 123


def test_nzbget_api_call_error_handling():
    """Test API call error handling"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch("clients.nzbget.requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")

        result = client._api_call("listgroups", [])

        assert result == {}  # Returns empty dict on error


def test_nzbget_api_call_with_error_response():
    """Test API call when server returns error"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch("clients.nzbget.requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": None,
            "error": {"code": -1, "message": "Invalid method"},
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = client._api_call("invalid_method", [])

        assert result == {}  # Returns empty dict on error


# --- submit_content tests ---


def test_nzbget_submit_content_success():
    """Test submitting NZB content directly to NZBGet."""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }
    client = NZBGetClient(config)
    nzb_content = '<?xml version="1.0"?><nzb><file></file></nzb>'

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 12345  # NZBGet returns NZBID as integer

        job_id = client.submit_content(nzb_content=nzb_content, title="Test Magazine", category="books")

        assert job_id == "12345"
        mock_api.assert_called_once()
        # Verify base64-encoded content was passed
        call_params = mock_api.call_args[0][1]
        assert call_params[0] == "Test Magazine.nzb"  # Filename
        assert call_params[2] == "books"  # Category

        # Verify content is valid base64
        import base64

        decoded = base64.b64decode(call_params[1]).decode("utf-8")
        assert decoded == nzb_content


def test_nzbget_submit_content_failure():
    """Test handling failed NZB content submission."""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 0  # NZBGet returns 0 on failure

        job_id = client.submit_content(nzb_content="<nzb/>", title="Bad NZB")
        assert job_id is None


def test_nzbget_submit_content_exception():
    """Test NZB content submission handles exceptions gracefully."""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.side_effect = Exception("API error")

        job_id = client.submit_content(nzb_content="<nzb/>", title="Test")
        assert job_id is None


def test_nzbget_submit_content_title_sanitization():
    """Test NZB content submission sanitizes titles."""
    config = {
        "name": "nzbget",
        "type": "download_client",
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = 999

        client.submit_content(nzb_content="<nzb/>", title="Bad/Path\\Name")

        call_params = mock_api.call_args[0][1]
        filename = call_params[0]
        assert "/" not in filename.replace(".nzb", "")
        assert "\\" not in filename


# --- Connection test ---


def test_nzbget_test_connection_success():
    """Test successful connection test"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = "24.3"

        result = client.test_connection()

        assert result["success"] is True
        assert "24.3" in result["message"]


def test_nzbget_test_connection_failure():
    """Test failed connection test"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {}

        result = client.test_connection()

        assert result["success"] is False


# --- Progress calculation tests ---


def test_nzbget_progress_calculation():
    """Test _calculate_progress uses correct MiB-based fields"""
    config = {"password": "test-password"}
    client = NZBGetClient(config)

    # Normal progress
    assert client._calculate_progress({"DownloadedSizeMB": 500, "FileSizeMB": 1000}) == 50

    # Complete
    assert client._calculate_progress({"DownloadedSizeMB": 1000, "FileSizeMB": 1000}) == 100

    # Zero file size (shouldn't divide by zero)
    assert client._calculate_progress({"DownloadedSizeMB": 0, "FileSizeMB": 0}) == 0

    # Missing fields default correctly
    assert client._calculate_progress({}) == 0


# --- Error message tests ---


def test_nzbget_build_error_message_known_status():
    """Test error messages for known composite statuses"""
    assert "unpack" in NZBGetClient._build_error_message("FAILURE/UNPACK").lower()
    assert "password" in NZBGetClient._build_error_message("WARNING/PASSWORD").lower()
    assert "disk space" in NZBGetClient._build_error_message("WARNING/SPACE").lower()
    assert "health" in NZBGetClient._build_error_message("FAILURE/HEALTH").lower()


def test_nzbget_build_error_message_unknown_status():
    """Test fallback error message for unknown composite status"""
    msg = NZBGetClient._build_error_message("FAILURE/SOMETHING_NEW")
    assert "failure" in msg.lower()
    assert "something_new" in msg.lower()
