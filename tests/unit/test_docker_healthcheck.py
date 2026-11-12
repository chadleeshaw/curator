"""The image health check fails unless /api/health returns a 2xx response."""

from pathlib import Path
from unittest.mock import Mock

import requests

from docker_healthcheck import main

ROOT = Path(__file__).resolve().parents[2]


def _response(status_code):
    response = Mock()
    response.status_code = status_code

    def raise_for_status():
        if status_code >= 400:
            raise requests.HTTPError(f"HTTP {status_code}")

    response.raise_for_status = raise_for_status
    return response


def test_a_healthy_response_passes(monkeypatch):
    monkeypatch.setattr("docker_healthcheck.requests.get", lambda *args, **kwargs: _response(200))
    assert main() == 0


def test_a_503_fails_the_check(monkeypatch):
    monkeypatch.setattr("docker_healthcheck.requests.get", lambda *args, **kwargs: _response(503))
    assert main() == 1


def test_a_connection_error_fails_the_check(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("docker_healthcheck.requests.get", boom)
    assert main() == 1


def test_the_image_healthcheck_invokes_the_status_check():
    dockerfile = (ROOT / "Dockerfile").read_text()
    script = (ROOT / "docker_healthcheck.py").read_text()
    assert "python docker_healthcheck.py" in dockerfile
    assert "raise_for_status" in script
    assert "requests.get('http://localhost:8000/api/health')" not in dockerfile
