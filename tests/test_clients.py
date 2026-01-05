#!/usr/bin/env python3
"""
Test suite for Download Clients (SABnzbd and NZBGet)
"""

import sys
from pathlib import Path  # noqa: E402
from unittest.mock import Mock, patch, MagicMock  # noqa: E402

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.sabnzbd import SABnzbdClient  # noqa: E402
from clients.nzbget import NZBGetClient  # noqa: E402


# ==================== SABnzbd Tests ====================


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

    print("Testing SABnzbd initialization... ✓ PASS")
    return True


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

    print("Testing SABnzbd missing API key... ✓ PASS")
    return True


def test_sabnzbd_defaults():
    """Test SABnzbd default values"""
    config = {
        "name": "sabnzbd",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    assert client.api_url == "http://localhost:8080"  # Default
    assert client.api_key == "test-key"

    print("Testing SABnzbd defaults... ✓ PASS")
    return True


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

    print("Testing SABnzbd submit... ✓ PASS")
    return True


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

    print("Testing SABnzbd submit failure... ✓ PASS")
    return True


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

    print("Testing SABnzbd get status (downloading)... ✓ PASS")
    return True


def test_sabnzbd_get_status_completed():
    """Test getting download status from SABnzbd (completed)"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.requests.get") as mock_get:
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

    print("Testing SABnzbd get status (completed)... ✓ PASS")
    return True


def test_sabnzbd_get_completed_downloads():
    """Test getting completed downloads from SABnzbd"""
    config = {
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
    }

    client = SABnzbdClient(config)

    with patch("clients.sabnzbd.requests.get") as mock_get:
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

    print("Testing SABnzbd get completed downloads... ✓ PASS")
    return True


# ==================== NZBGet Tests ====================


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

    print("Testing NZBGet initialization... ✓ PASS")
    return True


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

    print("Testing NZBGet missing password... ✓ PASS")
    return True


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

    print("Testing NZBGet defaults... ✓ PASS")
    return True


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

    print("Testing NZBGet submit... ✓ PASS")
    return True


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

    print("Testing NZBGet submit failure... ✓ PASS")
    return True


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

    print("Testing NZBGet get status (downloading)... ✓ PASS")
    return True


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

    print("Testing NZBGet get status (completed)... ✓ PASS")
    return True


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

    print("Testing NZBGet get status (unknown)... ✓ PASS")
    return True


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
                "Status": "DOWNLOADING",  # Not completed, should not be included
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

    print("Testing NZBGet get completed downloads... ✓ PASS")
    return True


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

    print("Testing NZBGet API call JSON-RPC format... ✓ PASS")
    return True


if __name__ == "__main__":
    print("\n🧪 Download Client Tests\n")
    print("=" * 70)

    results = {}

    # SABnzbd tests
    try:
        results["sabnzbd_init"] = test_sabnzbd_initialization()
    except Exception as e:
        print(f"Testing SABnzbd initialization... ❌ FAIL: {e}")
        results["sabnzbd_init"] = False

    try:
        results["sabnzbd_missing_key"] = test_sabnzbd_missing_api_key()
    except Exception as e:
        print(f"Testing SABnzbd missing API key... ❌ FAIL: {e}")
        results["sabnzbd_missing_key"] = False

    try:
        results["sabnzbd_defaults"] = test_sabnzbd_defaults()
    except Exception as e:
        print(f"Testing SABnzbd defaults... ❌ FAIL: {e}")
        results["sabnzbd_defaults"] = False

    try:
        results["sabnzbd_submit"] = test_sabnzbd_submit()
    except Exception as e:
        print(f"Testing SABnzbd submit... ❌ FAIL: {e}")
        results["sabnzbd_submit"] = False

    try:
        results["sabnzbd_submit_fail"] = test_sabnzbd_submit_failure()
    except Exception as e:
        print(f"Testing SABnzbd submit failure... ❌ FAIL: {e}")
        results["sabnzbd_submit_fail"] = False

    try:
        results["sabnzbd_status_dl"] = test_sabnzbd_get_status_downloading()
    except Exception as e:
        print(f"Testing SABnzbd get status (downloading)... ❌ FAIL: {e}")
        results["sabnzbd_status_dl"] = False

    try:
        results["sabnzbd_status_done"] = test_sabnzbd_get_status_completed()
    except Exception as e:
        print(f"Testing SABnzbd get status (completed)... ❌ FAIL: {e}")
        results["sabnzbd_status_done"] = False

    try:
        results["sabnzbd_completed"] = test_sabnzbd_get_completed_downloads()
    except Exception as e:
        print(f"Testing SABnzbd get completed downloads... ❌ FAIL: {e}")
        results["sabnzbd_completed"] = False

    # NZBGet tests
    try:
        results["nzbget_init"] = test_nzbget_initialization()
    except Exception as e:
        print(f"Testing NZBGet initialization... ❌ FAIL: {e}")
        results["nzbget_init"] = False

    try:
        results["nzbget_missing_pass"] = test_nzbget_missing_password()
    except Exception as e:
        print(f"Testing NZBGet missing password... ❌ FAIL: {e}")
        results["nzbget_missing_pass"] = False

    try:
        results["nzbget_defaults"] = test_nzbget_defaults()
    except Exception as e:
        print(f"Testing NZBGet defaults... ❌ FAIL: {e}")
        results["nzbget_defaults"] = False

    try:
        results["nzbget_submit"] = test_nzbget_submit()
    except Exception as e:
        print(f"Testing NZBGet submit... ❌ FAIL: {e}")
        results["nzbget_submit"] = False

    try:
        results["nzbget_submit_fail"] = test_nzbget_submit_failure()
    except Exception as e:
        print(f"Testing NZBGet submit failure... ❌ FAIL: {e}")
        results["nzbget_submit_fail"] = False

    try:
        results["nzbget_status_dl"] = test_nzbget_get_status_downloading()
    except Exception as e:
        print(f"Testing NZBGet get status (downloading)... ❌ FAIL: {e}")
        results["nzbget_status_dl"] = False

    try:
        results["nzbget_status_done"] = test_nzbget_get_status_completed()
    except Exception as e:
        print(f"Testing NZBGet get status (completed)... ❌ FAIL: {e}")
        results["nzbget_status_done"] = False

    try:
        results["nzbget_status_unknown"] = test_nzbget_get_status_unknown()
    except Exception as e:
        print(f"Testing NZBGet get status (unknown)... ❌ FAIL: {e}")
        results["nzbget_status_unknown"] = False

    try:
        results["nzbget_completed"] = test_nzbget_get_completed_downloads()
    except Exception as e:
        print(f"Testing NZBGet get completed downloads... ❌ FAIL: {e}")
        results["nzbget_completed"] = False

    try:
        results["nzbget_jsonrpc"] = test_nzbget_api_call_json_rpc()
    except Exception as e:
        print(f"Testing NZBGet API call JSON-RPC format... ❌ FAIL: {e}")
        results["nzbget_jsonrpc"] = False

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    sabnzbd_tests = {k: v for k, v in results.items() if "sabnzbd" in k}
    nzbget_tests = {k: v for k, v in results.items() if "nzbget" in k}

    print("\n📦 SABnzbd Client Tests:")
    for test_name, passed in sabnzbd_tests.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    print("\n📦 NZBGet Client Tests:")
    for test_name, passed in nzbget_tests.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + "=" * 70)
    print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))

    sys.exit(0 if all_passed else 1)
