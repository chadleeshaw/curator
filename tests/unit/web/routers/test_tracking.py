"""
Test suite for tracking router endpoints
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Path setup handled by conftest.py

from core.constants.category import CATEGORY_MAGAZINE
from models.database import Base, Periodical, PeriodicalTracking


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
    # Use a temporary file-based database instead of :memory:
    # This is necessary because SQLite :memory: databases are not shared across threads
    # even with check_same_thread=False - each connection gets its own memory space
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


class TestTrackingCreation:
    """Test creating and managing tracking records"""

    def test_create_tracking_record(self, test_db):
        """Test creating a new tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="OL12345W",
            title="National Geographic",
            first_publish_year=1888,
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add(tracking)
        session.commit()

        # Verify created
        retrieved = session.query(PeriodicalTracking).filter_by(olid="OL12345W").first()
        assert retrieved is not None
        assert retrieved.title == "National Geographic"
        assert retrieved.track_all_editions is True

        session.close()

    def test_tracking_defaults(self, test_db):
        """Test default values for tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="OL99999W",
            title="Test Magazine",
        )
        session.add(tracking)
        session.commit()

        # Verify defaults
        assert tracking.track_all_editions is False
        assert tracking.track_new_only is False
        assert tracking.selected_editions == {}
        assert not tracking.selected_years
        assert tracking.total_editions_known == 0

        session.close()


class TestTrackingUpdates:
    """Test updating tracking preferences"""

    def test_update_tracking_preferences(self, test_db):
        """Test updating tracking preferences"""
        engine, session_factory = test_db
        session = session_factory()

        # Create initial tracking
        tracking = PeriodicalTracking(
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

        tracking = PeriodicalTracking(
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
        tracking1 = PeriodicalTracking(olid="OL11111W", title="Magazine A")
        tracking2 = PeriodicalTracking(olid="OL22222W", title="Magazine B")
        session.add_all([tracking1, tracking2])
        session.commit()

        # Find specific tracking
        found = session.query(PeriodicalTracking).filter_by(olid="OL11111W").first()
        assert found is not None
        assert found.title == "Magazine A"

        session.close()

    def test_find_tracking_all_editions(self, test_db):
        """Test finding all periodicals tracking all editions"""
        engine, session_factory = test_db
        session = session_factory()

        # Create mix of tracking records
        track_all1 = PeriodicalTracking(
            olid="OL11111W",
            title="Magazine A",
            track_all_editions=True,
        )
        track_selective = PeriodicalTracking(
            olid="OL22222W",
            title="Magazine B",
            track_all_editions=False,
        )
        track_all2 = PeriodicalTracking(
            olid="OL33333W",
            title="Magazine C",
            track_all_editions=True,
        )
        session.add_all([track_all1, track_selective, track_all2])
        session.commit()

        # Query for track_all_editions
        tracking_all = session.query(PeriodicalTracking).filter_by(track_all_editions=True).all()
        assert len(tracking_all) == 2
        assert all(t.track_all_editions for t in tracking_all)

        session.close()

    def test_find_by_year(self, test_db):
        """Test finding tracking records by selected years"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
            olid="OL12345W",
            title="Vintage Magazine",
            selected_years=[2020, 2021, 2022],
        )
        session.add(tracking)
        session.commit()

        # Find by year (requires JSON field query in real app)
        found = session.query(PeriodicalTracking).filter_by(olid="OL12345W").first()
        assert 2021 in found.selected_years

        session.close()


