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
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.parsers import Parser, utc_now
from core.utils.date import dates_are_fuzzy_match
from core.utils.fuzzy_matching import get_fuzzy_group_id
from core.constants.app import MAX_DOWNLOAD_RETRIES_IA, NEW_ISSUE_THRESHOLD_DAYS
from core.constants.country import (
    FULL_NAME_COUNTRY_CODES,
    ISO_COUNTRIES,
    THREE_LETTER_COUNTRY_CODES,
)
from core.constants.validation import ANTI_PERIODICAL_PATTERNS, PERIODICAL_PATTERNS
from models.database import (
    DiscoveredIssue,
    DownloadStatus,
    Periodical,
    PeriodicalTracking,
)

logger = logging.getLogger(__name__)

_PRIORITY_BASE = 50
_PRIORITY_MIN = 1
_PRIORITY_MAX = 100
_RECENCY_BONUS_NEW = 30
_RECENCY_BONUS_RECENT = 20
_RECENCY_BONUS_MODERATE = 10
_NEW_ISSUE_DAYS = 7
_RECENT_ISSUE_DAYS = 30
_MODERATE_ISSUE_DAYS = 90
_TRACKING_PRIORITY_BOOST = 10


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

        Creates new DiscoveredIssue records or updates existing ones
        (incrementing times_seen and preferring newer NZB URLs).

        Returns:
            Dictionary with stats: {new, updated, duplicate, errors, rejected_non_periodical}
        """
        stats = {
            "new": 0,
            "updated": 0,
            "duplicate": 0,
            "errors": 0,
            "rejected_non_periodical": 0,
        }

        tracking = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return stats

        now = utc_now()

        for result in search_results:
            try:
                title = result.get("title", "")
                if not title:
                    logger.debug("Search result missing title, skipping")
                    stats["errors"] += 1
                    continue

                if not self._validate_is_periodical(result):
                    logger.debug(f"Rejecting non-periodical result: {title}")
                    stats["rejected_non_periodical"] += 1
                    continue

                if result.get("raw_metadata", {}).get("is_collection"):
                    logger.debug(f"Skipping IA collection archive: {title}")
                    stats["rejected_non_periodical"] += 1
                    continue

                if not self._ia_title_matches_tracking(result, tracking):
                    stats["rejected_non_periodical"] += 1
                    continue

                url = result.get("url", "")
                provider = result.get("provider", "")
                pubdate = self._parse_pubdate(result.get("pubdate") or result.get("publication_date"))

                parsed = self.parser.parse_search_result(
                    title=title,
                    url=url,
                    provider=provider,
                    publication_date=pubdate,
                    raw_metadata=result,
                )

                if parsed is None:
                    logger.debug(f"Skipping non-periodical result: {title}")
                    continue

                fuzzy_group = get_fuzzy_group_id(parsed.original_title)

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
                    self._update_existing_issue(existing, result, parsed, pubdate, now)
                    stats["updated"] += 1
                    logger.debug(f"Updated existing issue: {fuzzy_group} (seen {existing.times_seen} times)")
                else:
                    new_issue = self._create_new_issue(
                        tracking_id,
                        title,
                        fuzzy_group,
                        parsed,
                        pubdate,
                        provider,
                        result,
                        now,
                    )
                    session.add(new_issue)
                    stats["new"] += 1
                    logger.debug(f"Discovered new issue: {fuzzy_group}")

            except Exception as e:
                logger.error(f"Error processing search result '{title}': {e}")
                stats["errors"] += 1
                continue

        session.commit()
        logger.info(
            f"Recorded search results for tracking_id={tracking_id}: "
            f"{stats['new']} new, {stats['updated']} updated, {stats['errors']} errors, "
            f"{stats['rejected_non_periodical']} rejected (non-periodical)"
        )

        return stats

    def _parse_pubdate(self, pubdate_str) -> Optional[datetime]:
        """Parse a pubdate string or datetime to a UTC-aware datetime, or return None."""
        if not pubdate_str:
            return None
        try:
            if isinstance(pubdate_str, str):
                pubdate = datetime.fromisoformat(pubdate_str.rstrip("Z"))
                if pubdate.tzinfo is None:
                    pubdate = pubdate.replace(tzinfo=timezone.utc)
                else:
                    pubdate = pubdate.astimezone(timezone.utc)
            elif isinstance(pubdate_str, datetime):
                pubdate = pubdate_str
                if pubdate.tzinfo is None:
                    pubdate = pubdate.replace(tzinfo=timezone.utc)
                else:
                    pubdate = pubdate.astimezone(timezone.utc)
            else:
                return None
            return pubdate
        except (ValueError, AttributeError) as parse_error:
            logger.warning(f"Failed to parse pubdate '{pubdate_str}': {parse_error}")
            return None

    def _ia_title_matches_tracking(self, result: Dict[str, Any], tracking: PeriodicalTracking) -> bool:
        """Return False for Internet Archive results whose title doesn't match the tracked periodical."""
        if result.get("provider") != "internet_archive":
            return True

        title = result.get("title", "").lower()
        search_terms = tracking.title.lower().split()
        significant_terms = [t for t in search_terms if len(t) >= 3]
        if not significant_terms:
            return True

        matching_terms = sum(1 for t in significant_terms if t in title)
        match_ratio = matching_terms / len(significant_terms)
        if match_ratio < 0.5:
            logger.debug(
                f"Skipping IA result with poor title match: '{result.get('title')}' "
                f"(tracking '{tracking.title}', match ratio: {match_ratio:.1%})"
            )
            return False
        return True

    def _update_existing_issue(self, existing: DiscoveredIssue, result: Dict[str, Any], parsed, pubdate, now) -> None:
        """Update an existing DiscoveredIssue with fresher data from a new search result."""
        existing.last_seen = now
        existing.times_seen += 1

        should_update_url = (
            pubdate is not None and (existing.latest_pubdate is None or pubdate > existing.latest_pubdate)
        ) or (pubdate is None and existing.latest_pubdate is None)

        if should_update_url:
            if pubdate and existing.latest_pubdate and pubdate > existing.latest_pubdate:
                logger.debug(
                    f"Preferring newer NZB for {existing.fuzzy_match_group}: {pubdate} > {existing.latest_pubdate}"
                )
            existing.latest_url = result.get("url")
            existing.latest_provider = parsed.provider
            existing.latest_pubdate = pubdate

        search_result_id = result.get("search_result_id")
        if search_result_id and search_result_id not in existing.search_result_ids:
            existing.search_result_ids.append(search_result_id)

    def _create_new_issue(
        self,
        tracking_id: int,
        title: str,
        fuzzy_group: str,
        parsed,
        pubdate,
        provider: str,
        result: Dict[str, Any],
        now,
    ) -> DiscoveredIssue:
        """Build a new DiscoveredIssue from a parsed search result."""
        search_result_id = result.get("search_result_id")
        return DiscoveredIssue(
            tracking_id=tracking_id,
            title=title,
            normalized_title=parsed.cleaned_title.lower(),
            fuzzy_match_group=fuzzy_group,
            issue_date=parsed.publication_date,
            issue_number=parsed.raw_metadata.get("issue"),
            year=parsed.publication_date.year if parsed.publication_date else None,
            month=parsed.publication_date.month if parsed.publication_date else None,
            language=parsed.language,
            country=parsed.country,
            first_seen=now,
            last_seen=now,
            times_seen=1,
            download_status=DownloadStatus.DISCOVERED,
            download_priority=50,
            latest_url=result.get("url"),
            latest_provider=parsed.provider,
            latest_pubdate=pubdate,
            search_result_ids=[search_result_id] if search_result_id else [],
            max_retries=(MAX_DOWNLOAD_RETRIES_IA if provider == "internet_archive" else self.default_max_retries),
            extra_metadata={
                "raw_title": title,
                "base_title": parsed.base_title,
                "is_special_edition": parsed.is_special_edition,
                "special_edition_name": parsed.special_edition_name,
            },
        )

    def evaluate_discovered_issues(self, tracking_id: int, session: Session) -> Dict[str, int]:
        """
        Evaluate all "discovered" issues and determine which should be downloaded.

        This method:
        1. Queries DiscoveredIssue where download_status=DownloadStatus.DISCOVERED
        2. Checks if already in library (Magazine table)
        3. Checks if already being downloaded (current_submission_id)
        4. Applies tracking rules (track_all_editions, track_new_only, selected_editions)
        5. Marks as "wanted", "ignored", or "completed"
        6. Calculates priority for "wanted" issues

        Args:
            tracking_id: PeriodicalTracking ID to evaluate
            session: Database session

        Returns:
            Dictionary with stats: {wanted, ignored, already_have, errors}
        """
        stats = {"wanted": 0, "ignored": 0, "already_have": 0, "errors": 0}

        # Get the tracking record
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return stats

        # Get all discovered issues for this tracking
        discovered = (
            session.query(DiscoveredIssue)
            .filter(
                and_(
                    DiscoveredIssue.tracking_id == tracking_id,
                    DiscoveredIssue.download_status == DownloadStatus.DISCOVERED,
                )
            )
            .all()
        )

        logger.info(f"Evaluating {len(discovered)} discovered issues for '{tracking.title}'")

        for issue in discovered:
            try:
                # Check if we already have this in our library
                periodical_id = self._check_if_in_library(issue, tracking, session)
                if periodical_id:
                    issue.download_status = DownloadStatus.COMPLETED
                    issue.download_priority = 0
                    issue.periodical_id = periodical_id
                    stats["already_have"] += 1
                    logger.debug(f"Already have: {issue.title}")
                    continue

                # Apply tracking rules to determine if we want this issue
                if self._should_download(issue, tracking):
                    issue.download_status = DownloadStatus.WANTED
                    issue.download_priority = self._calculate_priority(issue, tracking)
                    stats["wanted"] += 1
                    logger.info(f"Marked as wanted (priority {issue.download_priority}): {issue.title}")
                else:
                    issue.download_status = DownloadStatus.IGNORED
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
        if len(error_message) > 512:
            logger.warning(f"Error message truncated from {len(error_message)} to 512 chars for issue {issue_id}")
        issue.last_error = error_message[:512]  # Truncate to column length

        # Check if we've exceeded max retries
        if issue.attempt_count > issue.max_retries:
            # Permanent failure - mark as permanently_failed
            issue.download_status = DownloadStatus.PERMANENTLY_FAILED
            issue.download_priority = 0
            logger.warning(f"Marking as permanently_failed after {issue.attempt_count} attempts: {issue.title}")
            new_status = DownloadStatus.PERMANENTLY_FAILED
        else:
            # Temporary failure - can retry
            issue.download_status = DownloadStatus.FAILED
            # Reduce priority slightly for failed downloads
            issue.download_priority = max(1, issue.download_priority - 10)
            logger.info(f"Download failed (attempt {issue.attempt_count}/{issue.max_retries + 1}): {issue.title}")
            new_status = DownloadStatus.FAILED

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
        query = session.query(DiscoveredIssue).filter(
            DiscoveredIssue.download_status.in_([DownloadStatus.WANTED, DownloadStatus.FAILED])
        )

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

        if issue.download_status != DownloadStatus.PERMANENTLY_FAILED:
            logger.warning(f"Issue {issue_id} is not marked as permanently_failed (status: {issue.download_status})")
            return False

        if reset_attempts:
            issue.attempt_count = 0

        issue.download_status = DownloadStatus.WANTED
        issue.download_priority = 50  # Reset to default priority
        issue.last_error = None

        session.commit()
        logger.info(f"Manually reset permanently_failed issue to wanted: {issue.title}")
        return True

    # Private helper methods

    def _validate_is_periodical(self, search_result: Dict[str, Any]) -> bool:
        """
        Validate that a search result represents a periodical issue, not a book/collection.

        Uses pattern analysis to identify periodicals regardless of category:
        1. Title pattern analysis (periodical indicators vs anti-patterns)
        2. File size heuristics (typical periodical size ranges)

        Note: We do NOT filter by Newsnab category because book categories (7000)
        often contain magazines in PDF/EPUB format. Pattern matching is sufficient.

        Args:
            search_result: Search result dictionary from provider

        Returns:
            True if likely a periodical, False if likely book/collection
        """
        title = search_result.get("title", "")

        logger.debug(f"[VALIDATION] Validating title: {title}")

        # Layer 1: Pattern analysis (most important - works across all categories)
        # Check anti-patterns FIRST - reject collections/books even if they have dates
        if self._has_anti_periodical_patterns(title):
            logger.debug(f"[VALIDATION] Rejecting '{title}': Has anti-periodical patterns")
            return False

        if not self._has_periodical_patterns(title):
            logger.debug(f"[VALIDATION] Rejecting '{title}': No periodical patterns found")
            return False

        # Has periodical patterns - accept regardless of category
        logger.debug(f"[VALIDATION] ✓ ACCEPTED: {title}")
        return True

    def _has_periodical_patterns(self, title: str) -> bool:
        """
        Check if title contains patterns typical of periodicals.

        Periodical indicators:
        - Date patterns: "January 2024", "Jan 2024", "01.2024", "2024-01"
        - Issue numbers: "#123", "Issue 45", "No. 67"
        - Volume numbers: "Vol. 12", "Volume 5"
        - Combined: "Vol 12 No 3"
        - Seasonal: "Spring 2024", "Winter 2024"

        Args:
            title: Title string to check

        Returns:
            True if periodical patterns found, False otherwise
        """
        # Strategy: Match patterns on both normalized (dashes→spaces) and original title

        # Try matching on original title first (preserves numeric date separators like "01-2024")
        title_lower = title.lower()
        for pattern in PERIODICAL_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                logger.debug(f"Found periodical pattern in '{title}': {pattern}")
                return True

        # If no match, try with dash→space normalization (catches "Magazine-January-2024")
        # Also normalize dots and underscores for NZB filenames: "Wired.Magazine.January.2024.pdf"
        normalized_title = title.replace(".", " ").replace("_", " ").replace("-", " ")
        title_lower_normalized = normalized_title.lower()

        for pattern in PERIODICAL_PATTERNS:
            if re.search(pattern, title_lower_normalized, re.IGNORECASE):
                logger.debug(f"Found periodical pattern in '{title}' (after normalization): {pattern}")
                return True

        return False

    def _has_anti_periodical_patterns(self, title: str) -> bool:
        """
        Check if title contains anti-patterns indicating books/collections.

        Anti-patterns:
        - "Complete Collection", "Full Series"
        - "Anthology", "Omnibus", "Compendium"
        - "Volumes 1-5", "Issues 10-20" (range indicators)
        - "Year 2023 Pack"
        - "Book 1", "Novel", "Trilogy"

        Args:
            title: Title string to check

        Returns:
            True if anti-patterns found (NOT a periodical), False otherwise
        """
        # Normalize dots and underscores to spaces
        normalized_title = title.replace(".", " ").replace("_", " ")
        title_lower = normalized_title.lower()

        for pattern in ANTI_PERIODICAL_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                logger.debug(f"Found anti-periodical pattern in '{title}': {pattern}")
                return True

        return False

    def _should_download(self, issue: DiscoveredIssue, tracking: PeriodicalTracking) -> bool:
        """
        Determine if an issue should be downloaded based on tracking rules.

        Args:
            issue: DiscoveredIssue to evaluate
            tracking: PeriodicalTracking with user preferences

        Returns:
            True if issue matches tracking criteria, False otherwise
        """
        # CRITICAL: Country matching - different countries are different periodicals
        # National Geographic US != National Geographic UK
        # Default: No country specified = USA
        issue_country = self._normalize_country(issue.country or "US")
        tracking_country = self._normalize_country(tracking.country or "US")

        if issue_country != tracking_country:
            logger.debug(
                f"Skipping '{issue.title}': Country mismatch " f"(issue: {issue_country}, tracking: {tracking_country})"
            )
            return False

        # Rule 1: track_all_editions = True means download everything
        if tracking.track_all_editions:
            return True

        # Rule 2: track_new_only = True means only download recent/current issues
        if tracking.track_new_only:
            if issue.issue_date:
                now = utc_now()
                # Ensure issue_date is timezone-aware for comparison
                issue_date = issue.issue_date
                if issue_date.tzinfo is None:
                    issue_date = issue_date.replace(tzinfo=timezone.utc)
                days_old = (now - issue_date).days
                # Consider issues within the threshold as "new"
                # Future-dated issues (days_old < 0) are always considered new
                is_new = days_old <= NEW_ISSUE_THRESHOLD_DAYS
                if not is_new:
                    logger.debug(
                        f"Skipping old issue for track_new_only: {issue.title} "
                        f"(issue_date: {issue.issue_date}, {days_old} days old)"
                    )
                return is_new
            elif issue.year:
                # If we have a year but no full date, check if it's the current year
                current_year = utc_now().year
                return issue.year >= current_year
            else:
                # No date information at all - skip to avoid downloading old back issues
                logger.debug(f"Skipping issue with no date for track_new_only: {issue.title}")
                return False

        # Rule 3: selected_years - download issues from specific years
        if tracking.selected_years and issue.year:
            return issue.year in tracking.selected_years

        # Rule 4: selected_editions - download specific editions (requires OLID)
        # This is harder to implement without OLID in search results
        # For now, we'll skip this rule and implement it later

        # Default: Don't download unless explicitly requested
        return False

    def _calculate_priority(self, issue: DiscoveredIssue, tracking: PeriodicalTracking) -> int:
        """
        Calculate download priority for an issue (1-100, higher = download first).

        Factors:
        - Recency: Newer issues get higher priority
        - Frequency: Issues seen multiple times get higher priority
        - Tracking preferences: track_all_editions gets boost

        Args:
            issue: DiscoveredIssue to prioritize
            tracking: PeriodicalTracking with user preferences

        Returns:
            Priority value (1-100)
        """
        priority = _PRIORITY_BASE

        if issue.issue_date:
            now = utc_now()
            days_old = (now - issue.issue_date).days

            if days_old < _NEW_ISSUE_DAYS:
                priority += _RECENCY_BONUS_NEW
            elif days_old < _RECENT_ISSUE_DAYS:
                priority += _RECENCY_BONUS_RECENT
            elif days_old < _MODERATE_ISSUE_DAYS:
                priority += _RECENCY_BONUS_MODERATE

        if issue.times_seen > 1:
            priority += min(10, issue.times_seen * 2)

        if tracking.track_all_editions:
            priority += _TRACKING_PRIORITY_BOOST

        return max(_PRIORITY_MIN, min(_PRIORITY_MAX, priority))

    def _normalize_country(self, country: Optional[str]) -> str:
        """Normalize a country name or code to a 2-letter ISO code. Defaults to 'US'."""
        if not country:
            return "US"

        country_upper = country.strip().upper()

        if country_upper in THREE_LETTER_COUNTRY_CODES:
            return THREE_LETTER_COUNTRY_CODES[country_upper]

        if country_upper in FULL_NAME_COUNTRY_CODES:
            return FULL_NAME_COUNTRY_CODES[country_upper]

        if len(country_upper) == 2 and country_upper in ISO_COUNTRIES:
            return country_upper

        for code, name in ISO_COUNTRIES.items():
            if name.upper() == country_upper:
                return code

        logger.warning(f"Could not normalize country '{country}', defaulting to US")
        return "US"

    def _check_if_in_library(
        self, issue: DiscoveredIssue, tracking: PeriodicalTracking, session: Session
    ) -> Optional[int]:
        """
        Check if an issue is already in the library.

        Uses two matching strategies:
        1. Fuzzy date matching (primary) - handles date defaulting and season spanning
        2. Fuzzy group ID matching (fallback) - handles missing dates by comparing
           normalized title+date identifiers against library items

        Args:
            issue: DiscoveredIssue to check
            tracking: PeriodicalTracking for context
            session: Database session

        Returns:
            Magazine ID if issue already exists in library, None otherwise
        """
        existing = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()

        if not existing:
            return None

        # Primary: fuzzy date matching (when issue has a date)
        if issue.issue_date:
            issue_date_only = issue.issue_date.date()
            for mag in existing:
                if mag.issue_date and dates_are_fuzzy_match(mag.issue_date.date(), issue_date_only):
                    logger.debug(
                        f"Fuzzy date match found: library {mag.issue_date.date()} matches search {issue_date_only}"
                    )
                    return mag.id

        # Fallback: match by fuzzy group ID against library items
        # This catches cases where date parsing failed but the issue is clearly the same
        # Pre-compute fuzzy groups for all library items to avoid repeated computation
        if issue.fuzzy_match_group:
            existing_by_id = {mag.id: mag for mag in existing}
            library_groups = {mag.id: get_fuzzy_group_id(mag.title) for mag in existing if mag.issue_date}
            for mag_id, lib_group in library_groups.items():
                if lib_group == issue.fuzzy_match_group:
                    mag = existing_by_id[mag_id]
                    logger.debug(f"Fuzzy group match found: library '{mag.title}' matches {issue.fuzzy_match_group}")
                    return mag.id

        return None
