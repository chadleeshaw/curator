"""
NZBGet download client implementation.
Handles NZB submissions and status tracking for NZBGet via JSON-RPC API.

API Reference: https://nzbget.com/documentation/api/
  - listgroups: https://nzbget.com/documentation/api/listgroups
  - history: https://nzbget.com/documentation/api/history
  - append: https://nzbget.com/documentation/api/append
  - editqueue: https://nzbget.com/documentation/api/editqueue
"""

import base64
import logging
from typing import Any, Dict, List, Optional

import requests

from core.constants.app import HTTP_REQUEST_TIMEOUT
from core.constants.download_clients import (
    NZBGET_DOWNLOADING_STATUSES,
    NZBGET_HISTORY_STATUS_MESSAGES,
    NZBGET_POST_PROCESSING_STATUSES,
)
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
        """Make JSON-RPC API call to NZBGet."""
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
                timeout=HTTP_REQUEST_TIMEOUT,
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

    def _calculate_progress(self, group: Dict) -> int:
        """
        Calculate download progress percentage from listgroups fields.

        Uses DownloadedSizeMB and FileSizeMB (both in MiB) per NZBGet API.
        Note: There is no DownloadedSize (bytes) field — only DownloadedSizeMB.
        """
        downloaded_mb = group.get("DownloadedSizeMB", 0)
        file_size_mb = group.get("FileSizeMB", 1)
        return min(int(downloaded_mb / max(file_size_mb, 1) * 100), 100)

    def submit(self, nzb_url: str, title: str = None, category: str = None) -> str:
        """
        Submit an NZB URL to NZBGet via the append API method.

        Per NZBGet API: append(Filename, Content, Category, Priority, ...)
        - Filename: display name with .nzb extension
        - Content: the URL to fetch the NZB from

        Args:
            nzb_url: URL to NZB file
            title: Optional title for the job (sanitized to prevent subfolder issues)
            category: Optional category (determines download folder)

        Returns:
            Job ID (NZBID), or None on failure
        """
        try:
            nzb_name = title or "download"

            # Sanitize title: replace path separators and limit length
            nzb_name = nzb_name.replace("/", "-").replace("\\", "-").strip()
            if len(nzb_name) > 100:
                nzb_name = nzb_name[:100].strip()

            # NZBGet append params: (Filename, Content, Category, Priority, AddToTop, AddPaused)
            # Filename = descriptive name with .nzb extension
            # Content = URL to fetch the NZB from
            params = [
                nzb_name + ".nzb",  # Filename
                nzb_url,  # Content (URL)
                category or "",  # Category
                50,  # Priority (high)
                False,  # AddToTop
                False,  # AddPaused
            ]
            result = self._api_call("append", params)

            if isinstance(result, (int, float)) and result > 0:
                job_id = str(int(result))
                logger.info(f"[NZBGet] Submitted URL: {title or nzb_url} -> {job_id}")
                return job_id
            else:
                logger.error(f"[NZBGet] URL submission failed: {result}")
                return None

        except Exception as e:
            logger.error(f"[NZBGet] Error submitting URL: {e}")
            return None

    def submit_content(self, nzb_content: str, title: str = None, category: str = None) -> Optional[str]:
        """
        Submit NZB content directly to NZBGet via base64-encoded content.

        Per NZBGet API: append(Filename, Content, Category, Priority, ...)
        - Filename: display name with .nzb extension
        - Content: base64-encoded NZB XML

        Args:
            nzb_content: Raw NZB XML content as string
            title: Optional title for the job
            category: Optional category for download client

        Returns:
            Job ID (NZBID), or None if submission failed
        """
        try:
            nzb_name = title or "download"
            nzb_name = nzb_name.replace("/", "-").replace("\\", "-").strip()
            if len(nzb_name) > 100:
                nzb_name = nzb_name[:100].strip()

            nzb_b64 = base64.b64encode(nzb_content.encode("utf-8")).decode("ascii")

            params = [
                nzb_name + ".nzb",  # Filename
                nzb_b64,  # Content (base64-encoded NZB)
                category or "",  # Category
                50,  # Priority (high)
                False,  # AddToTop
                False,  # AddPaused
                "",  # DupeKey
                0,  # DupeScore
                "ALL",  # DupeMode
            ]
            result = self._api_call("append", params)

            if isinstance(result, (int, float)) and result > 0:
                job_id = str(int(result))
                logger.info(f"[NZBGet] Submitted NZB content: {title} -> {job_id}")
                return job_id
            else:
                logger.error(f"[NZBGet] Content submission failed: {result}")
                return None

        except Exception as e:
            logger.error(f"[NZBGet] Error submitting NZB content: {e}")
            return None

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get download status for a job.

        Checks the active queue (listgroups) first, then falls back to
        history for completed/failed items that have left the queue.

        NZBGet listgroups Status values (active queue only):
            QUEUED, PAUSED, DOWNLOADING, FETCHING, PP_QUEUED,
            LOADING_PARS, VERIFYING_SOURCES, REPAIRING, VERIFYING_REPAIRED,
            RENAMING, UNPACKING, MOVING, EXECUTING_SCRIPT, PP_FINISHED

        NZBGet history Status values (composite):
            SUCCESS/ALL, SUCCESS/UNPACK, FAILURE/PAR, FAILURE/UNPACK,
            WARNING/PASSWORD, DELETED/MANUAL, etc.

        Args:
            job_id: NZBGet NZBID

        Returns:
            Dict with status info matching DownloadClient interface
        """
        try:
            # First check active queue (listgroups)
            result = self._api_call("listgroups", [0])

            if isinstance(result, list):
                for group in result:
                    if str(group.get("NZBID")) == job_id:
                        return self._parse_queue_status(job_id, group)

            # Not in queue — check history for completed/failed items
            history = self._api_call("history", [False])

            if isinstance(history, list):
                for item in history:
                    if str(item.get("NZBID")) == job_id:
                        return self._parse_history_status(job_id, item)

            return {"status": "unknown", "progress": 0}

        except Exception as e:
            logger.error(f"[NZBGet] Error getting status for {job_id}: {e}")
            return {"status": "error", "progress": 0}

    def _parse_queue_status(self, job_id: str, group: Dict) -> Dict[str, Any]:
        """
        Parse status from a listgroups queue item.

        Per NZBGet API, listgroups items use simple Status values:
        QUEUED, PAUSED, DOWNLOADING, FETCHING, PP_QUEUED, LOADING_PARS,
        VERIFYING_SOURCES, REPAIRING, VERIFYING_REPAIRED, RENAMING,
        UNPACKING, MOVING, POST_UNPACK_RENAMING, EXECUTING_SCRIPT, PP_FINISHED

        Note: listgroups does NOT have Message, CriticalMessage, or DownloadedSize fields.
        Progress uses DownloadedSizeMB / FileSizeMB (both in MiB).
        """
        status_str = group.get("Status", "")

        if status_str in NZBGET_DOWNLOADING_STATUSES:
            return {
                "status": "downloading",
                "progress": self._calculate_progress(group),
                "size": group.get("FileSizeMB"),
            }

        if status_str in NZBGET_POST_PROCESSING_STATUSES:
            # Post-processing stages — download is complete, processing in progress
            post_info = group.get("PostInfoText", "")
            return {
                "status": "downloading",
                "progress": self._calculate_progress(group),
                "extra_status": f"Post-processing: {post_info}" if post_info else "Post-processing",
            }

        # QUEUED, PAUSED, or any other queue status
        return {
            "status": "pending",
            "progress": self._calculate_progress(group),
        }

    def _parse_history_status(self, job_id: str, item: Dict) -> Dict[str, Any]:
        """
        Parse status from a history item.

        Per NZBGet API, history Status is a composite string like:
        SUCCESS/ALL, SUCCESS/UNPACK, FAILURE/PAR, FAILURE/UNPACK,
        WARNING/PASSWORD, WARNING/HEALTH, DELETED/MANUAL, etc.
        """
        status_str = item.get("Status", "")
        dest_dir = item.get("FinalDir") or item.get("DestDir", "")

        # SUCCESS/* — download completed successfully
        if status_str.startswith("SUCCESS"):
            return {
                "status": "completed",
                "progress": 100,
                "file_path": dest_dir,
            }

        # Check for encryption/password issues via UnpackStatus field
        unpack_status = item.get("UnpackStatus", "")
        if unpack_status == "PASSWORD" or "PASSWORD" in status_str:
            logger.warning(
                f"[NZBGet] Job {job_id} failed: password protected. "
                f"Status: {status_str}, UnpackStatus: {unpack_status}"
            )
            return {
                "status": "failed",
                "progress": 0,
                "error": "Archive is encrypted or password protected",
                "encrypted": True,
            }

        # FAILURE/*, WARNING/*, DELETED/* — download failed
        error_msg = self._build_error_message(status_str)
        logger.warning(f"[NZBGet] Job {job_id} failed: {status_str} - {error_msg}")
        return {
            "status": "failed",
            "progress": 0,
            "error": error_msg,
        }

    @staticmethod
    def _build_error_message(status_str: str) -> str:
        """Build human-readable error message from history composite status."""
        if status_str in NZBGET_HISTORY_STATUS_MESSAGES:
            return NZBGET_HISTORY_STATUS_MESSAGES[status_str]

        # Fallback: format the composite status
        parts = status_str.split("/", 1)
        if len(parts) == 2:
            return f"Download {parts[0].lower()}: {parts[1].lower()}"
        return f"Download failed: {status_str}"

    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of completed downloads from history.

        Completed items appear in NZBGet's history (not listgroups queue).
        Items with SUCCESS/* status are considered completed.

        Returns:
            List of completed download info
        """
        completed = []

        try:
            result = self._api_call("history", [False])

            if not isinstance(result, list):
                return completed

            for item in result:
                status = item.get("Status", "")
                if status.startswith("SUCCESS"):
                    dest_dir = item.get("FinalDir") or item.get("DestDir", "")
                    completed.append(
                        {
                            "job_id": str(item.get("NZBID")),
                            "file_path": dest_dir,
                            "title": item.get("Name", item.get("NZBName", "")),
                        }
                    )

        except Exception as e:
            logger.error(f"[NZBGet] Error getting completed downloads: {e}")

        return completed

    def delete(self, job_id: str) -> bool:
        """
        Delete a job from NZBGet (queue or history).

        Uses v18+ editqueue signature: editqueue(Command, Param, IDs).
        Tries queue first, then history.

        Args:
            job_id: NZBID to delete

        Returns:
            True if successfully deleted
        """
        try:
            nzbid = int(job_id)

            # Try deleting from queue first (removes without adding to history)
            result = self._api_call("editqueue", ["GroupFinalDelete", "", [nzbid]])

            if result:
                logger.info(f"[NZBGet] Deleted job {job_id} from queue")
                return True

            # If not in queue, try deleting from history
            result = self._api_call("editqueue", ["HistoryFinalDelete", "", [nzbid]])

            if result:
                logger.info(f"[NZBGet] Deleted job {job_id} from history")
                return True

            logger.warning(f"[NZBGet] Could not delete job {job_id} — not found in queue or history")
            return False

        except Exception as e:
            logger.error(f"[NZBGet] Error deleting job {job_id}: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to NZBGet."""
        try:
            version = self._api_call("version")

            if not version:
                return {
                    "success": False,
                    "message": "No response from NZBGet — check your API URL, username, and password",
                }

            if isinstance(version, str):
                return {
                    "success": True,
                    "message": f"Connection successful — NZBGet v{version}",
                    "version": version,
                }

            # Try getting status as fallback
            status = self._api_call("status")
            if status and isinstance(status, dict):
                nzbget_version = status.get("Version", "Unknown")
                return {
                    "success": True,
                    "message": f"Connection successful — NZBGet v{nzbget_version}",
                    "version": nzbget_version,
                }

            return {
                "success": False,
                "message": "Unexpected response from NZBGet",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timeout — check your API URL and network",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Connection failed — check your API URL and network",
            }
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed — check your username and password",
                }
            return {
                "success": False,
                "message": f"HTTP error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"[NZBGet] Connection test error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }
