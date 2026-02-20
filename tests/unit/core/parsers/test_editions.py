"""
Test individual edition tracking functionality.
Tests selected_editions dictionary and DB model behaviour.
"""

import sys

sys.path.insert(0, ".")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import (
    Base,
    PeriodicalTracking,
)


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
    # Use a temporary file-based database instead of :memory:
    # This is necessary because SQLite :memory: databases are not shared across threads
    # even with check_same_thread=False - each connection gets its own memory space
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


class TestSelectedEditionsDict:
    """Test selected_editions dictionary functionality"""

    def test_selected_editions_empty_by_default(self, test_db):
        """Test tracking record has empty selected_editions by default"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
        )
        session.add(tracking)
        session.commit()

        assert tracking.selected_editions == {}

        session.close()

    def test_can_add_edition_to_selected_editions(self, test_db):
        """Test adding editions to selected_editions dict"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            selected_editions={"OL123456M": True, "OL123457M": True},
        )
        session.add(tracking)
        session.commit()

        assert len(tracking.selected_editions) == 2
        assert tracking.selected_editions["OL123456M"] is True

        session.close()

    def test_can_untrack_edition(self, test_db):
        """Test marking edition as untracked (False)"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            selected_editions={"OL123456M": True, "OL123457M": False},
        )
        session.add(tracking)
        session.commit()

        # Only one is tracked
        tracked = [k for k, v in tracking.selected_editions.items() if v]
        assert len(tracked) == 1

        session.close()


class TestAutoDownloadIntegration:
    """Test integration with auto-download task"""

    def test_auto_download_checks_selected_editions(self, test_db):
        """Test that periodicals with selected_editions are processed"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking with selected editions
        tracking = PeriodicalTracking(
            olid="test-mag",
            title="Test Magazine",
            track_all_editions=False,
            track_new_only=False,
            selected_editions={"OL123456M": True},
        )
        session.add(tracking)
        session.commit()

        # Query for periodicals to check (mimics auto_download_task logic)
        tracked_with_selections = (
            session.query(PeriodicalTracking).filter(PeriodicalTracking.selected_editions.isnot(None)).all()
        )

        # Should find the tracking record
        assert len(tracked_with_selections) > 0

        # Check if any editions are actually selected
        has_selections = any(any(t.selected_editions.values()) for t in tracked_with_selections)
        assert has_selections is True

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