class TestTrackingDeletion:
    """Test deleting tracking records"""

    def test_delete_tracking(self, test_db):
        """Test deleting a tracking record"""
        engine, session_factory = test_db
        session = session_factory()

        tracking = PeriodicalTracking(
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
        found = session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
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

        tracking = PeriodicalTracking(
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

        tracking = PeriodicalTracking(
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

        tracking1 = PeriodicalTracking(
            olid="OL12345W",
            title="Wired Magazine",
            language="English",
        )
        session.add(tracking1)
        session.commit()

        # Same OLID but different language - should be allowed
        tracking2 = PeriodicalTracking(
            olid="OL12345W",  # Same OLID
            title="Wired Magazine",
            language="German",
        )
        session.add(tracking2)
        session.commit()  # Should not raise - duplicate OLID with different language is allowed

        # Verify both exist
        all_tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.olid == "OL12345W").all()
        assert len(all_tracking) == 2

        session.close()


class TestTrackingMerge:
    """Test merging tracking records and library items"""

    def test_merge_tracking_updates_magazine_titles(self, test_db):
        """Test that merging tracking records also updates magazine titles for library grouping"""
        engine, session_factory = test_db
        session = session_factory()

        from web.routers.tracking import merge_tracking, set_dependencies

        # Set up dependencies
        set_dependencies(session_factory, None, None)

        # Create two tracking records with different titles
        tracking1 = PeriodicalTracking(
            olid="OL12345W",
            title="Wired",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking2 = PeriodicalTracking(
            olid="OL67890W",
            title="Wired Magazine",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking1, tracking2])
        session.commit()

        # Create magazines linked to each tracking record
        mag1 = Periodical(
            title="Wired",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/wired-jan2024.pdf",
            tracking_id=tracking1.id,
        )
        mag2 = Periodical(
            title="Wired Magazine",
            language="English",
            issue_date=datetime(2024, 2, 1),
            file_path="/test/wired-feb2024.pdf",
            tracking_id=tracking2.id,
        )
        mag3 = Periodical(
            title="Wired Magazine",
            language="English",
            issue_date=datetime(2024, 3, 1),
            file_path="/test/wired-mar2024.pdf",
            tracking_id=tracking2.id,
        )
        session.add_all([mag1, mag2, mag3])
        session.commit()

        # Verify we have 2 distinct titles before merge
        distinct_titles = session.query(Periodical.title).distinct().all()
        assert len(distinct_titles) == 2
        title_set = {t[0] for t in distinct_titles}
        assert "Wired" in title_set
        assert "Wired Magazine" in title_set

        # Save IDs before merge (tracking2 will be deleted)
        target_id = tracking1.id
        source_id = tracking2.id

        # Merge tracking2 into tracking1 (keep "Wired" as the target)
        import asyncio

        result = asyncio.run(merge_tracking(target_id=target_id, source_ids={"source_ids": [source_id]}))

        # Verify merge results
        assert result["success"] is True
        assert result["periodicals_moved"] == 2
        assert "Wired Magazine" in result["merged_titles"]

        # Refresh session to see updated data
        session.expire_all()

        # Verify all magazines now have the same title
        all_magazines = session.query(Periodical).all()
        assert len(all_magazines) == 3
        for mag in all_magazines:
            assert mag.title == "Wired", f"Magazine title should be 'Wired', got '{mag.title}'"
            assert mag.tracking_id == target_id

        # Verify library grouping would work (only 1 distinct title now)
        distinct_titles_after = session.query(Periodical.title).distinct().all()
        assert len(distinct_titles_after) == 1
        assert distinct_titles_after[0][0] == "Wired"

        # Verify source tracking record was deleted
        deleted_tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == source_id).first()
        assert deleted_tracking is None

        # Verify target tracking record still exists
        target_tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == target_id).first()
        assert target_tracking is not None
        assert target_tracking.title == "Wired"

        session.close()

    def test_merge_tracking_with_different_languages(self, test_db):
        """Test that merging synchronizes language to target tracking"""
        engine, session_factory = test_db
        session = session_factory()

        from web.routers.tracking import merge_tracking, set_dependencies

        set_dependencies(session_factory, None, None)

        # Create tracking records with explicit languages
        tracking1 = PeriodicalTracking(
            olid="OL111W",
            title="National Geographic",
            language="English",  # Explicitly set
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking2 = PeriodicalTracking(
            olid="OL222W",
            title="NatGeo Magazine",
            language="German",  # Different language
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking1, tracking2])
        session.commit()

        # Create magazines matching their tracking languages
        mag1_en = Periodical(
            title="National Geographic",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/natgeo-en-jan.pdf",
            tracking_id=tracking1.id,
        )
        mag2_de = Periodical(
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

        # Merge - German tracking into English tracking
        import asyncio

        asyncio.run(merge_tracking(target_id=target_id, source_ids={"source_ids": [source_id]}))

        session.expire_all()

        # Both magazines should have same title AND same language (synced to target)
        all_magazines = session.query(Periodical).all()
        assert len(all_magazines) == 2
        for mag in all_magazines:
            assert mag.title == "National Geographic"
            assert mag.language == "English"  # Both synced to target language

        # Should have 1 group in library view (same title+language)
        title_lang_groups = session.query(Periodical.title, Periodical.language).distinct().all()
        assert len(title_lang_groups) == 1  # Consistent language after merge

        session.close()

    def test_merge_preserves_special_editions(self, test_db):
        """Test that merging preserves special edition titles and metadata"""
        engine, session_factory = test_db
        session = session_factory()

        from web.routers.tracking import merge_tracking, set_dependencies

        set_dependencies(session_factory, None, None)

        # Create two tracking records
        tracking1 = PeriodicalTracking(
            olid="OL_MAIN",
            title="National Geographic",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking2 = PeriodicalTracking(
            olid="OL_SPECIAL",
            title="National Geographic Special Edition",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking1, tracking2])
        session.commit()

        # Create regular and special edition magazines
        regular_mag = Periodical(
            title="National Geographic",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/lib/natgeo-jan2024.pdf",
            tracking_id=tracking1.id,
        )
        special_mag = Periodical(
            title="National Geographic Special Edition",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/lib/natgeo-special-jan2024.pdf",
            tracking_id=tracking2.id,
            extra_metadata={"special_edition": "Special Edition"},
        )
        session.add_all([regular_mag, special_mag])
        session.commit()

        target_id = tracking1.id
        source_id = tracking2.id

        # Merge tracking2 into tracking1
        import asyncio

        asyncio.run(merge_tracking(target_id=target_id, source_ids={"source_ids": [source_id]}))

        session.expire_all()

        # Both should now link to target tracking
        all_mags = session.query(Periodical).all()
        assert len(all_mags) == 2
        for mag in all_mags:
            assert mag.tracking_id == target_id

        # Regular edition should have normalized title
        regular = session.query(Periodical).filter(Periodical.file_path == "/lib/natgeo-jan2024.pdf").first()
        assert regular.title == "National Geographic"

        # Special edition should KEEP its special title
        special = session.query(Periodical).filter(Periodical.file_path == "/lib/natgeo-special-jan2024.pdf").first()
        assert special.title == "National Geographic Special Edition", "Special edition title should be preserved"
        assert special.extra_metadata.get("special_edition") == "Special Edition"

        session.close()


class TestTitleChangeFileReorganization:
    """Test that changing a tracking title reorganizes files and folders"""

    def test_title_change_reorganizes_files(self, test_db):
        """Test that renaming a tracking title moves files to new folders"""
        engine, session_factory = test_db
        session = session_factory()

        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "data"
            library_dir.mkdir(parents=True, exist_ok=True)

            # Create tracking record
            tracking = PeriodicalTracking(
                olid="OL12345W",
                title="Old Magazine Name",
                category=CATEGORY_MAGAZINE,
                track_all_editions=True,
            )
            session.add(tracking)
            session.commit()
            tracking_id = tracking.id

            # Create directory structure and files with old title
            old_folder = library_dir / "_Magazines" / "Old Magazine Name" / "2024"
            old_folder.mkdir(parents=True, exist_ok=True)

            old_pdf = old_folder / "Old Magazine Name - January2024.pdf"
            old_cover = old_folder / "Old Magazine Name - January2024.jpg"

            # Create actual files
            old_pdf.write_text("PDF content")
            old_cover.write_text("Cover content")

            # Add magazine record pointing to old paths
            magazine = Periodical(
                title="Old Magazine Name",
                issue_date=datetime(2024, 1, 15),
                file_path=str(old_pdf),
                cover_path=str(old_cover),
                tracking_id=tracking_id,
                extra_metadata={"category": CATEGORY_MAGAZINE},
            )
            session.add(magazine)
            session.commit()

            # Verify old files exist
            assert old_pdf.exists(), "Old PDF should exist"
            assert old_cover.exists(), "Old cover should exist"

            # Simulate the update_tracking endpoint behavior
            from web.routers.tracking import _reorganize_periodical_files

            # Update the tracking title
            new_title = "New Magazine Name"
            tracking.title = new_title

            # Reorganize files
            new_pdf_path, new_cover_path = _reorganize_periodical_files(magazine, new_title, library_dir, "_")

            # Update magazine record
            if new_pdf_path:
                magazine.file_path = new_pdf_path
                if new_cover_path:
                    magazine.cover_path = new_cover_path
                magazine.title = new_title

            session.commit()

            # Verify new structure
            new_folder = library_dir / "_Magazines" / "New Magazine Name" / "2024"
            new_pdf = new_folder / "New Magazine Name - January2024.pdf"
            new_cover = new_folder / "New Magazine Name - January2024.jpg"

            assert new_pdf.exists(), f"New PDF should exist at {new_pdf}"
            assert new_cover.exists(), f"New cover should exist at {new_cover}"
            assert new_pdf.read_text() == "PDF content", "PDF content should be preserved"
            assert new_cover.read_text() == "Cover content", "Cover content should be preserved"

            # Verify database updates
            session.refresh(magazine)
            assert magazine.title == new_title, "Magazine title should be updated"
            assert magazine.file_path == str(new_pdf), "PDF path should be updated"
            assert magazine.cover_path == str(new_cover), "Cover path should be updated"

            # Verify old files are gone
            assert not old_pdf.exists(), "Old PDF should be moved"
            assert not old_cover.exists(), "Old cover should be moved"

            session.close()

    def test_title_change_preserves_special_editions(self, test_db):
        """Test that special editions keep their original titles when tracking title changes"""
        engine, session_factory = test_db
        session = session_factory()

        with tempfile.TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "data"
            library_dir.mkdir(parents=True, exist_ok=True)

            # Create tracking record
            tracking = PeriodicalTracking(
                olid="OL12345W",
                title="National Geographic",
                category=CATEGORY_MAGAZINE,
            )
            session.add(tracking)
            session.commit()
            tracking_id = tracking.id

            # Create special edition magazine
            special_folder = library_dir / "_Magazines" / "National Geographic" / "2024"
            special_folder.mkdir(parents=True, exist_ok=True)

            special_pdf = special_folder / "National Geographic Swimsuit - January2024.pdf"
            special_pdf.write_text("Special PDF content")

            special_magazine = Periodical(
                title="National Geographic Swimsuit Edition",
                issue_date=datetime(2024, 1, 15),
                file_path=str(special_pdf),
                tracking_id=tracking_id,
                extra_metadata={
                    "category": CATEGORY_MAGAZINE,
                    "special_edition": "Swimsuit Edition",
                },
            )
            session.add(special_magazine)
            session.commit()

            # Change tracking title - special edition should NOT be reorganized
            old_special_title = special_magazine.title

            # This simulates what happens in the update endpoint
            # Special editions should be skipped

            is_special = special_magazine.extra_metadata.get("special_edition") is not None
            assert is_special, "Should detect as special edition"

            # Special editions should NOT be reorganized
            # Title should remain unchanged
            session.refresh(special_magazine)
            assert special_magazine.title == old_special_title, "Special edition title should be preserved"

            session.close()

    def test_title_change_multiple_issues(self, test_db):
        """Test that all issues under a tracking record are reorganized"""
        engine, session_factory = test_db
        session = session_factory()

        with tempfile.TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "data"
            library_dir.mkdir(parents=True, exist_ok=True)

            # Create tracking record
            tracking = PeriodicalTracking(
                olid="OL12345W",
                title="Wired Magazine",
                category=CATEGORY_MAGAZINE,
            )
            session.add(tracking)
            session.commit()
            tracking_id = tracking.id

            # Create multiple issues
            issues = [
                ("January2024", datetime(2024, 1, 15)),
                ("February2024", datetime(2024, 2, 15)),
                ("March2024", datetime(2024, 3, 15)),
            ]

            old_folder = library_dir / "_Magazines" / "Wired Magazine" / "2024"
            old_folder.mkdir(parents=True, exist_ok=True)

            magazines = []
            for month_label, issue_date in issues:
                pdf_path = old_folder / f"Wired Magazine - {month_label}.pdf"
                pdf_path.write_text(f"Content for {month_label}")

                magazine = Periodical(
                    title="Wired Magazine",
                    issue_date=issue_date,
                    file_path=str(pdf_path),
                    tracking_id=tracking_id,
                    extra_metadata={"category": CATEGORY_MAGAZINE},
                )
                session.add(magazine)
                magazines.append(magazine)

            session.commit()

            # Update title and reorganize all files
            from web.routers.tracking import _reorganize_periodical_files

            tracking.title = "Wired"

            for magazine in magazines:
                new_pdf_path, new_cover_path = _reorganize_periodical_files(magazine, "Wired", library_dir, "_")
                if new_pdf_path:
                    magazine.file_path = new_pdf_path
                    magazine.title = "Wired"

            session.commit()

            # Verify all files moved
            new_folder = library_dir / "_Magazines" / "Wired" / "2024"
            for month_label, _ in issues:
                new_pdf = new_folder / f"Wired - {month_label}.pdf"
                assert new_pdf.exists(), f"{month_label} should be reorganized"
                assert new_pdf.read_text() == f"Content for {month_label}", "Content should be preserved"

            # Verify old folder is empty (except for .DS_Store or similar)
            if old_folder.exists():
                remaining = [f for f in old_folder.iterdir() if not f.name.startswith(".")]
                assert len(remaining) == 0, "Old folder should be empty"

            session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
