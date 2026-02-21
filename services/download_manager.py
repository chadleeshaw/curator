"""
Download manager for handling periodical downloads.
Coordinates search, deduplication, submission, and status tracking.
"""

# pylint: disable=too-many-lines

import logging
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient, SearchProvider
from core.constants.app import (
    DEFAULT_FUZZY_THRESHOLD,
    MAX_DOWNLOAD_RETRIES,
    MAX_DOWNLOAD_RETRIES_IA,
    MAX_ERROR_LENGTH,
)
from core.constants.category import DEFAULT_CATEGORY
from core.constants.files import BLACKLISTED_FILE_EXTENSIONS
from core.constants.language import ENGLISH_INDICATORS
from core.parsers import utc_now, TitleMatcher, Parser
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    DownloadSubmission,
    Periodical,
    PeriodicalTracking,
)
from models.database import SearchResult as DBSearchResult
from services.download import (
    SearchService,
    DeduplicationService,
    SubmissionService,
    QueueProcessor,
    submit_with_nzb_content,
)
from services.issue_discovery import IssueDiscoveryService

logger = logging.getLogger(__name__)

MANUAL_DOWNLOAD_PRIORITY = 100


class DownloadManager:
    """Manage downloads for tracked periodicals"""

    # Default provider to client routing
    # Maps provider type → client type.  "default" is kept as a safety fallback key
    # only; the actual NZB client is keyed by its real type (sabnzbd/nzbget).
    DEFAULT_PROVIDER_CLIENT_MAP = {
        "internet_archive": "internet_archive",
        "torznab": "qbittorrent",
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
        issue_discovery_service: Optional[IssueDiscoveryService] = None,
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
            issue_discovery_service: Optional IssueDiscoveryService for routing downloads
                through the discovery pipeline. Falls back to a default instance if not provided.
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

        # Initialize services
        self.search_service = SearchService(search_providers, fuzzy_threshold)
        self.deduplication_service = DeduplicationService()
        self.submission_service = SubmissionService()
        self.queue_processor = QueueProcessor(
            download_client,
            max_downloads,
            nzb_cache_service,
            download_clients=self.download_clients,
        )
        self.issue_discovery_service: IssueDiscoveryService = issue_discovery_service or IssueDiscoveryService(
            fuzzy_threshold=fuzzy_threshold
        )

        # Lock to serialize slot counting + submission between concurrent callers
        # (auto-download Phase 3 and download monitor's process_queue)
        self._slot_lock = Lock()

        # Log available clients
        client_names = list(self.download_clients.keys())
        logger.info(f"DownloadManager initialized with clients: {client_names}")

    @property
    def all_providers_rate_limited(self) -> bool:
        """Check if all search providers are currently rate limited."""
        return self.search_service.all_providers_rate_limited

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

    def _submit_with_nzb_content(
        self,
        client: DownloadClient,
        nzb_url: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Submit a download, preferring cached NZB content over URL to avoid provider rate limits.

        Delegates to the shared submit_with_nzb_content helper in services.download.nzb_submit.

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

        # Use per-issue max_retries from DiscoveredIssue if available
        max_retries = self._get_max_retries_for_submission_context(
            tracking_id=tracking_id, fuzzy_group=fuzzy_group, url=url, session=session
        )

        return (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.tracking_id == tracking_id,
                DownloadSubmission.fuzzy_match_group == fuzzy_group,
                DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                DownloadSubmission.attempt_count > max_retries,
            )
            .first()
        )

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

    def search_periodical_issues(
        self,
        periodical_title: str,
        session: Session,
        aliases: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search all providers for available issues of a periodical.

        Args:
            periodical_title: Title of the periodical to search for (may include language)
            session: Database session
            aliases: Optional list of alternative search terms (e.g., from tracking record)

        Returns:
            List of search results with deduplication grouping
        """
        return self.search_service.search_periodical_issues(periodical_title, session, aliases=aliases)

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
            return DownloadStatus.PERMANENTLY_FAILED

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

    def _record_attempt(self, issue) -> None:
        """Increment attempt counter and record the attempt timestamp."""
        issue.attempt_count += 1
        issue.last_attempt = utc_now()

    def _register_submission_id(self, issue, submission_id: int) -> None:
        """Append submission_id to issue.submission_ids if not already present."""
        if submission_id not in (issue.submission_ids or []):
            issue.submission_ids = (issue.submission_ids or []) + [submission_id]

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
        from models.database import DiscoveredIssue

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

        # Acquire lock to prevent race condition in concurrent download limit checking
        with self._slot_lock:
            # Check if at download limit - if so, queue the submission
            active_count = self._get_active_download_count(session)
            if active_count >= self.max_downloads:
                return self._create_queued_submission(issue, search_result, session)

            # Submit to download client
            return self._submit_issue_to_client(issue, search_result, session)

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

        # Search for issues
        search_results = self.search_periodical_issues(tracking.title, session)

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
        # Acquire lock to prevent race condition in concurrent download limit checking
        with self._slot_lock:
            # Check if at concurrent download limit; queue if so, otherwise submit directly
            active_count = self._get_active_download_count(session)
            provider = search_result.get("provider", "unknown")
            if active_count >= self.max_downloads:
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

    def process_queue(self, session: Session) -> Dict[str, Any]:
        """
        Process queued downloads and submit them when slots are available.

        Thread-safe: acquires _slot_lock to prevent concurrent slot counting
        from auto-download Phase 3 and download monitor from exceeding max_downloads.

        After the queue processor promotes submissions (QUEUED→PENDING), syncs the
        linked DiscoveredIssue.download_status to QUEUED so the two state machines
        stay consistent.

        Args:
            session: Database session

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

    def submit_discovered_batch(self, session: Session, issue_discovery_service) -> int:
        """
        Submit discovered issues from the download queue, respecting slot limits.

        Thread-safe: acquires _slot_lock to prevent concurrent slot counting
        from process_queue() from exceeding max_downloads.

        This replaces inline Phase 3 logic in auto_download_task, consolidating
        all slot-aware submission through DownloadManager.

        Args:
            session: Database session
            issue_discovery_service: IssueDiscoveryService for fetching queue

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
                    submission = self.submit_from_discovered_issue(issue.id, session)
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


# Export all public items for wildcard imports
__all__ = ["DownloadManager"]
