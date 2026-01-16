#!/usr/bin/env python3
"""
Test suite for NZBGet Download Client
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from clients.nzbget import NZBGetClient


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


def test_nzbget_submit():
    """Test submitting NZB to NZBGet"""
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
        # Verify category was passed in API call
        call_args = mock_api.call_args[0]
        assert "books" in str(call_args)


def test_nzbget_submit_failure():
    """Test failed NZB submission to NZBGet"""
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


def test_nzbget_get_status_downloading():
    """Test getting download status from NZBGet (downloading)"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "DOWNLOADING",
                "NZBName": "Test Magazine",
                "DownloadedSize": 500 * 1024 * 1024,  # 500 MB
                "FileSizeMB": 1024,  # 1 GB
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "downloading"
        assert status["progress"] == 48  # ~500MB/1GB
        assert status["size"] == 1024


def test_nzbget_get_status_paused():
    """Test getting status for paused download"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "PAUSED",
                "NZBName": "Test Magazine",
                "DownloadedSize": 200 * 1024 * 1024,
                "FileSizeMB": 1024,
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "pending"


def test_nzbget_get_status_completed():
    """Test getting download status from NZBGet (completed)"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "SUCCESS",
                "NZBName": "Test Magazine",
                "DownloadedSize": 1024 * 1024 * 1024,  # 1 GB
                "FileSizeMB": 1024,  # 1 GB
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        assert status["status"] == "completed"
        assert status["progress"] == 100
        assert status["file_path"] == "/downloads/test"


def test_nzbget_get_status_failed():
    """Test getting status for failed/other download - returns pending"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "FAILURE",
                "NZBName": "Test Magazine",
                "DownloadedSize": 500 * 1024 * 1024,
                "FileSizeMB": 1024,
                "DestDir": "/downloads/test",
            }
        ]

        status = client.get_status("123")

        # Implementation returns "pending" for any non-SUCCESS/DOWNLOADING status
        assert status["status"] == "pending"


def test_nzbget_get_status_unknown():
    """Test getting download status for unknown job"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = []  # No jobs

        status = client.get_status("999")

        assert status["status"] == "unknown"
        assert status["progress"] == 0


def test_nzbget_get_completed_downloads():
    """Test getting completed downloads from NZBGet"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = [
            {
                "NZBID": 123,
                "Status": "SUCCESS",
                "NZBName": "Magazine 1",
                "DestDir": "/downloads/mag1",
            },
            {
                "NZBID": 124,
                "Status": "SUCCESS",
                "NZBName": "Magazine 2",
                "DestDir": "/downloads/mag2",
            },
            {
                "NZBID": 125,
                "Status": "DOWNLOADING",  # Not completed
                "NZBName": "Magazine 3",
                "DestDir": "/downloads/mag3",
            },
        ]

        downloads = client.get_completed_downloads()

        assert len(downloads) == 2
        assert downloads[0]["job_id"] == "123"
        assert downloads[1]["job_id"] == "124"
        assert downloads[0]["title"] == "Magazine 1"
        assert downloads[1]["title"] == "Magazine 2"


def test_nzbget_delete():
    """Test deleting a job from NZBGet"""
    config = {
        "api_url": "http://localhost:6789",
        "username": "nzbget",
        "password": "test-password",
    }

    client = NZBGetClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = True

        result = client.delete("123")

        assert result is True
        mock_api.assert_called()


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

        result = client._api_call("append", ["https://example.com/nzb", "Test", 50, False])

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
        mock_response.json.return_value = {"result": None, "error": {"code": -1, "message": "Invalid method"}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = client._api_call("invalid_method", [])

        assert result == {}  # Returns empty dict on error
