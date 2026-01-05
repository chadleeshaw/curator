"""
Download manager for handling periodical downloads.
Manages search, deduplication, submission, and status tracking.
"""

import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.bases import DownloadClient, SearchProvider
from core.matching import TitleMatcher
from models.database import (
    DownloadSubmission,
    MagazineTracking,
)
from models.database import SearchResult as DBSearchResult

logger = logging.getLogger(__name__)


class DownloadManager:
    """Manage downloads for tracked periodicals"""

    def __init__(
        self,
        search_providers: List[SearchProvider],
        download_client: DownloadClient,
        fuzzy_threshold: int = 80,
    ):
        """
        Initialize download manager.

        Args:
            search_providers: List of search providers to use
            download_client: Download client to submit jobs to
            fuzzy_threshold: Fuzzy matching threshold for deduplication
        """
        self.search_providers = search_providers
        self.download_client = download_client
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)

    def search_periodical_issues(
        self, periodical_title: str, session: Session
    ) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.

        Args:
            periodical_title: Title of the periodical to search for
            session: Database session

        Returns:
            List of search results with deduplication grouping
        """
        all_results = []

        for provider in self.search_providers:
            try:
                logger.info(f"Searching {provider.name} for: {periodical_title}")
                results = provider.search(periodical_title)

                for result in results:
                    all_results.append(
                        {
                            "title": result.title,
                            "url": result.url,
                            "provider": result.provider,
                            "publication_date": result.publication_date,
                            "raw_metadata": result.raw_metadata or {},
                        }
                    )

            except Exception as e:
                logger.error(
                    f"Error searching {provider.name} for '{periodical_title}': {e}"
                )

        logger.info(
            f"Found {len(all_results)} results for '{periodical_title}' across {len(self.search_providers)} providers"
        )
        return all_results

    def _get_fuzzy_group_id(self, title: str) -> str:
        """
        Get a normalized group ID for fuzzy matching duplicates.
        Uses title matching to create consistent grouping.

        Args:
            title: Title to normalize

        Returns:
            Group ID string
        """
        # Normalize title: lowercase, remove special chars, collapse spaces
        normalized = " ".join(title.lower().split())

        # Normalize common month abbreviations to full names for better matching
        month_mapping = {
            "jan": "january", "feb": "february", "mar": "march",
            "apr": "april", "may": "may", "jun": "june",
            "jul": "july", "aug": "august", "sep": "september",
            "sept": "september", "oct": "october", "nov": "november", "dec": "december"
        }

        words = []
        for word in normalized.split():
            # Replace month abbreviations with full month names
            words.append(month_mapping.get(word, word))

        # Keep first few significant words as group ID
        group_words = [w for w in words if len(w) > 2][:3]
        return "-".join(group_words)

    def check_duplicate_submission(
        self, tracking_id: int, result_title: str, session: Session
    ) -> Tuple[bool, Optional[DownloadSubmission]]:
        """
        Check if this search result was already submitted for download.

        Args:
            tracking_id: Periodical tracking ID
            result_title: Title of the search result
            session: Database session

        Returns:
            Tuple of (is_duplicate, existing_submission_record)
        """
        # Create group ID for this result
        fuzzy_group = self._get_fuzzy_group_id(result_title)

        # Check for similar results already submitted
        existing = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.tracking_id == tracking_id,
                DownloadSubmission.fuzzy_match_group == fuzzy_group,
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                        DownloadSubmission.StatusEnum.COMPLETED,
                    ]
                ),
            )
            .first()
        )

        if existing:
            logger.debug(
                f"Skipping duplicate: '{result_title}' (similar to '{existing.result_title}')"
            )
            return True, existing

        return False, None

    def submit_download(
        self,
        tracking_id: int,
        search_result: Dict[str, Any],
        session: Session,
        search_result_db_id: Optional[int] = None,
    ) -> Optional[DownloadSubmission]:
        """
        Submit a search result for download, checking for duplicates first.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            session: Database session
            search_result_db_id: Optional ID of SearchResult DB record

        Returns:
            DownloadSubmission record if submitted, None if duplicate or error
        """
        logger.debug(f"[DownloadManager] submit_download called for: {search_result['title']}")

        # Check for duplicates
        is_dup, existing = self.check_duplicate_submission(
            tracking_id, search_result["title"], session
        )

        if is_dup:
            logger.debug("[DownloadManager] Duplicate found, recording as SKIPPED")
            # Record this as a skipped submission
            skipped = DownloadSubmission(
                tracking_id=tracking_id,
                search_result_id=search_result_db_id,
                status=DownloadSubmission.StatusEnum.SKIPPED,
                source_url=search_result["url"],
                result_title=search_result["title"],
                fuzzy_match_group=self._get_fuzzy_group_id(search_result["title"]),
            )
            session.add(skipped)
            session.commit()
            logger.info(
                f"Skipped duplicate download: {search_result['title']} (tracking_id: {tracking_id})"
            )
            return None

        # Submit to download client
        try:
            logger.debug(f"[DownloadManager] Submitting to download client: {search_result['title']}")
            job_id = self.download_client.submit(
                nzb_url=search_result["url"], title=search_result["title"]
            )

            if not job_id:
                logger.warning(
                    f"Download client rejected submission: {search_result['title']}"
                )
                logger.debug("[DownloadManager] Recording as FAILED - client rejected")
                # Record failed submission
                submission = DownloadSubmission(
                    tracking_id=tracking_id,
                    search_result_id=search_result_db_id,
                    status=DownloadSubmission.StatusEnum.FAILED,
                    source_url=search_result["url"],
                    result_title=search_result["title"],
                    fuzzy_match_group=self._get_fuzzy_group_id(search_result["title"]),
                    last_error="Client rejected submission",
                )
                session.add(submission)
                session.commit()
                return None

            # Create submission record
            logger.debug(f"[DownloadManager] Client accepted, job_id: {job_id}")
            fuzzy_group = self._get_fuzzy_group_id(search_result["title"])
            submission = DownloadSubmission(
                tracking_id=tracking_id,
                search_result_id=search_result_db_id,
                job_id=job_id,
                status=DownloadSubmission.StatusEnum.PENDING,
                source_url=search_result["url"],
                result_title=search_result["title"],
                fuzzy_match_group=fuzzy_group,
                client_name=self.download_client.name,
                attempt_count=1,
            )
            session.add(submission)
            session.commit()
            logger.debug(f"[DownloadManager] Created DownloadSubmission record ID: {submission.id}")

            logger.info(
                f"Submitted download: {search_result['title']} (job_id: {job_id})"
            )
            return submission

        except Exception as e:
            logger.error(
                f"Error submitting download for '{search_result['title']}': {e}",
                exc_info=True,
            )
            logger.debug("[DownloadManager] Recording as FAILED - exception occurred")
            # Record error
            submission = DownloadSubmission(
                tracking_id=tracking_id,
                search_result_id=search_result_db_id,
                status=DownloadSubmission.StatusEnum.FAILED,
                source_url=search_result["url"],
                result_title=search_result["title"],
                fuzzy_match_group=self._get_fuzzy_group_id(search_result["title"]),
                last_error=str(e),
            )
            session.add(submission)
            session.commit()
            return None

    def download_all_periodical_issues(
        self, tracking_id: int, session: Session
    ) -> Dict[str, Any]:
        """
        Search for all issues of a tracked periodical and submit downloads.
        Called when track_all_editions is set to True.

        Args:
            tracking_id: Periodical tracking ID
            session: Database session

        Returns:
            Dict with submission results
        """
        # Get tracking record
        tracking = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.id == tracking_id)
            .first()
        )

        if not tracking:
            logger.error(f"Tracking record not found: {tracking_id}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        logger.info(
            f"Starting download search for all issues of: {tracking.title} (tracking_id: {tracking_id})"
        )

        # Search for issues
        search_results = self.search_periodical_issues(tracking.title, session)

        results = {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}

        for search_result in search_results:
            # Try to find or create SearchResult DB record
            search_result_db_id = None
            try:
                # Create DB search result record
                db_result = DBSearchResult(
                    provider=search_result.get("provider", "unknown"),
                    query=tracking.title,
                    title=search_result["title"],
                    url=search_result["url"],
                    publication_date=search_result.get("publication_date"),
                    raw_metadata=search_result.get("raw_metadata", {}),
                )
                session.add(db_result)
                session.flush()
                search_result_db_id = db_result.id
            except Exception as e:
                logger.warning(
                    f"Could not create DB search result: {e}", exc_info=True
                )

            # Submit download
            submission = self.submit_download(
                tracking_id, search_result, session, search_result_db_id
            )

            if submission:
                if submission.status == DownloadSubmission.StatusEnum.PENDING:
                    results["submitted"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.SKIPPED:
                    results["skipped"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.FAILED:
                    results["failed"] += 1
                    results["errors"].append(
                        f"Failed: {search_result['title']} - {submission.last_error}"
                    )
            else:
                results["skipped"] += 1

        logger.info(
            f"Download search completed: submitted={results['submitted']}, "
            f"skipped={results['skipped']}, failed={results['failed']}"
        )

        return results

    def download_single_issue(
        self, tracking_id: int, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Download a single issue submitted by the user.

        Args:
            tracking_id: Periodical tracking ID (for tracking/organization)
            search_result: Search result dict with title, url, etc.
            session: Database session

        Returns:
            DownloadSubmission record if successful
        """
        logger.info(
            f"Submitting single issue download: {search_result['title']} (tracking_id: {tracking_id})"
        )

        # Create DB search result record
        search_result_db_id = None
        try:
            db_result = DBSearchResult(
                provider=search_result.get("provider", "manual"),
                query=search_result.get("title", ""),
                title=search_result["title"],
                url=search_result["url"],
                publication_date=search_result.get("publication_date"),
                raw_metadata=search_result.get("raw_metadata", {}),
            )
            session.add(db_result)
            session.flush()
            search_result_db_id = db_result.id
        except Exception as e:
            logger.warning(f"Could not create DB search result: {e}", exc_info=True)

        # Submit download (still check for duplicates)
        submission = self.submit_download(
            tracking_id, search_result, session, search_result_db_id
        )

        return submission

    def update_submission_status(
        self, job_id: str, session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Update status of a submission from the download client.

        Args:
            job_id: Client job ID
            session: Database session

        Returns:
            Updated DownloadSubmission record
        """
        # Find submission
        submission = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.job_id == job_id)
            .first()
        )

        if not submission:
            logger.warning(f"Submission not found for job_id: {job_id}")
            return None

        # Get status from client
        try:
            client_status = self.download_client.get_status(job_id)
            logger.debug(f"[DownloadManager] Client status for {job_id}: {client_status}")

            # Map client status to our status
            status_map = {
                "completed": DownloadSubmission.StatusEnum.COMPLETED,
                "downloading": DownloadSubmission.StatusEnum.DOWNLOADING,
                "pending": DownloadSubmission.StatusEnum.PENDING,
                "failed": DownloadSubmission.StatusEnum.FAILED,
                "error": DownloadSubmission.StatusEnum.FAILED,
            }

            new_status = status_map.get(
                client_status.get("status"), DownloadSubmission.StatusEnum.PENDING
            )

            # Update submission
            submission.status = new_status
            submission.updated_at = datetime.now(UTC)

            if "file_path" in client_status:
                submission.file_path = client_status["file_path"]
                logger.debug(f"[DownloadManager] Updated file_path for {job_id}: {submission.file_path}")

            if new_status == DownloadSubmission.StatusEnum.FAILED:
                submission.last_error = client_status.get("error", "Unknown error")

            session.commit()

            logger.debug(
                f"[DownloadManager] Updated submission {job_id}: status={new_status.value}, file_path={submission.file_path}"
            )
            return submission

        except Exception as e:
            logger.error(f"Error updating submission {job_id}: {e}", exc_info=True)
            submission.status = DownloadSubmission.StatusEnum.FAILED
            submission.last_error = str(e)
            session.commit()
            return submission

    def get_completed_downloads(self, session: Session) -> List[DownloadSubmission]:
        """
        Get all completed downloads ready for processing.

        Args:
            session: Database session

        Returns:
            List of completed submissions with file paths
        """
        completed = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status == DownloadSubmission.StatusEnum.COMPLETED,
                DownloadSubmission.file_path.isnot(None),
            )
            .all()
        )

        return completed

    def mark_processed(self, submission_id: int, session: Session) -> bool:
        """
        Mark a submission as processed (move file out of downloads).

        Args:
            submission_id: DownloadSubmission ID
            session: Database session

        Returns:
            True if successful
        """
        submission = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.id == submission_id)
            .first()
        )

        if not submission:
            logger.warning(f"Submission not found: {submission_id}")
            return False

        # Mark as processed by setting file_path to None
        # (indicates it's been moved/processed)
        submission.file_path = None
        session.commit()

        logger.info(f"Marked submission as processed: {submission_id}")
        return True

    def get_pending_downloads(self, session: Session) -> List[DownloadSubmission]:
        """
        Get all pending/downloading submissions to monitor.

        Args:
            session: Database session

        Returns:
            List of active submissions
        """
        pending = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                    ]
                )
            )
            .all()
        )
        logger.debug(f"Found {len(pending)} pending submissions")
        return pending
