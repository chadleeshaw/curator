import logging
from typing import Any, Dict, List

import requests

from core.bases import DownloadClient

logger = logging.getLogger(__name__)


class SABnzbdClient(DownloadClient):
    """Download client for SABnzbd"""

    def __init__(self, config):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://localhost:8080")
        self.api_key = config.get("api_key")

        if not self.api_key:
            raise ValueError("SABnzbd client requires api_key")

    def _api_call(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make API call to SABnzbd"""
        if params is None:
            params = {}

        params["action"] = action
        params["output"] = "json"
        params["apikey"] = self.api_key

        try:
            url = f"{self.api_url}/api"
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SABnzbd API error: {e}")
            return {}

    def submit(self, nzb_url: str, title: str = None) -> str:
        """
        Submit an NZB URL to SABnzbd.

        Args:
            nzb_url: URL to NZB file
            title: Optional title for the job

        Returns:
            Job ID (NZO ID)
        """
        try:
            params = {
                "mode": "addurl",
                "name": nzb_url,
            }

            if title:
                params["nzbname"] = title

            response = self._api_call("add", params)

            if response.get("status") is True:
                job_id = response.get("nzo_ids", [None])[0]
                logger.info(f"Submitted to SABnzbd: {title or nzb_url} -> {job_id}")
                return job_id
            else:
                logger.error(f"SABnzbd submission failed: {response}")
                return None

        except Exception as e:
            logger.error(f"Error submitting to SABnzbd: {e}")
            return None

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get download status for a job.

        Args:
            job_id: SABnzbd NZO ID

        Returns:
            Dict with status info
        """
        try:
            logger.debug(f"[SABnzbd] Checking status for job_id: {job_id}")

            response = self._api_call("queue", {"mode": "queue"})

            queue = response.get("queue", {})
            slots = queue.get("slots", [])
            logger.debug(f"[SABnzbd] Queue has {len(slots)} active items")

            if slots:
                logger.debug(
                    f"[SABnzbd] Queue slots: {[s.get('nzo_id') for s in slots]}"
                )

            for slot in slots:
                if slot.get("nzo_id") == job_id:
                    logger.info(f"[SABnzbd] Found {job_id} in queue")
                    status = (
                        "downloading"
                        if slot.get("status") == "Downloading"
                        else "pending"
                    )
                    return {
                        "status": status,
                        "progress": int(float(slot.get("percentage", 0))),
                        "size": slot.get("size"),
                        "time_left": slot.get("timeleft"),
                    }

            # Check history for completed/failed downloads
            logger.debug("[SABnzbd] Job not in queue, checking history...")
            response = self._api_call("history", {"mode": "history"})

            history = response.get("history", {})
            slots = history.get("slots", [])
            logger.debug(f"[SABnzbd] History has {len(slots)} items")

            if slots:
                logger.debug(
                    f"[SABnzbd] History slots: {[s.get('nzo_id') for s in slots]}"
                )

            for slot in slots:
                if slot.get("nzo_id") == job_id:
                    slot_status = slot.get("status", "Unknown").lower()
                    logger.info(
                        f"[SABnzbd] Found {job_id} in history with status: {slot_status}"
                    )
                    logger.info(f"[SABnzbd] History slot: {slot}")

                    if "completed" in slot_status:
                        logger.info(
                            f"[SABnzbd] Job {job_id} completed, file_path: {slot.get('storage')}"
                        )
                        return {
                            "status": "completed",
                            "progress": 100,
                            "file_path": slot.get("storage"),
                        }
                    elif "fail" in slot_status or "abort" in slot_status:
                        logger.warning(f"[SABnzbd] Job {job_id} failed: {slot_status}")
                        return {
                            "status": "failed",
                            "progress": 0,
                            "error": f"Download {slot_status}: {slot.get('fail_message', 'No details available')}",
                        }
                    else:
                        logger.warning(
                            f"[SABnzbd] Job {job_id} has unknown status: {slot_status}"
                        )
                        return {
                            "status": "unknown",
                            "progress": int(float(slot.get("percentage", 0))),
                        }

            logger.warning(f"[SABnzbd] Job {job_id} not found in queue or history")
            return {"status": "unknown", "progress": 0}

        except Exception as e:
            logger.error(f"Error getting SABnzbd status: {e}")
            return {"status": "error", "progress": 0, "error": str(e)}

    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of completed downloads not yet processed.

        Returns:
            List of completed download info
        """
        completed = []

        try:
            response = self._api_call("history")
            history = response.get("history", {})
            slots = history.get("slots", [])

            for slot in slots:
                # Only include successfully completed downloads
                if slot.get("status") == "Completed":
                    completed.append(
                        {
                            "job_id": slot.get("nzo_id"),
                            "file_path": slot.get("storage"),
                            "title": slot.get("name"),
                        }
                    )

        except Exception as e:
            logger.error(f"Error getting completed downloads: {e}")

        return completed
