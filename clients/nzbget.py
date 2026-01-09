"""
NZBGet download client implementation.
Handles NZB submissions and status tracking for NZBGet via JSON-RPC API.
"""
import logging
from typing import Any, Dict, List

import requests

from core.bases import DownloadClient

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

            params = [nzb_url, nzb_name, category or "", 50, False, False]  # url, name, category, priority, addToTop, addPaused
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
