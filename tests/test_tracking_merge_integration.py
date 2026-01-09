"""
Integration test for tracking merge functionality with library view grouping
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import Base, Magazine, MagazineTracking
from web.routers.tracking import merge_tracking, set_dependencies


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory


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
        tracking_wired = MagazineTracking(
            olid="OL123W",
            title="Wired",
            publisher="Condé Nast",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking_wired_mag = MagazineTracking(
            olid="OL456W",
            title="Wired Magazine",
            publisher="Condé Nast",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking_wired_uk = MagazineTracking(
            olid="OL789W",
            title="Wired UK",
            publisher="Condé Nast",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking_wired, tracking_wired_mag, tracking_wired_uk])
        session.commit()

        # Create magazines from different sources/imports
        magazines = [
            Magazine(
                title="Wired",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/library/wired-jan2024.pdf",
                tracking_id=tracking_wired.id,
            ),
            Magazine(
                title="Wired",
                language="English",
                issue_date=datetime(2024, 2, 1),
                file_path="/library/wired-feb2024.pdf",
                tracking_id=tracking_wired.id,
            ),
            Magazine(
                title="Wired Magazine",
                language="English",
                issue_date=datetime(2024, 3, 1),
                file_path="/library/wired-magazine-mar2024.pdf",
                tracking_id=tracking_wired_mag.id,
            ),
            Magazine(
                title="Wired Magazine",
                language="English",
                issue_date=datetime(2024, 4, 1),
                file_path="/library/wired-magazine-apr2024.pdf",
                tracking_id=tracking_wired_mag.id,
            ),
            Magazine(
                title="Wired UK",
                language="English",
                issue_date=datetime(2024, 5, 1),
                file_path="/library/wired-uk-may2024.pdf",
                tracking_id=tracking_wired_uk.id,
            ),
        ]
        session.add_all(magazines)
        session.commit()

        # BEFORE MERGE: Library view shows 3 separate periodical groups
        # This simulates /api/periodicals endpoint query
        subquery = (
            session.query(
                Magazine.title,
                Magazine.language,
                func.max(Magazine.issue_date).label("max_date")
            )
            .group_by(Magazine.title, Magazine.language)
            .subquery()
        )

        library_groups_before = session.query(Magazine).join(
            subquery,
            (Magazine.title == subquery.c.title)
            & (Magazine.language == subquery.c.language)
            & (Magazine.issue_date == subquery.c.max_date)
        ).all()

        assert len(library_groups_before) == 3, "Should show 3 separate groups before merge"
        library_titles_before = {mag.title for mag in library_groups_before}
        assert library_titles_before == {"Wired", "Wired Magazine", "Wired UK"}

        # USER ACTION: Merge the tracking records
        # Keep "Wired" as canonical title, merge others into it
        import asyncio
        result = asyncio.run(merge_tracking(
            target_id=tracking_wired.id,
            source_ids={"source_ids": [tracking_wired_mag.id, tracking_wired_uk.id]}
        ))

        assert result["success"] is True
        assert result["magazines_moved"] == 3  # 2 from Wired Magazine + 1 from Wired UK
        assert len(result["merged_titles"]) == 2

        # Refresh session
        session.expire_all()

        # AFTER MERGE: Library view shows 1 consolidated group
        library_groups_after = session.query(Magazine).join(
            subquery,
            (Magazine.title == subquery.c.title)
            & (Magazine.language == subquery.c.language)
            & (Magazine.issue_date == subquery.c.max_date)
        ).all()

        assert len(library_groups_after) == 1, "Should show 1 consolidated group after merge"
        assert library_groups_after[0].title == "Wired"

        # Verify all magazines are grouped together
        all_mags = session.query(Magazine).order_by(Magazine.issue_date).all()
        assert len(all_mags) == 5
        for mag in all_mags:
            assert mag.title == "Wired", "All magazines should have normalized title"
            assert mag.tracking_id == tracking_wired.id, "All should link to target tracking"

        # Verify issue count for the group
        wired_count = session.query(Magazine).filter(
            Magazine.title == "Wired",
            Magazine.language == "English"
        ).count()
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
        tracking_en = MagazineTracking(
            olid="OL_EN",
            title="Le Monde Diplomatique",
            language="English",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        tracking_fr = MagazineTracking(
            olid="OL_FR",
            title="Monde Diplomatique",
            language="French",
            track_all_editions=True,
            last_metadata_update=datetime.now(UTC),
        )
        session.add_all([tracking_en, tracking_fr])
        session.commit()

        # Add magazines in each language
        magazines = [
            Magazine(
                title="Le Monde Diplomatique",
                language="English",
                issue_date=datetime(2024, 1, 1),
                file_path="/lib/monde-en-jan.pdf",
                tracking_id=tracking_en.id,
            ),
            Magazine(
                title="Monde Diplomatique",
                language="French",
                issue_date=datetime(2024, 1, 1),
                file_path="/lib/monde-fr-jan.pdf",
                tracking_id=tracking_fr.id,
            ),
        ]
        session.add_all(magazines)
        session.commit()

        # Merge tracking records
        import asyncio
        asyncio.run(merge_tracking(
            target_id=tracking_en.id,
            source_ids={"source_ids": [tracking_fr.id]}
        ))

        session.expire_all()

        # Both should have same title now
        all_mags = session.query(Magazine).all()
        for mag in all_mags:
            assert mag.title == "Le Monde Diplomatique"

        # But library should still show 2 groups (different languages)
        from sqlalchemy import func
        language_groups = session.query(
            Magazine.title,
            Magazine.language
        ).distinct().all()

        assert len(language_groups) == 2, "Should maintain language-based grouping"
        languages = {group[1] for group in language_groups}
        assert languages == {"English", "French"}

        session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
