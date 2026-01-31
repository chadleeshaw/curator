"""
NZBGet download client implementation.
Handles NZB submissions and status tracking for NZBGet via JSON-RPC API.
"""

import logging
from typing import Any, Dict, List

import requests

from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


class NZBGetClient(DownloadClient):
    """Download client for NZBGet"""

    def __init__(self, config):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://localhost:6789")
        self.username = config.get("username", "nzbget")
        self.password = config.get("password")

        if not self.password:
            raise ValueError("NZBGet client requires password")

    def _api_call(self, method: str, params: List = None) -> Dict[str, Any]:
        """Make JSON-RPC API call to NZBGet"""
        if params is None:
            params = []

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }

        try:
            url = f"{self.api_url}/jsonrpc"
            response = requests.post(
                url,
                json=payload,
                auth=(self.username, self.password),
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result and result["error"] is not None:
                logger.error(f"NZBGet API error: {result['error']}")
                return {}

            return result.get("result", {})

        except Exception as e:
            logger.error(f"NZBGet API error: {e}")
            return {}

    def submit(self, nzb_url: str, title: str = None, category: str = None) -> str:
        """
        Submit an NZB URL to NZBGet.

        Args:
            nzb_url: URL to NZB file
            title: Optional title for the job (sanitized to prevent subfolder issues)
            category: Optional category (determines download folder)

        Returns:
            Job ID (NZBID)
        """
        try:
            # NZBGet uses AddUrl method to add NZB from URL
            nzb_name = title or nzb_url.split("/")[-1]

            # Sanitize title: replace path separators and limit length
            nzb_name = nzb_name.replace("/", "-").replace("\\", "-").strip()
            if len(nzb_name) > 100:
                nzb_name = nzb_name[:100].strip()

            params = [
                nzb_url,
                nzb_name,
                category or "",
                50,
                False,
                False,
            ]  # url, name, category, priority, addToTop, addPaused
            result = self._api_call("append", params)

            if isinstance(result, (int, float)) and result > 0:
                job_id = str(int(result))
                logger.info(f"Submitted to NZBGet: {title or nzb_url} -> {job_id}")
                return job_id
            else:
                logger.error(f"NZBGet submission failed: {result}")
                return None

        except Exception as e:
            logger.error(f"Error submitting to NZBGet: {e}")
            return None

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get download status for a job.

        Args:
            job_id: NZBGet NZBID

        Returns:
            Dict with status info
        """
        try:
            # Get list of downloads
            result = self._api_call("listgroups", [0])

            if not isinstance(result, list):
                return {"status": "unknown", "progress": 0}

            for group in result:
                if str(group.get("NZBID")) == job_id:
                    status_str = group.get("Status", "")

                    # Check for encryption/password protection in failed downloads
                    if status_str in ["FAILURE", "WARNING"]:
                        failure_message = group.get("Message", "")
                        critical_message = group.get("CriticalMessage", "")
                        unpack_status = group.get("UnpackStatus", "")

                        encryption_indicators = [
                            "encrypted",
                            "password",
                            "password protected",
                            "archive requires a password",
                            "unpack failed",
                            "all passwords were tried",
                        ]

                        combined_messages = f"{failure_message} {critical_message} {unpack_status}".lower()
                        is_encrypted = any(indicator in combined_messages for indicator in encryption_indicators)

                        if is_encrypted:
                            logger.warning(
                                f"[NZBGet] Job {job_id} failed due to encryption/password protection. "
                                f"Status: {status_str}, Message: {failure_message}, Unpack: {unpack_status}"
                            )
                            return {
                                "status": "failed",
                                "progress": 0,
                                "error": f"{failure_message or unpack_status or 'Archive is encrypted or password protected'}",
                                "encrypted": True,
                            }

                        # Generic failure
                        logger.warning(f"[NZBGet] Job {job_id} failed: {status_str} - {failure_message}")
                        return {
                            "status": "failed",
                            "progress": 0,
                            "error": failure_message or "Download failed",
                        }

                    if status_str == "SUCCESS":
                        return {
                            "status": "completed",
                            "progress": 100,
                            "file_path": group.get("DestDir"),
                        }
                    elif status_str == "DOWNLOADING":
                        return {
                            "status": "downloading",
                            "progress": int(
                                group.get("DownloadedSize", 0) / max(group.get("FileSizeMB", 1) * 1024 * 1024, 1) * 100
                            ),
                            "size": group.get("FileSizeMB"),
                        }
                    else:
                        return {
                            "status": "pending",
                            "progress": int(
                                group.get("DownloadedSize", 0) / max(group.get("FileSizeMB", 1) * 1024 * 1024, 1) * 100
                            ),
                        }

            return {"status": "unknown", "progress": 0}

        except Exception as e:
            logger.error(f"Error getting NZBGet status: {e}")
            return {"status": "error", "progress": 0}

    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of completed downloads not yet processed.

        Returns:
            List of completed download info
        """
        completed = []

        try:
            result = self._api_call("listgroups", [0])

            if not isinstance(result, list):
                return completed

            for group in result:
                if group.get("Status") == "SUCCESS":
                    completed.append(
                        {
                            "job_id": str(group.get("NZBID")),
                            "file_path": group.get("DestDir"),
                            "title": group.get("NZBName"),
                        }
                    )

        except Exception as e:
            logger.error(f"Error getting completed downloads: {e}")

        return completed

    def delete(self, job_id: str) -> bool:
        """
        Delete a job from NZBGet (queue or history).

        Args:
            job_id: NZBID to delete

        Returns:
            True if successfully deleted
        """
        try:
            # Try deleting from history first
            result = self._api_call("editqueue", ["HistoryDelete", 0, "", [int(job_id)]])

            if result:
                logger.info(f"[NZBGet] Deleted job {job_id} from history")
                return True

            # If not in history, try deleting from queue
            result = self._api_call("editqueue", ["GroupDelete", 0, "", [int(job_id)]])

            if result:
                logger.info(f"[NZBGet] Deleted job {job_id} from queue")
                return True

            logger.warning(f"[NZBGet] Could not delete job {job_id} - not found")
            return False

        except Exception as e:
            logger.error(f"[NZBGet] Error deleting job {job_id}: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to NZBGet.

        Returns:
            Dict with success status and message
        """
        try:
            # Use the version endpoint as a lightweight test
            version = self._api_call("version")

            if not version:
                return {
                    "success": False,
                    "message": "No response from NZBGet - check your API URL, username, and password",
                }

            # NZBGet returns version as a string
            if isinstance(version, str):
                return {
                    "success": True,
                    "message": f"Connection successful - NZBGet v{version}",
                    "version": version,
                }

            # Try getting status as fallback
            status = self._api_call("status")
            if status and isinstance(status, dict):
                nzbget_version = status.get("Version", "Unknown")
                return {
                    "success": True,
                    "message": f"Connection successful - NZBGet v{nzbget_version}",
                    "version": nzbget_version,
                }

            return {
                "success": False,
                "message": "Unexpected response from NZBGet",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timeout - check your API URL and network",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Connection failed - check your API URL and network",
            }
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed - check your username and password",
                }
            return {
                "success": False,
                "message": f"HTTP error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"NZBGet connection test error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }
