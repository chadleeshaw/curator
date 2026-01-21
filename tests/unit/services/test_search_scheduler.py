"""
Test SearchScheduler - Adaptive search scheduling for Issue Discovery & Tracking.

Tests cover:
- Selecting periodicals to search (adaptive scheduling)
- Updating search statistics (interval adjustments)
- Priority for never-searched and overdue periodicals
- Search interval transitions (rapid → normal → slow → very_slow)
- Manual interval reset
"""

import sys

sys.path.insert(0, ".")

import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services import SearchScheduler
from models.database import Base, PeriodicalTracking


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        from pathlib import Path

        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def search_scheduler():
    """Create SearchScheduler with test settings"""
    return SearchScheduler(
        max_periodicals_per_run=2,
        rapid_interval_hours=1,
        normal_interval_hours=6,
        slow_interval_hours=24,
        very_slow_interval_hours=168,  # 7 days
        empty_search_threshold=3,
    )


class TestSelectPeriodicalsToSearch:
    """Test selecting periodicals to search with adaptive scheduling"""

    def test_select_never_searched_first(self, test_db, search_scheduler):
        """Test that never-searched periodicals are selected first"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodicals - some never searched, some searched
        never_searched = PeriodicalTracking(
            olid="never-searched",
            title="Never Searched Magazine",
            track_all_editions=True,
            last_searched=None,
        )
        recently_searched = PeriodicalTracking(
            olid="recent",
            title="Recently Searched Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(minutes=30),
            search_interval_hours=6,
        )
        session.add_all([never_searched, recently_searched])
        session.commit()

        # Select periodicals
        selected = search_scheduler.select_periodicals_to_search(session)

        # Should prioritize never_searched
        assert len(selected) >= 1
        # The never_searched should be in the list
        never_searched_ids = [p.id for p in selected if p.id == never_searched.id]
        assert len(never_searched_ids) == 1

        session.close()

    def test_select_overdue_periodicals(self, test_db, search_scheduler):
        """Test selecting overdue periodicals based on interval"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodicals with different intervals
        overdue = PeriodicalTracking(
            olid="overdue",
            title="Overdue Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=7),  # 7 hours ago
            search_interval_hours=6,  # Should have been searched 1 hour ago
        )
        not_due = PeriodicalTracking(
            olid="not-due",
            title="Not Due Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(minutes=30),  # 30 min ago
            search_interval_hours=6,  # Not due yet
        )
        session.add_all([overdue, not_due])
        session.commit()

        # Select periodicals
        selected = search_scheduler.select_periodicals_to_search(session)

        # Should include overdue
        assert len(selected) >= 1
        overdue_ids = [p.id for p in selected if p.id == overdue.id]
        assert len(overdue_ids) == 1

        session.close()

    def test_select_respects_max_limit(self, test_db, search_scheduler):
        """Test that selection respects max_periodicals_per_run"""
        engine, session_factory = test_db
        session = session_factory()

        # Create 5 overdue periodicals
        for i in range(5):
            tracking = PeriodicalTracking(
                olid=f"mag-{i}",
                title=f"Magazine {i}",
                track_all_editions=True,
                last_searched=datetime.now(UTC) - timedelta(hours=10),
                search_interval_hours=6,
            )
            session.add(tracking)
        session.commit()

        # Select periodicals (max=2)
        selected = search_scheduler.select_periodicals_to_search(session)

        # Should only select 2 (max_periodicals_per_run)
        assert len(selected) == 2

        session.close()

    def test_select_prioritizes_longer_overdue(self, test_db, search_scheduler):
        """Test that longer overdue periodicals are selected first"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodicals overdue by different amounts
        very_overdue = PeriodicalTracking(
            olid="very-overdue",
            title="Very Overdue Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(days=10),
            search_interval_hours=6,
        )
        slightly_overdue = PeriodicalTracking(
            olid="slightly-overdue",
            title="Slightly Overdue Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=7),
            search_interval_hours=6,
        )
        session.add_all([slightly_overdue, very_overdue])  # Add in reverse order
        session.commit()

        # Select periodicals
        selected = search_scheduler.select_periodicals_to_search(session)

        # Should select most overdue first
        assert len(selected) == 2
        assert selected[0].id == very_overdue.id
        assert selected[1].id == slightly_overdue.id

        session.close()


class TestUpdateSearchStats:
    """Test updating search statistics and interval adjustments"""

    def test_update_search_stats_found_issues(self, test_db, search_scheduler):
        """Test that finding issues switches to rapid interval"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical with normal interval
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=7),
            search_interval_hours=6,  # Normal interval
            searches_without_new_issues=2,
        )
        session.add(tracking)
        session.commit()

        # Update with found issues
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=5,
            session=session,
        )

        # Check database
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 1  # Rapid interval
        assert tracking.searches_without_new_issues == 0  # Reset
        assert tracking.last_searched is not None

        session.close()

    def test_update_search_stats_no_issues_increments_counter(self, test_db, search_scheduler):
        """Test that finding no issues increments counter"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=7),
            search_interval_hours=6,
            searches_without_new_issues=0,  # Start at 0
        )
        session.add(tracking)
        session.commit()

        # Update with no found issues
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )

        # Check database
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.searches_without_new_issues == 1  # Incremented
        # Interval should still be normal (not enough empty searches yet)
        assert tracking.search_interval_hours == 6

        session.close()

    def test_update_search_stats_transitions_to_slow(self, test_db, search_scheduler):
        """Test transition from normal to slow interval"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical with normal interval
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=7),
            search_interval_hours=6,  # Normal
            searches_without_new_issues=2,  # Need 3 for slow (threshold)
        )
        session.add(tracking)
        session.commit()

        # Update with no found issues (3rd search without issues)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )

        # Check database
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 24  # Slow interval
        assert tracking.searches_without_new_issues == 3

        session.close()

    def test_update_search_stats_transitions_to_very_slow(self, test_db, search_scheduler):
        """Test transition from slow to very_slow interval"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical with slow interval
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(days=2),
            search_interval_hours=24,  # Slow
            searches_without_new_issues=5,  # Need 6+ for very_slow
        )
        session.add(tracking)
        session.commit()

        # Update with no found issues (6th search without issues)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )

        # Check database
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 168  # Very slow interval (7 days)
        assert tracking.searches_without_new_issues == 6

        session.close()

    def test_update_search_stats_stays_at_very_slow(self, test_db, search_scheduler):
        """Test that very_slow is the maximum interval"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical already at very_slow
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(days=8),
            search_interval_hours=168,  # Very slow
            searches_without_new_issues=10,
        )
        session.add(tracking)
        session.commit()

        # Update with no found issues
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )

        # Check database - should stay at very_slow
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 168  # Still very slow
        assert tracking.searches_without_new_issues == 11  # Counter still increments

        session.close()


