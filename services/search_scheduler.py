"""
Search Scheduler - Adaptive search scheduling for periodical tracking.

Handles:
- Selecting which periodicals to search each run
- Adjusting search intervals based on discovery success
- Prioritizing active/promising periodicals
- Updating search statistics
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.parsers import utc_now
from models.database import MagazineTracking

logger = logging.getLogger(__name__)


class SearchScheduler:
    """
    Adaptive scheduler for periodical searches.

    Instead of searching ALL tracked periodicals every 30 minutes (overwhelming),
    this scheduler:
    - Searches 1-2 periodicals per run
    - Adjusts search intervals based on discovery success
    - Prioritizes periodicals that are actively finding new issues
    """

    def __init__(
        self,
        max_periodicals_per_run: int = 2,
        rapid_interval_hours: int = 1,
        normal_interval_hours: int = 6,
        slow_interval_hours: int = 24,
        very_slow_interval_hours: int = 168,  # 7 days
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

    def select_periodicals_to_search(self, session: Session) -> List[MagazineTracking]:
        """
        Select which periodicals to search this run.

        Selection criteria (in priority order):
        1. Never searched before (last_searched is NULL)
        2. Overdue for search (last_searched + interval < now)
        3. Recently successful (found new issues recently)

        Args:
            session: Database session

        Returns:
            List of MagazineTracking objects to search (max: max_periodicals_per_run)
        """
        now = utc_now()
        candidates = []

        # Priority 1: Never searched before
        never_searched = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.last_searched.is_(None))
            .limit(self.max_periodicals_per_run)
            .all()
        )

        if never_searched:
            logger.info(f"Found {len(never_searched)} periodicals never searched before")
            candidates.extend(never_searched)

        # If we have enough, return
        if len(candidates) >= self.max_periodicals_per_run:
            return candidates[: self.max_periodicals_per_run]

        # Priority 2: Overdue for search
        overdue = (
            session.query(MagazineTracking)
            .filter(
                and_(
                    MagazineTracking.last_searched.isnot(None),
                    # Calculate due time: last_searched + (search_interval_hours * 3600)
                    MagazineTracking.last_searched + timedelta(hours=1) * MagazineTracking.search_interval_hours <= now,
                )
            )
            .order_by(MagazineTracking.last_searched.asc())  # Oldest first
            .limit(self.max_periodicals_per_run - len(candidates))
            .all()
        )

        if overdue:
            logger.info(f"Found {len(overdue)} periodicals overdue for search")
            candidates.extend(overdue)

        logger.info(f"Selected {len(candidates)} periodicals to search: " f"{[p.title for p in candidates]}")

        return candidates[: self.max_periodicals_per_run]

    def update_search_stats(
        self,
        tracking_id: int,
        new_issues_found: int,
        session: Session,
    ) -> None:
        """
        Update search statistics and adjust search interval.

        This method:
        1. Updates last_searched timestamp
        2. Increments search_count
        3. Updates discovery statistics
        4. Adjusts search_interval_hours based on success

        Args:
            tracking_id: MagazineTracking ID
            new_issues_found: Number of new issues discovered in this search
            session: Database session
        """
        tracking = session.query(MagazineTracking).filter_by(id=tracking_id).first()
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
        total_tracked = session.query(MagazineTracking).count()

        never_searched = session.query(MagazineTracking).filter(MagazineTracking.last_searched.is_(None)).count()

        now = utc_now()

        # Count by interval
        rapid = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.search_interval_hours == self.rapid_interval_hours)
            .count()
        )

        normal = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.search_interval_hours == self.normal_interval_hours)
            .count()
        )

        slow = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.search_interval_hours == self.slow_interval_hours)
            .count()
        )

        very_slow = (
            session.query(MagazineTracking)
            .filter(MagazineTracking.search_interval_hours == self.very_slow_interval_hours)
            .count()
        )

        # Count overdue
        overdue = (
            session.query(MagazineTracking)
            .filter(
                and_(
                    MagazineTracking.last_searched.isnot(None),
                    MagazineTracking.last_searched + timedelta(hours=1) * MagazineTracking.search_interval_hours <= now,
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
            tracking_id: MagazineTracking ID
            session: Database session
            interval_hours: New interval in hours (defaults to normal_interval_hours)

        Returns:
            True if successful, False otherwise
        """
        tracking = session.query(MagazineTracking).filter_by(id=tracking_id).first()
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

    # Private helper methods

    def _calculate_new_interval(self, searches_without_new_issues: int) -> int:
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
