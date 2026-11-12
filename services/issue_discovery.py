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

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.parsers import Parser, utc_now
from core.utils.fuzzy_matching import get_fuzzy_group_id
from services.cache.provider_cache import INDEXER_REJECTION_ERROR
from core.constants.app import (
    MAX_DOWNLOAD_RETRIES_IA,
    MAX_ERROR_LENGTH,
    NEW_ISSUE_THRESHOLD_DAYS,
)
from core.constants.date import DATE_PRECISION_DAY, DATE_PRECISION_YEAR
from core.constants.country import (
    FULL_NAME_COUNTRY_CODES,
    ISO_COUNTRIES,
    THREE_LETTER_COUNTRY_CODES,
)
from core.constants.title import SPECIAL_EDITION_KEYWORDS
from core.constants.validation import ANTI_PERIODICAL_PATTERNS, PERIODICAL_PATTERNS
from core.utils.result_filter import title_contains_name, title_has_blacklisted_extension, title_matches_query
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


def _precision_from_parsed(parsed) -> Optional[str]:
    """Date precision recorded by the filename parser, if it ran."""
    raw = getattr(parsed, "raw_metadata", None)
    if not isinstance(raw, dict):
        return None
    precision = raw.get("date_precision")
    return str(precision) if precision else None


def _as_date(value):
    """Calendar date for a datetime or date. Neighboring months stay distinct."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _text(value) -> Optional[str]:
    """Stripped text, or None when the value is missing or blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nested_value(container, key):
    """Read a plain field or a derived ``{value, source, confidence}`` entry."""
    if not isinstance(container, dict):
        return None
    raw = container.get(key)
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _first_present(sources, key):
    """First non-empty value for key across metadata dicts."""
    for source in sources:
        value = _nested_value(source, key)
        if value not in (None, "", []):
            return value
    return None


def _date_precision(record) -> Optional[str]:
    """Parsed precision, from the column or from stored metadata."""
    column = getattr(record, "date_precision", None)
    if column:
        return str(column)
    stored = _first_present(_metadata_sources(record), "date_precision")
    return str(stored) if stored else None


def _known_day(record) -> Optional[int]:
    """Calendar day when date_precision says the day was parsed.

    Month-only and year-only dates are stored on the 1st. That placeholder is
    not a known day, and neither is a time of day on the timestamp.
    """
    if _date_precision(record) != DATE_PRECISION_DAY:
        return None
    issue_date = getattr(record, "issue_date", None)
    if not issue_date:
        return None
    return _as_date(issue_date).day


def _days_conflict(issue, magazine) -> bool:
    """True when a named day does not belong to the other copy.

    Two month-only dates do not conflict. A day-precision issue conflicts with
    a month-only issue, and with another day-precision issue on a different day.
    """
    wanted = _known_day(issue)
    owned = _known_day(magazine)
    if wanted is None and owned is None:
        return False
    if wanted is not None and owned is not None:
        return wanted != owned
    return True


def _year_precision_conflict(issue, magazine) -> bool:
    """A year-only date is not the month or day stored on the 1st of that year."""
    wanted = _date_precision(issue)
    owned = _date_precision(magazine)
    if wanted != DATE_PRECISION_YEAR and owned != DATE_PRECISION_YEAR:
        return False
    if not wanted or not owned:
        return False
    return wanted != owned


def _edition_keyword(title: Optional[str]) -> Optional[str]:
    """Longest special-edition phrase in a title, if one is present."""
    if not title:
        return None
    lowered = title.lower()
    padded = f" {lowered} "
    found = []
    for keyword in SPECIAL_EDITION_KEYWORDS:
        if keyword.startswith(" ") or keyword.endswith(" "):
            if keyword in padded:
                found.append(keyword.strip())
        elif keyword in lowered:
            found.append(keyword)
    if not found:
        return None
    return max(found, key=len)


