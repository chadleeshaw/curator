#!/usr/bin/env python3
"""
Test suite for SABnzbd Download Client
"""

from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from clients.sabnzbd import SABnzbdClient


def test_sabnzbd_initialization():
    """Test SABnzbd client initialization"""
    config = {
        "name": "sabnzbd",
        "type": "download_client",
        "api_url": "http://localhost:8080",
        "api_key": "test-key-12345",
    }

    client = SABnzbdClient(config)

    assert client.name == "sabnzbd"
    assert client.type == "download_client"
    assert client.api_url == "http://localhost:8080"
    assert client.api_key == "test-key-12345"


def test_sabnzbd_missing_api_key():
    """Test that SABnzbd raises error without API key"""
    config = {
        "name": "sabnzbd",
        "type": "download_client",
        "api_url": "http://localhost:8080",
    }

    try:
        SABnzbdClient(config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "api_key" in str(e)


def test_sabnzbd_defaults():
    """Test SABnzbd default values"""
    config = {
        "name": "sabnzbd",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    assert client.api_url == "http://localhost:8080"  # Default
    assert client.api_key == "test-key"


def test_sabnzbd_submit():
    """Test submitting NZB to SABnzbd"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {"status": True, "nzo_ids": ["nzo_12345"]}

        job_id = client.submit("https://example.com/nzb/test.nzb", title="Test Magazine")

        assert job_id == "nzo_12345"
        mock_api.assert_called_once()


def test_sabnzbd_submit_with_category():
    """Test submitting NZB with category"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {"status": True, "nzo_ids": ["nzo_12345"]}

        job_id = client.submit("https://example.com/nzb/test.nzb", title="Test Magazine", category="books")

        assert job_id == "nzo_12345"
        # Verify category was passed
        call_args = mock_api.call_args[0]
        params = mock_api.call_args[1].get("params", call_args[1] if len(call_args) > 1 else {})
        assert params.get("cat") == "books"


def test_sabnzbd_submit_failure():
    """Test failed NZB submission to SABnzbd"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {"status": False, "error": "Invalid NZB"}

        job_id = client.submit("https://example.com/nzb/test.nzb")

        assert job_id is None


def test_sabnzbd_get_status_downloading():
    """Test getting download status from SABnzbd (downloading)"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {
            "queue": {
                "slots": [
                    {
                        "nzo_id": "nzo_12345",
                        "status": "Downloading",
                        "percentage": "45.5",
                        "size": "1.5GB",
                        "timeleft": "01:30:00",
                    }
                ]
            }
        }

        status = client.get_status("nzo_12345")

        assert status["status"] == "downloading"
        assert status["progress"] == 45
        assert status["size"] == "1.5GB"


def test_sabnzbd_get_status_pending():
    """Test getting download status for pending job"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {
            "queue": {
                "slots": [
                    {
                        "nzo_id": "nzo_12345",
                        "status": "Paused",
                        "percentage": "0",
                        "size": "1.5GB",
                    }
                ]
            }
        }

        status = client.get_status("nzo_12345")

        assert status["status"] == "pending"
        assert status["progress"] == 0


def test_sabnzbd_get_status_completed():
    """Test getting download status from SABnzbd (completed)"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.get") as mock_get:
        # First call returns empty queue, second returns completed in history
        mock_response = Mock()
        mock_response.json.side_effect = [
            {
                "queue": {"slots": []},
            },
            {
                "history": {
                    "slots": [
                        {
                            "nzo_id": "nzo_12345",
                            "status": "Completed",
                            "storage": "/downloads/magazine.nzb",
                            "name": "Test Magazine",
                        }
                    ]
                }
            },
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        status = client.get_status("nzo_12345")

        assert status["status"] == "completed"
        assert status["progress"] == 100
        assert status["file_path"] == "/downloads/magazine.nzb"


def test_sabnzbd_get_status_failed():
    """Test getting status for failed download"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.get") as mock_get:
        mock_response = Mock()
        mock_response.json.side_effect = [
            {"queue": {"slots": []}},
            {
                "history": {
                    "slots": [
                        {
                            "nzo_id": "nzo_12345",
                            "status": "Failed",
                            "fail_message": "Missing articles",
                            "percentage": "50",
                        }
                    ]
                }
            },
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        status = client.get_status("nzo_12345")

        assert status["status"] == "failed"
        assert "Missing articles" in status["error"]


def test_sabnzbd_get_status_unknown():
    """Test getting status for unknown job"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.get") as mock_get:
        mock_response = Mock()
        mock_response.json.side_effect = [
            {"queue": {"slots": []}},
            {"history": {"slots": []}},
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        status = client.get_status("nzo_99999")

        assert status["status"] == "unknown"
        assert status["progress"] == 0


def test_sabnzbd_get_completed_downloads():
    """Test getting completed downloads from SABnzbd"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.get") as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {
            "history": {
                "slots": [
                    {
                        "nzo_id": "nzo_12345",
                        "status": "Completed",
                        "storage": "/downloads/mag1.nzb",
                        "name": "Magazine 1",
                    },
                    {
                        "nzo_id": "nzo_12346",
                        "status": "Completed",
                        "storage": "/downloads/mag2.nzb",
                        "name": "Magazine 2",
                    },
                    {
                        "nzo_id": "nzo_12347",
                        "status": "Failed",
                        "storage": "/downloads/mag3.nzb",
                        "name": "Magazine 3",
                    },
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        downloads = client.get_completed_downloads()

        assert len(downloads) == 2
        assert downloads[0]["job_id"] == "nzo_12345"
        assert downloads[1]["job_id"] == "nzo_12346"
        assert downloads[0]["title"] == "Magazine 1"
        assert downloads[1]["title"] == "Magazine 2"


def test_sabnzbd_delete():
    """Test deleting a job from SABnzbd"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {"status": True}

        result = client.delete("nzo_12345")

        assert result is True
        mock_api.assert_called()


def test_sabnzbd_api_call_error_handling():
    """Test API call error handling"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")

        result = client._api_call("queue")

        assert result == {}


def test_sabnzbd_title_sanitization():
    """Test that long titles with path separators are sanitized"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch.object(client, "_api_call") as mock_api:
        mock_api.return_value = {"status": True, "nzo_ids": ["nzo_12345"]}

        # Submit with a title containing path separators
        job_id = client.submit(
            "https://example.com/nzb/test.nzb",
            title="Test/Magazine\\With/Bad\\Characters",
        )

        # Verify the title was sanitized in the API call
        call_args = mock_api.call_args
        params = call_args[1].get("params", call_args[0][1] if len(call_args[0]) > 1 else {})
        sanitized_title = params.get("nzbname", "")

        assert "/" not in sanitized_title
        assert "\\" not in sanitized_title
        assert "-" in sanitized_title  # Should have replaced separators with dashes


# --- submit_content tests ---


def test_sabnzbd_submit_content_success():
    """Test submitting NZB content directly to SABnzbd."""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }
    client = SABnzbdClient(config)
    nzb_content = '<?xml version="1.0"?><nzb><file></file></nzb>'

    with patch("clients.sabnzbd.httpx.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": True,
            "nzo_ids": ["nzo_content_123"],
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        job_id = client.submit_content(nzb_content=nzb_content, title="Test Magazine", category="books")

        assert job_id == "nzo_content_123"
        mock_post.assert_called_once()
        # Verify it used multipart file upload
        call_kwargs = mock_post.call_args
        assert "files" in call_kwargs.kwargs or "files" in (call_kwargs[1] if len(call_kwargs) > 1 else {})


def test_sabnzbd_submit_content_failure():
    """Test handling failed NZB content submission."""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }
    client = SABnzbdClient(config)
    nzb_content = "<nzb></nzb>"

    with patch("clients.sabnzbd.httpx.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"status": False, "error": "Invalid NZB"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        job_id = client.submit_content(nzb_content=nzb_content, title="Bad NZB")
        assert job_id is None


def test_sabnzbd_submit_content_with_category():
    """Test NZB content submission includes category parameter."""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }
    client = SABnzbdClient(config)
    nzb_content = "<nzb><file></file></nzb>"

    with patch("clients.sabnzbd.httpx.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": True,
            "nzo_ids": ["nzo_content_123"],
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        job_id = client.submit_content(nzb_content=nzb_content, title="Test", category="magazines")
        assert job_id == "nzo_content_123"

        # Verify category was included in params
        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("cat") == "magazines"


def test_sabnzbd_submit_content_network_error():
    """Test NZB content submission handles network errors gracefully."""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }
    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.httpx.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")

        job_id = client.submit_content(nzb_content="<nzb/>", title="Test")
        assert job_id is None
