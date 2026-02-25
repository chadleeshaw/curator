"""
Integration test for tracking merge functionality with library view grouping
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Path setup handled by conftest.py

from core.constants.category import CATEGORY_MAGAZINE
from models.database import Base, Periodical, PeriodicalTracking
from web.routers.tracking import merge_tracking, set_dependencies


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


class TestTrackingMergeIntegration:
    """Integration test demonstrating full merge workflow"""

    def test_merge_consolidates_library_view(self, test_db):
        """
        End-to-end test: User has magazines with variant titles.
        After merging tracking records, library view should group them together.
        """
        engine, session_factory = test_db
        session = session_factory()

        # Set up dependencies
        set_dependencies(session_factory, None, None)

        # Scenario: User downloaded magazines with different title variations
        # These could come from different providers or filename variations
        tracking_wired = PeriodicalTracking(
            olid="OL123W",
            title="Wired",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        tracking_wired_mag = PeriodicalTracking(
            olid="OL456W",
            title="Wired Magazine",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        tracking_wired_uk = PeriodicalTracking(
            olid="OL789W",
            title="Wired UK",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        session.add_all([tracking_wired, tracking_wired_mag, tracking_wired_uk])
        session.commit()

        # Create magazines from different sources/imports
        magazines = [
            Periodical(
                title="Wired",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/library/wired-jan2024.pdf",
                tracking_id=tracking_wired.id,
                user_id=1,
            ),
            Periodical(
                title="Wired",
                language="English",
                issue_date=datetime(2024, 2, 1),
                file_path="/library/wired-feb2024.pdf",
                tracking_id=tracking_wired.id,
                user_id=1,
            ),
            Periodical(
                title="Wired Magazine",
                language="English",
                issue_date=datetime(2024, 3, 1),
                file_path="/library/wired-magazine-mar2024.pdf",
                tracking_id=tracking_wired_mag.id,
                user_id=1,
            ),
            Periodical(
                title="Wired Magazine",
                language="English",
                issue_date=datetime(2024, 4, 1),
                file_path="/library/wired-magazine-apr2024.pdf",
                tracking_id=tracking_wired_mag.id,
                user_id=1,
            ),
            Periodical(
                title="Wired UK",
                language="English",
                issue_date=datetime(2024, 5, 1),
                file_path="/library/wired-uk-may2024.pdf",
                tracking_id=tracking_wired_uk.id,
                user_id=1,
            ),
        ]
        session.add_all(magazines)
        session.commit()

        # BEFORE MERGE: Library view shows 3 separate periodical groups
        # This simulates /api/periodicals endpoint query
        subquery = (
            session.query(
                Periodical.title,
                Periodical.language,
                func.max(Periodical.issue_date).label("max_date"),
            )
            .group_by(Periodical.title, Periodical.language)
            .subquery()
        )

        library_groups_before = (
            session.query(Periodical)
            .join(
                subquery,
                (Periodical.title == subquery.c.title)
                & (Periodical.language == subquery.c.language)
                & (Periodical.issue_date == subquery.c.max_date),
            )
            .all()
        )

        assert len(library_groups_before) == 3, "Should show 3 separate groups before merge"
        library_titles_before = {mag.title for mag in library_groups_before}
        assert library_titles_before == {"Wired", "Wired Magazine", "Wired UK"}

        # USER ACTION: Merge the tracking records
        # Keep "Wired" as canonical title, merge others into it
        import asyncio

        result = asyncio.run(
            merge_tracking(
                target_id=tracking_wired.id,
                source_ids={"source_ids": [tracking_wired_mag.id, tracking_wired_uk.id]},
            )
        )

        assert result["success"] is True
        assert result["periodicals_moved"] == 3  # 2 from Wired Magazine + 1 from Wired UK
        assert len(result["merged_titles"]) == 2

        # Refresh session
        session.expire_all()

        # AFTER MERGE: Library view shows 1 consolidated group
        library_groups_after = (
            session.query(Periodical)
            .join(
                subquery,
                (Periodical.title == subquery.c.title)
                & (Periodical.language == subquery.c.language)
                & (Periodical.issue_date == subquery.c.max_date),
            )
            .all()
        )

        assert len(library_groups_after) == 1, "Should show 1 consolidated group after merge"
        assert library_groups_after[0].title == "Wired"

        # Verify all magazines are grouped together
        all_mags = session.query(Periodical).order_by(Periodical.issue_date).all()
        assert len(all_mags) == 5
        for mag in all_mags:
            assert mag.title == "Wired", "All magazines should have normalized title"
            assert mag.tracking_id == tracking_wired.id, "All should link to target tracking"

        # Verify issue count for the group
        wired_count = (
            session.query(Periodical).filter(Periodical.title == "Wired", Periodical.language == "English").count()
        )
        assert wired_count == 5, "Should have all 5 issues under one title"

        session.close()

    def test_merge_preserves_language_separation(self, test_db):
        """
        Merging should normalize titles but preserve language-based grouping
        """
        engine, session_factory = test_db
        session = session_factory()

        set_dependencies(session_factory, None, None)

        # Create tracking for different language editions
        tracking_en = PeriodicalTracking(
            olid="OL_EN",
            title="Le Monde Diplomatique",
            language="English",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        tracking_fr = PeriodicalTracking(
            olid="OL_FR",
            title="Monde Diplomatique",
            language="French",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        session.add_all([tracking_en, tracking_fr])
        session.commit()

        # Add magazines in each language
        magazines = [
            Periodical(
                title="Le Monde Diplomatique",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/lib/monde-en-jan.pdf",
                tracking_id=tracking_en.id,
                user_id=1,
            ),
            Periodical(
                title="Monde Diplomatique",
                language="French",
                issue_date=datetime(2024, 1, 1),
                file_path="/lib/monde-fr-jan.pdf",
                tracking_id=tracking_fr.id,
                user_id=1,
            ),
        ]
        session.add_all(magazines)
        session.commit()

        # Merge tracking records
        import asyncio

        asyncio.run(merge_tracking(target_id=tracking_en.id, source_ids={"source_ids": [tracking_fr.id]}))

        session.expire_all()

        # Both should have same title now
        all_mags = session.query(Periodical).all()
        for mag in all_mags:
            assert mag.title == "Le Monde Diplomatique"

        # But library should still show 2 groups (different languages)
        language_groups = session.query(Periodical.title, Periodical.language).distinct().all()

        assert len(language_groups) == 2, "Should maintain language-based grouping"
        languages = {group[1] for group in language_groups}
        assert languages == {"English", "French"}

        session.close()

    def test_merge_reorganizes_files_on_disk(self, test_db):
        """
        Test that merging tracking records actually moves files on disk
        and updates database paths accordingly.
        """
        engine, session_factory = test_db
        session = session_factory()

        set_dependencies(session_factory, None, None)

        # Create temporary directory structure for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create source folder structures
            wired_dir = tmpdir_path / "_Magazines" / "Wired" / "2024"
            wired_mag_dir = tmpdir_path / "_Magazines" / "Wired Magazine" / "2024"
            wired_dir.mkdir(parents=True, exist_ok=True)
            wired_mag_dir.mkdir(parents=True, exist_ok=True)

            # Create actual test files
            wired_jan_pdf = wired_dir / "Wired - January2024.pdf"
            wired_jan_jpg = wired_dir / "Wired - January2024.jpg"
            wired_mag_feb_pdf = wired_mag_dir / "Wired Magazine - February2024.pdf"
            wired_mag_feb_jpg = wired_mag_dir / "Wired Magazine - February2024.jpg"

            wired_jan_pdf.write_text("fake pdf content 1")
            wired_jan_jpg.write_text("fake jpg content 1")
            wired_mag_feb_pdf.write_text("fake pdf content 2")
            wired_mag_feb_jpg.write_text("fake jpg content 2")

            # Create tracking records
            tracking_wired = PeriodicalTracking(
                olid="OL123W",
                title="Wired",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
                user_id=1,
            )
            tracking_wired_mag = PeriodicalTracking(
                olid="OL456W",
                title="Wired Magazine",
                track_all_editions=True,
                last_metadata_update=datetime.now(UTC),
                user_id=1,
            )
            session.add_all([tracking_wired, tracking_wired_mag])
            session.commit()

            # Create magazine records with proper metadata
            mag1 = Periodical(
                title="Wired",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path=str(wired_jan_pdf),
                cover_path=str(wired_jan_jpg),
                tracking_id=tracking_wired.id,
                extra_metadata={"category": CATEGORY_MAGAZINE},
                user_id=1,
            )
            mag2 = Periodical(
                title="Wired Magazine",
                language="English",
                issue_date=datetime(2024, 2, 1),
                file_path=str(wired_mag_feb_pdf),
                cover_path=str(wired_mag_feb_jpg),
                tracking_id=tracking_wired_mag.id,
                extra_metadata={"category": CATEGORY_MAGAZINE},
                user_id=1,
            )
            session.add_all([mag1, mag2])
            session.commit()

            # Verify files exist in source locations
            assert wired_jan_pdf.exists()
            assert wired_mag_feb_pdf.exists()
            assert wired_mag_feb_jpg.exists()

            # Mock the library_base_dir to use our temp directory
            import web.routers.tracking as tracking_module

            async def patched_merge(target_id, source_ids):
                # Temporarily patch the library_base_dir
                db_session = session_factory()
                try:
                    from models.database import Periodical as Mag

                    # Get target tracking record
                    target = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == target_id).first()
                    sources = (
                        db_session.query(PeriodicalTracking)
                        .filter(PeriodicalTracking.id.in_(source_ids["source_ids"]))
                        .all()
                    )

                    periodicals_moved = 0
                    files_reorganized = 0
                    directories_to_cleanup = set()
                    library_base_dir = tmpdir_path  # Use temp dir
                    category_prefix = "_"

                    # Import helper functions
                    from web.routers.tracking import _reorganize_periodical_files
                    from core.utils.general import cleanup_empty_directories

                    for source in sources:
                        periodicals = db_session.query(Mag).filter(Mag.tracking_id == source.id).all()
                        for periodical in periodicals:
                            periodical.tracking_id = target.id

                            # Store old title directory for cleanup (parent of year directory)
                            old_pdf_path = Path(periodical.file_path)
                            if old_pdf_path.exists():
                                # Add title directory (grandparent of PDF) not just year directory
                                # Structure: title_dir/year/periodical.pdf
                                title_dir = old_pdf_path.parent.parent
                                directories_to_cleanup.add(title_dir)

                            # Reorganize files
                            new_pdf_path, new_cover_path = _reorganize_periodical_files(
                                periodical,
                                target.title,
                                library_base_dir,
                                category_prefix,
                            )

                            if new_pdf_path:
                                periodical.file_path = new_pdf_path
                                if new_cover_path:
                                    periodical.cover_path = new_cover_path
                                files_reorganized += 1

                            periodical.title = target.title
                            periodicals_moved += 1

                        db_session.delete(source)

                    db_session.commit()

                    # Clean up empty directories
                    for directory in directories_to_cleanup:
                        if directory.exists():
                            cleanup_empty_directories(directory, library_base_dir)

                    return {
                        "success": True,
                        "periodicals_moved": periodicals_moved,
                        "files_reorganized": files_reorganized,
                        "merged_titles": [s.title for s in sources],
                    }
                finally:
                    db_session.close()

            # Perform merge
            import asyncio

            result = asyncio.run(
                patched_merge(
                    target_id=tracking_wired.id,
                    source_ids={"source_ids": [tracking_wired_mag.id]},
                )
            )

            session.expire_all()

            # Verify merge succeeded
            assert result["success"] is True
            assert result["files_reorganized"] == 1

            # Verify files were moved to new location (without language folder)
            expected_new_pdf = tmpdir_path / "_Magazines" / "Wired" / "2024" / "Wired - February2024.pdf"
            expected_new_jpg = tmpdir_path / "_Magazines" / "Wired" / "2024" / "Wired - February2024.jpg"

            assert expected_new_pdf.exists(), f"File should exist at {expected_new_pdf}"
            assert expected_new_jpg.exists(), f"Cover should exist at {expected_new_jpg}"

            # Verify old files no longer exist
            assert not wired_mag_feb_pdf.exists(), "Old PDF should be moved"
            assert not wired_mag_feb_jpg.exists(), "Old cover should be moved"

            # Verify database paths were updated
            mag2_updated = session.query(Periodical).filter(Periodical.id == mag2.id).first()
            assert mag2_updated.file_path == str(expected_new_pdf)
            assert mag2_updated.cover_path == str(expected_new_jpg)
            assert mag2_updated.title == "Wired"

            # Verify empty source directory was cleaned up
            assert not wired_mag_dir.exists(), "Empty source directory should be removed"

            session.close()

    def test_merge_handles_duplicate_filenames(self, test_db):
        """
        Test that merging handles duplicate filenames by renaming with (2), (3), etc.
        This prevents UNIQUE constraint errors on file_path.
        """
        engine, session_factory = test_db
        session = session_factory()

        # Use default configuration (not a temp directory)
        set_dependencies(session_factory, None, None)

        # Create tracking records
        tracking_a = PeriodicalTracking(
            olid="OL123A",
            title="Magazine",
            category=CATEGORY_MAGAZINE,
            language="en",
            country="us",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        tracking_b = PeriodicalTracking(
            olid="OL456B",
            title="Magazine B",
            category=CATEGORY_MAGAZINE,
            language="en",
            country="us",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
            user_id=1,
        )
        session.add_all([tracking_a, tracking_b])
        session.commit()

        # Create multiple periodicals with tracking_b that will all organize to same filename
        # when merged into tracking_a
        issue_date = datetime(2024, 2, 1, tzinfo=UTC)

        # Create directory structure and files in the real library
        library_base_dir = Path("local/data")
        mag_dir_b = library_base_dir / "_Magazines" / "Magazine B" / "2024"
        mag_dir_b.mkdir(parents=True, exist_ok=True)

        created_files = []
        periodicals = []
        for i in range(1, 4):  # Create 3 duplicates
            pdf_path = mag_dir_b / f"Magazine B - February2024 ({i}).pdf"
            jpg_path = mag_dir_b / f"Magazine B - February2024 ({i}).jpg"

            # Create dummy files
            pdf_path.write_text(f"PDF content {i}")
            jpg_path.write_text(f"JPG content {i}")
            created_files.extend([pdf_path, jpg_path])

            mag = Periodical(
                title="Magazine B",
                file_path=str(pdf_path),
                cover_path=str(jpg_path),
                issue_date=issue_date,
                tracking_id=tracking_b.id,
                category=CATEGORY_MAGAZINE,
                language="en",
                user_id=1,
            )
            periodicals.append(mag)
            session.add(mag)

        session.commit()

        try:
            # Merge tracking_b into tracking_a
            import asyncio

            result = asyncio.run(merge_tracking(target_id=tracking_a.id, source_ids={"source_ids": [tracking_b.id]}))

            # Verify merge succeeded (no UNIQUE constraint error!)
            assert result["success"] is True
            assert result["periodicals_moved"] == 3
            assert result["files_reorganized"] == 3

            # Verify all periodicals still exist in database
            remaining = session.query(Periodical).filter(Periodical.tracking_id == tracking_a.id).all()
            assert len(remaining) == 3

            # Verify they all have unique file paths (this is the critical test)
            file_paths = [p.file_path for p in remaining]
            assert len(file_paths) == len(set(file_paths)), "All file paths should be unique"

            # Verify at least one file has been renamed with a conflict suffix
            # The file-level conflict resolution uses timestamp suffixes like (20260213_160735)
            # while the db-level fallback uses (2), (3), etc.
            base_path = "Magazine - February2024.pdf"
            renamed_count = sum(1 for path in file_paths if base_path not in path)
            assert renamed_count >= 1, f"Expected at least 1 renamed file, got {renamed_count}\nPaths: {file_paths}"

            # Verify titles were normalized
            for periodical in remaining:
                assert periodical.title == "Magazine"

        finally:
            # Clean up test files
            session.close()
            for file_path in created_files:
                if file_path.exists():
                    file_path.unlink()
            # Clean up directories - use try/except for each since some may have been moved/deleted
            try:
                if mag_dir_b.exists():
                    mag_dir_b.rmdir()
            except (FileNotFoundError, OSError):
                pass
            try:
                mag_dir_b.parent.rmdir()  # 2024
            except (FileNotFoundError, OSError):
                pass
            try:
                if mag_dir_b.parent.parent.exists() and not list(mag_dir_b.parent.parent.iterdir()):
                    mag_dir_b.parent.parent.rmdir()  # Magazine B
            except (FileNotFoundError, OSError):
                pass
            # Also clean up the Magazine directory if it exists
            mag_dir_a = library_base_dir / "_Magazines" / "Magazine"
            if mag_dir_a.exists():
                import shutil

                shutil.rmtree(mag_dir_a)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