def _edition_key(is_special, name, title) -> Optional[str]:
    """Edition identity: a name, the title's keyword, or regular/special."""
    named = _text(name)
    if named:
        return named.lower()
    keyword = _edition_keyword(title)
    if keyword:
        return keyword
    if is_special is True:
        return "special"
    if is_special is False:
        return "regular"
    return None


def _metadata_sources(record) -> list:
    """Metadata dicts that may carry day, issue number, or edition."""
    sources = [getattr(record, "derived_metadata", None), getattr(record, "extra_metadata", None)]
    parsed = getattr(record, "parsed_metadata", None)
    if isinstance(parsed, dict):
        sources.extend(parsed.get(name) for name in ("file_scan", "text_scan", "ocr_scan"))
    return sources


def _edition_of(record) -> Optional[str]:
    """Edition key for a discovered issue or a library copy."""
    sources = _metadata_sources(record)
    flag = _first_present(sources, "is_special_edition")
    if flag is None:
        flag = _first_present(sources, "special_edition")
    if isinstance(flag, str):
        flag = flag.strip().lower() in {"1", "true", "yes"}
    name = _first_present(sources, "special_edition_name")
    return _edition_key(flag if isinstance(flag, bool) else None, name, getattr(record, "title", None))


def _issue_number_of(record) -> Optional[str]:
    """Issue number from the column or from stored metadata."""
    column = _text(getattr(record, "issue_number", None))
    if column:
        return column
    return _text(_first_present(_metadata_sources(record), "issue_number")) or _text(
        _first_present(_metadata_sources(record), "issue")
    )


def _editions_conflict(left: Optional[str], right: Optional[str]) -> bool:
    """True when both sides name an edition and they are not the same one.

    A special edition is not the unlabeled or regular issue in the same month.
    A regular issue can still match a library copy that never recorded an edition.
    """

    def _special(key):
        return bool(key) and key != "regular"

    if _special(left) and _special(right):
        return _normalize_edition(left) != _normalize_edition(right)
    return _special(left) or _special(right)


def _normalize_edition(key: str) -> str:
    """Collapse case and spacing so two names of one edition compare equal."""
    return " ".join(key.lower().split())


