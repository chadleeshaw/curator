"""Config masking, merges, and connection tests keep real secrets."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers import config as config_router
from web.routers.auth import get_verify_token
from web.routers.config import (
    _deep_merge,
    _mask_sensitive_config,
    _resolve_masked_client_key,
    _resolve_masked_provider_key,
)


def test_sensitive_fields_are_masked_for_display():
    masked = _mask_sensitive_config(
        {
            "search_providers": [{"api_key": "secret"}, {"api_key": ""}],
            "download_clients": [{"api_key": "k", "password": "p"}],
            "download_client": {"api_key": "legacy"},
        }
    )
    assert masked["search_providers"][0]["api_key"] == "***"
    assert masked["search_providers"][1]["api_key"] == ""
    assert masked["download_clients"][0]["password"] == "***"
    assert masked["download_client"]["api_key"] == "***"


def test_a_masked_key_is_replaced_with_the_saved_one():
    base = {
        "search_providers": [{"api_url": "http://indexer", "api_key": "real"}],
        "download_clients": [
            {"type": "sabnzbd", "api_url": "http://sab", "api_key": "sab-key", "password": "sab-pass"}
        ],
        "download_client": {"api_key": "legacy-key"},
        "matching": {"fuzzy_threshold": 80},
    }
    update = {
        "search_providers": [{"api_url": "http://indexer", "api_key": "***"}],
        "download_clients": [{"type": "sabnzbd", "api_key": "***", "password": "***"}],
        "download_client": {"api_key": "***"},
        "matching": {"fuzzy_threshold": 90},
        "new_section": {"enabled": True},
    }
    merged = _deep_merge(base, update)
    assert merged["search_providers"][0]["api_key"] == "real"
    assert merged["download_clients"][0]["api_key"] == "sab-key"
    assert merged["download_clients"][0]["password"] == "sab-pass"
    assert merged["download_client"]["api_key"] == "legacy-key"
    assert merged["matching"]["fuzzy_threshold"] == 90
    assert merged["new_section"]["enabled"] is True


def test_masked_credentials_resolve_from_the_saved_config():
    loader = MagicMock()
    loader.get_all_config.return_value = {
        "search_providers": [{"api_url": "http://indexer", "api_key": "real-key"}],
        "download_clients": [{"type": "qbittorrent", "api_url": "http://qbit", "password": "secret"}],
    }
    config_router.set_dependencies(loader)

    provider = _resolve_masked_provider_key({"api_url": "http://indexer", "api_key": "***"})
    missing = _resolve_masked_provider_key({"api_url": "http://missing", "api_key": "***"})
    client = _resolve_masked_client_key({"type": "qbittorrent", "password": "***"})
    plain = _resolve_masked_provider_key({"api_key": "already-real"})

    assert provider["api_key"] == "real-key"
    assert missing["api_key"] == "***"
    assert client["password"] == "secret"
    assert plain["api_key"] == "already-real"


def _client():
    app = FastAPI()
    app.dependency_overrides[get_verify_token] = lambda: "tester"
    app.include_router(config_router.router)
    return TestClient(app)


def test_provider_and_client_connection_tests(monkeypatch):
    client = _client()
    assert client.post("/api/config/test-provider", json={}).status_code == 400
    assert client.post("/api/config/test-provider", json={"type": "rss"}).status_code == 200
    assert client.post("/api/config/test-provider", json={"type": "nope"}).status_code == 400
    assert client.post("/api/config/test-download-client", json={}).status_code == 400
    assert client.post("/api/config/test-download-client", json={"type": "nope"}).status_code == 400

    for provider_type, path in (
        ("newsnab", "providers.newsnab.NewsnabProvider"),
        ("internet_archive", "providers.internet_archive.InternetArchiveProvider"),
        ("torznab", "providers.torznab.TorznabProvider"),
    ):
        with patch(path) as cls:
            cls.return_value.test_connection.return_value = {"status": "ok"}
            response = client.post("/api/config/test-provider", json={"type": provider_type, "api_key": "k"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    for client_type, path in (
        ("sabnzbd", "clients.sabnzbd.SABnzbdClient"),
        ("nzbget", "clients.nzbget.NZBGetClient"),
        ("internet_archive", "clients.internet_archive.InternetArchiveClient"),
        ("qbittorrent", "clients.qbittorrent.QBittorrentClient"),
    ):
        with patch(path) as cls:
            cls.return_value.test_connection.return_value = {"status": "ok"}
            response = client.post("/api/config/test-download-client", json={"type": client_type, "api_key": "k"})
        assert response.status_code == 200


def test_reload_rereads_the_file_and_restart_does_not_exec(monkeypatch):
    loader = MagicMock()
    config_router.set_dependencies(loader)
    client = _client()
    assert client.post("/api/config/reload").status_code == 200
    loader.reload_config.assert_called()

    monkeypatch.setattr("web.routers.config.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("web.routers.config.os.execv", lambda *_args: None)
    response = client.post("/api/config/restart")
    assert response.status_code == 200
    assert "restart" in response.json()["message"].lower()
