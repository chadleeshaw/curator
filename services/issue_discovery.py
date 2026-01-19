"""
Issue Discovery Service - Core service for the Issue Discovery & Tracking system.

Handles:
- Recording search results as discovered issues
- Evaluating discovered issues against tracking rules
- Managing download state transitions
- Handling failures and retry logic
- Priority calculation
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.parsers import Parser, utc_now
from models.database import DiscoveredIssue, Magazine, MagazineTracking

logger = logging.getLogger(__name__)


class IssueDiscoveryService:
    """
    Service for discovering, tracking, and managing periodical issues.

    This is the core of the Issue Discovery & Tracking system, replacing
    scattered download logic with a unified, stateful approach.
    """

    def __init__(self, fuzzy_threshold: int = 80, default_max_retries: int = 1):
        """
        Initialize the issue discovery service.

        Args:
            fuzzy_threshold: Threshold for fuzzy title matching (0-100)
            default_max_retries: Default maximum retry attempts for failed downloads
        """
        self.parser = Parser(fuzzy_threshold=fuzzy_threshold)
        self.default_max_retries = default_max_retries

    def record_search_results(
        self, tracking_id: int, search_results: List[Dict[str, Any]], session: Session
    ) -> Dict[str, int]:
        """
        Process search results and record as discovered issues.

        This method:
        1. Parses each search result to extract metadata
        2. Creates a fuzzy_match_group for deduplication
        3. Checks for existing DiscoveredIssue by fuzzy_match_group
        4. Creates new or updates existing (increment times_seen, update last_seen)

        Args:
            tracking_id: MagazineTracking ID these results belong to
            search_results: List of search result dicts from providers
            session: Database session

        Returns:
            Dictionary with stats: {new, updated, duplicate, errors}

        Example:
            search_results = [
                {
                    "title": "Magazine - January 2024",
                    "url": "https://provider.com/nzb/12345",
                    "provider": "NZBGeek",
                    "pubdate": "2024-01-15T10:30:00Z",
                    "guid": "12345",
                    ...
                },
                ...
            ]
        """
        stats = {"new": 0, "updated": 0, "duplicate": 0, "errors": 0}

        # Get the tracking record for context
        tracking = session.query(MagazineTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return stats

        now = utc_now()

        for result in search_results:
            try:
                # Parse the search result title
                title = result.get("title", "")
                if not title:
                    logger.warning("Search result missing title, skipping")
                    stats["errors"] += 1
                    continue

                url = result.get("url", "")
                provider = result.get("provider", "")
                pubdate_str = result.get("pubdate")

                # Parse pubdate string to datetime if provided
                pubdate = None
                if pubdate_str:
                    try:
                        # Handle ISO format (2024-01-15T10:30:00Z)
                        if isinstance(pubdate_str, str):
                            # Remove 'Z' suffix if present
                            pubdate_str_clean = pubdate_str.rstrip("Z")
                            pubdate = datetime.fromisoformat(pubdate_str_clean)
                            # Convert to naive datetime (remove timezone info)
                            if pubdate.tzinfo is not None:
                                pubdate = pubdate.replace(tzinfo=None)
                        elif isinstance(pubdate_str, datetime):
                            pubdate = pubdate_str
                            # Convert to naive datetime if needed
                            if pubdate.tzinfo is not None:
                                pubdate = pubdate.replace(tzinfo=None)
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Failed to parse pubdate '{pubdate_str}': {e}")

                parsed = self.parser.parse_search_result(
                    title=title,
                    url=url,
                    provider=provider,
                    publication_date=pubdate,
                    raw_metadata=result,
                )

                # Generate fuzzy match group for deduplication
                # This normalizes the title to group similar results together
                fuzzy_group = self._get_fuzzy_group_id(parsed.cleaned_title, parsed.publication_date)

                # Check if we've already discovered this issue
                existing = (
                    session.query(DiscoveredIssue)
                    .filter(
                        and_(
                            DiscoveredIssue.tracking_id == tracking_id,
                            DiscoveredIssue.fuzzy_match_group == fuzzy_group,
                        )
                    )
                    .first()
                )

                if existing:
                    # Update existing issue
                    existing.last_seen = now
                    existing.times_seen += 1

                    # Update with latest metadata (may be from different provider)
                    existing.latest_url = result.get("url")
                    existing.latest_provider = parsed.provider

                    # Add search result ID if available
                    if "search_result_id" in result and result["search_result_id"]:
                        if result["search_result_id"] not in existing.search_result_ids:
                            existing.search_result_ids.append(result["search_result_id"])

                    stats["updated"] += 1
                    logger.debug(f"Updated existing issue: {fuzzy_group} (seen {existing.times_seen} times)")
                else:
                    # Create new discovered issue
                    new_issue = DiscoveredIssue(
                        tracking_id=tracking_id,
                        title=title,
                        normalized_title=parsed.cleaned_title.lower(),
                        fuzzy_match_group=fuzzy_group,
                        issue_date=parsed.publication_date,
                        issue_number=None,  # Not easily extractable from search results
                        year=parsed.publication_date.year if parsed.publication_date else None,
                        month=parsed.publication_date.month if parsed.publication_date else None,
                        language=parsed.language,
                        first_seen=now,
                        last_seen=now,
                        times_seen=1,
                        download_status="discovered",
                        download_priority=50,  # Default middle priority
                        latest_url=result.get("url"),
                        latest_provider=parsed.provider,
                        search_result_ids=(
                            [result["search_result_id"]]
                            if "search_result_id" in result and result["search_result_id"]
                            else []
                        ),
                        max_retries=self.default_max_retries,
                        extra_metadata={
                            "raw_title": title,
                            "base_title": parsed.base_title,
                            "is_special_edition": parsed.is_special_edition,
                            "special_edition_name": parsed.special_edition_name,
                        },
                    )
                    session.add(new_issue)
                    stats["new"] += 1
                    logger.info(f"Discovered new issue: {fuzzy_group}")

            except Exception as e:
                logger.error(f"Error processing search result '{title}': {e}")
                stats["errors"] += 1
                continue

        session.commit()
        logger.info(
            f"Recorded search results for tracking_id={tracking_id}: "
            f"{stats['new']} new, {stats['updated']} updated, {stats['errors']} errors"
        )

        return stats

    def evaluate_discovered_issues(self, tracking_id: int, session: Session) -> Dict[str, int]:
        """
        Evaluate all "discovered" issues and determine which should be downloaded.

        This method:
        1. Queries DiscoveredIssue where download_status="discovered"
        2. Checks if already in library (Magazine table)
        3. Checks if already being downloaded (current_submission_id)
        4. Applies tracking rules (track_all_editions, track_new_only, selected_editions)
        5. Marks as "wanted", "ignored", or "completed"
        6. Calculates priority for "wanted" issues

        Args:
            tracking_id: MagazineTracking ID to evaluate
            session: Database session

        Returns:
            Dictionary with stats: {wanted, ignored, already_have, errors}
        """
        stats = {"wanted": 0, "ignored": 0, "already_have": 0, "errors": 0}

        # Get the tracking record
        tracking = session.query(MagazineTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return stats

        # Get all discovered issues for this tracking
        discovered = (
            session.query(DiscoveredIssue)
            .filter(
                and_(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.download_status == "discovered",
                )
            )
            .all()
        )

        logger.info(f"Evaluating {len(discovered)} discovered issues for '{tracking.title}'")

        for issue in discovered:
            try:
                # Check if we already have this in our library
                magazine_id = self._check_if_in_library(issue, tracking, session)
                if magazine_id:
                    issue.download_status = "completed"
                    issue.download_priority = 0
                    issue.magazine_id = magazine_id
                    stats["already_have"] += 1
                    logger.debug(f"Already have: {issue.title}")
                    continue

                # Apply tracking rules to determine if we want this issue
                if self._should_download(issue, tracking):
                    issue.download_status = "wanted"
                    issue.download_priority = self._calculate_priority(issue, tracking)
                    stats["wanted"] += 1
                    logger.info(f"Marked as wanted (priority {issue.download_priority}): {issue.title}")
                else:
                    issue.download_status = "ignored"
                    issue.download_priority = 0
                    stats["ignored"] += 1
                    logger.debug(f"Ignored (doesn't match criteria): {issue.title}")

            except Exception as e:
                logger.error(f"Error evaluating issue '{issue.title}': {e}")
                stats["errors"] += 1
                continue

        session.commit()
        logger.info(
            f"Evaluated issues for tracking_id={tracking_id}: "
            f"{stats['wanted']} wanted, {stats['ignored']} ignored, "
            f"{stats['already_have']} already have"
        )

        return stats

    def handle_download_failure(self, issue_id: int, error_message: str, session: Session) -> str:
        """
        Handle a download failure for a discovered issue.

        This method:
        1. Increments attempt_count
        2. Compares to max_retries
        3. Marks as "failed" (can retry) or "permanently_failed" (permanent)
        4. Adjusts priority (reduce for failures)
        5. Records error message

        Args:
            issue_id: DiscoveredIssue ID
            error_message: Error message from download failure
            session: Database session

        Returns:
            New status: "failed" or "permanently_failed"
        """
        issue = session.query(DiscoveredIssue).filter_by(id=issue_id).first()
        if not issue:
            logger.error(f"DiscoveredIssue {issue_id} not found")
            return "unknown"

        now = utc_now()
        issue.attempt_count += 1
        issue.last_attempt = now
        issue.last_error = error_message[:512]  # Truncate to column length

        # Check if we've exceeded max retries
        if issue.attempt_count > issue.max_retries:
            # Permanent failure - mark as permanently_failed
            issue.download_status = "permanently_failed"
            issue.download_priority = 0
            logger.warning(f"Marking as permanently_failed after {issue.attempt_count} attempts: {issue.title}")
            new_status = "permanently_failed"
        else:
            # Temporary failure - can retry
            issue.download_status = "failed"
            # Reduce priority slightly for failed downloads
            issue.download_priority = max(1, issue.download_priority - 10)
            logger.info(f"Download failed (attempt {issue.attempt_count}/{issue.max_retries + 1}): {issue.title}")
            new_status = "failed"

        session.commit()
        return new_status

    def get_download_queue(
        self, session: Session, limit: int = 10, tracking_id: Optional[int] = None
    ) -> List[DiscoveredIssue]:
        """
        Get the download queue ordered by priority.

        Returns issues with status "wanted" or "failed" (retryable),
        ordered by priority (descending) and first_seen (ascending).

        Args:
            session: Database session
            limit: Maximum number of issues to return
            tracking_id: Optional filter by tracking ID

        Returns:
            List of DiscoveredIssue objects ready for download
        """
        query = session.query(DiscoveredIssue).filter(DiscoveredIssue.download_status.in_(["wanted", "failed"]))

        if tracking_id:
            query = query.filter(DiscoveredIssue.tracking_id == tracking_id)

        issues = (
            query.order_by(
                DiscoveredIssue.download_priority.desc(),
                DiscoveredIssue.first_seen.asc(),
            )
            .limit(limit)
            .all()
        )

        logger.debug(f"Download queue: {len(issues)} issues ready")
        return issues

    def retry_permanently_failed(self, issue_id: int, session: Session, reset_attempts: bool = True) -> bool:
        """
        Manually retry a permanently_failed issue (admin override).

        Args:
            issue_id: DiscoveredIssue ID
            session: Database session
            reset_attempts: Whether to reset attempt_count to 0

        Returns:
            True if successfully reset, False otherwise
        """
        issue = session.query(DiscoveredIssue).filter_by(id=issue_id).first()
        if not issue:
            logger.error(f"DiscoveredIssue {issue_id} not found")
            return False

        if issue.download_status != "permanently_failed":
            logger.warning(f"Issue {issue_id} is not marked as permanently_failed (status: {issue.download_status})")
            return False

        if reset_attempts:
            issue.attempt_count = 0

        issue.download_status = "wanted"
        issue.download_priority = 50  # Reset to default priority
        issue.last_error = None

        session.commit()
        logger.info(f"Manually reset permanently_failed issue to wanted: {issue.title}")
        return True

    # Private helper methods

    def _get_fuzzy_group_id(self, title: str, publication_date: Optional[datetime] = None) -> str:
        """
        Generate a fuzzy match group ID for deduplication.

        Normalizes the title to group similar search results together.
        This prevents duplicate downloads of the same issue from different providers.

        Args:
            title: Cleaned title from parser
            publication_date: Publication date if available

        Returns:
            Normalized string for grouping
        """
        # Convert to lowercase and strip whitespace
        normalized = title.lower().strip()

        # Remove common noise words
        noise_words = ["the", "magazine", "comic", "edition"]
        for word in noise_words:
            normalized = normalized.replace(f" {word} ", " ")

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        # Add date component if available
        if publication_date:
            date_str = publication_date.strftime("%Y-%m")
            normalized = f"{normalized}_{date_str}"

        return normalized

    def _should_download(self, issue: DiscoveredIssue, tracking: MagazineTracking) -> bool:
        """
        Determine if an issue should be downloaded based on tracking rules.

        Args:
            issue: DiscoveredIssue to evaluate
            tracking: MagazineTracking with user preferences

        Returns:
            True if issue matches tracking criteria, False otherwise
        """
        # Rule 1: track_all_editions = True means download everything
        if tracking.track_all_editions:
            return True

        # Rule 2: track_new_only = True means only download future/current issues
        if tracking.track_new_only:
            if issue.issue_date:
                now = utc_now()
                # Download if issue date is current or future
                return issue.issue_date >= now
            else:
                # If no date, assume it's new and download it
                return True

        # Rule 3: selected_years - download issues from specific years
        if tracking.selected_years and issue.year:
            return issue.year in tracking.selected_years

        # Rule 4: selected_editions - download specific editions (requires OLID)
        # This is harder to implement without OLID in search results
        # For now, we'll skip this rule and implement it later

        # Default: Don't download unless explicitly requested
        return False

    def _calculate_priority(self, issue: DiscoveredIssue, tracking: MagazineTracking) -> int:
        """
        Calculate download priority for an issue (1-100, higher = download first).

        Factors:
        - Recency: Newer issues get higher priority
        - Frequency: Issues seen multiple times get higher priority
        - Tracking preferences: track_all_editions gets boost

        Args:
            issue: DiscoveredIssue to prioritize
            tracking: MagazineTracking with user preferences

        Returns:
            Priority value (1-100)
        """
        priority = 50  # Base priority

        # Factor 1: Recency (max +30)
        if issue.issue_date:
            # Use naive datetime for comparison (issue_date is stored as naive in DB)
            now = datetime.now()
            days_old = (now - issue.issue_date).days

            if days_old < 7:
                priority += 30  # Very recent
            elif days_old < 30:
                priority += 20  # Recent
            elif days_old < 90:
                priority += 10  # Moderately recent
            # Older than 90 days: no bonus

        # Factor 2: Seen multiple times (max +10)
        # Issues seen from multiple providers are likely more reliable
        if issue.times_seen > 1:
            priority += min(10, issue.times_seen * 2)

        # Factor 3: Tracking preferences
        if tracking.track_all_editions:
            priority += 10  # Boost for comprehensive tracking

        # Clamp to 1-100
        return max(1, min(100, priority))

    def _check_if_in_library(
        self, issue: DiscoveredIssue, tracking: MagazineTracking, session: Session
    ) -> Optional[int]:
        """
        Check if an issue is already in the library.

        Args:
            issue: DiscoveredIssue to check
            tracking: MagazineTracking for context
            session: Database session

        Returns:
            Magazine ID if issue already exists in library, None otherwise
        """
        # Check by fuzzy match - look for similar titles and dates
        if not issue.issue_date:
            # Without a date, we can't reliably determine if we have it
            return None

        # Normalize dates to just the date part (ignore time) for comparison
        issue_date_only = issue.issue_date.date()

        # Query for magazines with similar title and same date
        existing = (
            session.query(Magazine)
            .filter(
                and_(
                    Magazine.tracking_id == tracking.id,
                )
            )
            .all()
        )

        # Check if any existing magazine matches the date (ignoring time)
        for mag in existing:
            if mag.issue_date and mag.issue_date.date() == issue_date_only:
                return mag.id

        return None