def _same_library_issue(issue: DiscoveredIssue, magazine: Periodical) -> bool:
    """True when the library copy is this issue, not merely the same month."""
    if not issue.issue_date or not magazine.issue_date:
        return False
    wanted = _as_date(issue.issue_date)
    owned = _as_date(magazine.issue_date)
    if wanted.year != owned.year or wanted.month != owned.month:
        return False

    if _year_precision_conflict(issue, magazine) or _days_conflict(issue, magazine):
        return False

    wanted_number = _issue_number_of(issue)
    owned_number = _issue_number_of(magazine)
    if wanted_number and owned_number and wanted_number.lower() != owned_number.lower():
        return False

    if _editions_conflict(_edition_of(issue), _edition_of(magazine)):
        return False
    return True


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

        for search_result in search_results:
            try:
                title = search_result.get("title", "")
                if not title:
                    logger.debug("Search result missing title, skipping")
                    stats["errors"] += 1
                    continue

                if not self._validate_is_periodical(search_result):
                    logger.debug(f"Rejecting non-periodical result: {title}")
                    stats["rejected_non_periodical"] += 1
                    continue

                if title_has_blacklisted_extension(title):
                    logger.debug(f"Rejecting blacklisted file type: {title}")
                    stats["rejected_non_periodical"] += 1
                    continue

                if search_result.get("raw_metadata", {}).get("is_collection"):
                    logger.debug(f"Skipping IA collection archive: {title}")
                    stats["rejected_non_periodical"] += 1
                    continue

                if not self._title_matches_tracking(search_result, tracking):
                    stats["rejected_non_periodical"] += 1
                    continue

                url = search_result.get("url", "")
                provider = search_result.get("provider", "")
                pubdate = self._parse_pubdate(search_result.get("pubdate") or search_result.get("publication_date"))

                parsed = self.parser.parse_search_result(
                    title=title,
                    url=url,
                    provider=provider,
                    publication_date=pubdate,
                    raw_metadata=search_result,
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
                    self._update_existing_issue(existing, search_result, parsed, pubdate, now)
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
                        search_result,
                        now,
                        session,
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

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """Normalise a datetime to a timezone-aware UTC datetime."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _parse_pubdate(self, pubdate_str) -> Optional[datetime]:
        """Parse a pubdate string or datetime to a UTC-aware datetime, or return None."""
        if not pubdate_str:
            return None
        try:
            if isinstance(pubdate_str, str):
                pubdate = datetime.fromisoformat(pubdate_str.rstrip("Z"))
            elif isinstance(pubdate_str, datetime):
                pubdate = pubdate_str
            else:
                return None
            return self._ensure_utc(pubdate)
        except (ValueError, AttributeError) as parse_error:
            logger.warning(f"Failed to parse pubdate '{pubdate_str}': {parse_error}")
            return None

    def _title_matches_tracking(self, result: Dict[str, Any], tracking: PeriodicalTracking) -> bool:
        """Return False for results whose title doesn't match the tracked periodical.

        Indexer searches are loose (substring/prefix), so without this check a
        tracked "Time" queues "Timeless" comics and unrelated ebooks.
        """
        aliases = [a.strip() for a in (tracking.search_aliases or "").split(",") if a.strip()]
        names = [tracking.title, *aliases]

        if result.get("provider") == "internet_archive":
            title = result.get("title", "")
            if not any(title_matches_query(title, name) for name in names):
                logger.debug(f"Skipping IA result with poor title match: '{title}' (tracking '{tracking.title}')")
                return False
            return True

        title = result.get("original_title") or result.get("title", "")
        if not title_contains_name(title, names):
            logger.debug(f"Skipping result with poor title match: '{title}' (tracking '{tracking.title}')")
            return False
        return True

    # Statuses that should be re-evaluated when the issue is seen again in search results.
    # WANTED: not yet in the download pipeline — re-evaluate in case tracking rules changed.
    # FAILED is handled separately: the same URL stays failed, and only a new URL
    # is worth another fetch. Resetting every cycle re-downloads rejected releases.
    # Excluded intentionally:
    #   COMPLETED/DOWNLOADING/PENDING/QUEUED — terminal or mid-flight; re-evaluation would cause duplicates.
    #   IGNORED — deliberate exclusion; resetting would override user decisions on every search cycle.
    #   PERMANENTLY_FAILED — has an explicit admin override path (retry_permanently_failed).
    _REEVALUATE_ON_RESEEN = frozenset({DownloadStatus.WANTED})

    def _update_existing_issue(self, existing: DiscoveredIssue, result: Dict[str, Any], parsed, pubdate, now) -> None:
        """Update an existing DiscoveredIssue with fresher data from a new search result.

        WANTED issues return to DISCOVERED so tracking-rule changes are applied
        on the next evaluation. A FAILED issue stays failed until the URL
        changes; seeing the same rejected link again must not queue another fetch.
        """
        existing.last_seen = now
        existing.times_seen += 1
        previous_url = existing.latest_url

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

        # A failed issue keeps its URL when the pubdate does not move, so a
        # repaired indexer (same release, new link) never replaces a dead one.
        # Skip an older hit so it cannot clobber a newer URL. Run this while
        # the status is still FAILED; a new URL resets it below.
        new_url = result.get("url")
        same_or_newer = pubdate is None or existing.latest_pubdate is None or pubdate >= existing.latest_pubdate
        if (
            existing.download_status == DownloadStatus.FAILED
            and new_url
            and new_url != existing.latest_url
            and same_or_newer
        ):
            logger.debug(f"Replacing failed URL for {existing.fuzzy_match_group}")
            existing.latest_url = new_url
            existing.latest_provider = parsed.provider
            if pubdate is not None:
                existing.latest_pubdate = pubdate

        search_result_id = result.get("search_result_id")
        if search_result_id and search_result_id not in existing.search_result_ids:
            existing.search_result_ids.append(search_result_id)

        precision = _precision_from_parsed(parsed)
        if precision:
            existing.date_precision = precision

        url_changed = bool(existing.latest_url) and existing.latest_url != previous_url
        if existing.download_status == DownloadStatus.FAILED:
            if not url_changed:
                return
            logger.debug(f"Resetting failed {existing.fuzzy_match_group} because the URL changed")
            existing.download_status = DownloadStatus.DISCOVERED
            return

        if existing.download_status in self._REEVALUATE_ON_RESEEN:
            logger.debug(
                f"Resetting {existing.fuzzy_match_group} from '{existing.download_status}' "
                f"to 'discovered' for re-evaluation"
            )
            existing.download_status = DownloadStatus.DISCOVERED

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
        session: Session,
    ) -> DiscoveredIssue:
        """Build a new DiscoveredIssue from a parsed search result."""
        search_result_id = result.get("search_result_id")
        # Get the user_id from the tracking record
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        if not tracking:
            raise ValueError(f"Tracking ID {tracking_id} not found")

        return DiscoveredIssue(
            user_id=tracking.user_id,
            tracking_id=tracking_id,
            title=title,
            normalized_title=parsed.cleaned_title.lower(),
            fuzzy_match_group=fuzzy_group,
            issue_date=parsed.publication_date,
            date_precision=_precision_from_parsed(parsed),
            issue_number=parsed.raw_metadata.get("issue"),
            year=parsed.publication_date.year if parsed.publication_date else None,
            month=parsed.publication_date.month if parsed.publication_date else None,
            language=parsed.language,
            country=parsed.country,
            first_seen=now,
            last_seen=now,
            times_seen=1,
            download_status=DownloadStatus.DISCOVERED,
            download_priority=_PRIORITY_BASE,
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

    def discover_and_evaluate(
        self, tracking_id: int, search_results: List[Dict[str, Any]], session: Session
    ) -> Dict[str, Any]:
        """
        Full discovery pipeline: record search results then evaluate discovered issues.

        This is the preferred entry point for callers that need both steps. Using this
        method ensures the required record → evaluate sequence is always followed and
        prevents callers from accidentally omitting the evaluation step (which would
        leave new issues stuck in DISCOVERED status and invisible to the download queue).

        Args:
            tracking_id: PeriodicalTracking ID
            search_results: Raw search results from a provider
            session: Database session

        Returns:
            Combined stats dict with keys from both record_search_results and
            evaluate_discovered_issues: {new, updated, duplicate, errors,
            rejected_non_periodical, wanted, ignored, already_have}
        """
        record_stats = self.record_search_results(
            tracking_id=tracking_id,
            search_results=search_results,
            session=session,
        )
        eval_stats = self.evaluate_discovered_issues(
            tracking_id=tracking_id,
            session=session,
        )
        return {
            **record_stats,
            **eval_stats,
            "errors": record_stats["errors"] + eval_stats["errors"],
        }

    def handle_download_failure(self, issue_id: int, error_message: str, session: Session) -> DownloadStatus:
        """
        Handle a download failure for a discovered issue.

        This method:
        1. Increments attempt_count
        2. Compares to max_retries
        3. Marks as FAILED (can retry) or PERMANENTLY_FAILED (permanent)
        4. Adjusts priority (reduce for failures)
        5. Records error message

        Args:
            issue_id: DiscoveredIssue ID
            error_message: Error message from download failure
            session: Database session

        Returns:
            New status: DownloadStatus.FAILED or DownloadStatus.PERMANENTLY_FAILED
        """
        issue = session.query(DiscoveredIssue).filter_by(id=issue_id).first()
        if not issue:
            logger.error(f"DiscoveredIssue {issue_id} not found")
            return DownloadStatus.FAILED

        now = utc_now()
        issue.attempt_count += 1
        issue.last_attempt = now
        issue.current_submission_id = None
        if len(error_message) > MAX_ERROR_LENGTH:
            logger.warning(
                f"Error message truncated from {len(error_message)} to {MAX_ERROR_LENGTH} chars for issue {issue_id}"
            )
        issue.last_error = error_message[:MAX_ERROR_LENGTH]

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

        An indexer rejection stays failed until a search replaces the URL.
        Putting that issue back on the queue would resubmit the same dead link.

        Args:
            session: Database session
            limit: Maximum number of issues to return
            tracking_id: Optional filter by tracking ID

        Returns:
            List of DiscoveredIssue objects ready for download
        """
        indexer_rejection = DiscoveredIssue.last_error.like(f"{INDEXER_REJECTION_ERROR}%")
        query = session.query(DiscoveredIssue).filter(
            or_(
                DiscoveredIssue.download_status == DownloadStatus.WANTED,
                and_(
                    DiscoveredIssue.download_status == DownloadStatus.FAILED,
                    or_(DiscoveredIssue.last_error.is_(None), ~indexer_rejection),
                ),
            )
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
        issue.download_priority = _PRIORITY_BASE
        issue.last_error = None

        session.commit()
        logger.info(f"Manually reset permanently_failed issue to wanted: {issue.title}")
        return True

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
        # Only filter by country when both the issue and the tracking record have an
        # explicit country set. If either is unset we cannot make a meaningful comparison
        # and should not reject the issue.
        if issue.country and tracking.country:
            issue_country = self._normalize_country(issue.country)
            tracking_country = self._normalize_country(tracking.country)
            if issue_country != tracking_country:
                logger.debug(
                    f"Skipping '{issue.title}': Country mismatch "
                    f"(issue: {issue_country}, tracking: {tracking_country})"
                )
                return False

        if tracking.track_all_editions:
            return True

        if tracking.track_new_only:
            if issue.issue_date:
                now = utc_now()
                issue_date = issue.issue_date
                if issue_date.tzinfo is None:
                    issue_date = issue_date.replace(tzinfo=timezone.utc)
                days_old = (now - issue_date).days
                is_new = days_old <= NEW_ISSUE_THRESHOLD_DAYS
                if not is_new:
                    logger.debug(
                        f"Skipping old issue for track_new_only: {issue.title} "
                        f"(issue_date: {issue.issue_date}, {days_old} days old)"
                    )
                return is_new
            elif issue.year:
                current_year = utc_now().year
                return issue.year >= current_year
            else:
                logger.debug(f"Skipping issue with no date for track_new_only: {issue.title}")
                return False

        if tracking.selected_years and issue.year:
            return issue.year in tracking.selected_years

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

        A library copy matches when the year and month agree. ``date_precision``
        says whether the day was parsed. A month-only issue does not own a
        weekly or daily issue. Two day-precision dates have to fall on the same
        day, including the 1st. Two month-only issues in that month are the
        same copy unless the issue number or edition differs.

        If either side has no date, fall back to the fuzzy group id, which
        compares normalized titles.

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

        if issue.issue_date:
            for mag in existing:
                if _same_library_issue(issue, mag):
                    owned = _as_date(mag.issue_date)
                    logger.debug(f"Library already has {owned.year}-{owned.month:02d}: {issue.title}")
                    return mag.id

        if issue.fuzzy_match_group:
            for mag in existing:
                if issue.issue_date and mag.issue_date:
                    continue
                if get_fuzzy_group_id(mag.title) == issue.fuzzy_match_group:
                    logger.debug(f"Fuzzy group match found: library '{mag.title}' matches {issue.fuzzy_match_group}")
                    return mag.id

        return None
