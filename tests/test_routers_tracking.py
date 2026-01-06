"""
Test suite for tracking router endpoints
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import Base, MagazineTracking


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory


class TestTrackingCreation:
    """Test creating and managing tracking records"""

    def test_create_tracking_record(self, test_db):
        """Test creating a new tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL12345W",
            title="National Geographic",
            publisher="National Geographic Society",
            issn="0027-9358",
            first_publish_year=1888,
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add(tracking)
        session.commit()

        # Verify created
        retrieved = session.query(MagazineTracking).filter_by(olid="OL12345W").first()
        assert retrieved is not None
        assert retrieved.title == "National Geographic"
        assert retrieved.track_all_editions is True
        assert retrieved.issn == "0027-9358"

        session.close()

    def test_tracking_defaults(self, test_db):
        """Test default values for tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL99999W",
            title="Test Magazine",
        )
        session.add(tracking)
        session.commit()

        # Verify defaults
        assert tracking.track_all_editions is False
        assert tracking.track_new_only is False
        assert tracking.selected_editions == {}
        assert tracking.selected_years == []
        assert tracking.total_editions_known == 0

        session.close()


class TestTrackingUpdates:
    """Test updating tracking preferences"""

    def test_update_tracking_preferences(self, test_db):
        """Test updating tracking preferences"""
        engine, session_factory = test_db
        session = session_factory()

        # Create initial tracking
        tracking = MagazineTracking(
            olid="OL12345W",
            title="Wired Magazine",
            track_all_editions=False,
        )
        session.add(tracking)
        session.commit()

        # Update preferences
        tracking.track_all_editions = True
        tracking.selected_years = [2020, 2021, 2022]
        tracking.last_metadata_update = datetime.now(UTC)
        session.commit()

        # Verify updates
        session.refresh(tracking)
        assert tracking.track_all_editions is True
        assert len(tracking.selected_years) == 3
        assert 2020 in tracking.selected_years

        session.close()

    def test_update_specific_editions(self, test_db):
        """Test selecting specific editions"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL12345W",
            title="Time Magazine",
            selected_editions={
                "OL111M": True,
                "OL222M": True,
                "OL333M": False,
            },
        )
        session.add(tracking)
        session.commit()

        # Verify edition selections
        assert len(tracking.selected_editions) == 3
        assert tracking.selected_editions["OL111M"] is True
        assert tracking.selected_editions["OL333M"] is False

        session.close()


class TestTrackingQueries:
    """Test querying tracking records"""

    def test_find_by_olid(self, test_db):
        """Test finding tracking by Open Library ID"""
        engine, session_factory = test_db
        session = session_factory()

        # Create multiple tracking records
        tracking1 = MagazineTracking(olid="OL11111W", title="Magazine A")
        tracking2 = MagazineTracking(olid="OL22222W", title="Magazine B")
        session.add_all([tracking1, tracking2])
        session.commit()

        # Find specific tracking
        found = session.query(MagazineTracking).filter_by(olid="OL11111W").first()
        assert found is not None
        assert found.title == "Magazine A"

        session.close()

    def test_find_tracking_all_editions(self, test_db):
        """Test finding all periodicals tracking all editions"""
        engine, session_factory = test_db
        session = session_factory()

        # Create mix of tracking records
        track_all1 = MagazineTracking(
            olid="OL11111W",
            title="Magazine A",
            track_all_editions=True,
        )
        track_selective = MagazineTracking(
            olid="OL22222W",
            title="Magazine B",
            track_all_editions=False,
        )
        track_all2 = MagazineTracking(
            olid="OL33333W",
            title="Magazine C",
            track_all_editions=True,
        )
        session.add_all([track_all1, track_selective, track_all2])
        session.commit()

        # Query for track_all_editions
        tracking_all = (
            session.query(MagazineTracking).filter_by(track_all_editions=True).all()
        )
        assert len(tracking_all) == 2
        assert all(t.track_all_editions for t in tracking_all)

        session.close()

    def test_find_by_year(self, test_db):
        """Test finding tracking records by selected years"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL12345W",
            title="Vintage Magazine",
            selected_years=[2020, 2021, 2022],
        )
        session.add(tracking)
        session.commit()

        # Find by year (requires JSON field query in real app)
        found = session.query(MagazineTracking).filter_by(olid="OL12345W").first()
        assert 2021 in found.selected_years

        session.close()


class TestTrackingDeletion:
    """Test deleting tracking records"""

    def test_delete_tracking(self, test_db):
        """Test deleting a tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL12345W",
            title="Temporary Magazine",
        )
        session.add(tracking)
        session.commit()
        tracking_id = tracking.id

        # Delete
        session.delete(tracking)
        session.commit()

        # Verify deleted
        found = session.query(MagazineTracking).filter_by(id=tracking_id).first()
        assert found is None

        session.close()


class TestTrackingMetadata:
    """Test metadata storage in tracking records"""

    def test_store_periodical_metadata(self, test_db):
        """Test storing periodical metadata"""
        engine, session_factory = test_db
        session = session_factory()

        metadata = {
            "description": "American news magazine",
            "covers": ["https://example.com/cover1.jpg"],
            "language": "eng",
            "subjects": ["News", "Politics", "Culture"],
        }

        tracking = MagazineTracking(
            olid="OL12345W",
            title="Time Magazine",
            periodical_metadata=metadata,
        )
        session.add(tracking)
        session.commit()

        # Verify metadata stored correctly
        session.refresh(tracking)
        assert tracking.periodical_metadata["description"] == "American news magazine"
        assert len(tracking.periodical_metadata["subjects"]) == 3

        session.close()

    def test_update_metadata_timestamp(self, test_db):
        """Test updating metadata timestamp"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = MagazineTracking(
            olid="OL12345W",
            title="Test Magazine",
            last_metadata_update=None,
        )
        session.add(tracking)
        session.commit()

        # Update metadata and timestamp
        tracking.periodical_metadata = {"test": "data"}
        tracking.last_metadata_update = datetime.now(UTC)
        session.commit()

        # Verify timestamp updated
        session.refresh(tracking)
        assert tracking.last_metadata_update is not None
        assert tracking.periodical_metadata["test"] == "data"

        session.close()


class TestTrackingUniqueness:
    """Test uniqueness constraints"""

    def test_olid_uniqueness(self, test_db):
        """Test that OLID must be unique"""
        engine, session_factory = test_db
        session = session_factory()

        tracking1 = MagazineTracking(
            olid="OL12345W",
            title="Magazine 1",
        )
        session.add(tracking1)
        session.commit()

        # Try to add another with same OLID
        tracking2 = MagazineTracking(
            olid="OL12345W",  # Same OLID
            title="Magazine 2",
        )
        session.add(tracking2)

        with pytest.raises(Exception):  # Should raise integrity error
            session.commit()

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
