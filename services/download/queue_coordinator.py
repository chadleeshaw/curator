"""
Queue coordinator for download manager.
Handles queue operations: process_queue, submit_discovered_batch, and client routing.
"""

import logging
from threading import Lock
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
)
from services.download._coordinator_helpers import (
    get_active_download_count,
    get_client_for_provider,
)

logger = logging.getLogger(__name__)


class QueueCoordinator:
    """Coordinate download queue operations and batch submission."""

    def __init__(
        self,
        download_clients: Dict[str, DownloadClient],
        provider_client_map: Dict[str, str],
        max_downloads: int,
        queue_processor: Any,
        slot_lock: Lock,
    ):
        """
        Initialize queue coordinator.

        Args:
            download_clients: Dict of available download clients keyed by type
            provider_client_map: Mapping of provider types to client types
            max_downloads: Maximum number of concurrent downloads allowed
            queue_processor: QueueProcessor instance for processing the download queue
            slot_lock: Threading lock for serializing slot counting
        """
        self.download_clients = download_clients
        self.provider_client_map = provider_client_map
        self.max_downloads = max_downloads
        self.queue_processor = queue_processor
        self._slot_lock = slot_lock

    # ------------------------------------------------------------------
    # Client routing
    # ------------------------------------------------------------------

    def _get_client_for_provider(self, provider: str, url: Optional[str] = None) -> DownloadClient:
        """Get the appropriate download client for a provider."""
        return get_client_for_provider(self.download_clients, self.provider_client_map, provider, url)

    # ------------------------------------------------------------------
    # Slot counting
    # ------------------------------------------------------------------

    def _get_active_download_count(self, session: Session) -> int:
        """Count currently active (pending or downloading) submissions."""
        return get_active_download_count(session)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def process_queue(self, session: Session, submission_coordinator: Any) -> Dict[str, Any]:
        """
        Process queued downloads and submit them when slots are available.

        Thread-safe: acquires _slot_lock to prevent concurrent slot counting
        from auto-download Phase 3 and download monitor from exceeding max_downloads.

        After the queue processor promotes submissions (QUEUED→PENDING), syncs the
        linked DiscoveredIssue.download_status to QUEUED so the two state machines
        stay consistent.

        Args:
            session: Database session
            submission_coordinator: SubmissionCoordinator instance (unused here, kept
                for API symmetry if needed in future)

        Returns:
            Dict with processing results
        """
        with self._slot_lock:
            result = self.queue_processor.process_queue(session)

        # Sync DiscoveredIssue status for each promoted submission (outside _slot_lock;
        # no slot counting involved in the sync).
        for submission in result.get("promoted_submissions", []):
            try:
                discovered_issue = (
                    session.query(DiscoveredIssue)
                    .filter(DiscoveredIssue.current_submission_id == submission.id)
                    .first()
                )
                if discovered_issue:
                    logger.debug(
                        f"Syncing DiscoveredIssue {discovered_issue.id} status: "
                        f"{discovered_issue.download_status} -> {DownloadStatus.PENDING} "
                        f"(submission {submission.id} promoted to PENDING)"
                    )
                    discovered_issue.download_status = DownloadStatus.PENDING
                    session.commit()
            except Exception as e:
                logger.error(
                    f"Error syncing DiscoveredIssue for promoted submission {submission.id}: {e}",
                    exc_info=True,
                )

        return result

    def submit_discovered_batch(
        self,
        session: Session,
        issue_discovery_service: Any,
        submission_coordinator: Any,
    ) -> int:
        """
        Submit discovered issues from the download queue, respecting slot limits.

        Thread-safe: acquires _slot_lock to prevent concurrent slot counting
        from process_queue() from exceeding max_downloads.

        This replaces inline Phase 3 logic in auto_download_task, consolidating
        all slot-aware submission through DownloadManager.

        Args:
            session: Database session
            issue_discovery_service: IssueDiscoveryService for fetching queue
            submission_coordinator: SubmissionCoordinator for submitting issues

        Returns:
            Number of issues successfully submitted
        """
        with self._slot_lock:
            active_count = self._get_active_download_count(session)
            remaining_slots = max(0, self.max_downloads - active_count)
            logger.debug(f"Auto-download: {remaining_slots} slots available ({active_count} in progress)")

            if remaining_slots <= 0:
                return 0

            download_queue = issue_discovery_service.get_download_queue(session, limit=remaining_slots)
            if not download_queue:
                return 0

            logger.info(f"Auto-download: Submitting {len(download_queue)} issues")
            submitted_count = 0
            for issue in download_queue:
                try:
                    submission = submission_coordinator.submit_from_discovered_issue(issue.id, session)
                    if submission:
                        submitted_count += 1
                        logger.info(
                            f"Auto-download: Submitted '{issue.title}' "
                            f"(priority {issue.download_priority}, job_id: {submission.job_id})"
                        )
                except Exception as e:
                    logger.error(
                        f"Auto-download: Error submitting '{issue.title}': {e}",
                        exc_info=True,
                    )

            if submitted_count > 0:
                logger.info(f"Auto-download: Submitted {submitted_count} downloads")

            return submitted_count
