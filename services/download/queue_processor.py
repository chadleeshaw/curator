"""
Download queue processing service.
Handles automatic submission of queued downloads to download client.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from core.parsers import utc_now
from models.database import DiscoveredIssue, DownloadStatus, DownloadSubmission, PeriodicalTracking
from services.cache.provider_cache import INDEXER_REJECTION_ERROR, NzbContentRejected
from services.download.nzb_submit import submit_with_nzb_content

logger = logging.getLogger(__name__)


def release_linked_issue(
    session: Session,
    submission: DownloadSubmission,
    error: str,
    *,
    count_attempt: bool = False,
) -> None:
    """Move a queued issue back to failed when its submission never reached the client.

    Indexer error pages do not count as an attempt. A client rejection does,
    and past max_retries it is permanently failed instead of left queued.
    """
    issue = session.query(DiscoveredIssue).filter(DiscoveredIssue.current_submission_id == submission.id).first()
    if issue is None:
        return
    if issue.download_status not in (
        DownloadStatus.QUEUED,
        DownloadStatus.PENDING,
        DownloadStatus.DOWNLOADING,
    ):
        return
    issue.last_error = error[:512]
    issue.current_submission_id = None
    if count_attempt:
        issue.attempt_count = (issue.attempt_count or 0) + 1
        issue.last_attempt = utc_now()
        max_retries = issue.max_retries if issue.max_retries is not None else 1
        if issue.attempt_count > max_retries:
            issue.download_status = DownloadStatus.PERMANENTLY_FAILED
            issue.download_priority = 0
            return
    issue.download_status = DownloadStatus.FAILED


class QueueProcessor:
    """Process queued downloads and submit to download client"""

    def __init__(
        self,
        download_client: DownloadClient,
        max_downloads: int = 10,
        nzb_cache_service=None,
        download_clients: Optional[Dict[str, DownloadClient]] = None,
    ):
        """
        Initialize queue processor.

        Args:
            download_client: Default download client to submit jobs to
            max_downloads: Maximum number of concurrent downloads allowed
            nzb_cache_service: Optional NZB cache service for content caching
            download_clients: Optional dict of all available download clients keyed by type
        """
        self.download_client = download_client
        self.max_downloads = max_downloads
        self.nzb_cache_service = nzb_cache_service
        self.download_clients: Dict[str, DownloadClient] = {"default": download_client}
        if download_clients:
            self.download_clients.update(download_clients)

    def _get_client_for_submission(self, submission) -> DownloadClient:
        """
        Get the appropriate download client for a queued submission.

        Uses client_name stored on the submission to route to the correct client.
        Falls back to the default client if no matching client is found.

        Args:
            submission: DownloadSubmission record

        Returns:
            DownloadClient instance
        """
        if submission.client_name:
            # Search by client name
            for client in self.download_clients.values():
                if client.name == submission.client_name:
                    return client
            logger.debug(f"Client '{submission.client_name}' not found for submission {submission.id}, using default")
        return self.download_client

    def _fail_unsent_submission(
        self,
        session: Session,
        submission: DownloadSubmission,
        message: str,
        client_name: Optional[str] = None,
        *,
        count_attempt: bool = True,
    ) -> None:
        """Fail a submission that never got a job id, and free the linked issue."""
        submission.status = DownloadSubmission.StatusEnum.FAILED
        submission.last_error = message[:512]
        if client_name:
            submission.client_name = client_name
        release_linked_issue(session, submission, message, count_attempt=count_attempt)
        session.commit()

    def process_queue(self, session: Session) -> Dict[str, Any]:
        """
        Process queued downloads and submit to download client.

        Checks for pending downloads and submits queued items if capacity available.

        Args:
            session: Database session

        Returns:
            Dict with processing statistics:
                - checked: Number of queued items checked
                - submitted: Number of items submitted to client
                - skipped: Number of items skipped (already at capacity)
                - errors: List of error messages
        """
        # Get count of active downloads
        active_count = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                    ]
                )
            )
            .count()
        )

        logger.debug(f"Active downloads: {active_count}/{self.max_downloads}")

        # Check if at capacity
        if active_count >= self.max_downloads:
            logger.info(f"Download capacity reached ({active_count}/{self.max_downloads}), skipping queue processing")
            return {
                "checked": 0,
                "submitted": 0,
                "errors": [],
            }

        # Get queued submissions
        queued = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.QUEUED)
            .order_by(DownloadSubmission.created_at.asc())
            .limit(self.max_downloads - active_count)
            .all()
        )

        # Only log at INFO level if there are items to process
        if len(queued) > 0:
            logger.info(f"Processing {len(queued)} queued downloads")
        else:
            logger.debug("No queued downloads to process")

        submitted_count = 0
        errors: List[str] = []
        promoted_submissions: List[DownloadSubmission] = []

        for submission in queued:
            try:
                # Get tracking info for category
                tracking = session.query(PeriodicalTracking).filter_by(id=submission.tracking_id).first()

                if not tracking:
                    message = "Tracking record not found"
                    logger.error(f"Tracking {submission.tracking_id} not found for submission {submission.id}")
                    self._fail_unsent_submission(session, submission, message)
                    errors.append(f"Submission {submission.id}: Tracking not found")
                    continue

                category = tracking.download_category or self.download_client.config.get("default_category")

                # Get the appropriate client for this submission
                client = self._get_client_for_submission(submission)

                # Submit to download client (prefer cached NZB content)
                logger.debug(
                    f"Submitting queued download: {submission.result_title} "
                    f"(submission_id: {submission.id}, category: {category}, client: {client.name})"
                )

                try:
                    job_id = submit_with_nzb_content(
                        client=client,
                        nzb_url=submission.source_url,
                        title=submission.result_title,
                        category=category,
                        nzb_cache_service=self.nzb_cache_service,
                    )
                except NzbContentRejected as exc:
                    message = f"{INDEXER_REJECTION_ERROR}: {exc}"
                    logger.warning(f"{message} ({submission.result_title})")
                    self._fail_unsent_submission(session, submission, message, client.name, count_attempt=False)
                    errors.append(f"Submission {submission.id}: {message}")
                    continue

                if not job_id:
                    message = "Download client rejected submission (no job ID returned)"
                    logger.warning(
                        f"Download client rejected submission: {submission.result_title} "
                        f"(submission_id: {submission.id})"
                    )
                    self._fail_unsent_submission(session, submission, message, client.name)
                    errors.append(f"Submission {submission.id}: Client rejected (no job ID)")
                    continue

                # Update submission record
                submission.status = DownloadSubmission.StatusEnum.PENDING
                submission.job_id = job_id
                submission.client_name = client.name
                session.commit()

                logger.info(
                    f"Successfully submitted queued download: {submission.result_title} "
                    f"(job_id: {job_id}, submission_id: {submission.id})"
                )
                submitted_count += 1
                promoted_submissions.append(submission)

            except Exception as e:
                logger.error(
                    f"Failed to submit queued download {submission.id}: {e}",
                    exc_info=True,
                )
                self._fail_unsent_submission(session, submission, str(e))
                errors.append(f"Submission {submission.id}: {str(e)}")
                continue

        # Only log completion at INFO level if there was actual activity
        if len(queued) > 0 or len(errors) > 0:
            logger.info(f"Queue processing complete: {submitted_count} submitted, " f"{len(errors)} errors")
        else:
            logger.debug("Queue processing complete: no items processed")

        return {
            "checked": len(queued),
            "submitted": submitted_count,
            "errors": errors,
            "promoted_submissions": promoted_submissions,
        }
