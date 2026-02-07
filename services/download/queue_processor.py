"""
Download queue processing service.
Handles automatic submission of queued downloads to download client.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from core.parsers import utc_now
from models.database import DownloadSubmission, PeriodicalTracking

logger = logging.getLogger(__name__)


class QueueProcessor:
    """Process queued downloads and submit to download client"""

    def __init__(self, download_client: DownloadClient, max_downloads: int = 10, nzb_cache_service=None):
        """
        Initialize queue processor.

        Args:
            download_client: Download client to submit jobs to
            max_downloads: Maximum number of concurrent downloads allowed
            nzb_cache_service: Optional NZB cache service for content caching
        """
        self.download_client = download_client
        self.max_downloads = max_downloads
        self.nzb_cache_service = nzb_cache_service

    def _submit_with_nzb_content(self, nzb_url: str, title: str, category: str = None) -> str:
        """
        Submit a download, preferring cached NZB content to avoid provider rate limits.

        Args:
            nzb_url: NZB download URL
            title: Download title
            category: Optional download category

        Returns:
            Job ID from download client
        """
        if self.nzb_cache_service and hasattr(self.download_client, "submit_content"):
            try:
                nzb_content = self.nzb_cache_service.get_nzb_content(nzb_url)
                if nzb_content:
                    job_id = self.download_client.submit_content(
                        nzb_content=nzb_content, title=title, category=category
                    )
                    if job_id:
                        logger.info(f"Submitted via cached NZB content: {title} -> {job_id}")
                        return job_id
                    logger.warning(f"submit_content failed for {title}, falling back to URL")
            except Exception as e:
                logger.warning(f"NZB content submission error: {e}, falling back to URL")

        return self.download_client.submit(nzb_url=nzb_url, title=title, category=category)

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
                "skipped": 0,
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
        skipped_count = 0
        errors: List[str] = []

        for submission in queued:
            try:
                # Get tracking info for category
                tracking = session.query(PeriodicalTracking).filter_by(id=submission.tracking_id).first()

                if not tracking:
                    logger.error(f"Tracking {submission.tracking_id} not found for submission {submission.id}")
                    submission.status = DownloadSubmission.StatusEnum.FAILED
                    submission.last_error = "Tracking record not found"
                    session.commit()
                    errors.append(f"Submission {submission.id}: Tracking not found")
                    continue

                category = tracking.category or self.download_client.config.get("default_category", "Other")

                # Submit to download client (prefer cached NZB content)
                logger.debug(
                    f"Submitting queued download: {submission.result_title} "
                    f"(submission_id: {submission.id}, category: {category})"
                )

                job_id = self._submit_with_nzb_content(
                    nzb_url=submission.source_url,
                    title=submission.result_title,
                    category=category,
                )

                # Update submission record
                submission.status = DownloadSubmission.StatusEnum.PENDING
                submission.job_id = job_id
                submission.client_name = self.download_client.config.get("name", "Unknown")
                session.commit()

                logger.info(
                    f"Successfully submitted queued download: {submission.result_title} "
                    f"(job_id: {job_id}, submission_id: {submission.id})"
                )
                submitted_count += 1

            except Exception as e:
                logger.error(f"Failed to submit queued download {submission.id}: {e}", exc_info=True)
                submission.status = DownloadSubmission.StatusEnum.FAILED
                submission.last_error = str(e)
                session.commit()
                errors.append(f"Submission {submission.id}: {str(e)}")
                continue

        # Only log completion at INFO level if there was actual activity
        if len(queued) > 0 or len(errors) > 0:
            logger.info(
                f"Queue processing complete: {submitted_count} submitted, "
                f"{skipped_count} skipped, {len(errors)} errors"
            )
        else:
            logger.debug("Queue processing complete: no items processed")

        return {
            "checked": len(queued),
            "submitted": submitted_count,
            "skipped": skipped_count,
            "errors": errors,
        }
