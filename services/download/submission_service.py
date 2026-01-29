"""
Download submission record management service.
Handles creation, status updates, and retrieval of download submissions.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.constants.app import MAX_DOWNLOAD_RETRIES
from core.parsers import utc_now
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import DownloadSubmission

logger = logging.getLogger(__name__)


class SubmissionService:
    """Manage download submission records"""

    @staticmethod
    def create_submission_record(
        tracking_id: int,
        search_result: Dict[str, Any],
        status: DownloadSubmission.StatusEnum,
        session: Session,
        *,
        search_result_db_id: Optional[int] = None,
        job_id: Optional[str] = None,
        error_message: Optional[str] = None,
        client_name: Optional[str] = None,
        attempt_count: int = 0,
    ) -> DownloadSubmission:
        """
        Create a download submission record.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            status: Initial submission status
            session: Database session
            search_result_db_id: Optional ID of the SearchResult record
            job_id: Optional download client job ID
            error_message: Optional error message if submission failed
            client_name: Optional name of download client used
            attempt_count: Number of submission attempts (for retries)

        Returns:
            The created DownloadSubmission record
        """
        # Create fuzzy match group for deduplication
        fuzzy_group = get_fuzzy_group_id(search_result["title"])

        submission = DownloadSubmission(
            tracking_id=tracking_id,
            search_result_id=search_result_db_id,
            result_title=search_result["title"],
            source_url=search_result["url"],
            fuzzy_match_group=fuzzy_group,
            status=status,
            job_id=job_id,
            last_error=error_message,
            client_name=client_name,
            attempt_count=attempt_count,
        )
        session.add(submission)
        session.commit()

        logger.info(
            f"Created submission record: {submission.result_title} "
            f"(status: {status.value}, job_id: {job_id}, attempt: {attempt_count})"
        )
        return submission

    @staticmethod
    def get_completed_downloads(session: Session) -> List[DownloadSubmission]:
        """
        Get all completed downloads that haven't been processed.

        Args:
            session: Database session

        Returns:
            List of completed but unprocessed download submissions
        """
        submissions = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED,
                DownloadSubmission.file_path.isnot(None),
            )
            .order_by(DownloadSubmission.created_at.desc())
            .all()
        )
        logger.debug(f"Found {len(submissions)} completed unprocessed downloads")
        return submissions

    @staticmethod
    def mark_processed(submission_id: int, session: Session) -> bool:
        """
        Mark a submission as processed.

        Args:
            submission_id: ID of the submission to mark
            session: Database session

        Returns:
            True if marked successfully, False if submission not found
        """
        submission = session.query(DownloadSubmission).filter_by(id=submission_id).first()
        if not submission:
            logger.warning(f"Submission {submission_id} not found")
            return False

        # Mark as processed by clearing file_path (indicates it's been moved/processed)
        submission.file_path = None
        session.commit()
        logger.info(f"Marked submission {submission_id} as processed: {submission.result_title}")
        return True

    @staticmethod
    def get_pending_downloads(session: Session) -> List[DownloadSubmission]:
        """
        Get all pending/downloading submissions.

        Args:
            session: Database session

        Returns:
            List of submissions that are pending or currently downloading
        """
        submissions = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                    ]
                )
            )
            .order_by(DownloadSubmission.created_at.desc())
            .all()
        )
        logger.debug(f"Found {len(submissions)} pending/downloading submissions")
        return submissions

    @staticmethod
    def can_retry_submission(submission: DownloadSubmission) -> bool:
        """
        Check if a failed submission can be retried.

        Args:
            submission: The submission record to check

        Returns:
            True if submission can be retried, False otherwise
        """
        if submission.status != DownloadSubmission.StatusEnum.FAILED:
            return False

        if submission.attempt_count >= MAX_DOWNLOAD_RETRIES:
            logger.warning(
                f"Cannot retry submission {submission.id}: "
                f"max retries ({MAX_DOWNLOAD_RETRIES}) reached"
            )
            return False

        return True

    @staticmethod
    def update_submission_for_retry(submission: DownloadSubmission, session: Session) -> None:
        """
        Update submission record for a retry attempt.

        Args:
            submission: The submission record to update
            session: Database session
        """
        submission.status = DownloadSubmission.StatusEnum.QUEUED
        submission.attempt_count += 1
        submission.error_message = None
        submission.job_id = None
        submission.updated_at = utc_now()
        session.commit()

        logger.info(
            f"Reset submission {submission.id} for retry "
            f"(attempt {submission.attempt_count}/{MAX_DOWNLOAD_RETRIES})"
        )
