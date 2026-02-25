"""
Status coordinator for download manager.
Handles status tracking: update_submission_status, retry_submission, and related helpers.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from core.constants.app import (
    MAX_DOWNLOAD_RETRIES,
    MAX_DOWNLOAD_RETRIES_IA,
)
from core.parsers import utc_now
from models.database import (
    DiscoveredIssue,
    DownloadSubmission,
)
from services.download.nzb_submit import submit_with_nzb_content
from services.download._coordinator_helpers import get_download_category

logger = logging.getLogger(__name__)


class StatusCoordinator:
    """Coordinate download status tracking and retry logic."""

    def __init__(
        self,
        download_clients: Dict[str, DownloadClient],
        nzb_cache_service: Optional[Any],
        default_category: Optional[str],
        submission_service: Any,
    ):
        """
        Initialize status coordinator.

        Args:
            download_clients: Dict of available download clients keyed by type
            nzb_cache_service: Optional NZB cache service for content caching
            default_category: Default download category
            submission_service: SubmissionService instance
        """
        self.download_clients = download_clients
        self.nzb_cache_service = nzb_cache_service
        self.default_category = default_category
        self.submission_service = submission_service

    # ------------------------------------------------------------------
    # Client lookup helpers
    # ------------------------------------------------------------------

    def _get_client_by_name(self, client_name: Optional[str]) -> DownloadClient:
        """
        Get a download client by its name.

        Args:
            client_name: Name of the client (from submission.client_name)

        Returns:
            DownloadClient instance, or default client if not found
        """
        if not client_name:
            return self.download_clients["default"]

        # Search through clients by name
        for client in self.download_clients.values():
            if client.name == client_name:
                return client

        # Fallback to default
        logger.debug(f"Client '{client_name}' not found by name, using default")
        return self.download_clients["default"]

    def _submit_with_nzb_content(
        self,
        client: DownloadClient,
        nzb_url: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Submit a download, preferring cached NZB content over URL to avoid provider rate limits.

        Args:
            client: Download client to submit to
            nzb_url: NZB download URL
            title: Download title
            category: Optional download category

        Returns:
            Job ID from download client, or None if all methods failed
        """
        return submit_with_nzb_content(
            client=client,
            nzb_url=nzb_url,
            title=title,
            category=category,
            nzb_cache_service=self.nzb_cache_service,
        )

    # ------------------------------------------------------------------
    # Category and retry helpers
    # ------------------------------------------------------------------

    def _get_download_category(self, tracking_id: int, session: Session) -> Optional[str]:
        """Determine the download category for a submission."""
        return get_download_category(tracking_id, session, self.default_category)

    def _get_max_retries_for_submission_context(
        self,
        session: Session,
        *,
        submission: Optional[DownloadSubmission] = None,
        tracking_id: Optional[int] = None,
        fuzzy_group: Optional[str] = None,
        url: Optional[str] = None,
    ) -> int:
        """
        Determine the correct max_retries for a download based on its DiscoveredIssue.

        Looks up the associated DiscoveredIssue to get per-issue max_retries,
        which differs between IA (5) and NZB (config-based, typically 1-3).

        Args:
            session: Database session
            submission: Optional DownloadSubmission to look up
            tracking_id: Optional tracking ID (used if submission not provided)
            fuzzy_group: Optional fuzzy match group (used if submission not provided)
            url: Optional source URL for fallback provider detection

        Returns:
            The max_retries value for this download context
        """
        # Extract identifiers from submission if provided
        if submission:
            tracking_id = tracking_id or submission.tracking_id
            fuzzy_group = fuzzy_group or submission.fuzzy_match_group
            url = url or submission.source_url

        # Try to find the associated DiscoveredIssue
        issue = None
        if submission:
            # First try by current_submission_id (most direct link)
            issue = (
                session.query(DiscoveredIssue).filter(DiscoveredIssue.current_submission_id == submission.id).first()
            )

        if not issue and tracking_id and fuzzy_group:
            # Fall back to tracking_id + fuzzy_match_group
            issue = (
                session.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.fuzzy_match_group == fuzzy_group,
                )
                .first()
            )

        if issue:
            return issue.max_retries

        # Fallback: detect provider from URL
        if url and "archive.org" in url:
            return MAX_DOWNLOAD_RETRIES_IA

        return MAX_DOWNLOAD_RETRIES

    # ------------------------------------------------------------------
    # Status update helpers
    # ------------------------------------------------------------------

    def _handle_rate_limited_submission(
        self, submission: DownloadSubmission, client_status: Dict[str, Any], job_id: str
    ) -> None:
        """
        Handle submission that is rate limited by the provider.

        Args:
            submission: Submission record to update
            client_status: Status dict from download client
            job_id: Client job ID
        """
        wait_time = client_status.get("wait_time", 0)
        message = client_status.get("message", f"Rate limited, waiting {wait_time}s")
        logger.info(f"[DownloadManager] Job {job_id} is rate limited: {message}")

        submission.status = DownloadSubmission.StatusEnum.PENDING
        submission.last_error = message
        submission.extra_status = message
        submission.updated_at = utc_now()

    def _map_client_status_to_submission_status(
        self, client_status: Dict[str, Any], job_id: str
    ) -> DownloadSubmission.StatusEnum:
        """
        Map download client status to submission status enum.

        Args:
            client_status: Status dict from download client
            job_id: Client job ID

        Returns:
            Mapped submission status enum
        """
        status_map = {
            "completed": DownloadSubmission.StatusEnum.COMPLETED,
            "downloading": DownloadSubmission.StatusEnum.DOWNLOADING,
            "pending": DownloadSubmission.StatusEnum.PENDING,
            "failed": DownloadSubmission.StatusEnum.FAILED,
            "error": DownloadSubmission.StatusEnum.FAILED,
        }

        client_status_value = client_status.get("status")
        if client_status_value == "unknown":
            logger.warning(
                f"[DownloadManager] Job {job_id} returned 'unknown' status - "
                f"job no longer exists in download client"
            )
            client_status.setdefault("error", "Job no longer exists in download client")
            return DownloadSubmission.StatusEnum.FAILED

        return status_map.get(client_status_value, DownloadSubmission.StatusEnum.PENDING)

    def _update_submission_from_client_status(
        self,
        submission: DownloadSubmission,
        client_status: Dict[str, Any],
        new_status: DownloadSubmission.StatusEnum,
        job_id: str,
    ) -> None:
        """
        Update submission record fields from client status.

        Args:
            submission: Submission record to update
            client_status: Status dict from download client
            new_status: New status enum value
            job_id: Client job ID
        """
        submission.status = new_status
        submission.updated_at = utc_now()

        # Clear extra_status if no longer rate limited
        if not client_status.get("rate_limited") and submission.extra_status:
            submission.extra_status = None

        # Update file path if provided
        if "file_path" in client_status:
            submission.file_path = client_status["file_path"]
            logger.debug(f"[DownloadManager] Updated file_path for {job_id}: {submission.file_path}")

    def _handle_failed_submission(
        self,
        submission: DownloadSubmission,
        client_status: Dict[str, Any],
        job_id: str,
        session: Session,
    ) -> None:
        """
        Handle submission that failed, including retry logic.

        Args:
            submission: Submission record to update
            client_status: Status dict from download client
            job_id: Client job ID
            session: Database session
        """
        submission.attempt_count = (submission.attempt_count or 0) + 1
        submission.last_error = client_status.get("error", "Unknown error")

        max_retries = self._get_max_retries_for_submission_context(session, submission=submission)

        logger.warning(
            f"[DownloadManager] Download failed for {job_id}: {submission.last_error} "
            f"(attempt {submission.attempt_count}/{max_retries + 1})"
        )

        if submission.attempt_count > max_retries:
            logger.error(
                f"[DownloadManager] Max retries reached for '{submission.result_title}' "
                f"- marking as permanently failed (will not retry). "
                f"Reason: {submission.last_error}"
            )

    # ------------------------------------------------------------------
    # Retry helpers
    # ------------------------------------------------------------------

    def _validate_retry_submission(
        self, submission: DownloadSubmission, submission_id: int, session: Session
    ) -> Optional[Dict[str, Any]]:
        """
        Validate that a submission can be retried.

        Args:
            submission: Submission record
            submission_id: Submission ID
            session: Database session

        Returns:
            Error dict if validation failed, None if valid
        """
        if submission.status not in [
            DownloadSubmission.StatusEnum.FAILED,
            DownloadSubmission.StatusEnum.SKIPPED,
        ]:
            return {
                "success": False,
                "message": f"Cannot retry submission with status: {submission.status.value}",
            }

        # Check if exceeded max retries
        max_retries = self._get_max_retries_for_submission_context(session, submission=submission)
        if submission.attempt_count > max_retries:
            logger.warning(
                f"Cannot retry bad file (failed {submission.attempt_count} times): "
                f"{submission.result_title} (ID: {submission_id})"
            )
            return {
                "success": False,
                "message": f"Cannot retry: file has failed {submission.attempt_count} times (max {max_retries + 1})",
            }

        return None

    def _resubmit_to_client(
        self, submission: DownloadSubmission, category: Optional[str], session: Session
    ) -> Optional[str]:
        """
        Resubmit a failed submission to the download client.

        Args:
            submission: Submission record to retry
            category: Download category to use
            session: Database session

        Returns:
            New job ID or None if submission failed
        """
        client = self._get_client_by_name(submission.client_name)

        logger.info(f"Retrying submission {submission.id} with {client.name}: {submission.result_title}")

        job_id = self._submit_with_nzb_content(
            client=client,
            nzb_url=submission.source_url,
            title=submission.result_title,
            category=category,
        )

        if not job_id:
            logger.warning(f"Download client {client.name} rejected retry submission: {submission.result_title}")
            return None

        return job_id

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def update_submission_status(self, job_id: str, session: Session) -> Optional[DownloadSubmission]:
        """
        Update status of a submission from the download client.

        Args:
            job_id: Client job ID
            session: Database session

        Returns:
            Updated DownloadSubmission record
        """
        # Find submission
        submission = session.query(DownloadSubmission).filter(DownloadSubmission.job_id == job_id).first()

        if not submission:
            logger.warning(f"Submission not found for job_id: {job_id}")
            return None

        # Get the client that was used for this submission
        client = self._get_client_by_name(submission.client_name)

        # Get status from client
        try:
            client_status = client.get_status(job_id)
            logger.debug(f"[DownloadManager] Client {client.name} status for {job_id}: {client_status}")

            # Check if download client is waiting due to provider rate limit
            if client_status.get("rate_limited"):
                self._handle_rate_limited_submission(submission, client_status, job_id)
                session.commit()
                return submission

            # Map client status to our status
            new_status = self._map_client_status_to_submission_status(client_status, job_id)

            # Update submission fields
            self._update_submission_from_client_status(submission, client_status, new_status, job_id)

            # Handle failure with retry logic
            if new_status == DownloadSubmission.StatusEnum.FAILED:
                self._handle_failed_submission(submission, client_status, job_id, session)

            session.commit()

            logger.debug(
                f"[DownloadManager] Updated submission {job_id}: status={new_status.value}, "
                f"attempt_count={submission.attempt_count}, file_path={submission.file_path}"
            )
            return submission

        except Exception as e:
            logger.error(f"Error updating submission {job_id}: {e}", exc_info=True)
            submission.status = DownloadSubmission.StatusEnum.FAILED
            submission.attempt_count = (submission.attempt_count or 0) + 1
            submission.last_error = str(e)
            session.commit()
            return submission

    def retry_submission(self, submission_id: int, session: Session) -> Dict[str, Any]:
        """
        Retry a failed download submission by resubmitting it to the download client.

        Args:
            submission_id: ID of the DownloadSubmission to retry
            session: Database session

        Returns:
            Dict with success status and message
        """
        submission = session.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()

        if not submission:
            logger.warning(f"Submission not found: {submission_id}")
            return {"success": False, "message": "Submission not found"}

        # Validate submission can be retried
        validation_error = self._validate_retry_submission(submission, submission_id, session)
        if validation_error:
            return validation_error

        try:
            # Get download category using helper
            download_category = self._get_download_category(submission.tracking_id, session)

            # Resubmit to download client
            job_id = self._resubmit_to_client(submission, download_category, session)
            if not job_id:
                return {
                    "success": False,
                    "message": f"Download client {submission.client_name} rejected submission",
                }

            # Update submission record
            submission.job_id = job_id
            submission.status = DownloadSubmission.StatusEnum.PENDING
            submission.last_error = None
            submission.updated_at = utc_now()
            session.commit()

            logger.info(f"Successfully retried submission {submission_id} with new job_id: {job_id}")
            return {
                "success": True,
                "message": f"Retry submitted (attempt {submission.attempt_count + 1})",
                "job_id": job_id,
            }

        except Exception as e:
            logger.error(f"Error retrying submission {submission_id}: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {str(e)}"}

    def _update_discovered_issue_status(
        self,
        submission: DownloadSubmission,
        session: Session,
    ) -> None:
        """
        Update the DiscoveredIssue linked to a submission after a status change.

        This is a no-op stub kept for API compatibility; status syncing for
        DiscoveredIssue is handled in process_queue (QueueCoordinator) and in the
        download monitor scheduler directly.

        Args:
            submission: The DownloadSubmission whose status changed
            session: Database session
        """
        # Intentionally left as a pass-through.
        # DiscoveredIssue syncing is handled at the queue/monitor layer.
        pass