class TestResetSearchInterval:
    """Test manual reset of search interval"""

    def test_reset_search_interval_to_rapid(self, test_db, search_scheduler):
        """Test manually resetting search interval to rapid"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical at very_slow
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(days=8),
            search_interval_hours=168,  # Very slow
            searches_without_new_issues=10,
        )
        session.add(tracking)
        session.commit()

        # Reset to rapid
        success = search_scheduler.reset_search_interval(
            tracking_id=tracking.id,
            session=session,
            interval_hours=1,  # Rapid
        )

        assert success is True

        # Check database
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 1  # Rapid
        assert tracking.searches_without_new_issues == 0  # Reset counter

        session.close()

    def test_reset_search_interval_invalid_tracking_id(self, test_db, search_scheduler):
        """Test reset fails for non-existent tracking ID"""
        engine, session_factory = test_db
        session = session_factory()

        # Try to reset non-existent tracking
        success = search_scheduler.reset_search_interval(
            tracking_id=999,
            session=session,
            interval_hours=1,
        )

        assert success is False

        session.close()


class TestGetSearchStatistics:
    """Test retrieving global search statistics"""

    def test_get_search_statistics_returns_correct_data(self, test_db, search_scheduler):
        """Test getting global search statistics"""
        engine, session_factory = test_db
        session = session_factory()

        # Create several periodicals with different states
        tracking1 = PeriodicalTracking(
            olid="mag-1",
            title="Magazine 1",
            track_all_editions=True,
            last_searched=None,  # Never searched
            search_interval_hours=6,
        )
        tracking2 = PeriodicalTracking(
            olid="mag-2",
            title="Magazine 2",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=1),
            search_interval_hours=1,  # Rapid
        )
        tracking3 = PeriodicalTracking(
            olid="mag-3",
            title="Magazine 3",
            track_all_editions=True,
            last_searched=datetime.now(UTC) - timedelta(hours=5),
            search_interval_hours=6,  # Normal
        )
        session.add_all([tracking1, tracking2, tracking3])
        session.commit()

        # Get statistics
        stats = search_scheduler.get_search_statistics(session)

        assert stats is not None
        assert stats["total_tracked"] == 3
        assert stats["never_searched"] == 1
        assert "interval_distribution" in stats
        assert stats["interval_distribution"]["rapid"] >= 1  # At least tracking2
        assert stats["interval_distribution"]["normal"] >= 1  # At least tracking3

        session.close()


class TestIntervalTransitions:
    """Test complete interval transition scenarios"""

    def test_complete_interval_lifecycle(self, test_db, search_scheduler):
        """Test complete lifecycle: normal → slow → very_slow → rapid (on discovery)"""
        engine, session_factory = test_db
        session = session_factory()

        # Create periodical (starts at normal interval by default)
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=True,
            last_searched=datetime.now(UTC),
            search_interval_hours=6,  # Normal
            searches_without_new_issues=0,
        )
        session.add(tracking)
        session.commit()

        # Search 1: No issues (stay at normal)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 6  # Normal
        assert tracking.searches_without_new_issues == 1

        # Search 2: No issues (stay at normal)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 6  # Normal
        assert tracking.searches_without_new_issues == 2

        # Search 3: No issues (transition to slow - hits threshold of 3)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 24  # Slow
        assert tracking.searches_without_new_issues == 3

        # Searches 4-5: No issues (stay at slow)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 24  # Still slow
        assert tracking.searches_without_new_issues == 5

        # Search 6: No issues (transition to very_slow)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=0,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 168  # Very slow
        assert tracking.searches_without_new_issues == 6

        # Discovery: Found new issues (transition to rapid)
        search_scheduler.update_search_stats(
            tracking_id=tracking.id,
            new_issues_found=3,
            session=session,
        )
        tracking = session.query(PeriodicalTracking).filter_by(id=tracking.id).first()
        assert tracking.search_interval_hours == 1  # Rapid
        assert tracking.searches_without_new_issues == 0  # Reset

        session.close()
