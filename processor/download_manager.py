"""
Download manager for handling periodical downloads.
Manages search, deduplication, submission, and status tracking.
"""

import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.bases import DownloadClient, SearchProvider
from core.constants import (
    DEFAULT_FUZZY_THRESHOLD,
    MAX_DOWNLOAD_RETRIES,
    MAX_DOWNLOADS_PER_BATCH,
)
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
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
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

    def search_periodical_issues(self, periodical_title: str, session: Session) -> List[Dict[str, Any]]:
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
                logger.error(f"Error searching {provider.name} for '{periodical_title}': {e}")

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
            "jan": "january",
            "feb": "february",
            "mar": "march",
            "apr": "april",
            "may": "may",
            "jun": "june",
            "jul": "july",
            "aug": "august",
            "sep": "september",
            "sept": "september",
            "oct": "october",
            "nov": "november",
            "dec": "december",
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
            logger.debug(f"Skipping duplicate: '{result_title}' (similar to '{existing.result_title}')")
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
        Submit a search result for download, checking for duplicates and bad files first.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            session: Database session
            search_result_db_id: Optional ID of SearchResult DB record

        Returns:
            DownloadSubmission record if submitted, None if duplicate or error
        """
        logger.debug(f"[DownloadManager] submit_download called for: {search_result['title']}")

        # Check if this URL has failed too many times (bad file)
        previous_failures = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.source_url == search_result["url"],
                DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                DownloadSubmission.attempt_count >= MAX_DOWNLOAD_RETRIES,
            )
            .first()
        )

        if previous_failures:
            logger.info(
                f"[DownloadManager] Skipping bad file (failed {previous_failures.attempt_count} times): "
                f"{search_result['title']} - Last error: {previous_failures.last_error}"
            )
            return None

        # Check for duplicates
        is_dup, existing = self.check_duplicate_submission(tracking_id, search_result["title"], session)

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
            logger.info(f"Skipped duplicate download: {search_result['title']} (tracking_id: {tracking_id})")
            return None

        # Submit to download client
        try:
            logger.debug(f"[DownloadManager] Submitting to download client: {search_result['title']}")
            job_id = self.download_client.submit(nzb_url=search_result["url"], title=search_result["title"])

            if not job_id:
                logger.warning(f"Download client rejected submission: {search_result['title']}")
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

            logger.info(f"Submitted download: {search_result['title']} (job_id: {job_id})")
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

    def download_selected_editions(self, tracking_id: int, session: Session) -> Dict[str, Any]:
        """
        Download only the specific editions marked in selected_editions dict.
        Used when specific issues are individually tracked.

        Args:
            tracking_id: Periodical tracking ID
            session: Database session

        Returns:
            Dict with submission results
        """
        # Get tracking record
        tracking = session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()

        if not tracking:
            logger.error(f"Tracking record not found: {tracking_id}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        # Get selected editions that are marked as True
        selected_editions = tracking.selected_editions or {}
        editions_to_download = [olid for olid, tracked in selected_editions.items() if tracked]

        if not editions_to_download:
            logger.debug(f"No selected editions to download for: {tracking.title}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        logger.info(f"Downloading {len(editions_to_download)} selected editions for: {tracking.title}")

        # Search for issues
        search_results = self.search_periodical_issues(tracking.title, session)

        results = {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}

        # Filter search results to only selected editions
        for search_result in search_results:
            # Try to match search result to selected editions
            should_download = False
            matched_edition = None

            # Check if metadata contains an OLID that matches selected editions
            raw_metadata = search_result.get("raw_metadata", {})
            result_olid = (
                raw_metadata.get("olid") or raw_metadata.get("edition_id") or raw_metadata.get("open_library_id")
            )

            if result_olid and result_olid in editions_to_download:
                should_download = True
                matched_edition = result_olid
                logger.debug(f"Matched search result to selected edition {result_olid}: {search_result['title']}")
            else:
                # No OLID match - try fuzzy matching against edition titles stored in metadata
                # Check if tracking has detailed edition metadata
                edition_metadata = tracking.periodical_metadata or {}
                editions_list = edition_metadata.get("editions", [])

                if editions_list:
                    # Try to match by title similarity
                    for olid in editions_to_download:
                        edition_info = next((e for e in editions_list if e.get("olid") == olid), None)
                        if edition_info:
                            edition_title = edition_info.get("title", "")
                            # Use fuzzy matching to compare titles
                            is_match, score = self.title_matcher.match(search_result["title"], edition_title)
                            if is_match:
                                should_download = True
                                matched_edition = olid
                                logger.debug(
                                    f"Fuzzy matched search result to edition {olid}: {search_result['title']} (score: {score})"
                                )
                                break

            # If we still haven't matched and there are selected editions, log and skip
            if not should_download:
                logger.debug(f"Skipping search result (no match to selected editions): {search_result['title']}")
                results["skipped"] += 1
                continue

            # Try to find or create SearchResult DB record
            search_result_db_id = None
            try:
                # Create DB search result record with edition info
                metadata = search_result.get("raw_metadata", {}).copy()
                if matched_edition:
                    metadata["matched_edition_olid"] = matched_edition

                db_result = DBSearchResult(
                    provider=search_result.get("provider", "unknown"),
                    query=tracking.title,
                    title=search_result["title"],
                    url=search_result["url"],
                    publication_date=search_result.get("publication_date"),
                    raw_metadata=metadata,
                )
                session.add(db_result)
                session.flush()
                search_result_db_id = db_result.id
            except Exception as e:
                logger.warning(f"Could not create DB search result: {e}", exc_info=True)

            # Submit download
            submission = self.submit_download(tracking_id, search_result, session, search_result_db_id)

            if submission:
                if submission.status == DownloadSubmission.StatusEnum.PENDING:
                    results["submitted"] += 1
                    logger.info(f"Submitted selected edition {matched_edition}: {search_result['title']}")
                elif submission.status == DownloadSubmission.StatusEnum.SKIPPED:
                    results["skipped"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.FAILED:
                    results["failed"] += 1
                    results["errors"].append(f"Failed: {search_result['title']} - {submission.last_error}")
            else:
                results["skipped"] += 1

        logger.info(
            f"Selected editions download completed: submitted={results['submitted']}, "
            f"skipped={results['skipped']}, failed={results['failed']}"
        )

        return results

    def download_all_periodical_issues(self, tracking_id: int, session: Session) -> Dict[str, Any]:
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
        tracking = session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()

        if not tracking:
            logger.error(f"Tracking record not found: {tracking_id}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        logger.info(f"Starting download search for all issues of: {tracking.title} (tracking_id: {tracking_id})")

        # Search for issues
        search_results = self.search_periodical_issues(tracking.title, session)

        # Filter out issues that are already downloaded, pending, or in library
        filtered_results = []
        for search_result in search_results:
            # Check if already submitted or downloaded
            is_duplicate, _ = self.check_duplicate_submission(tracking_id, search_result["title"], session)
            if not is_duplicate:
                filtered_results.append(search_result)

        logger.info(f"Found {len(filtered_results)} new issues (filtered from {len(search_results)} total results)")

        # Prefer English editions and limit to 10 per batch
        # Sort results: English first, then by date (newest first)
        def sort_key(result):
            title_lower = result.get("title", "").lower()
            is_english = any(
                lang in title_lower
                for lang in ["english", "en", "usa", "uk", "us"]
            )
            # Put English first (0), others after (1)
            lang_priority = 0 if is_english else 1
            # Sort by publication date if available (newest first)
            pub_date = result.get("publication_date")
            if pub_date:
                # Negate timestamp to sort newest first within same language priority
                date_sort = -pub_date.timestamp()
            else:
                date_sort = 0
            return (lang_priority, date_sort)

        filtered_results.sort(key=sort_key)

        # Limit issues per batch - scheduler will pick up next batch on next run
        batch_results = filtered_results[:MAX_DOWNLOADS_PER_BATCH]

        if len(batch_results) > 0:
            logger.info(
                f"Submitting batch of {len(batch_results)} issues (limited to {MAX_DOWNLOADS_PER_BATCH} per batch, "
                f"English editions preferred). {len(filtered_results) - len(batch_results)} more available for next run."
            )
        elif len(filtered_results) == 0:
            logger.info(f"No new issues to download for '{tracking.title}' - all found issues already downloaded or pending")

        results = {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}

        for search_result in batch_results:
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
                logger.warning(f"Could not create DB search result: {e}", exc_info=True)

            # Submit download
            submission = self.submit_download(tracking_id, search_result, session, search_result_db_id)

            if submission:
                if submission.status == DownloadSubmission.StatusEnum.PENDING:
                    results["submitted"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.SKIPPED:
                    results["skipped"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.FAILED:
                    results["failed"] += 1
                    results["errors"].append(f"Failed: {search_result['title']} - {submission.last_error}")
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
        logger.info(f"Submitting single issue download: {search_result['title']} (tracking_id: {tracking_id})")

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
        submission = self.submit_download(tracking_id, search_result, session, search_result_db_id)

        return submission

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

            new_status = status_map.get(client_status.get("status"), DownloadSubmission.StatusEnum.PENDING)

            # Track previous status to detect transitions
            previous_status = submission.status

            # Update submission
            submission.status = new_status
            submission.updated_at = datetime.now(UTC)

            if "file_path" in client_status:
                submission.file_path = client_status["file_path"]
                logger.debug(f"[DownloadManager] Updated file_path for {job_id}: {submission.file_path}")

            if new_status == DownloadSubmission.StatusEnum.FAILED:
                # Increment attempt count on failure
                submission.attempt_count = (submission.attempt_count or 0) + 1
                submission.last_error = client_status.get("error", "Unknown error")

                logger.warning(
                    f"[DownloadManager] Download failed for {job_id}: {submission.last_error} "
                    f"(attempt {submission.attempt_count}/3)"
                )

                # Check if max retries reached
                if submission.attempt_count >= 3:
                    logger.error(
                        f"[DownloadManager] Max retries reached for '{submission.result_title}' "
                        f"- marking as bad file (will not retry)"
                    )

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
        submission = session.query(DownloadSubmission).filter(DownloadSubmission.id == submission_id).first()

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

    def get_failed_downloads(self, session: Session, include_bad_files: bool = False) -> List[DownloadSubmission]:
        """
        Get all failed download submissions.

        Args:
            session: Database session
            include_bad_files: If True, include files that have exceeded max retries

        Returns:
            List of failed submissions
        """
        query = session.query(DownloadSubmission).filter(
            DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED
        )

        if not include_bad_files:
            # Exclude submissions that have failed too many times (bad files)
            query = query.filter(DownloadSubmission.attempt_count < 3)

        failed = query.all()
        logger.debug(
            f"Found {len(failed)} failed submissions "
            f"({'including' if include_bad_files else 'excluding'} bad files)"
        )
        return failed

    def get_bad_files(self, session: Session) -> List[DownloadSubmission]:
        """
        Get submissions marked as bad (failed 3+ times).

        Args:
            session: Database session

        Returns:
            List of bad file submissions
        """
        bad_files = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                DownloadSubmission.attempt_count >= 3,
            )
            .all()
        )
        logger.debug(f"Found {len(bad_files)} bad files (failed 3+ times)")
        return bad_files

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

        if submission.status not in [
            DownloadSubmission.StatusEnum.FAILED,
            DownloadSubmission.StatusEnum.SKIPPED,
        ]:
            return {"success": False, "message": f"Cannot retry submission with status: {submission.status.value}"}

        # Check if this is a bad file (failed 3+ times)
        if submission.attempt_count >= 3:
            logger.warning(
                f"Cannot retry bad file (failed {submission.attempt_count} times): "
                f"{submission.result_title} (ID: {submission_id})"
            )
            return {
                "success": False,
                "message": f"Cannot retry: file has failed {submission.attempt_count} times (max 3)",
            }

        try:
            # Resubmit to download client
            logger.info(f"Retrying submission {submission_id}: {submission.result_title}")
            job_id = self.download_client.submit(nzb_url=submission.source_url, title=submission.result_title)

            if not job_id:
                logger.warning(f"Download client rejected retry submission: {submission.result_title}")
                return {"success": False, "message": "Download client rejected submission"}

            # Update submission record
            submission.job_id = job_id
            submission.status = DownloadSubmission.StatusEnum.PENDING
            submission.last_error = None
            submission.updated_at = datetime.now(UTC)
            # Note: Don't reset attempt_count, it should accumulate across retries
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
