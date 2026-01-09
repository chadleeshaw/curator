"""
Test suite for Database Models and initialization
"""

import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import DatabaseManager
from models.database import (
    Base,
    Download,
    DownloadSubmission,
    Magazine,
    MagazineTracking,
    SearchResult,
)


@pytest.fixture
def test_db():
    """Create temporary test database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        db_manager = DatabaseManager(db_url)
        db_manager.create_tables()
        yield db_manager.engine, db_manager.session_factory


@pytest.fixture
def session(test_db):
    """Create database session for testing"""
    engine, session_factory = test_db
    session = session_factory()
    yield session
    session.close()


class TestMagazineModel:
    """Test Magazine model"""

    def test_magazine_creation_with_all_fields(self):
        """Test Magazine model creation with all fields"""
        mag = Magazine(
            title="National Geographic",
            issue_date=datetime(2023, 3, 15),
            file_path="/data/National Geographic - Mar2023.pdf",
            cover_path="/data/National Geographic - Mar2023.jpg",
            extra_metadata={"keywords": ["nature", "wildlife"]},
        )

        assert mag.title == "National Geographic"
        assert mag.file_path == "/data/National Geographic - Mar2023.pdf"
        assert mag.cover_path == "/data/National Geographic - Mar2023.jpg"
        assert mag.extra_metadata["keywords"] == ["nature", "wildlife"]

    def test_magazine_required_fields_only(self):
        """Test Magazine model with only required fields"""
        mag = Magazine(
            title="Wired",
            issue_date=datetime(2020, 1, 1),
            file_path="/data/wired.pdf",
        )

        assert mag.title == "Wired"
        assert mag.issue_date == datetime(2020, 1, 1)
        assert mag.file_path == "/data/wired.pdf"
        assert mag.cover_path is None
        assert mag.extra_metadata is None

    def test_magazine_persistence(self, session):
        """Test saving and retrieving Magazine from database"""
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/path.pdf",
        )
        session.add(mag)
        session.commit()
        magazine_id = mag.id

        # Retrieve
        retrieved = session.query(Magazine).filter(Magazine.id == magazine_id).first()
        assert retrieved is not None
        assert retrieved.title == "Test Magazine"
        assert retrieved.file_path == "/test/path.pdf"


class TestMagazineTracking:
    """Test MagazineTracking model"""

    def test_tracking_creation(self):
        """Test MagazineTracking model creation"""
        tracking = MagazineTracking(
            olid="OL1234567W",
            title="Time Magazine",
            first_publish_year=1923,
            total_editions_known=5200,
            track_all_editions=True,
            periodical_metadata={"description": "American magazine", "country": "US"},
        )

        assert tracking.olid == "OL1234567W"
        assert tracking.title == "Time Magazine"
        assert tracking.first_publish_year == 1923
        assert tracking.total_editions_known == 5200
        assert tracking.track_all_editions is True
        assert tracking.periodical_metadata["country"] == "US"

    def test_tracking_defaults(self, session):
        """Test MagazineTracking model default values"""
        tracking = MagazineTracking(
            olid="OL9876543W",
            title="Scientific American",
        )
        session.add(tracking)
        session.commit()

        # Defaults are applied when saved to DB
        assert tracking.track_all_editions is False
        assert tracking.track_new_only is False
        assert tracking.selected_editions == {}
        assert tracking.selected_years == []
        assert tracking.total_editions_known == 0


class TestSearchResultModel:
    """Test SearchResult model"""

    def test_search_result_creation(self):
        """Test SearchResult model creation"""
        result = SearchResult(
            provider="newsnab",
            query="National Geographic",
            title="National Geographic March 2023",
            url="https://example.com/nzb/12345",
            publication_date=datetime(2023, 3, 1),
            raw_metadata={"size": 523456789, "age_days": 45},
            fuzzy_match_group_id="nat_geo_group_1",
        )

        assert result.provider == "newsnab"
        assert result.query == "National Geographic"
        assert result.title == "National Geographic March 2023"
        assert result.url == "https://example.com/nzb/12345"
        assert result.publication_date == datetime(2023, 3, 1)
        assert result.raw_metadata["size"] == 523456789
        assert result.fuzzy_match_group_id == "nat_geo_group_1"

    def test_search_result_minimal_fields(self):
        """Test SearchResult model with minimal fields"""
        result = SearchResult(
            provider="rss",
            query="Wired",
            title="Wired Latest",
            url="https://example.com/article/123",
        )

        assert result.provider == "rss"
        assert result.publication_date is None
        assert result.raw_metadata is None
        assert result.fuzzy_match_group_id is None


class TestDownloadModel:
    """Test Download model"""

    def test_download_creation(self):
        """Test Download model creation"""
        download = Download(
            job_id="SAB-12345",
            status=Download.StatusEnum.DOWNLOADING,
            source_url="https://example.com/nzb/12345",
            client_name="sabnzbd",
        )

        assert download.job_id == "SAB-12345"
        assert download.status == Download.StatusEnum.DOWNLOADING
        assert download.source_url == "https://example.com/nzb/12345"
        assert download.client_name == "sabnzbd"

    def test_download_status_enum(self):
        """Test Download status enum values"""
        assert Download.StatusEnum.PENDING.value == "pending"
        assert Download.StatusEnum.DOWNLOADING.value == "downloading"
        assert Download.StatusEnum.COMPLETED.value == "completed"
        assert Download.StatusEnum.FAILED.value == "failed"


class TestDownloadSubmissionModel:
    """Test DownloadSubmission model"""

    def test_download_submission_creation(self, session):
        """Test DownloadSubmission creation"""
        # Create tracking first
        tracking = MagazineTracking(olid="test_mag", title="Test")
        session.add(tracking)
        session.flush()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_123",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/test.nzb",
            result_title="Test Issue",
            fuzzy_match_group="test-group",
            client_name="TestClient",
        )
        session.add(submission)
        session.commit()

        assert submission.tracking_id == tracking.id
        assert submission.job_id == "job_123"
        assert submission.status == DownloadSubmission.StatusEnum.PENDING

    def test_download_submission_status_enum(self):
        """Test DownloadSubmission status enum values"""
        assert DownloadSubmission.StatusEnum.PENDING.value == "pending"
        assert DownloadSubmission.StatusEnum.DOWNLOADING.value == "downloading"
        assert DownloadSubmission.StatusEnum.COMPLETED.value == "completed"
        assert DownloadSubmission.StatusEnum.FAILED.value == "failed"
        assert DownloadSubmission.StatusEnum.SKIPPED.value == "skipped"


class TestDatabaseOperations:
    """Test database operations"""

    def test_create_and_retrieve(self, session):
        """Test creating and retrieving records"""
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/path.pdf",
        )
        session.add(mag)
        session.commit()
        magazine_id = mag.id

        retrieved = session.query(Magazine).filter(Magazine.id == magazine_id).first()
        assert retrieved is not None
        assert retrieved.title == "Test Magazine"

    def test_foreign_key_relationships(self, session):
        """Test foreign key relationships"""
        # Create magazine
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/path.pdf",
        )
        session.add(mag)
        session.flush()

        # Create search result linked to magazine
        search_result = SearchResult(
            provider="test",
            query="test",
            title="test result",
            url="https://test.com",
            magazine_id=mag.id,
        )
        session.add(search_result)
        session.flush()

        # Create download linked to both
        download = Download(
            job_id="job123",
            status=Download.StatusEnum.COMPLETED,
            source_url="https://test.com/nzb",
            client_name="test_client",
            magazine_id=mag.id,
            search_result_id=search_result.id,
        )
        session.add(download)
        session.commit()

        assert search_result.magazine_id == mag.id
        assert download.magazine_id == mag.id
        assert download.search_result_id == search_result.id

    def test_unique_constraint_file_path(self, session):
        """Test unique constraint on Magazine file_path"""
        mag1 = Magazine(
            title="Magazine 1",
            issue_date=datetime(2023, 1, 1),
            file_path="/unique/path.pdf",
        )
        session.add(mag1)
        session.commit()

        # Try to create another with same file_path
        mag2 = Magazine(
            title="Magazine 2",
            issue_date=datetime(2023, 2, 1),
            file_path="/unique/path.pdf",
        )
        session.add(mag2)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_olid_can_be_duplicate_for_languages(self, session):
        """Test that OLID can be shared across different language editions"""
        # Same OLID but different languages - should be allowed
        tracking1 = MagazineTracking(
            olid="OL12345W",
            title="Wired Magazine",
            language="English"
        )
        session.add(tracking1)
        session.commit()

        tracking2 = MagazineTracking(
            olid="OL12345W",
            title="Wired Magazine",
            language="German"
        )
        session.add(tracking2)
        session.commit()  # Should not raise - duplicate OLID is allowed

        # Verify both exist
        all_tracking = session.query(MagazineTracking).filter(
            MagazineTracking.olid == "OL12345W"
        ).all()
        assert len(all_tracking) == 2
        assert {t.language for t in all_tracking} == {"English", "German"}


class TestLanguageFields:
    """Test language field functionality in Magazine and MagazineTracking"""

    def test_magazine_language_default(self, session):
        """Test that Magazine language defaults to English"""
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/magazine.pdf",
        )
        session.add(mag)
        session.commit()

        assert mag.language == "English"

    def test_magazine_language_custom(self, session):
        """Test setting custom language on Magazine"""
        mag = Magazine(
            title="Wired Magazine",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/wired_de.pdf",
            language="German",
        )
        session.add(mag)
        session.commit()

        assert mag.language == "German"

        # Verify it persists
        retrieved = session.query(Magazine).filter(Magazine.id == mag.id).first()
        assert retrieved.language == "German"

    def test_tracking_language_default(self, session):
        """Test that MagazineTracking language defaults to English"""
        tracking = MagazineTracking(
            olid="OL12345W",
            title="Test Periodical",
        )
        session.add(tracking)
        session.commit()

        assert tracking.language == "English"

    def test_tracking_language_custom(self, session):
        """Test setting custom language on MagazineTracking"""
        tracking = MagazineTracking(
            olid="OL99999W",
            title="Revista Española",
            language="Spanish",
        )
        session.add(tracking)
        session.commit()

        assert tracking.language == "Spanish"

        # Verify it persists
        retrieved = session.query(MagazineTracking).filter(
            MagazineTracking.id == tracking.id
        ).first()
        assert retrieved.language == "Spanish"

    def test_multiple_languages_same_title(self, session):
        """Test tracking same magazine in multiple languages"""
        # English edition
        tracking_en = MagazineTracking(
            olid="wired",
            title="Wired Magazine",
            language="English",
        )
        session.add(tracking_en)

        # German edition
        tracking_de = MagazineTracking(
            olid="wired",
            title="Wired Magazine",
            language="German",
        )
        session.add(tracking_de)

        # French edition
        tracking_fr = MagazineTracking(
            olid="wired",
            title="Wired Magazine",
            language="French",
        )
        session.add(tracking_fr)

        session.commit()

        # All should persist independently
        all_wired = session.query(MagazineTracking).filter(
            MagazineTracking.olid == "wired"
        ).all()
        assert len(all_wired) == 3

        languages = {t.language for t in all_wired}
        assert languages == {"English", "German", "French"}

    def test_magazine_language_query(self, session):
        """Test querying magazines by language"""
        # Add English magazines
        mag_en1 = Magazine(
            title="PC Gamer", issue_date=datetime(2024, 1, 1),
            file_path="/test/pcgamer_en.pdf", language="English"
        )
        mag_en2 = Magazine(
            title="Wired", issue_date=datetime(2024, 1, 1),
            file_path="/test/wired_en.pdf", language="English"
        )

        # Add German magazines
        mag_de1 = Magazine(
            title="PC Gamer", issue_date=datetime(2024, 1, 1),
            file_path="/test/pcgamer_de.pdf", language="German"
        )
        mag_de2 = Magazine(
            title="Wired", issue_date=datetime(2024, 1, 1),
            file_path="/test/wired_de.pdf", language="German"
        )

        session.add_all([mag_en1, mag_en2, mag_de1, mag_de2])
        session.commit()

        # Query by language
        english_mags = session.query(Magazine).filter(
            Magazine.language == "English"
        ).all()
        german_mags = session.query(Magazine).filter(
            Magazine.language == "German"
        ).all()

        assert len(english_mags) == 2
        assert len(german_mags) == 2


class TestTimestampFields:
    """Test timestamp fields"""

    def test_magazine_timestamps(self, session):
        """Test Magazine created_at and updated_at"""
        mag = Magazine(
            title="Timestamped Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/timestamps.pdf",
        )
        session.add(mag)
        session.commit()

        # Timestamps should be set
        assert mag.created_at is not None
        assert mag.updated_at is not None
        assert mag.created_at <= mag.updated_at

    def test_tracking_timestamps(self, session):
        """Test MagazineTracking timestamps"""
        tracking = MagazineTracking(olid="test_olid", title="Test")
        session.add(tracking)
        session.commit()

        assert tracking.created_at is not None
        assert tracking.updated_at is not None


class TestIndexing:
    """Test that indexed fields work correctly"""

    def test_magazine_indexed_fields(self):
        """Test Magazine indexed columns"""
        assert hasattr(Magazine, "title")
        assert hasattr(Magazine, "issue_date")
        assert hasattr(Magazine, "created_at")

    def test_tracking_indexed_fields(self):
        """Test MagazineTracking indexed columns"""
        assert hasattr(MagazineTracking, "olid")
        assert hasattr(MagazineTracking, "title")
        assert hasattr(MagazineTracking, "created_at")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
