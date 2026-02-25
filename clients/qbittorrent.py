"""
qBittorrent download client implementation.
Uses the qBittorrent Web API v2 with cookie-based session authentication.
Re-authenticates automatically on 403 responses.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

import httpx

from core.constants.app import HTTP_REQUEST_TIMEOUT
from core.constants.download_clients import (
    QBITTORRENT_COMPLETED_STATES,
    QBITTORRENT_STATE_MAP,
)
from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


class QBittorrentClient(DownloadClient):
    """Download client for qBittorrent Web API v2."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://localhost:8080").rstrip("/")
        self.username = config.get("username", "admin")
        self.password = config.get("password", "")
        self.default_category = config.get("default_category", "curator")
        self._session = httpx.Client()
        self._authenticated = False
        self._lock = threading.Lock()

    def _login(self) -> bool:
        """Authenticate with qBittorrent and store session cookie."""
        try:
            response = self._session.post(
                f"{self.api_url}/api/v2/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=HTTP_REQUEST_TIMEOUT,
            )
            if response.text.strip() == "Ok.":
                self._authenticated = True
                logger.debug("qBittorrent login successful")
                return True
            logger.warning(f"qBittorrent login failed: {response.text.strip()}")
            self._authenticated = False
            return False
        except Exception as e:
            logger.error(f"qBittorrent login error: {e}")
            self._authenticated = False
            return False

    def _ensure_authenticated(self) -> bool:
        """Ensure the client is authenticated. Thread-safe via lock."""
        with self._lock:
            if not self._authenticated:
                return self._login()
            return True

    def _request(self, method: str, path: str, **kwargs) -> Optional[httpx.Response]:
        """
        Make an authenticated request to the qBittorrent API.

        Automatically re-authenticates once on 403 responses.
        The lock is held only during auth state checks and updates, not during
        network I/O, so concurrent callers are not serialized by the lock.
        Note: requests.Session is not thread-safe for truly concurrent use;
        callers should avoid issuing simultaneous requests from multiple threads.
        """
        if not self._ensure_authenticated():
            return None

        url = f"{self.api_url}/api/v2{path}"
        try:
            response = getattr(self._session, method)(url, timeout=HTTP_REQUEST_TIMEOUT, **kwargs)

            if response.status_code == 403:
                logger.debug("qBittorrent session expired, re-authenticating")
                with self._lock:
                    self._authenticated = False
                    if not self._login():
                        return None
                response = getattr(self._session, method)(url, timeout=HTTP_REQUEST_TIMEOUT, **kwargs)

            response.raise_for_status()
            return response

        except httpx.TimeoutException:
            logger.error(f"qBittorrent request timeout: {path}")
            return None
        except httpx.ConnectError:
            logger.error(f"qBittorrent connection error: {path}")
            return None
        except Exception as e:
            logger.error(f"qBittorrent request error {path}: {e}")
            return None

    def submit(self, url: str, title: str = None, category: str = None) -> Optional[str]:
        """
        Add a torrent by magnet link or .torrent URL.

        Returns the torrent hash when the URL is a magnet link, or None for .torrent URLs
        (hash is unavailable without a second API call) and on failure.
        """
        data = {"urls": url, "category": category or self.default_category}
        if title:
            data["rename"] = title

        response = self._request("post", "/torrents/add", data=data)
        if response is None:
            return None

        if response.text.strip() != "Ok.":
            logger.error(f"qBittorrent submission failed: {response.text.strip()}")
            return None

        torrent_hash = self._resolve_hash_from_url(url)
        logger.info(f"Submitted to qBittorrent: {title or url} -> {torrent_hash or 'unknown'}")
        return torrent_hash

    def submit_content(self, content: bytes, title: str = None, category: str = None) -> Optional[str]:
        """
        Upload a .torrent file directly.

        Always returns None — the hash is not available in the upload response.
        Use get_completed_downloads() to discover finished torrents instead.
        """
        filename = f"{title or 'download'}.torrent"
        files = {"torrents": (filename, content, "application/x-bittorrent")}
        data = {"category": category or self.default_category}
        if title:
            data["rename"] = title

        response = self._request("post", "/torrents/add", data=data, files=files)
        if response is None:
            return None

        if response.text.strip() != "Ok.":
            logger.error(f"qBittorrent .torrent upload failed: {response.text.strip()}")
            return None

        logger.info(f"Uploaded .torrent to qBittorrent: {title}")
        return None

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status for a torrent by hash.

        Returns a dict with keys: status, progress, and file_path (when completed).
        """
        response = self._request("get", "/torrents/info", params={"hashes": job_id})
        if response is None:
            return {"status": "error", "progress": 0}

        torrents = response.json()
        if not torrents:
            return {"status": "unknown", "progress": 0}

        torrent = torrents[0]
        status = QBITTORRENT_STATE_MAP.get(torrent.get("state", "unknown"), "pending")
        progress = int(torrent.get("progress", 0) * 100)

        result: Dict[str, Any] = {"status": status, "progress": progress}
        if status == "completed":
            result["file_path"] = torrent.get("save_path")

        return result

    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Return completed torrents in the configured category.

        Returns a list of dicts with keys: job_id, file_path, title.
        """
        params: Dict[str, Any] = {"filter": "completed"}
        if self.default_category:
            params["category"] = self.default_category

        response = self._request("get", "/torrents/info", params=params)
        if response is None:
            return []

        return [
            {
                "job_id": torrent.get("hash"),
                "file_path": torrent.get("save_path"),
                "title": torrent.get("name"),
            }
            for torrent in response.json()
            if torrent.get("state", "") in QBITTORRENT_COMPLETED_STATES
        ]

    def delete(self, job_id: str, delete_files: bool = False) -> bool:
        """
        Remove a torrent, optionally deleting downloaded files from disk.

        Returns True on success, False if the request failed.
        """
        response = self._request(
            "post",
            "/torrents/delete",
            data={"hashes": job_id, "deleteFiles": str(delete_files).lower()},
        )
        if response is None:
            return False

        logger.info(f"[qBittorrent] Deleted torrent {job_id} (delete_files={delete_files})")
        return True

    def test_connection(self) -> Dict[str, Any]:
        """Test connectivity by fetching the application version."""
        try:
            response = self._request("get", "/app/version")
            if response is None:
                return {
                    "success": False,
                    "message": "Could not connect to qBittorrent — check URL and credentials",
                }

            version = response.text.strip()
            return {
                "success": True,
                "message": f"Connection successful — qBittorrent {version}",
                "version": version,
            }

        except Exception as e:
            logger.error(f"qBittorrent connection test error: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {e}"}

    def _resolve_hash_from_url(self, url: str) -> Optional[str]:
        """
        Extract the torrent hash from a magnet link's xt=urn:btih parameter.

        Returns None for non-magnet URLs (e.g. .torrent file URLs).
        """
        if not url.startswith("magnet:"):
            return None
        query = url[len("magnet:?") :] if url.startswith("magnet:?") else url[len("magnet:") :]
        for part in query.split("&"):
            if part.startswith("xt=urn:btih:"):
                return part.split(":")[-1].lower()
        return None

    def close(self) -> None:
        """Close the underlying HTTP session and release network resources."""
        self._session.close()
        self._authenticated = False

    def __enter__(self) -> "QBittorrentClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
