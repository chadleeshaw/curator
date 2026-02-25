"""
SABnzbd download client implementation.
Handles NZB submissions and status tracking for SABnzbd.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union

import httpx

from core.constants.app import HTTP_REQUEST_TIMEOUT
from core.constants.download_clients import (
    ENCRYPTION_INDICATORS,
    ENCRYPTION_INDICATORS_HISTORY,
)
from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


class SABnzbdClient(DownloadClient):
    """Download client for SABnzbd"""

    def __init__(self, config):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://localhost:8080")
        self.api_key = config.get("api_key")

        if not self.api_key:
            raise ValueError("SABnzbd client requires api_key")

    def _parse_wait_time(self, text: str) -> Optional[int]:
        """
        Parse wait time from SABnzbd labels or status text.

        SABnzbd returns messages like:
        - "WAIT 3600 seconds until retry"
        - "WAIT 13887 seconds until retry"

        Args:
            text: Text from SABnzbd labels array or status field

        Returns:
            Wait time in seconds, or None if not a WAIT message
        """
        if not text:
            return None

        # Pattern: "WAIT X seconds until retry" or "WAIT X sec"
        match = re.search(r"WAIT\s+(\d+)\s*(?:seconds?|sec)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

    def _api_call(self, mode: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make API call to SABnzbd"""
        if params is None:
            params = {}

        # SABnzbd API uses 'mode' parameter, not 'action'
        # Only set mode if not already present (allows caller to override)
        if "mode" not in params:
            params["mode"] = mode
        params["output"] = "json"
        params["apikey"] = self.api_key

        try:
            url = f"{self.api_url}/api"
            response = httpx.get(url, params=params, timeout=HTTP_REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SABnzbd API error: {e}")
            return {}

    def submit(self, url: str, title: str = None, category: str = None) -> str:
        """
        Submit an NZB URL to SABnzbd.

        Args:
            url: URL to NZB file
            title: Optional title for the job (sanitized to prevent subfolder issues)
            category: Optional category (determines download folder)

        Returns:
            Job ID (NZO ID)
        """
        try:
            params = {"mode": "addurl", "name": url}
            if title:
                params["nzbname"] = self._sanitize_title(title)
            if category:
                params["cat"] = category

            response = self._api_call("add", params)

            if response.get("status"):
                job_id = response.get("nzo_ids", [None])[0]
                logger.info(f"Submitted to SABnzbd: {title or url} -> {job_id}")
                return job_id
            else:
                logger.error(f"SABnzbd submission failed: {response}")
                return None

        except Exception as e:
            logger.error(f"Error submitting to SABnzbd: {e}")
            return None

    def submit_content(  # pylint: disable=arguments-renamed
        self, nzb_content: Union[str, bytes], title: str = None, category: str = None
    ) -> Optional[str]:
        """
        Submit NZB content directly to SABnzbd via file upload.

        Uses SABnzbd's addfile API mode to upload NZB XML content directly,
        avoiding the provider URL fetch that would otherwise hit rate limits.

        Args:
            nzb_content: Raw NZB XML content as string or bytes
            title: Optional title for the job
            category: Optional category for download client

        Returns:
            Job ID (NZO ID), or None if submission failed
        """
        try:
            params = {"mode": "addfile", "output": "json", "apikey": self.api_key}
            if title:
                params["nzbname"] = self._sanitize_title(title)
            if category:
                params["cat"] = category

            nzb_filename = f"{title or 'download'}.nzb"
            files = {
                "nzbfile": (
                    nzb_filename,
                    self._to_bytes(nzb_content),
                    "application/x-nzb",
                )
            }

            url = f"{self.api_url}/api"
            response = httpx.post(url, params=params, files=files, timeout=HTTP_REQUEST_TIMEOUT)
            response.raise_for_status()
            result = response.json()

            if result.get("status"):
                job_id = result.get("nzo_ids", [None])[0]
                logger.info(f"Submitted NZB content to SABnzbd: {title} -> {job_id}")
                return job_id
            else:
                logger.error(f"SABnzbd content submission failed: {result}")
                return None

        except Exception as e:
            logger.error(f"Error submitting NZB content to SABnzbd: {e}")
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

            # Check queue first
            queue_status = self._check_queue_status(job_id)
            if queue_status:
                return queue_status

            # Not in queue, check history
            history_status = self._check_history_status(job_id)
            if history_status:
                return history_status

            # Job not found
            logger.debug(f"[SABnzbd] Job {job_id} not found in queue or history (may have been deleted)")
            return {"status": "unknown", "progress": 0}

        except Exception as e:
            logger.error(f"Error getting SABnzbd status: {e}")
            return {"status": "error", "progress": 0, "error": str(e)}

    def _check_queue_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Check if job is in the active queue and return its status."""
        response = self._api_call("queue")
        queue = response.get("queue", {})
        slots = queue.get("slots", [])
        logger.debug(f"[SABnzbd] Queue has {len(slots)} active items")

        if slots:
            logger.debug(f"[SABnzbd] Queue slots: {[s.get('nzo_id') for s in slots]}")

        for slot in slots:
            if slot.get("nzo_id") == job_id:
                logger.debug(f"[SABnzbd] Found {job_id} in queue: {slot}")
                return self._process_queue_slot(job_id, slot)

        return None

    def _process_queue_slot(self, job_id: str, slot: Dict[str, Any]) -> Dict[str, Any]:
        """Process a queue slot and determine its status."""
        slot_status = slot.get("status", "")
        labels = slot.get("labels", [])
        msg = slot.get("msg", "")

        # Check for encryption (takes priority)
        encryption_status = self._check_encryption_status(job_id, slot_status, labels, msg)
        if encryption_status:
            return encryption_status

        # Check for rate limiting
        wait_text = self._extract_wait_text(labels, slot_status)
        if wait_text:
            rate_limit_status = self._check_rate_limit_status(job_id, wait_text, labels)
            if rate_limit_status:
                return rate_limit_status

        # Normal download status
        status = "downloading" if slot.get("status") == "Downloading" else "pending"
        return {
            "status": status,
            "progress": int(float(slot.get("percentage", 0))),
            "size": slot.get("size"),
            "time_left": slot.get("timeleft"),
        }

    def _check_encryption_status(
        self, job_id: str, slot_status: str, labels: list, msg: str
    ) -> Optional[Dict[str, Any]]:
        """Check if job is paused due to encryption."""
        all_text = " ".join(labels + [msg]).lower()
        is_encrypted = slot_status == "Paused" and any(indicator in all_text for indicator in ENCRYPTION_INDICATORS)

        if not is_encrypted:
            return None

        logger.warning(
            f"[SABnzbd] Job {job_id} is paused due to encryption/password protection. "
            f"Status: {slot_status}, Labels: {labels}, Msg: {msg}"
        )
        return {
            "status": "failed",
            "progress": 0,
            "error": "Archive is encrypted or password protected",
            "encrypted": True,
        }

    def _extract_wait_text(self, labels: list, slot_status: str) -> str:
        """Extract WAIT text from labels or status field."""
        for label in labels:
            if "WAIT" in label.upper():
                return label

        if "WAIT" in slot_status.upper():
            return slot_status

        return ""

    def _check_rate_limit_status(self, job_id: str, wait_text: str, labels: list) -> Optional[Dict[str, Any]]:
        """Check if job is rate limited and return status."""
        wait_time = self._parse_wait_time(wait_text)
        if not wait_time:
            return None

        logger.warning(
            f"[SABnzbd] Job {job_id} is rate limited by provider. "
            f"Waiting {wait_time} seconds (~{wait_time / 3600:.1f} hours) before retry. "
            f"Labels: {labels}"
        )
        return {
            "status": "pending",
            "progress": 0,
            "rate_limited": True,
            "wait_time": wait_time,
            "message": f"Provider rate limit: waiting {wait_time}s (~{wait_time / 3600:.1f}h)",
        }

    def _check_history_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Check if job is in history and return its status."""
        logger.debug("[SABnzbd] Job not in queue, checking history...")
        response = self._api_call("history")

        history = response.get("history", {})
        slots = history.get("slots", [])
        logger.debug(f"[SABnzbd] History has {len(slots)} items")

        if slots:
            logger.debug(f"[SABnzbd] History slots: {[s.get('nzo_id') for s in slots]}")

        for slot in slots:
            if slot.get("nzo_id") == job_id:
                return self._process_history_slot(job_id, slot)

        return None

    def _process_history_slot(self, job_id: str, slot: Dict[str, Any]) -> Dict[str, Any]:
        """Process a history slot and determine its final status."""
        slot_status = slot.get("status", "Unknown").lower()
        logger.info(f"[SABnzbd] Found {job_id} in history with status: {slot_status}")
        logger.info(f"[SABnzbd] History slot: {slot}")

        if "completed" in slot_status:
            logger.info(f"[SABnzbd] Job {job_id} completed, file_path: {slot.get('storage')}")
            return {
                "status": "completed",
                "progress": 100,
                "file_path": slot.get("storage"),
            }

        if "fail" in slot_status or "abort" in slot_status:
            return self._build_failure_status(job_id, slot, slot_status)

        logger.warning(f"[SABnzbd] Job {job_id} has unknown status: {slot_status}")
        return {
            "status": "unknown",
            "progress": int(float(slot.get("percentage", 0))),
        }

    def _build_failure_status(self, job_id: str, slot: Dict[str, Any], slot_status: str) -> Dict[str, Any]:
        """Build failure status with detailed error information."""
        fail_message = slot.get("fail_message", "No details available")
        failure_details = self._extract_failure_details(slot.get("stage_log", []))

        error_parts = [f"Download {slot_status}: {fail_message}"]
        if failure_details:
            error_parts.append(" | ".join(failure_details))
        error_message = " - ".join(error_parts)

        logger.warning(f"[SABnzbd] Job {job_id} failed: {error_message}")

        is_encrypted = any(indicator in fail_message.lower() for indicator in ENCRYPTION_INDICATORS_HISTORY)

        return {
            "status": "failed",
            "progress": 0,
            "error": error_message,
            "encrypted": is_encrypted,
        }

    def _extract_failure_details(self, stage_log: list) -> list:
        """Extract detailed failure information from stage log."""
        failure_details = []
        for stage in stage_log:
            stage_name = stage.get("name", "")
            actions = stage.get("actions", [])
            for action in actions:
                if any(keyword in action.lower() for keyword in ["missing", "failed", "error", "incomplete"]):
                    failure_details.append(f"{stage_name}: {action}")
        return failure_details

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

    def delete(self, job_id: str) -> bool:
        """
        Delete a job from SABnzbd (queue or history).

        Args:
            job_id: NZO ID to delete

        Returns:
            True if successfully deleted
        """
        try:
            # Try deleting from history first (most common case after completion)
            response = self._api_call("history", {"name": "delete", "value": job_id})

            if response.get("status"):
                logger.info(f"[SABnzbd] Deleted job {job_id} from history")
                return True

            # If not in history, try queue
            response = self._api_call("queue", {"name": "delete", "value": job_id})

            if response.get("status"):
                logger.info(f"[SABnzbd] Deleted job {job_id} from queue")
                return True

            logger.warning(f"[SABnzbd] Could not delete job {job_id} - not found")
            return False

        except Exception as e:
            logger.error(f"[SABnzbd] Error deleting job {job_id}: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to SABnzbd.

        Returns:
            Dict with success status and message
        """
        try:
            # Use the version endpoint as a lightweight test
            response = self._api_call("version")

            if not response:
                return {
                    "success": False,
                    "message": "No response from SABnzbd - check your API URL and key",
                }

            # Check if we got version info
            version = response.get("version")
            if version:
                return {
                    "success": True,
                    "message": f"Connection successful - SABnzbd v{version}",
                    "version": version,
                }

            # Try getting queue info as fallback
            queue_response = self._api_call("queue")
            if queue_response and "queue" in queue_response:
                return {
                    "success": True,
                    "message": "Connection successful",
                }

            return {
                "success": False,
                "message": "Unexpected response from SABnzbd",
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Connection timeout - check your API URL and network",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "message": "Connection failed - check your API URL and network",
            }
        except Exception as e:
            logger.error(f"SABnzbd connection test error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }
