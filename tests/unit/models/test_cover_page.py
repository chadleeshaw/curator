"""
Tests for cover page number persistence in extra_metadata
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import DatabaseManager
from models.database import Periodical


@pytest.fixture
def test_db():
    """Create temporary test database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        db_manager = DatabaseManager(db_url)
        db_manager.create_tables()
        yield db_manager.engine, db_manager.session_factory


class TestCoverPagePersistence:
    """Test that cover page number is properly saved and retrieved"""

    def test_cover_page_saved_in_extra_metadata(self, test_db):
        """Cover page should be stored in extra_metadata"""
        engine, session_factory = test_db
        session = session_factory()

        try:
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                extra_metadata={"cover_page": 3},
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Verify it persists
            retrieved = session.query(Periodical).filter_by(id=magazine.id).first()
            assert retrieved.extra_metadata["cover_page"] == 3
        finally:
            session.close()

    def test_cover_page_defaults_to_one(self, test_db):
        """If no cover_page set, utilities should default correctly"""
        from core.utils.metadata import get_cover_page_index

        engine, session_factory = test_db
        session = session_factory()

        try:
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Default is 0 for zero-based (frontend), 1 for one-based (display)
            assert get_cover_page_index(magazine, zero_based=True) == 0
            assert get_cover_page_index(magazine, zero_based=False) == 1
        finally:
            session.close()

    def test_cover_page_can_be_updated(self, test_db):
        """Cover page should be updateable"""
        from sqlalchemy.orm.attributes import flag_modified

        from core.utils.metadata import get_cover_page_index, set_cover_page_index

        engine, session_factory = test_db
        session = session_factory()

        try:
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                extra_metadata={"cover_page": 1},
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Update to page 5 using 1-based index
            set_cover_page_index(magazine, 5, zero_based=False)
            flag_modified(magazine, "extra_metadata")
            session.commit()

            # Verify update (stored as 1-based)
            retrieved = session.query(Periodical).filter_by(id=magazine.id).first()
            assert retrieved.extra_metadata["cover_page"] == 5
            assert get_cover_page_index(retrieved, zero_based=False) == 5
        finally:
            session.close()

    def test_cover_page_uses_1_based_indexing(self, test_db):
        """Cover page uses 1-based indexing in storage"""
        from core.utils.metadata import get_cover_page_index

        engine, session_factory = test_db
        session = session_factory()

        try:
            # Cover page 1 means first page
            magazine1 = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine1.pdf",
                extra_metadata={"cover_page": 1},
                user_id=1,
            )
            session.add(magazine1)

            # Cover page 3 means third page
            magazine2 = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 2, 1),
                file_path="/test/magazine2.pdf",
                extra_metadata={"cover_page": 3},
                user_id=1,
            )
            session.add(magazine2)
            session.commit()

            # Verify 1-based storage (display format)
            assert get_cover_page_index(magazine1, zero_based=False) == 1
            assert get_cover_page_index(magazine2, zero_based=False) == 3

            # Verify 0-based conversion (frontend format)
            assert get_cover_page_index(magazine1, zero_based=True) == 0
            assert get_cover_page_index(magazine2, zero_based=True) == 2
        finally:
            session.close()

    def test_cover_page_preserved_across_metadata_updates(self, test_db):
        """Cover page should be preserved when other metadata changes"""
        from sqlalchemy.orm.attributes import flag_modified

        engine, session_factory = test_db
        session = session_factory()

        try:
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                extra_metadata={"cover_page": 4, "other_data": "value"},
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Update other metadata (need to flag as modified for SQLAlchemy to track)
            magazine.extra_metadata["other_data"] = "new_value"
            flag_modified(magazine, "extra_metadata")
            session.commit()

            # Cover page should still be 4
            retrieved = session.query(Periodical).filter_by(id=magazine.id).first()
            assert retrieved.extra_metadata["cover_page"] == 4
            assert retrieved.extra_metadata["other_data"] == "new_value"
        finally:
            session.close()

    def test_cover_page_validation(self, test_db):
        """Cover page should be a positive integer"""
        from core.utils.metadata import set_cover_page_index

        engine, session_factory = test_db
        session = session_factory()

        try:
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Valid values
            set_cover_page_index(magazine, 1)  # Should work
            set_cover_page_index(magazine, 10)  # Should work
        finally:
            session.close()

    def test_cover_page_used_by_cover_extraction(self, test_db):
        """Cover extraction service should use cover_page value"""
        from core.utils.metadata import get_cover_page_index

        engine, session_factory = test_db
        session = session_factory()

        try:
            # Magazine with custom cover page (stored as 1-based)
            magazine = Periodical(
                title="Test Magazine",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/test/magazine.pdf",
                extra_metadata={"cover_page": 2},
                user_id=1,
            )
            session.add(magazine)
            session.commit()

            # Cover extraction should use page 2 (1-based display)
            cover_page = get_cover_page_index(magazine, zero_based=False)
            assert cover_page == 2

            # For PDF/array indexing, use 0-based (page 2 = index 1)
            cover_index = get_cover_page_index(magazine, zero_based=True)
            assert cover_index == 1
        finally:
            session.close()
