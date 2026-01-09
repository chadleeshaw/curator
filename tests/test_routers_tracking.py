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
        """Test that OLID can be shared for different language editions"""
        engine, session_factory = test_db
        session = session_factory()

        tracking1 = MagazineTracking(
            olid="OL12345W",
            title="Wired Magazine",
            language="English",
        )
        session.add(tracking1)
        session.commit()

        # Same OLID but different language - should be allowed
        tracking2 = MagazineTracking(
            olid="OL12345W",  # Same OLID
            title="Wired Magazine",
            language="German",
        )
        session.add(tracking2)
        session.commit()  # Should not raise - duplicate OLID with different language is allowed

        # Verify both exist
        all_tracking = session.query(MagazineTracking).filter(
            MagazineTracking.olid == "OL12345W"
        ).all()
        assert len(all_tracking) == 2

        session.close()


class TestTrackingMerge:
    """Test merging tracking records and library items"""

    def test_merge_tracking_updates_magazine_titles(self, test_db):
        """Test that merging tracking records also updates magazine titles for library grouping"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Magazine
        from web.routers.tracking import merge_tracking, set_dependencies

        # Set up dependencies
        set_dependencies(session_factory, None, None)

        # Create two tracking records with different titles
        tracking1 = MagazineTracking(
            olid="OL12345W",
            title="Wired",
            publisher="Condé Nast",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking2 = MagazineTracking(
            olid="OL67890W",
            title="Wired Magazine",
            publisher="Condé Nast",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking1, tracking2])
        session.commit()

        # Create magazines linked to each tracking record
        mag1 = Magazine(
            title="Wired",
            language="English",
            publisher="Condé Nast",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/wired-jan2024.pdf",
            tracking_id=tracking1.id,
        )
        mag2 = Magazine(
            title="Wired Magazine",
            language="English",
            publisher="Condé Nast",
            issue_date=datetime(2024, 2, 1),
            file_path="/test/wired-feb2024.pdf",
            tracking_id=tracking2.id,
        )
        mag3 = Magazine(
            title="Wired Magazine",
            language="English",
            publisher="Condé Nast",
            issue_date=datetime(2024, 3, 1),
            file_path="/test/wired-mar2024.pdf",
            tracking_id=tracking2.id,
        )
        session.add_all([mag1, mag2, mag3])
        session.commit()

        # Verify we have 2 distinct titles before merge
        distinct_titles = session.query(Magazine.title).distinct().all()
        assert len(distinct_titles) == 2
        title_set = {t[0] for t in distinct_titles}
        assert "Wired" in title_set
        assert "Wired Magazine" in title_set

        # Save IDs before merge (tracking2 will be deleted)
        target_id = tracking1.id
        source_id = tracking2.id

        # Merge tracking2 into tracking1 (keep "Wired" as the target)
        import asyncio
        result = asyncio.run(merge_tracking(
            target_id=target_id,
            source_ids={"source_ids": [source_id]}
        ))

        # Verify merge results
        assert result["success"] is True
        assert result["magazines_moved"] == 2
        assert "Wired Magazine" in result["merged_titles"]

        # Refresh session to see updated data
        session.expire_all()

        # Verify all magazines now have the same title
        all_magazines = session.query(Magazine).all()
        assert len(all_magazines) == 3
        for mag in all_magazines:
            assert mag.title == "Wired", f"Magazine title should be 'Wired', got '{mag.title}'"
            assert mag.tracking_id == target_id

        # Verify library grouping would work (only 1 distinct title now)
        distinct_titles_after = session.query(Magazine.title).distinct().all()
        assert len(distinct_titles_after) == 1
        assert distinct_titles_after[0][0] == "Wired"

        # Verify source tracking record was deleted
        deleted_tracking = session.query(MagazineTracking).filter(
            MagazineTracking.id == source_id
        ).first()
        assert deleted_tracking is None

        # Verify target tracking record still exists
        target_tracking = session.query(MagazineTracking).filter(
            MagazineTracking.id == target_id
        ).first()
        assert target_tracking is not None
        assert target_tracking.title == "Wired"

        session.close()

    def test_merge_tracking_with_different_languages(self, test_db):
        """Test that merging preserves language differences while normalizing titles"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Magazine
        from web.routers.tracking import merge_tracking, set_dependencies

        set_dependencies(session_factory, None, None)

        # Create tracking records
        tracking1 = MagazineTracking(
            olid="OL111W",
            title="National Geographic",
            publisher="NatGeo",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking2 = MagazineTracking(
            olid="OL222W",
            title="NatGeo Magazine",
            publisher="NatGeo",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking1, tracking2])
        session.commit()

        # Create magazines in different languages
        mag1_en = Magazine(
            title="National Geographic",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/natgeo-en-jan.pdf",
            tracking_id=tracking1.id,
        )
        mag2_de = Magazine(
            title="NatGeo Magazine",
            language="German",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/natgeo-de-jan.pdf",
            tracking_id=tracking2.id,
        )
        session.add_all([mag1_en, mag2_de])
        session.commit()

        # Save IDs before merge
        target_id = tracking1.id
        source_id = tracking2.id

        # Merge
        import asyncio
        asyncio.run(merge_tracking(
            target_id=target_id,
            source_ids={"source_ids": [source_id]}
        ))

        session.expire_all()

        # Both magazines should have same title but different languages
        all_magazines = session.query(Magazine).all()
        assert len(all_magazines) == 2
        for mag in all_magazines:
            assert mag.title == "National Geographic"

        # Should have 2 groups in library view (by title+language)
        from sqlalchemy import func
        title_lang_groups = session.query(
            Magazine.title,
            Magazine.language
        ).distinct().all()
        assert len(title_lang_groups) == 2

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
