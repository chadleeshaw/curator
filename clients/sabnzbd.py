"""
SABnzbd download client implementation.
Handles NZB submissions and status tracking for SABnzbd.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import requests

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

    def _parse_wait_time(self, extra_status: str) -> Optional[int]:
        """
        Parse wait time from SABnzbd extra_status field.

        SABnzbd returns messages like:
        - "WAIT 3600 seconds until retry"
        - "WAIT 13887 seconds until retry"

        Args:
            extra_status: The extra_status field from SABnzbd queue slot

        Returns:
            Wait time in seconds, or None if not a WAIT message
        """
        if not extra_status:
            return None

        # Pattern: "WAIT X seconds until retry"
        match = re.search(r"WAIT\s+(\d+)\s+seconds?", extra_status, re.IGNORECASE)
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
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"SABnzbd API error: {e}")
            return {}

    def submit(self, nzb_url: str, title: str = None, category: str = None) -> str:
        """
        Submit an NZB URL to SABnzbd.

        Args:
            nzb_url: URL to NZB file
            title: Optional title for the job (sanitized to prevent subfolder issues)
            category: Optional category (determines download folder)

        Returns:
            Job ID (NZO ID)
        """
        try:
            params = {
                "mode": "addurl",
                "name": nzb_url,
            }

            if title:
                # Sanitize title: replace path separators and limit length
                sanitized_title = title.replace("/", "-").replace("\\", "-").strip()
                if len(sanitized_title) > 100:
                    sanitized_title = sanitized_title[:100].strip()
                params["nzbname"] = sanitized_title

            if category:
                params["cat"] = category

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

    def submit_content(self, nzb_content: str, title: str = None, category: str = None) -> Optional[str]:
        """
        Submit NZB content directly to SABnzbd via file upload.

        Uses SABnzbd's addfile API mode to upload NZB XML content directly,
        avoiding the provider URL fetch that would otherwise hit rate limits.

        Args:
            nzb_content: Raw NZB XML content as string
            title: Optional title for the job
            category: Optional category for download client

        Returns:
            Job ID (NZO ID), or None if submission failed
        """
        try:
            params = {
                "mode": "addfile",
                "output": "json",
                "apikey": self.api_key,
            }

            if title:
                sanitized_title = title.replace("/", "-").replace("\\", "-").strip()
                if len(sanitized_title) > 100:
                    sanitized_title = sanitized_title[:100].strip()
                params["nzbname"] = sanitized_title

            if category:
                params["cat"] = category

            # Upload NZB content as multipart file
            nzb_filename = f"{title or 'download'}.nzb"
            files = {
                "nzbfile": (nzb_filename, nzb_content.encode("utf-8"), "application/x-nzb"),
            }

            url = f"{self.api_url}/api"
            response = requests.post(url, params=params, files=files, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("status") is True:
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

            response = self._api_call("queue")

            queue = response.get("queue", {})
            slots = queue.get("slots", [])
            logger.debug(f"[SABnzbd] Queue has {len(slots)} active items")

            if slots:
                logger.debug(f"[SABnzbd] Queue slots: {[s.get('nzo_id') for s in slots]}")

            for slot in slots:
                if slot.get("nzo_id") == job_id:
                    logger.debug(f"[SABnzbd] Found {job_id} in queue")

                    # Check for paused job due to encryption
                    slot_status = slot.get("status", "")
                    extra_status = slot.get("extra_status", "")
                    msg = slot.get("msg", "")
                    status_line = slot.get("status_line", "")

                    # Check if paused due to encryption
                    encryption_indicators = [
                        "encrypted rar",
                        "encrypted archive",
                        "archive requires a password",
                        "password protected",
                        "all passwords were tried",
                    ]

                    is_encrypted = slot_status == "Paused" and any(
                        indicator in text.lower()
                        for text in [extra_status, msg, status_line]
                        for indicator in encryption_indicators
                    )

                    if is_encrypted:
                        logger.warning(
                            f"[SABnzbd] Job {job_id} is paused due to encryption/password protection. "
                            f"Status: {slot_status}, Extra: {extra_status}, Msg: {msg}"
                        )
                        return {
                            "status": "failed",
                            "progress": 0,
                            "error": "Archive is encrypted or password protected",
                            "encrypted": True,
                        }

                    # Check for rate limit WAIT status
                    wait_time = self._parse_wait_time(extra_status)

                    if wait_time:
                        # Provider rate limited - SABnzbd is waiting to retry
                        logger.warning(
                            f"[SABnzbd] Job {job_id} is rate limited by provider. "
                            f"Waiting {wait_time} seconds (~{wait_time / 3600:.1f} hours) before retry. "
                            f"Extra status: {extra_status}"
                        )
                        return {
                            "status": "pending",  # Keep as pending, not failed
                            "progress": 0,
                            "rate_limited": True,
                            "wait_time": wait_time,
                            "message": f"Provider rate limit: waiting {wait_time}s (~{wait_time / 3600:.1f}h)",
                        }

                    status = "downloading" if slot.get("status") == "Downloading" else "pending"
                    return {
                        "status": status,
                        "progress": int(float(slot.get("percentage", 0))),
                        "size": slot.get("size"),
                        "time_left": slot.get("timeleft"),
                    }

            # Check history for completed/failed downloads
            logger.debug("[SABnzbd] Job not in queue, checking history...")
            response = self._api_call("history")

            history = response.get("history", {})
            slots = history.get("slots", [])
            logger.debug(f"[SABnzbd] History has {len(slots)} items")

            if slots:
                logger.debug(f"[SABnzbd] History slots: {[s.get('nzo_id') for s in slots]}")

            for slot in slots:
                if slot.get("nzo_id") == job_id:
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
                    elif "fail" in slot_status or "abort" in slot_status:
                        fail_message = slot.get("fail_message", "No details available")

                        # Extract additional failure details from stage_log
                        stage_log = slot.get("stage_log", [])
                        failure_details = []
                        for stage in stage_log:
                            stage_name = stage.get("name", "")
                            actions = stage.get("actions", [])
                            for action in actions:
                                if any(
                                    keyword in action.lower()
                                    for keyword in ["missing", "failed", "error", "incomplete"]
                                ):
                                    failure_details.append(f"{stage_name}: {action}")

                        # Build comprehensive error message
                        error_parts = [f"Download {slot_status}: {fail_message}"]
                        if failure_details:
                            error_parts.append(" | ".join(failure_details))
                        error_message = " - ".join(error_parts)

                        logger.warning(f"[SABnzbd] Job {job_id} failed: {error_message}")

                        # Check if failure was due to encryption
                        encryption_indicators = [
                            "encrypted rar",
                            "encrypted archive",
                            "archive requires a password",
                            "password protected",
                            "unpacking failed",
                            "all passwords were tried",
                        ]

                        is_encrypted = any(indicator in fail_message.lower() for indicator in encryption_indicators)

                        return {
                            "status": "failed",
                            "progress": 0,
                            "error": error_message,
                            "encrypted": is_encrypted,
                        }
                    else:
                        logger.warning(f"[SABnzbd] Job {job_id} has unknown status: {slot_status}")
                        return {
                            "status": "unknown",
                            "progress": int(float(slot.get("percentage", 0))),
                        }

            # Job not found - likely deleted or expired from history
            logger.debug(f"[SABnzbd] Job {job_id} not found in queue or history (may have been deleted)")
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
        except Exception as e:
            logger.error(f"SABnzbd connection test error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }
