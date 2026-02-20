"""
Adaptive search scheduling for periodical tracking.

Adjusts search intervals based on discovery success to optimize API rate limit usage.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.parsers import utc_now
from models.database import PeriodicalTracking

logger = logging.getLogger(__name__)


class SearchScheduler:
    """
    Adaptive scheduler for periodical searches.

    Prevents rate limit exhaustion by searching a small number of periodicals per run
    and adjusting intervals based on discovery success.
    """

    def __init__(
        self,
        max_periodicals_per_run: int = 10,
        rapid_interval_hours: float = 0.5,  # 30 minutes when finding new issues
        normal_interval_hours: float = 2,  # 2 hours default
        slow_interval_hours: float = 12,  # 12 hours after some empty searches
        very_slow_interval_hours: float = 48,  # 2 days after many empty searches
        empty_search_threshold: int = 3,  # Slow down after N empty searches
    ):
        """
        Initialize the search scheduler.

        Args:
            max_periodicals_per_run: Maximum number of periodicals to search per run
            rapid_interval_hours: Interval for periodicals finding new issues
            normal_interval_hours: Default interval
            slow_interval_hours: Interval after some empty searches
            very_slow_interval_hours: Interval after many empty searches
            empty_search_threshold: Number of empty searches before slowing down
        """
        self.max_periodicals_per_run = max_periodicals_per_run
        self.rapid_interval_hours = rapid_interval_hours
        self.normal_interval_hours = normal_interval_hours
        self.slow_interval_hours = slow_interval_hours
        self.very_slow_interval_hours = very_slow_interval_hours
        self.empty_search_threshold = empty_search_threshold

    def select_periodicals_to_search(self, session: Session) -> List[PeriodicalTracking]:
        """
        Prioritizes never-searched periodicals, then overdue searches.
        Filters out "watch only" items that will never trigger downloads.
        """
        now = utc_now()
        candidates = []

        never_searched = session.query(PeriodicalTracking).filter(PeriodicalTracking.last_searched.is_(None)).all()

        downloadable_never_searched = [p for p in never_searched if self._has_download_criteria(p)]

        if downloadable_never_searched:
            logger.debug(f"Found {len(downloadable_never_searched)} downloadable periodicals never searched before")
            candidates.extend(downloadable_never_searched[: self.max_periodicals_per_run])

        if len(candidates) >= self.max_periodicals_per_run:
            return candidates[: self.max_periodicals_per_run]

        remaining_slots = self.max_periodicals_per_run - len(candidates)
        next_search_due = (
            PeriodicalTracking.last_searched + timedelta(hours=1) * PeriodicalTracking.search_interval_hours
        )
        is_overdue = next_search_due <= now

        overdue = (
            session.query(PeriodicalTracking)
            .filter(
                and_(
                    PeriodicalTracking.last_searched.isnot(None),
                    is_overdue,
                )
            )
            .order_by(PeriodicalTracking.last_searched.asc())
            .all()
        )

        downloadable_overdue = [p for p in overdue if self._has_download_criteria(p)][:remaining_slots]

        if downloadable_overdue:
            logger.debug(f"Found {len(downloadable_overdue)} downloadable periodicals overdue for search")
            candidates.extend(downloadable_overdue)

        logger.debug(f"Selected {len(candidates)} periodicals to search: " f"{[p.title for p in candidates]}")

        return candidates[: self.max_periodicals_per_run]

    @staticmethod
    def _has_download_criteria(tracking: PeriodicalTracking) -> bool:
        """Check if a tracked periodical has download criteria set.

        Periodicals in "watch only" mode should not be searched during auto-download
        to avoid wasting API rate limits.
        """
        if tracking.track_all_editions:
            return True
        if tracking.track_new_only:
            return True
        if tracking.selected_years and len(tracking.selected_years) > 0:
            return True
        return False

    def update_search_stats(
        self,
        tracking_id: int,
        new_issues_found: int,
        session: Session,
    ) -> None:
        """
        Update search statistics and adjust search interval based on discovery success.
        """
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return

        now = utc_now()

        # Update search tracking
        tracking.last_searched = now
        tracking.search_count += 1

        # Update discovery statistics
        if new_issues_found > 0:
            # Found new issues - this is good!
            tracking.total_issues_discovered += new_issues_found
            tracking.last_discovery_count = new_issues_found
            tracking.last_discovery_date = now
            tracking.searches_without_new_issues = 0  # Reset counter

            # Increase search frequency (move to rapid interval)
            old_interval = tracking.search_interval_hours
            tracking.search_interval_hours = self.rapid_interval_hours

            logger.info(
                f"Found {new_issues_found} new issues for '{tracking.title}', "
                f"adjusting interval {old_interval}h -> {tracking.search_interval_hours}h"
            )
        else:
            # No new issues found
            tracking.last_discovery_count = 0
            tracking.searches_without_new_issues += 1

            # Adjust interval based on consecutive empty searches
            old_interval = tracking.search_interval_hours
            new_interval = self._calculate_new_interval(tracking.searches_without_new_issues)

            if new_interval != old_interval:
                tracking.search_interval_hours = new_interval
                logger.info(
                    f"No new issues for '{tracking.title}' "
                    f"({tracking.searches_without_new_issues} consecutive empty searches), "
                    f"adjusting interval {old_interval}h -> {new_interval}h"
                )

        session.commit()

    def get_search_statistics(self, session: Session) -> Dict[str, Any]:
        """
        Get overall search statistics for monitoring.

        Returns:
            Dictionary with search statistics
        """
        total_tracked = session.query(PeriodicalTracking).count()

        never_searched = session.query(PeriodicalTracking).filter(PeriodicalTracking.last_searched.is_(None)).count()

        now = utc_now()

        # Count by interval
        rapid = (
            session.query(PeriodicalTracking)
            .filter(PeriodicalTracking.search_interval_hours == self.rapid_interval_hours)
            .count()
        )

        normal = (
            session.query(PeriodicalTracking)
            .filter(PeriodicalTracking.search_interval_hours == self.normal_interval_hours)
            .count()
        )

        slow = (
            session.query(PeriodicalTracking)
            .filter(PeriodicalTracking.search_interval_hours == self.slow_interval_hours)
            .count()
        )

        very_slow = (
            session.query(PeriodicalTracking)
            .filter(PeriodicalTracking.search_interval_hours == self.very_slow_interval_hours)
            .count()
        )

        # Count overdue
        overdue = (
            session.query(PeriodicalTracking)
            .filter(
                and_(
                    PeriodicalTracking.last_searched.isnot(None),
                    PeriodicalTracking.last_searched + timedelta(hours=1) * PeriodicalTracking.search_interval_hours
                    <= now,
                )
            )
            .count()
        )

        return {
            "total_tracked": total_tracked,
            "never_searched": never_searched,
            "overdue": overdue,
            "interval_distribution": {
                "rapid": rapid,
                "normal": normal,
                "slow": slow,
                "very_slow": very_slow,
            },
            "timestamp": now.isoformat(),
        }

    def reset_search_interval(self, tracking_id: int, session: Session, interval_hours: Optional[int] = None) -> bool:
        """
        Manually reset search interval for a periodical (admin override).

        Args:
            tracking_id: PeriodicalTracking ID
            session: Database session
            interval_hours: New interval in hours (defaults to normal_interval_hours)

        Returns:
            True if successful, False otherwise
        """
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
        if not tracking:
            logger.error(f"Tracking ID {tracking_id} not found")
            return False

        new_interval = interval_hours if interval_hours else self.normal_interval_hours
        old_interval = tracking.search_interval_hours

        tracking.search_interval_hours = new_interval
        tracking.searches_without_new_issues = 0  # Reset counter

        session.commit()
        logger.info(f"Manually reset interval for '{tracking.title}': {old_interval}h -> {new_interval}h")

        return True

    def reset_all_search_intervals(self, session: Session) -> Dict[str, int]:
        """
        Reset all tracked periodicals to normal search interval.

        Useful after filter changes or to recover from overly slowed-down intervals.

        Args:
            session: Database session

        Returns:
            Dict with stats: {reset: count, already_normal: count}
        """
        stats = {"reset": 0, "already_normal": 0}

        periodicals = session.query(PeriodicalTracking).all()

        for tracking in periodicals:
            if tracking.search_interval_hours != self.normal_interval_hours:
                old_interval = tracking.search_interval_hours
                tracking.search_interval_hours = self.normal_interval_hours
                tracking.searches_without_new_issues = 0
                stats["reset"] += 1
                logger.debug(f"Reset interval for '{tracking.title}': {old_interval}h -> {self.normal_interval_hours}h")
            else:
                stats["already_normal"] += 1

        session.commit()
        logger.info(
            f"Reset all search intervals: {stats['reset']} reset to normal, "
            f"{stats['already_normal']} already at normal interval"
        )

        return stats

    # Private helper methods

    def _calculate_new_interval(self, searches_without_new_issues: int) -> float:
        """
        Calculate new search interval based on consecutive empty searches.

        Strategy:
        - 0 empty searches: rapid interval (found something last time)
        - 1-2 empty searches: normal interval
        - 3-5 empty searches: slow interval
        - 6+ empty searches: very slow interval

        Args:
            searches_without_new_issues: Consecutive searches finding nothing

        Returns:
            New interval in hours
        """
        if searches_without_new_issues == 0:
            return self.rapid_interval_hours
        elif searches_without_new_issues <= 2:
            return self.normal_interval_hours
        elif searches_without_new_issues <= 5:
            return self.slow_interval_hours
        else:
            return self.very_slow_interval_hours
