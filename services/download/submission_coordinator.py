"""
Submission coordinator for download manager.
Handles submission logic: direct submission, issue-based submission, and batch queuing.
"""

import logging
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from core.constants.app import MAX_ERROR_LENGTH
from core.constants.files import BLACKLISTED_FILE_EXTENSIONS
from core.constants.language import ENGLISH_INDICATORS
from core.parsers import utc_now, Parser
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
    PeriodicalTracking,
)
from models.database import SearchResult as DBSearchResult
from services.download.nzb_submit import submit_with_nzb_content

logger = logging.getLogger(__name__)

MANUAL_DOWNLOAD_PRIORITY = 100


class SubmissionCoordinator:
    """Coordinate download submission logic."""

    def __init__(
        self,
        download_clients: Dict[str, DownloadClient],
        provider_client_map: Dict[str, str],
        nzb_cache_service: Optional[Any],
        max_downloads: int,
        default_category: Optional[str],
        parser: Parser,
        submission_service: Any,
        issue_discovery_service: Any,
        slot_lock: Lock,
        search_service: Any = None,
    ):
        """
        Initialize submission coordinator.

        Args:
            download_clients: Dict of available download clients keyed by type
            provider_client_map: Mapping of provider types to client types
            nzb_cache_service: Optional NZB cache service for content caching
            max_downloads: Maximum number of concurrent downloads allowed
            default_category: Default download category
            parser: Parser instance for parsing search results
            submission_service: SubmissionService instance
            issue_discovery_service: IssueDiscoveryService instance
            slot_lock: Threading lock for serializing slot counting
            search_service: Optional SearchService instance (needed for download_all_periodical_issues)
        """
        self.download_clients = download_clients
        self.provider_client_map = provider_client_map
        self.nzb_cache_service = nzb_cache_service
        self.max_downloads = max_downloads
        self.default_category = default_category
        self.parser = parser
        self.submission_service = submission_service
        self.issue_discovery_service = issue_discovery_service
        self._slot_lock = slot_lock
        self.search_service = search_service

    # ------------------------------------------------------------------
    # Client routing helpers
    # ------------------------------------------------------------------

    def _get_client_for_provider(self, provider: str, url: Optional[str] = None) -> DownloadClient:
        """
        Get the appropriate download client for a provider.

        Uses URL-based fallback detection if provider routing fails.
        This handles legacy data where provider field may be incorrect.

        Args:
            provider: Provider type (e.g., 'internet_archive', 'newsnab')
            url: Optional download URL for fallback provider detection

        Returns:
            DownloadClient instance for this provider
        """
        # Look up which client type to use for this provider
        client_type = self.provider_client_map.get(provider, "default")

        # If routing failed (using default) and URL provided, try URL-based detection
        if client_type == "default" and url:
            # Check if this is an Internet Archive URL
            if "archive.org" in url or url.startswith("ia:"):
                # Try to use IA client if available
                if "internet_archive" in self.download_clients:
                    logger.debug(
                        f"Provider '{provider}' not in routing map, but URL indicates "
                        f"Internet Archive - using IA client"
                    )
                    client_type = "internet_archive"
                else:
                    logger.warning(f"Archive.org URL detected but no IA client configured: {url}")

        # Get the client, falling back to default if not available
        client = self.download_clients.get(client_type)
        if not client:
            logger.debug(f"Client '{client_type}' not found for provider '{provider}', using default")
            client = self.download_clients["default"]

        return client

    def _get_client_name_for_provider(self, provider: str) -> str:
        """
        Get the client name for a provider, for storing on QUEUED submissions.

        Args:
            provider: Provider type (e.g., 'internet_archive', 'newsnab')

        Returns:
            Client name string
        """
        client = self._get_client_for_provider(provider)
        return client.name

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
    # Category and slot helpers
    # ------------------------------------------------------------------

    def _get_download_category(self, tracking_id: int, session: Session) -> Optional[str]:
        """
        Determine the download category for a submission.

        Priority: tracking-specific category > system default.

        Args:
            tracking_id: Periodical tracking ID
            session: Database session

        Returns:
            Category name or None if no category configured
        """
        tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()

        if tracking and tracking.download_category:
            logger.debug(f"[DownloadManager] Using tracked item download_category: {tracking.download_category}")
            return tracking.download_category
        elif self.default_category:
            logger.debug(f"[DownloadManager] Using default download_category: {self.default_category}")
            return self.default_category

        return None

    def _get_active_download_count(self, session: Session) -> int:
        """
        Count currently active (pending or downloading) submissions.

        Args:
            session: Database session

        Returns:
            Number of active downloads
        """
        return (
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

    # ------------------------------------------------------------------
    # Title / file validation helpers
    # ------------------------------------------------------------------

    def _is_english_edition(self, title: str) -> bool:
        """
        Check if title contains English language/region indicators.

        Args:
            title: Search result title to check

        Returns:
            True if title contains English language/region indicators
        """
        title_lower = title.lower()
        return any(indicator in f" {title_lower} " for indicator in ENGLISH_INDICATORS)

    def _has_blacklisted_extension(self, title: str) -> bool:
        """
        Check if title contains a blacklisted file extension.

        Args:
            title: Search result title to check

        Returns:
            True if title contains a blacklisted extension
        """
        title_lower = title.lower()
        return any(ext in title_lower for ext in BLACKLISTED_FILE_EXTENSIONS)

    def _create_search_result_record(
        self,
        search_result: Dict[str, Any],
        query: str,
        session: Session,
    ) -> Optional[int]:
        """
        Create a database SearchResult record for tracking.

        Args:
            search_result: Search result dict
            query: Original search query
            session: Database session

        Returns:
            Database record ID or None if creation failed
        """
        try:
            db_result = DBSearchResult(
                provider=search_result.get("provider", "unknown"),
                query=query,
                title=search_result["title"],
                url=search_result["url"],
                publication_date=search_result.get("publication_date"),
                raw_metadata=search_result.get("raw_metadata", {}),
            )
            session.add(db_result)
            session.flush()
            return db_result.id
        except Exception as e:
            logger.warning(f"Could not create DB search result: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Submission record helpers
    # ------------------------------------------------------------------

    def _create_submission_record(
        self,
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
        Create and commit a DownloadSubmission record.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            status: Submission status
            session: Database session
            search_result_db_id: Optional ID of SearchResult DB record
            job_id: Download client job ID (for PENDING/DOWNLOADING)
            error_message: Error message (for FAILED)
            client_name: Name of download client (for PENDING/DOWNLOADING)
            attempt_count: Number of attempts (default 0, set to 1 for new submissions)

        Returns:
            Created DownloadSubmission record
        """
        return self.submission_service.create_submission_record(
            tracking_id,
            search_result,
            status,
            session,
            search_result_db_id=search_result_db_id,
            job_id=job_id,
            error_message=error_message,
            client_name=client_name,
            attempt_count=attempt_count,
        )

    def _handle_client_rejection(
        self,
        tracking_id: int,
        search_result: Dict[str, Any],
        client_name: str,
        session: Session,
        search_result_db_id: Optional[int],
    ) -> None:
        """
        Handle download client rejection of submission.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict
            client_name: Name of the client that rejected
            session: Database session
            search_result_db_id: Optional SearchResult DB record ID
        """
        title = search_result["title"]
        logger.warning(f"Download client {client_name} rejected submission: {title}")
        self._create_submission_record(
            tracking_id,
            search_result,
            DownloadSubmission.StatusEnum.FAILED,
            session,
            search_result_db_id=search_result_db_id,
            error_message=f"Client {client_name} rejected submission",
            attempt_count=1,
        )

    def _handle_submission_error(
        self,
        tracking_id: int,
        search_result: Dict[str, Any],
        error: Exception,
        session: Session,
        search_result_db_id: Optional[int],
    ) -> None:
        """
        Handle error during submission to download client.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict
            error: Exception that occurred
            session: Database session
            search_result_db_id: Optional SearchResult DB record ID
        """
        title = search_result["title"]
        logger.error(f"Error submitting download for '{title}': {error}", exc_info=True)
        self._create_submission_record(
            tracking_id,
            search_result,
            DownloadSubmission.StatusEnum.FAILED,
            session,
            search_result_db_id=search_result_db_id,
            error_message=str(error),
            attempt_count=1,
        )

    # ------------------------------------------------------------------
    # DiscoveredIssue helpers
    # ------------------------------------------------------------------

    def _record_attempt(self, issue) -> None:
        """Increment attempt counter and record the attempt timestamp."""
        issue.attempt_count += 1
        issue.last_attempt = utc_now()

    def _register_submission_id(self, issue, submission_id: int) -> None:
        """Append submission_id to issue.submission_ids if not already present."""
        if submission_id not in (issue.submission_ids or []):
            issue.submission_ids = (issue.submission_ids or []) + [submission_id]

    def _build_search_result_from_issue(self, issue, discovered_issue_id: int) -> Dict[str, Any]:
        """
        Build search_result dict from DiscoveredIssue for use by submission helpers.

        Args:
            issue: DiscoveredIssue record
            discovered_issue_id: ID of the discovered issue

        Returns:
            Search result dictionary
        """
        return {
            "title": issue.title,
            "url": issue.latest_url,
            "provider": issue.latest_provider or "unknown",
            "pubdate": issue.issue_date.isoformat() if issue.issue_date else None,
            "guid": str(discovered_issue_id),
            "raw_metadata": issue.extra_metadata or {},
        }

    def _create_queued_submission(self, issue, search_result: Dict[str, Any], session: Session) -> DownloadSubmission:
        """
        Create a queued submission when at download limit.

        Args:
            issue: DiscoveredIssue record
            search_result: Search result dict
            session: Database session

        Returns:
            Created DownloadSubmission record
        """
        provider = issue.latest_provider or "unknown"
        active_count = self._get_active_download_count(session)

        logger.info(f"At download limit ({active_count}/{self.max_downloads}), " f"queuing download: '{issue.title}'")

        submission = self._create_submission_record(
            issue.tracking_id,
            search_result,
            DownloadSubmission.StatusEnum.QUEUED,
            session,
            client_name=self._get_client_name_for_provider(provider),
            attempt_count=0,
        )

        # Update DiscoveredIssue with submission info
        issue.download_status = DownloadStatus.QUEUED
        issue.current_submission_id = submission.id
        self._register_submission_id(issue, submission.id)
        session.commit()

        return submission

    # ------------------------------------------------------------------
    # Core submission methods
    # ------------------------------------------------------------------

    def _submit_to_client(
        self,
        tracking_id: int,
        search_result: Dict[str, Any],
        session: Session,
        search_result_db_id: Optional[int] = None,
    ) -> Optional[DownloadSubmission]:
        """
        Submit a download to the appropriate download client based on provider.

        Handles client selection, submission, rejection, and error recording.
        Called after all validation checks pass.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            session: Database session
            search_result_db_id: Optional ID of SearchResult DB record

        Returns:
            DownloadSubmission record if submitted successfully, None if failed
        """
        title = search_result["title"]
        provider = search_result.get("provider", "unknown")
        download_category = self._get_download_category(tracking_id, session)
        client = self._get_client_for_provider(provider, search_result.get("url"))

        try:
            logger.debug(
                f"[DownloadManager] Submitting to {client.name} (provider: {provider}): "
                f"{title} (category: {download_category})"
            )

            job_id = self._submit_with_nzb_content(
                client=client,
                nzb_url=search_result["url"],
                title=title,
                category=download_category,
            )

            if not job_id:
                self._handle_client_rejection(
                    tracking_id,
                    search_result,
                    client.name,
                    session,
                    search_result_db_id,
                )
                return None

            logger.debug(f"[DownloadManager] Client {client.name} accepted, job_id: {job_id}")
            submission = self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.PENDING,
                session,
                search_result_db_id=search_result_db_id,
                job_id=job_id,
                client_name=client.name,
                attempt_count=0,
            )
            logger.info(f"Submitted download: {title} (job_id: {job_id}, client: {client.name})")
            return submission

        except Exception as e:
            self._handle_submission_error(tracking_id, search_result, e, session, search_result_db_id)
            return None

    def _validate_discovered_issue(self, issue, session: Session) -> Optional[str]:
        """
        Validate discovered issue for download submission.

        Args:
            issue: DiscoveredIssue record
            session: Database session

        Returns:
            Error message if validation fails, None if valid
        """
        if not issue:
            return "DiscoveredIssue not found"

        # Check if already downloading, queued, or pending — prevent duplicate concurrent submissions
        if (
            issue.download_status
            in (
                DownloadStatus.DOWNLOADING,
                DownloadStatus.QUEUED,
                DownloadStatus.PENDING,
            )
            and issue.current_submission_id
        ):
            logger.warning(
                f"Issue already has active download: {issue.title} "
                f"(status: {issue.download_status}, submission_id: {issue.current_submission_id})"
            )
            return "already_downloading"

        # Check if this is a bad file
        if issue.download_status == DownloadStatus.PERMANENTLY_FAILED:
            logger.warning(f"Skipping bad file (marked as permanently failed): {issue.title}")
            return "permanently_failed"

        # Check blacklisted file types
        if self._has_blacklisted_extension(issue.title):
            logger.warning(f"Skipping discovered issue with blacklisted extension: {issue.title}")
            issue.download_status = DownloadStatus.PERMANENTLY_FAILED
            issue.last_error = "Blacklisted file extension"
            session.commit()
            return "blacklisted_extension"

        # Validate we have the necessary metadata
        if not issue.latest_url:
            logger.error(f"DiscoveredIssue missing URL: {issue.title}")
            # Mark as failed
            issue.download_status = DownloadStatus.FAILED
            issue.last_error = "Missing URL"
            session.commit()
            return "missing_url"

        return None

    def _submit_issue_to_client(
        self, issue, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Submit discovered issue to download client.

        Args:
            issue: DiscoveredIssue record
            search_result: Search result dict
            session: Database session

        Returns:
            DownloadSubmission record or None if failed
        """
        try:
            # Get category for this periodical
            download_category = self._get_download_category(issue.tracking_id, session)

            # Get the appropriate client for this provider
            provider = issue.latest_provider or "unknown"
            client = self._get_client_for_provider(provider, issue.latest_url)

            logger.info(
                f"Submitting discovered issue to {client.name}: {issue.title} "
                f"(priority: {issue.download_priority}, category: {download_category}, provider: {provider})"
            )

            job_id = self._submit_with_nzb_content(
                client=client,
                nzb_url=issue.latest_url,
                title=issue.title,
                category=download_category,
            )

            if not job_id:
                logger.warning(f"Download client {client.name} rejected submission: {issue.title}")
                issue.download_status = DownloadStatus.FAILED
                issue.last_error = f"Client {client.name} rejected submission"
                self._record_attempt(issue)
                session.commit()
                return None

            # Create submission record
            submission = self._create_submission_record(
                issue.tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.PENDING,
                session,
                job_id=job_id,
                client_name=client.name,
                attempt_count=1,
            )

            # Update DiscoveredIssue with submission info
            issue.download_status = DownloadStatus.PENDING  # Submitted to and accepted by download client
            issue.current_submission_id = submission.id
            self._register_submission_id(issue, submission.id)
            self._record_attempt(issue)

            session.commit()

            logger.info(f"Submitted discovered issue: {issue.title} (job_id: {job_id}, submission_id: {submission.id})")
            return submission

        except Exception as e:
            logger.error(
                f"Error submitting discovered issue '{issue.title}': {e}",
                exc_info=True,
            )
            issue.download_status = DownloadStatus.FAILED
            error_str = str(e)
            if len(error_str) > MAX_ERROR_LENGTH:
                logger.warning(f"Error message truncated from {len(error_str)} to {MAX_ERROR_LENGTH} chars")
            issue.last_error = error_str[:MAX_ERROR_LENGTH]
            self._record_attempt(issue)
            session.commit()
            return None

    def submit_from_discovered_issue(self, discovered_issue_id: int, session: Session) -> Optional[DownloadSubmission]:
        """
        Submit a download from a DiscoveredIssue (new Issue Discovery & Tracking system).

        This method bridges the new DiscoveredIssue system with the existing download submission.
        It updates the DiscoveredIssue status as it progresses through the download lifecycle.

        Args:
            discovered_issue_id: DiscoveredIssue ID to download
            session: Database session

        Returns:
            DownloadSubmission record if submitted, None if error or already downloading
        """
        # Get the discovered issue
        issue = session.query(DiscoveredIssue).filter(DiscoveredIssue.id == discovered_issue_id).first()

        # Validate the issue
        error = self._validate_discovered_issue(issue, session)
        if error:
            if error not in ["already_downloading", "permanently_failed"]:
                logger.error(f"DiscoveredIssue validation failed: {error} (id: {discovered_issue_id})")
            return None

        # Build search result for compatibility
        search_result = self._build_search_result_from_issue(issue, discovered_issue_id)

        # Acquire lock only to check the slot count and make the queue-vs-submit decision.
        # The actual submission (which calls session.commit()) happens outside the lock
        # to avoid holding a threading lock across slow DB operations.
        with self._slot_lock:
            active_count = self._get_active_download_count(session)
            should_queue = active_count >= self.max_downloads

        if should_queue:
            return self._create_queued_submission(issue, search_result, session)

        # Submit to download client (outside the lock)
        return self._submit_issue_to_client(issue, search_result, session)

    def _manual_direct_submission(
        self, tracking_id: int, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Direct submission for manual user-initiated downloads.
        Bypasses duplicate checking since the user explicitly requested the download.
        Used as fallback when Issue Discovery system fails.

        Attempts to create a minimal DiscoveredIssue after submission so the download
        monitor can track the submission going forward.
        """
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

        # Skip duplicate checking for manual downloads — user explicitly wants this
        # Acquire lock only to check the slot count and make the queue-vs-submit decision.
        # The actual submission (which calls session.commit()) happens outside the lock
        # to avoid holding a threading lock across slow DB operations.
        provider = search_result.get("provider", "unknown")
        with self._slot_lock:
            active_count = self._get_active_download_count(session)
            should_queue = active_count >= self.max_downloads

        if should_queue:
            logger.info(
                f"[DownloadManager] At download limit ({active_count}/{self.max_downloads}), "
                f"queuing manual download: '{search_result['title']}'"
            )
            submission = self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.QUEUED,
                session,
                search_result_db_id=search_result_db_id,
                client_name=self._get_client_name_for_provider(provider),
                attempt_count=0,
            )
        else:
            submission = self._submit_to_client(tracking_id, search_result, session, search_result_db_id)

        # Attempt to create a DiscoveredIssue and link it so the monitor can track this submission.
        # This is best-effort — we're already in a fallback path, so don't fail if this also errors.
        if submission:
            self._link_manual_submission_to_discovered_issue(tracking_id, search_result, submission, session)

        return submission

    def _link_manual_submission_to_discovered_issue(
        self,
        tracking_id: int,
        search_result: Dict[str, Any],
        submission: DownloadSubmission,
        session: Session,
    ) -> None:
        """
        Best-effort: create or find a DiscoveredIssue and link it to a manual submission.

        Called after _manual_direct_submission creates a DownloadSubmission without going
        through IssueDiscoveryService. Ensures the download monitor can sync status for this
        submission going forward.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict
            submission: The DownloadSubmission that was just created
            session: Database session
        """
        try:
            title = search_result.get("title", "")
            url = search_result.get("url", "")
            provider = search_result.get("provider", "unknown")

            parsed = self.parser.parse_search_result(title=title, url=url, provider=provider)
            if not parsed:
                logger.debug(f"[DownloadManager] Could not parse title for manual submission link: {title}")
                return

            fuzzy_group = get_fuzzy_group_id(parsed.original_title)

            # Find an existing DiscoveredIssue for this group, or create one
            discovered_issue = (
                session.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.fuzzy_match_group == fuzzy_group,
                )
                .first()
            )

            if not discovered_issue:
                now = utc_now()
                discovered_issue = DiscoveredIssue(
                    tracking_id=tracking_id,
                    title=title,
                    normalized_title=parsed.cleaned_title.lower(),
                    fuzzy_match_group=fuzzy_group,
                    issue_date=parsed.publication_date,
                    year=parsed.publication_date.year if parsed.publication_date else None,
                    month=parsed.publication_date.month if parsed.publication_date else None,
                    language=parsed.language,
                    country=parsed.country,
                    first_seen=now,
                    last_seen=now,
                    times_seen=1,
                    download_priority=MANUAL_DOWNLOAD_PRIORITY,
                    latest_url=url,
                    latest_provider=provider,
                )
                session.add(discovered_issue)
                session.flush()
                logger.debug(f"[DownloadManager] Created DiscoveredIssue for manual fallback submission: {title}")

            # Set status and link to submission
            if submission.status == DownloadSubmission.StatusEnum.PENDING:
                discovered_issue.download_status = DownloadStatus.PENDING
            elif submission.status == DownloadSubmission.StatusEnum.QUEUED:
                discovered_issue.download_status = DownloadStatus.QUEUED
            else:
                discovered_issue.download_status = DownloadStatus.WANTED

            discovered_issue.current_submission_id = submission.id
            ids = list(discovered_issue.submission_ids or [])
            if submission.id not in ids:
                ids.append(submission.id)
                discovered_issue.submission_ids = ids

            session.commit()
            logger.debug(
                f"[DownloadManager] Linked manual submission {submission.id} to "
                f"DiscoveredIssue {discovered_issue.id} (status: {discovered_issue.download_status})"
            )

        except Exception as e:
            logger.warning(
                f"[DownloadManager] Could not link manual submission {submission.id} to DiscoveredIssue: {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def download_single_issue(
        self, tracking_id: int, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Download a single issue submitted by the user.

        This method now uses the Issue Discovery & Tracking system to ensure
        all downloads (manual and automatic) flow through the same tracking system.

        Args:
            tracking_id: Periodical tracking ID (for tracking/organization)
            search_result: Search result dict with title, url, etc.
            session: Database session

        Returns:
            DownloadSubmission record if successful
        """
        title = search_result["title"]
        logger.info(f"Submitting single issue download: {title} (tracking_id: {tracking_id})")

        # Record this as a discovered issue (will be "wanted" if it matches tracking rules)
        record_result = self.issue_discovery_service.record_search_results(
            tracking_id=tracking_id,
            search_results=[search_result],
            session=session,
        )

        if record_result["new"] == 0 and record_result["updated"] == 0:
            logger.warning(f"Failed to record search result for manual download: {title}")
            return self._manual_direct_submission(tracking_id, search_result, session)

        # Find the discovered issue by fuzzy_match_group (same approach as issue_discovery)
        # NOTE: Don't match by exact title — record_search_results may have found an
        # existing DiscoveredIssue whose stored title differs from this search result title
        parsed = self.parser.parse_search_result(
            title=title,
            url=search_result.get("url", ""),
            provider=search_result.get("provider", ""),
        )

        discovered_issue = None
        if parsed:
            fuzzy_group = get_fuzzy_group_id(parsed.original_title)
            discovered_issue = (
                session.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.fuzzy_match_group == fuzzy_group,
                )
                .first()
            )

        if not discovered_issue:
            logger.error(f"Could not find DiscoveredIssue after recording: {title}")
            return self._manual_direct_submission(tracking_id, search_result, session)

        # Force status to "wanted" for manual downloads (user explicitly requested it)
        # This allows re-downloading previously failed/completed/skipped issues
        if discovered_issue.download_status not in [
            DownloadStatus.WANTED,
            DownloadStatus.QUEUED,
            DownloadStatus.PENDING,
            DownloadStatus.DOWNLOADING,
        ]:
            discovered_issue.download_status = DownloadStatus.WANTED
            discovered_issue.download_priority = MANUAL_DOWNLOAD_PRIORITY
            discovered_issue.attempt_count = 0
            discovered_issue.last_error = None
            session.commit()

        # Submit using the standard Issue Discovery flow
        return self.submit_from_discovered_issue(discovered_issue.id, session)

    def download_all_periodical_issues(self, tracking_id: int, session: Session) -> Dict[str, Any]:
        """
        Search for all issues of a tracked periodical and submit downloads.
        Called when track_all_editions is set to True.

        Routes all results through IssueDiscoveryService so every submission is
        linked to a DiscoveredIssue and tracked through the unified state machine.

        Args:
            tracking_id: Periodical tracking ID
            session: Database session

        Returns:
            Dict with submission results
        """
        # Get tracking record
        tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()

        if not tracking:
            logger.error(f"Tracking record not found: {tracking_id}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        logger.info(f"Starting download search for all issues of: {tracking.title} (tracking_id: {tracking_id})")

        # Search for issues — delegate to a search service if available, otherwise use stored reference
        search_results = self._search_periodical_issues(tracking.title, session)

        results = {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}

        if not search_results:
            logger.info(f"No search results for '{tracking.title}'")
            return results

        # Record and evaluate in one step: creates/updates DiscoveredIssue records,
        # then promotes "discovered" → "wanted" or "ignored" based on tracking rules.
        pipeline_stats = self.issue_discovery_service.discover_and_evaluate(
            tracking_id=tracking_id,
            search_results=search_results,
            session=session,
        )
        logger.info(
            f"Recorded search results: {pipeline_stats['new']} new, {pipeline_stats['updated']} updated, "
            f"{pipeline_stats.get('rejected_non_periodical', 0)} rejected"
        )
        logger.info(
            f"Evaluated issues: {pipeline_stats['wanted']} wanted, {pipeline_stats['ignored']} ignored, "
            f"{pipeline_stats['already_have']} already have"
        )

        # Fetch all "wanted" issues for this tracking record and submit them
        wanted_issues = self.issue_discovery_service.get_download_queue(
            session, limit=len(search_results), tracking_id=tracking_id
        )

        if not wanted_issues:
            logger.info(
                f"No new issues to download for '{tracking.title}' - "
                f"all found issues already downloaded, pending, or filtered"
            )
            return results

        logger.info(
            f"Submitting {len(wanted_issues)} issues for download "
            f"(max concurrent: {self.max_downloads}, excess will be queued)"
        )

        for issue in wanted_issues:
            submission = self.submit_from_discovered_issue(issue.id, session)
            if submission:
                if submission.status == DownloadSubmission.StatusEnum.PENDING:
                    results["submitted"] += 1
                elif submission.status == DownloadSubmission.StatusEnum.QUEUED:
                    results.setdefault("queued", 0)
                    results["queued"] += 1
                else:
                    results["skipped"] += 1
            else:
                results["skipped"] += 1

        logger.info(
            f"Download search completed: submitted={results['submitted']}, "
            f"queued={results.get('queued', 0)}, "
            f"skipped={results['skipped']}, failed={results['failed']}"
        )

        return results

    def _search_periodical_issues(self, periodical_title: str, session: Session) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.
        Delegates to the search_service stored on this coordinator.

        Args:
            periodical_title: Title of the periodical to search for
            session: Database session

        Returns:
            List of search results
        """
        if not self.search_service:
            logger.error("[SubmissionCoordinator] No search_service configured for download_all_periodical_issues")
            return []
        return self.search_service.search_periodical_issues(periodical_title, session)

    def queue_issue_for_batch(
        self, tracking_id: int, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Record a single issue in the discovery system and queue it for download.

        Unlike download_single_issue, this method never calls the download client
        directly — it always creates a QUEUED submission.  This makes it safe to
        call for large batches inside a single HTTP request because no outbound
        HTTP round-trips are made; the queue processor picks up the work later.

        Args:
            tracking_id: Periodical tracking ID
            search_result: Search result dict with title, url, provider, etc.
            session: Database session

        Returns:
            DownloadSubmission record (status QUEUED), or None on error
        """
        title = search_result["title"]
        logger.info(f"Queuing issue for batch download: {title} (tracking_id: {tracking_id})")

        # Record in the discovery system so the queue processor can track it
        record_result = self.issue_discovery_service.record_search_results(
            tracking_id=tracking_id,
            search_results=[search_result],
            session=session,
        )

        if record_result["new"] == 0 and record_result["updated"] == 0:
            logger.warning(f"Failed to record search result for batch download: {title}")
            return None

        # Find the discovered issue by fuzzy_match_group
        parsed = self.parser.parse_search_result(
            title=title,
            url=search_result.get("url", ""),
            provider=search_result.get("provider", ""),
        )

        discovered_issue = None
        if parsed:
            fuzzy_group = get_fuzzy_group_id(parsed.original_title)
            discovered_issue = (
                session.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.fuzzy_match_group == fuzzy_group,
                )
                .first()
            )

        if not discovered_issue:
            logger.error(f"Could not find DiscoveredIssue after recording for batch: {title}")
            return None

        # Skip issues already actively downloading or queued — no double-submission
        if discovered_issue.download_status in (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.QUEUED,
            DownloadStatus.PENDING,
        ):
            logger.debug(f"Skipping already-active issue in batch: {title} ({discovered_issue.download_status})")
            return None

        # Reset failed/skipped issues so the user's explicit request takes priority
        if discovered_issue.download_status not in (DownloadStatus.WANTED,):
            discovered_issue.download_status = DownloadStatus.WANTED
            discovered_issue.download_priority = MANUAL_DOWNLOAD_PRIORITY
            discovered_issue.attempt_count = 0
            discovered_issue.last_error = None

        # Always queue — never submit directly to the HTTP client in a batch
        build = self._build_search_result_from_issue(discovered_issue, discovered_issue.id)
        return self._create_queued_submission(discovered_issue, build, session)
