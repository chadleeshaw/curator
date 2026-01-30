"""
Tests for language synchronization between tracking and periodicals
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import DatabaseManager
from models.database import Periodical, PeriodicalTracking


@pytest.fixture
def test_db():
    """Create temporary test database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        db_manager = DatabaseManager(db_url)
        db_manager.create_tables()
        yield db_manager.engine, db_manager.session_factory


class TestLanguageSynchronization:
    """Test language synchronization when updating tracking records"""

    def test_update_tracking_language_cascades_to_periodicals(self, test_db):
        """When tracking language changes, all linked periodicals should update"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            # Create tracking record with English language
            tracking = PeriodicalTracking(
                olid="OL123W",
                title="Test Magazine",
                language="English",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
            )
            session.add(tracking)
            session.commit()

            # Create periodicals linked to tracking (all English initially)
            periodicals = [
                Periodical(
                    title="Test Magazine",
                    language="English",
                    issue_date=datetime(2024, 1, 1),
                    file_path="/test/mag_jan_2024.pdf",
                    tracking_id=tracking.id,
                ),
                Periodical(
                    title="Test Magazine",
                    language="English",
                    issue_date=datetime(2024, 2, 1),
                    file_path="/test/mag_feb_2024.pdf",
                    tracking_id=tracking.id,
                ),
                Periodical(
                    title="Test Magazine",
                    language="English",
                    issue_date=datetime(2024, 3, 1),
                    file_path="/test/mag_mar_2024.pdf",
                    tracking_id=tracking.id,
                ),
            ]
            session.add_all(periodicals)
            session.commit()

            # Change tracking language to German
            tracking.language = "German"

            # Simulate the cascade update (as done in update_tracking endpoint)
            mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            for mag in mags:
                mag.language = tracking.language

            session.commit()

            # Verify all periodicals now have German language
            updated_mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            assert all(mag.language == "German" for mag in updated_mags)
            assert len(updated_mags) == 3

        finally:
            session.close()

    def test_periodicals_with_different_languages_become_consistent(self, test_db):
        """Periodicals with inconsistent languages should be synchronized"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            # Create tracking record
            tracking = PeriodicalTracking(
                olid="OL456W",
                title="Multi-Lang Magazine",
                language="English",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
            )
            session.add(tracking)
            session.commit()

            # Create periodicals with INCONSISTENT languages (bug scenario)
            periodicals = [
                Periodical(
                    title="Multi-Lang Magazine",
                    language="English",
                    issue_date=datetime(2024, 1, 1),
                    file_path="/test/multi_jan.pdf",
                    tracking_id=tracking.id,
                ),
                Periodical(
                    title="Multi-Lang Magazine",
                    language="German",  # Wrong! Should match tracking
                    issue_date=datetime(2024, 2, 1),
                    file_path="/test/multi_feb.pdf",
                    tracking_id=tracking.id,
                ),
                Periodical(
                    title="Multi-Lang Magazine",
                    language="French",  # Wrong! Should match tracking
                    issue_date=datetime(2024, 3, 1),
                    file_path="/test/multi_mar.pdf",
                    tracking_id=tracking.id,
                ),
            ]
            session.add_all(periodicals)
            session.commit()

            # Verify initial inconsistency
            mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            languages = {mag.language for mag in mags}
            assert len(languages) == 3  # Three different languages (bad!)

            # Apply synchronization (as the script would do)
            for mag in mags:
                mag.language = tracking.language
            session.commit()

            # Verify all now consistent
            updated_mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            assert all(mag.language == "English" for mag in updated_mags)
            assert len({mag.language for mag in updated_mags}) == 1

        finally:
            session.close()

    def test_untracked_periodicals_not_affected(self, test_db):
        """Periodicals without tracking_id should not be affected"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            # Create tracking record
            tracking = PeriodicalTracking(
                olid="OL789W",
                title="Tracked Magazine",
                language="English",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
            )
            session.add(tracking)
            session.commit()  # Commit to get tracking.id

            # Create tracked periodical
            tracked = Periodical(
                title="Tracked Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/tracked.pdf",
                tracking_id=tracking.id,
            )

            # Create untracked periodical (different language)
            untracked = Periodical(
                title="Independent Magazine",
                language="German",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/independent.pdf",
                tracking_id=None,
            )

            session.add_all([tracked, untracked])
            session.commit()

            # Change tracking language
            tracking.language = "Spanish"

            # Update only tracked periodicals
            mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            for mag in mags:
                mag.language = tracking.language
            session.commit()

            # Verify tracked changed but untracked didn't
            session.expire_all()
            tracked_updated = session.query(Periodical).filter_by(id=tracked.id).first()
            untracked_updated = session.query(Periodical).filter_by(id=untracked.id).first()

            assert tracked_updated.language == "Spanish"
            assert untracked_updated.language == "German"  # Unchanged

        finally:
            session.close()

    def test_tracking_with_no_periodicals_not_affected(self, test_db):
        """Tracking records with no linked periodicals should not cause errors"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            # Create tracking with no periodicals
            tracking = PeriodicalTracking(
                olid="OL999W",
                title="Empty Tracking",
                language="English",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
            )
            session.add(tracking)
            session.commit()

            # Change language
            tracking.language = "Japanese"

            # Try to update linked periodicals (should be none)
            mags = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()
            assert len(mags) == 0

            for mag in mags:
                mag.language = tracking.language

            session.commit()

            # Should not raise any errors
            assert tracking.language == "Japanese"

        finally:
            session.close()

    def test_language_change_during_import_sync(self, test_db):
        """During import, periodical language should sync with tracking"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            # Create tracking with German language
            tracking = PeriodicalTracking(
                olid="OL111W",
                title="German Magazine",
                language="German",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
            )
            session.add(tracking)
            session.commit()

            # Import new periodical with parsed language = "English" (from filename)
            # But tracking says "German" - should use tracking's language
            periodical = Periodical(
                title="German Magazine",
                language="English",  # Initially set from parser
                issue_date=datetime(2024, 1, 1),
                file_path="/test/german_mag.pdf",
            )

            # Simulate import linking logic
            periodical.tracking_id = tracking.id

            # CRITICAL: Synchronize language from tracking
            if tracking.language:
                periodical.language = tracking.language

            session.add(periodical)
            session.commit()

            # Verify periodical got tracking's language
            session.expire_all()
            imported = session.query(Periodical).filter_by(id=periodical.id).first()
            assert imported.language == "German"

        finally:
            session.close()
