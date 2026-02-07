"""
Download manager for handling periodical downloads.
Coordinates search, deduplication, submission, and status tracking.
"""

# pylint: disable=too-many-lines

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient, SearchProvider
from core.constants.app import (
    DEFAULT_FUZZY_THRESHOLD,
    MAX_DOWNLOAD_RETRIES,
)
from core.constants.category import DEFAULT_CATEGORY
from core.constants.files import BLACKLISTED_FILE_EXTENSIONS
from core.parsers import utc_now, TitleMatcher, Parser
from core.parsers.categorizer import FileCategorizer
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import (
    DownloadSubmission,
    Periodical,
    PeriodicalTracking,
)
from models.database import SearchResult as DBSearchResult
from services.download import SearchService, DeduplicationService, SubmissionService, QueueProcessor

logger = logging.getLogger(__name__)


class DownloadManager:
    """Manage downloads for tracked periodicals"""

    # Default provider to client routing
    DEFAULT_PROVIDER_CLIENT_MAP = {
        "internet_archive": "internet_archive",
        "newsnab": "default",
        "rss": "default",
    }

    def __init__(
        self,
        search_providers: List[SearchProvider],
        download_client: DownloadClient,
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
        max_downloads: int = 10,
        nzb_cache_service: Optional[Any] = None,
        download_clients: Optional[Dict[str, DownloadClient]] = None,
        provider_client_map: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize download manager.

        Args:
            search_providers: List of search providers to use
            download_client: Default download client to submit jobs to
            fuzzy_threshold: Fuzzy matching threshold for deduplication
            max_downloads: Maximum number of concurrent downloads allowed
            nzb_cache_service: Optional NZB cache service for content caching
            download_clients: Optional dict of additional download clients keyed by type
            provider_client_map: Optional mapping of provider types to client types
        """
        self.search_providers = search_providers
        self.download_client = download_client

        # Multi-client support: build dict of all available clients
        self.download_clients: Dict[str, DownloadClient] = {"default": download_client}
        if download_clients:
            self.download_clients.update(download_clients)

        # Provider to client routing
        self.provider_client_map = provider_client_map or self.DEFAULT_PROVIDER_CLIENT_MAP.copy()

        # Get default category from client config (handles mocks gracefully)
        client_config = getattr(download_client, "config", {})
        self.default_category = (
            client_config.get("default_category", DEFAULT_CATEGORY)
            if isinstance(client_config, dict)
            else DEFAULT_CATEGORY
        )
        self.max_downloads = max_downloads
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.nzb_cache_service = nzb_cache_service
        self.categorizer = FileCategorizer()

        # Initialize services
        self.search_service = SearchService(search_providers, fuzzy_threshold)
        self.deduplication_service = DeduplicationService()
        self.submission_service = SubmissionService()
        self.queue_processor = QueueProcessor(download_client, max_downloads, nzb_cache_service)

        # Log available clients
        client_names = list(self.download_clients.keys())
        logger.info(f"DownloadManager initialized with clients: {client_names}")

    def _get_client_for_provider(self, provider: str) -> DownloadClient:
        """
        Get the appropriate download client for a provider.

        Args:
            provider: Provider type (e.g., 'internet_archive', 'newsnab')

        Returns:
            DownloadClient instance for this provider
        """
        # Look up which client type to use for this provider
        client_type = self.provider_client_map.get(provider, "default")

        # Get the client, falling back to default if not available
        client = self.download_clients.get(client_type)
        if not client:
            logger.debug(f"Client '{client_type}' not found for provider '{provider}', using default")
            client = self.download_clients["default"]

        return client

    def _submit_with_nzb_content(
        self,
        client: DownloadClient,
        nzb_url: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Submit a download, preferring cached NZB content over URL to avoid provider rate limits.

        Tries in order:
        1. Cached NZB content from provider cache → submit_content() (no provider hit)
        2. Fetch NZB content from provider → submit_content() (one provider hit, then cached)
        3. Fallback to URL submission → submit() (provider hit by download client)

        Args:
            client: Download client to submit to
            nzb_url: NZB download URL
            title: Download title
            category: Optional download category

        Returns:
            Job ID from download client, or None if all methods failed
        """
        # Try NZB content-based submission if cache service is available
        if self.nzb_cache_service and hasattr(client, "submit_content"):
            try:
                nzb_content = self.nzb_cache_service.get_nzb_content(nzb_url)
                if nzb_content:
                    job_id = client.submit_content(
                        nzb_content=nzb_content,
                        title=title,
                        category=category,
                    )
                    if job_id:
                        logger.info(f"[DownloadManager] Submitted via cached NZB content: {title} -> {job_id}")
                        return job_id
                    logger.warning(f"[DownloadManager] submit_content failed for {title}, falling back to URL")
            except Exception as e:
                logger.warning(f"[DownloadManager] NZB content submission error: {e}, falling back to URL")

        # Fallback: submit URL directly (download client fetches NZB from provider)
        return client.submit(nzb_url=nzb_url, title=title, category=category)

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

    def _is_english_edition(self, title: str) -> bool:
        """
        Check if a search result title appears to be an English-language edition.

        Used to prioritize English editions when downloading all issues.
        Detection is intentionally broad - false positives (e.g., "Queen Magazine"
        matching "en") are acceptable since this only affects sort order, not filtering.

        Args:
            title: Search result title to check

        Returns:
            True if title contains English language/region indicators
        """
        title_lower = title.lower()
        english_indicators = ["english", " en ", " en-", "-en ", "usa", " uk ", " uk-", "-uk ", " us ", " us-", "-us "]
        return any(indicator in f" {title_lower} " for indicator in english_indicators)

    def _get_result_sort_key(self, result: Dict[str, Any]) -> Tuple[int, float]:
        """
        Generate sort key for prioritizing search results.

        Sorts by: English editions first, then newest publication date.
        Used when downloading all issues to prefer English and recent releases.

        Args:
            result: Search result dict with title and optional publication_date

        Returns:
            Tuple of (language_priority, date_sort) for sorting
        """
        # English editions get priority 0, others get 1
        lang_priority = 0 if self._is_english_edition(result.get("title", "")) else 1

        # Sort by publication date (newest first via negative timestamp)
        pub_date = result.get("publication_date")
        date_sort = -pub_date.timestamp() if pub_date else 0

        return (lang_priority, date_sort)

    def _has_blacklisted_extension(self, title: str) -> bool:
        """
        Check if title contains a blacklisted file extension.

        Blacklisted extensions indicate non-periodical content (e.g., .exe, .mp3)
        that should never be downloaded.

        Args:
            title: Search result title to check

        Returns:
            True if title contains a blacklisted extension
        """
        title_lower = title.lower()
        return any(ext in title_lower for ext in BLACKLISTED_FILE_EXTENSIONS)

    def _collect_submission_result(
        self,
        submission: Optional[DownloadSubmission],
        search_result: Dict[str, Any],
        results: Dict[str, Any],
    ) -> None:
        """
        Update result counts based on submission status.

        Args:
            submission: DownloadSubmission or None if skipped
            search_result: Original search result dict (for error messages)
            results: Results dict to update with counts and errors
        """
        if not submission:
            results["skipped"] += 1
            return

        if submission.status == DownloadSubmission.StatusEnum.PENDING:
            results["submitted"] += 1
        elif submission.status == DownloadSubmission.StatusEnum.QUEUED:
            results.setdefault("queued", 0)
            results["queued"] += 1
        elif submission.status == DownloadSubmission.StatusEnum.SKIPPED:
            results["skipped"] += 1
        elif submission.status == DownloadSubmission.StatusEnum.FAILED:
            results["failed"] += 1
            results["errors"].append(f"Failed: {search_result['title']} - {submission.last_error}")

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

    def _is_bad_file(
        self, tracking_id: int, fuzzy_group: str, session: Session, url: str = ""
    ) -> Optional[DownloadSubmission]:
        """
        Check if this file has failed too many times and should not be retried.

        Uses fuzzy_match_group instead of URL because providers may return different
        URLs for the same file (e.g., different tokens/timestamps).

        Note: Internet Archive downloads are treated more leniently since failures
        are typically due to server load rather than bad files.

        Args:
            tracking_id: Periodical tracking ID
            fuzzy_group: Fuzzy match group identifier for the title
            session: Database session
            url: Download URL (used to identify provider)

        Returns:
            The failed submission record if this is a bad file, None otherwise
        """
        # Internet Archive failures are usually transient (server busy, rate limits)
        # not bad files - don't mark them as permanently failed
        if url and "archive.org" in url:
            return None

        return (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.tracking_id == tracking_id,
                DownloadSubmission.fuzzy_match_group == fuzzy_group,
                DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                DownloadSubmission.attempt_count > MAX_DOWNLOAD_RETRIES,
            )
            .first()
        )

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

    def _get_download_category(self, tracking_id: int, session: Session) -> Optional[str]:
        """
        Determine the download category for a submission.

        Priority: tracking-specific category > system default.
        This allows per-periodical organization (e.g., "Comics" vs "Magazines").

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

    def search_periodical_issues(self, periodical_title: str, session: Session) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.

        Args:
            periodical_title: Title of the periodical to search for (may include language)
            session: Database session

        Returns:
            List of search results with deduplication grouping
        """
        return self.search_service.search_periodical_issues(periodical_title, session)

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

        Centralizes submission creation to ensure consistency.

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

    def check_duplicate_submission(
        self, tracking_id: int, result_title: str, session: Session
    ) -> Tuple[bool, Optional[DownloadSubmission]]:
        """
        Check if this search result was already submitted for download or exists in library.

        Args:
            tracking_id: Periodical tracking ID
            result_title: Title of the search result
            session: Database session

        Returns:
            Tuple of (is_duplicate, existing_submission_record)
        """
        # Check submissions table for duplicates
        is_dup, existing = self.deduplication_service.check_duplicate_submission(result_title, tracking_id, session)

        if is_dup:
            return True, existing

        # Also check if already in library (Periodical table)
        # Parse search result to get standardized fields
        parsed = self.parser.parse_search_result(
            title=result_title,
            url="",  # Not needed for duplicate check
            provider="",  # Not needed for duplicate check
        )

        # Skip if parser rejected as non-periodical (movies/TV/audiobooks)
        if parsed is None:
            logger.debug(f"Skipping non-periodical result: {result_title}")
            return False, None

        logger.debug(f"Parsed result title: '{result_title}' -> base_title: '{parsed.base_title}'")

        # Compute tracking_title the same way file_importer does
        tracking_title = parsed.base_title
        result_language = parsed.language

        # Get all library items for this tracking to check with fuzzy matching
        library_items = (
            session.query(Periodical)
            .filter(
                Periodical.tracking_id == tracking_id,
                Periodical.language == result_language,
            )
            .all()
        )

        # Use fuzzy title matching to detect duplicates
        # This is consistent with how search results are filtered in web/routers/search.py
        for lib_item in library_items:
            is_match, score = self.title_matcher.match(tracking_title, lib_item.title)

            if is_match:
                logger.debug(
                    f"Skipping duplicate: '{result_title}' (parsed as '{tracking_title}') "
                    f"matches library item '{lib_item.title}' (fuzzy score: {score})"
                )
                return True, None

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
        title = search_result["title"]
        logger.debug(f"[DownloadManager] submit_download called for: {title}")

        # Validate: skip blacklisted file types
        if self._has_blacklisted_extension(title):
            logger.warning(f"[DownloadManager] Skipping download with blacklisted extension: {title}")
            self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.SKIPPED,
                session,
                search_result_db_id=search_result_db_id,
                error_message="Skipped: blacklisted file extension",
            )
            return None

        # Validate: skip files that have failed too many times
        fuzzy_group = get_fuzzy_group_id(title)
        url = search_result.get("url", "")
        bad_file = self._is_bad_file(tracking_id, fuzzy_group, session, url=url)
        if bad_file:
            logger.info(
                f"[DownloadManager] Skipping bad file (failed {bad_file.attempt_count} times): "
                f"{title} - Last error: {bad_file.last_error}"
            )
            return None

        # Validate: skip duplicates
        is_dup, _ = self.check_duplicate_submission(tracking_id, title, session)
        if is_dup:
            logger.debug("[DownloadManager] Duplicate found, recording as SKIPPED")
            self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.SKIPPED,
                session,
                search_result_db_id=search_result_db_id,
                error_message="Skipped: duplicate download",
            )
            logger.info(f"Skipped duplicate download: {title} (tracking_id: {tracking_id})")
            return None

        # Queue if at concurrent download limit
        active_count = self._get_active_download_count(session)
        if active_count >= self.max_downloads:
            logger.info(
                f"[DownloadManager] At download limit ({active_count}/{self.max_downloads}), "
                f"queuing download: '{title}'"
            )
            submission = self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.QUEUED,
                session,
                search_result_db_id=search_result_db_id,
                attempt_count=0,
            )
            logger.info(f"Download queued: {title} (tracking_id: {tracking_id})")
            return submission

        # Submit to download client
        return self._submit_to_client(tracking_id, search_result, session, search_result_db_id)

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

        # Get the appropriate client for this provider
        client = self._get_client_for_provider(provider)

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
                logger.warning(f"Download client {client.name} rejected submission: {title}")
                self._create_submission_record(
                    tracking_id,
                    search_result,
                    DownloadSubmission.StatusEnum.FAILED,
                    session,
                    search_result_db_id=search_result_db_id,
                    error_message=f"Client {client.name} rejected submission",
                    attempt_count=1,
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
            logger.error(f"Error submitting download for '{title}': {e}", exc_info=True)
            self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.FAILED,
                session,
                search_result_db_id=search_result_db_id,
                error_message=str(e),
                attempt_count=1,
            )
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
        from models.database import DiscoveredIssue

        # Get the discovered issue
        issue = session.query(DiscoveredIssue).filter(DiscoveredIssue.id == discovered_issue_id).first()

        if not issue:
            logger.error(f"DiscoveredIssue not found: {discovered_issue_id}")
            return None

        # Check if already downloading
        if issue.download_status == "downloading" and issue.current_submission_id:
            logger.warning(
                f"Issue already has active download: {issue.title} (submission_id: {issue.current_submission_id})"
            )
            return None

        # Check if this is a bad file
        if issue.download_status == "permanently_failed":
            logger.warning(f"Skipping bad file (marked as permanently failed): {issue.title}")
            return None

        # Validate we have the necessary metadata
        if not issue.latest_url:
            logger.error(f"DiscoveredIssue missing URL: {issue.title}")
            # Mark as failed
            issue.download_status = "failed"
            issue.last_error = "Missing URL"
            session.commit()
            return None

        # Build search_result dict for compatibility with existing submit_download
        search_result = {
            "title": issue.title,
            "url": issue.latest_url,
            "provider": issue.latest_provider or "unknown",
            "pubdate": issue.issue_date.isoformat() if issue.issue_date else None,
            "guid": str(discovered_issue_id),  # Use discovered issue ID as guid
            "raw_metadata": issue.extra_metadata or {},
        }

        # Check if we're at the concurrent download limit
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

        # If at limit, create a QUEUED submission so the queue processor picks it up later
        if active_count >= self.max_downloads:
            logger.info(
                f"At download limit ({active_count}/{self.max_downloads}), " f"queuing download: '{issue.title}'"
            )
            submission = self._create_submission_record(
                issue.tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.QUEUED,
                session,
                attempt_count=0,
            )

            # Update DiscoveredIssue with submission info
            issue.download_status = "queued"
            issue.current_submission_id = submission.id
            if submission.id not in (issue.submission_ids or []):
                issue.submission_ids = (issue.submission_ids or []) + [submission.id]
            session.commit()

            return submission

        # Submit to download client
        try:
            # Get tracking for category
            tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == issue.tracking_id).first()

            download_category = None
            if tracking and tracking.download_category:
                download_category = tracking.download_category
            elif self.default_category:
                download_category = self.default_category

            # Get the appropriate client for this provider
            provider = issue.latest_provider or "unknown"
            client = self._get_client_for_provider(provider)

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
                # Mark as failed
                issue.download_status = "failed"
                issue.last_error = f"Client {client.name} rejected submission"
                issue.attempt_count += 1
                issue.last_attempt = utc_now()
                session.commit()
                return None

            # Create submission record (using existing helper)
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
            issue.download_status = "queued"  # Queued in download client
            issue.current_submission_id = submission.id
            # Add to submission_ids history
            if submission.id not in (issue.submission_ids or []):
                issue.submission_ids = (issue.submission_ids or []) + [submission.id]
            issue.attempt_count += 1
            issue.last_attempt = utc_now()

            session.commit()

            logger.info(f"Submitted discovered issue: {issue.title} (job_id: {job_id}, submission_id: {submission.id})")
            return submission

        except Exception as e:
            logger.error(
                f"Error submitting discovered issue '{issue.title}': {e}",
                exc_info=True,
            )
            # Mark as failed
            issue.download_status = "failed"
            issue.last_error = str(e)[:512]  # Truncate to column length
            issue.attempt_count += 1
            issue.last_attempt = utc_now()
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
        tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()

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
            self._collect_submission_result(submission, search_result, results)

            if submission and submission.status == DownloadSubmission.StatusEnum.PENDING:
                logger.info(f"Submitted selected edition {matched_edition}: {search_result['title']}")

        logger.info(
            f"Selected editions download completed: submitted={results['submitted']}, "
            f"queued={results.get('queued', 0)}, "
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
        tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()

        if not tracking:
            logger.error(f"Tracking record not found: {tracking_id}")
            return {"submitted": 0, "skipped": 0, "failed": 0}

        logger.info(f"Starting download search for all issues of: {tracking.title} (tracking_id: {tracking_id})")

        # Search for issues
        search_results = self.search_periodical_issues(tracking.title, session)

        results = {"submitted": 0, "skipped": 0, "failed": 0, "errors": []}

        # Filter out issues that are already downloaded, pending, or in library
        filtered_results = []
        for search_result in search_results:
            # Check if already submitted or downloaded
            is_duplicate, _ = self.check_duplicate_submission(tracking_id, search_result["title"], session)
            if not is_duplicate:
                filtered_results.append(search_result)

        logger.info(f"Found {len(filtered_results)} new issues (filtered from {len(search_results)} total results)")

        # Sort results: English editions first, then by date (newest first)
        filtered_results.sort(key=self._get_result_sort_key)

        if filtered_results:
            logger.info(
                f"Submitting {len(filtered_results)} issues for download "
                f"(max concurrent: {self.max_downloads}, excess will be queued)"
            )
        else:
            logger.info(
                f"No new issues to download for '{tracking.title}' - all found issues already downloaded or pending"
            )

        # Submit each result - submit_download will queue excess beyond max_downloads
        for search_result in filtered_results:
            search_result_db_id = self._create_search_result_record(search_result, tracking.title, session)
            submission = self.submit_download(tracking_id, search_result, session, search_result_db_id)
            self._collect_submission_result(submission, search_result, results)

        logger.info(
            f"Download search completed: submitted={results['submitted']}, "
            f"queued={results.get('queued', 0)}, "
            f"skipped={results['skipped']}, failed={results['failed']}"
        )

        return results

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
        from models.database import DiscoveredIssue
        from services import IssueDiscoveryService

        title = search_result["title"]
        logger.info(f"Submitting single issue download: {title} (tracking_id: {tracking_id})")

        # Use Issue Discovery service to create/find DiscoveredIssue
        # This ensures manual downloads go through the same system as automatic ones
        service = IssueDiscoveryService()

        # Record this as a discovered issue (will be "wanted" if it matches tracking rules)
        record_result = service.record_search_results(
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
            fuzzy_group = get_fuzzy_group_id(parsed.cleaned_title, parsed.publication_date)
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
        if discovered_issue.download_status not in ["wanted", "queued", "downloading"]:
            discovered_issue.download_status = "wanted"
            discovered_issue.download_priority = 100  # Highest priority for manual downloads
            discovered_issue.attempt_count = 0  # Reset attempts for manual re-download
            discovered_issue.last_error = None
            session.commit()

        # Submit using the standard Issue Discovery flow
        return self.submit_from_discovered_issue(discovered_issue.id, session)

    def _manual_direct_submission(
        self, tracking_id: int, search_result: Dict[str, Any], session: Session
    ) -> Optional[DownloadSubmission]:
        """
        Direct submission for manual user-initiated downloads.
        Bypasses duplicate checking since the user explicitly requested the download.
        Used as fallback when Issue Discovery system fails.
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
        # Check if at concurrent download limit; queue if so, otherwise submit directly
        active_count = self._get_active_download_count(session)
        if active_count >= self.max_downloads:
            logger.info(
                f"[DownloadManager] At download limit ({active_count}/{self.max_downloads}), "
                f"queuing manual download: '{search_result['title']}'"
            )
            return self._create_submission_record(
                tracking_id,
                search_result,
                DownloadSubmission.StatusEnum.QUEUED,
                session,
                search_result_db_id=search_result_db_id,
                attempt_count=0,
            )

        return self._submit_to_client(tracking_id, search_result, session, search_result_db_id)

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
                wait_time = client_status.get("wait_time", 0)
                message = client_status.get("message", f"Rate limited, waiting {wait_time}s")
                logger.info(f"[DownloadManager] Job {job_id} is rate limited: {message}")

                # Update submission with rate limit info but don't mark as failed
                submission.status = DownloadSubmission.StatusEnum.PENDING
                submission.last_error = message
                submission.extra_status = message  # Store rate limit info in extra_status
                submission.updated_at = utc_now()
                session.commit()
                return submission

            # Map client status to our status
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
                new_status = DownloadSubmission.StatusEnum.FAILED
                client_status.setdefault("error", "Job no longer exists in download client")
            else:
                new_status = status_map.get(client_status_value, DownloadSubmission.StatusEnum.PENDING)

            # Update submission
            submission.status = new_status
            submission.updated_at = utc_now()

            # Clear extra_status if no longer rate limited and status changed
            if not client_status.get("rate_limited") and submission.extra_status:
                submission.extra_status = None

            if "file_path" in client_status:
                submission.file_path = client_status["file_path"]
                logger.debug(f"[DownloadManager] Updated file_path for {job_id}: {submission.file_path}")

            if new_status == DownloadSubmission.StatusEnum.FAILED:
                # Increment attempt count on failure
                submission.attempt_count = (submission.attempt_count or 0) + 1
                submission.last_error = client_status.get("error", "Unknown error")

                logger.warning(
                    f"[DownloadManager] Download failed for {job_id}: {submission.last_error} "
                    f"(attempt {submission.attempt_count}/{MAX_DOWNLOAD_RETRIES + 1})"
                )

                # Check if max retries reached
                if submission.attempt_count > MAX_DOWNLOAD_RETRIES:
                    logger.error(
                        f"[DownloadManager] Max retries reached for '{submission.result_title}' "
                        f"- marking as permanently failed (will not retry). "
                        f"Reason: {submission.last_error}"
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
        return self.submission_service.get_completed_downloads(session)

    def mark_processed(self, submission_id: int, session: Session) -> bool:
        """
        Mark a submission as processed (move file out of downloads).

        Args:
            submission_id: DownloadSubmission ID
            session: Database session

        Returns:
            True if successful
        """
        return self.submission_service.mark_processed(submission_id, session)

    def get_pending_downloads(self, session: Session) -> List[DownloadSubmission]:
        """
        Get all pending/downloading submissions to monitor.

        Args:
            session: Database session

        Returns:
            List of active submissions
        """
        return self.submission_service.get_pending_downloads(session)

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
            return {
                "success": False,
                "message": f"Cannot retry submission with status: {submission.status.value}",
            }

        # Check if this is a bad file (failed MAX_DOWNLOAD_RETRIES+ times)
        if submission.attempt_count > MAX_DOWNLOAD_RETRIES:
            logger.warning(
                f"Cannot retry bad file (failed {submission.attempt_count} times): "
                f"{submission.result_title} (ID: {submission_id})"
            )
            return {
                "success": False,
                "message": f"Cannot retry: file has failed {submission.attempt_count} times (max {MAX_DOWNLOAD_RETRIES + 1})",
            }

        try:
            # Get the client that was used for this submission (or fallback to default)
            client = self._get_client_by_name(submission.client_name)

            # Resubmit to download client
            logger.info(f"Retrying submission {submission_id} with {client.name}: {submission.result_title}")
            # Determine download client category: tracked item download_category > config default
            tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == submission.tracking_id).first()
            download_category = None
            if tracking and tracking.download_category:
                download_category = tracking.download_category
            elif self.default_category:
                download_category = self.default_category

            job_id = self._submit_with_nzb_content(
                client=client,
                nzb_url=submission.source_url,
                title=submission.result_title,
                category=download_category,
            )

            if not job_id:
                logger.warning(f"Download client {client.name} rejected retry submission: {submission.result_title}")
                return {
                    "success": False,
                    "message": f"Download client {client.name} rejected submission",
                }

            # Update submission record
            submission.job_id = job_id
            submission.status = DownloadSubmission.StatusEnum.PENDING
            submission.last_error = None
            submission.updated_at = utc_now()
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

    def process_queue(self, session: Session) -> Dict[str, Any]:
        """
        Process queued downloads and submit them when slots are available.

        This method should be called periodically (e.g., by a scheduler) to:
        1. Check how many active downloads are running
        2. Submit queued downloads if slots are available

        Args:
            session: Database session

        Returns:
            Dict with processing results
        """
        return self.queue_processor.process_queue(session)


# Export all public items for wildcard imports
__all__ = ["DownloadManager"]
