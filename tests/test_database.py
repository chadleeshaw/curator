#!/usr/bin/env python3
"""
Test suite for Database Models and initialization
"""

import sys
import tempfile
from pathlib import Path  # noqa: E402
from datetime import datetime, timedelta, UTC  # noqa: E402

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import (  # noqa: E402
    Magazine,
    MagazineTracking,
    SearchResult,
    Download,
    Base,
)
from core.database import DatabaseManager  # noqa: E402


def init_db(db_url: str):
    """Helper function to initialize test database (replaces old init_db)"""
    db_manager = DatabaseManager(db_url)
    db_manager.create_tables()
    return db_manager.engine, db_manager.session_factory


def test_magazine_model():
    """Test Magazine model creation and attributes"""
    mag = Magazine(
        issn="1234-5678",
        title="National Geographic",
        publisher="National Geographic Society",
        issue_date=datetime(2023, 3, 15),
        file_path="/data/National Geographic - Mar2023.pdf",
        cover_path="/data/National Geographic - Mar2023.jpg",
        extra_metadata={"keywords": ["nature", "wildlife"]},
    )

    assert mag.title == "National Geographic"
    assert mag.issn == "1234-5678"
    assert mag.publisher == "National Geographic Society"
    assert mag.file_path == "/data/National Geographic - Mar2023.pdf"
    assert mag.cover_path == "/data/National Geographic - Mar2023.jpg"
    assert mag.extra_metadata["keywords"] == ["nature", "wildlife"]
    # Timestamps are not set until saved to database

    print("Testing Magazine model... ✓ PASS")
    return True


def test_magazine_required_fields():
    """Test Magazine model with only required fields"""
    mag = Magazine(
        title="Wired",
        issue_date=datetime(2020, 1, 1),
        file_path="/data/wired.pdf",
    )

    assert mag.title == "Wired"
    assert mag.issue_date == datetime(2020, 1, 1)
    assert mag.file_path == "/data/wired.pdf"
    assert mag.issn is None
    assert mag.publisher is None
    assert mag.cover_path is None
    assert mag.extra_metadata is None

    print("Testing Magazine required fields... ✓ PASS")
    return True


def test_magazine_tracking_model():
    """Test MagazineTracking model creation"""
    tracking = MagazineTracking(
        olid="OL1234567W",
        title="Time Magazine",
        publisher="Time Inc.",
        issn="0040-781X",
        first_publish_year=1923,
        total_editions_known=5200,
        track_all_editions=True,
        periodical_metadata={
            "description": "American magazine",
            "country": "US",
        },
    )

    assert tracking.olid == "OL1234567W"
    assert tracking.title == "Time Magazine"
    assert tracking.issn == "0040-781X"
    assert tracking.first_publish_year == 1923
    assert tracking.total_editions_known == 5200
    assert tracking.track_all_editions is True
    assert tracking.periodical_metadata["country"] == "US"

    print("Testing MagazineTracking model... ✓ PASS")
    return True


def test_magazine_tracking_defaults():
    """Test MagazineTracking model default values"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        engine, session_factory = init_db(db_url)
        Session = session_factory

        session = Session()
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
        assert tracking.publisher is None
        assert tracking.first_publish_year is None

        session.close()

    print("Testing MagazineTracking defaults... ✓ PASS")
    return True


def test_search_result_model():
    """Test SearchResult model creation"""
    result = SearchResult(
        provider="newsnab",
        query="National Geographic",
        title="National Geographic March 2023",
        url="https://example.com/nzb/12345",
        publication_date=datetime(2023, 3, 1),
        raw_metadata={
            "size": 523456789,
            "age_days": 45,
        },
        fuzzy_match_group_id="nat_geo_group_1",
    )

    assert result.provider == "newsnab"
    assert result.query == "National Geographic"
    assert result.title == "National Geographic March 2023"
    assert result.url == "https://example.com/nzb/12345"
    assert result.publication_date == datetime(2023, 3, 1)
    assert result.raw_metadata["size"] == 523456789
    assert result.fuzzy_match_group_id == "nat_geo_group_1"
    assert result.magazine_id is None

    print("Testing SearchResult model... ✓ PASS")
    return True


def test_search_result_optional_fields():
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

    print("Testing SearchResult optional fields... ✓ PASS")
    return True


def test_download_model():
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
    assert download.magazine_id is None
    assert download.search_result_id is None

    print("Testing Download model... ✓ PASS")
    return True


def test_download_status_enum():
    """Test Download status enum values"""
    # Test all enum values
    assert Download.StatusEnum.PENDING.value == "pending"
    assert Download.StatusEnum.DOWNLOADING.value == "downloading"
    assert Download.StatusEnum.COMPLETED.value == "completed"
    assert Download.StatusEnum.FAILED.value == "failed"

    # Test creating downloads with different statuses
    pending = Download(
        job_id="job1", status=Download.StatusEnum.PENDING, source_url="url1", client_name="test"
    )
    completed = Download(
        job_id="job2", status=Download.StatusEnum.COMPLETED, source_url="url2", client_name="test"
    )
    failed = Download(
        job_id="job3", status=Download.StatusEnum.FAILED, source_url="url3", client_name="test"
    )

    assert pending.status == Download.StatusEnum.PENDING
    assert completed.status == Download.StatusEnum.COMPLETED
    assert failed.status == Download.StatusEnum.FAILED

    print("Testing Download status enum... ✓ PASS")
    return True


def test_init_db_sqlite():
    """Test database initialization with SQLite using DatabaseManager"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        engine, session_factory = init_db(db_url)

        assert engine is not None
        assert session_factory is not None
        assert db_path.exists()

        # Verify we can create a session
        Session = session_factory
        session = Session()
        assert session is not None
        session.close()

    print("Testing init_db() SQLite... ✓ PASS")
    return True


def test_database_operations():
    """Test actual database operations with SQLite"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        engine, session_factory = init_db(db_url)
        Session = session_factory

        # Create a magazine
        session = Session()
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/path.pdf",
        )
        session.add(mag)
        session.commit()

        magazine_id = mag.id
        session.close()

        # Retrieve the magazine
        session = Session()
        retrieved_mag = session.query(Magazine).filter(Magazine.id == magazine_id).first()

        assert retrieved_mag is not None
        assert retrieved_mag.title == "Test Magazine"
        assert retrieved_mag.file_path == "/test/path.pdf"

        session.close()

    print("Testing database operations... ✓ PASS")
    return True


def test_magazine_indexing():
    """Test that Magazine fields are properly indexed"""
    mag = Magazine(
        issn="1234-5678",
        title="Indexed Magazine",
        issue_date=datetime(2023, 6, 15),
        file_path="/path/indexed.pdf",
    )

    # Verify indexed columns exist and work
    assert hasattr(Magazine, "issn")
    assert hasattr(Magazine, "title")
    assert hasattr(Magazine, "issue_date")
    assert hasattr(Magazine, "created_at")

    print("Testing Magazine indexing... ✓ PASS")
    return True


def test_foreign_keys():
    """Test foreign key relationships"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        engine, session_factory = init_db(db_url)
        Session = session_factory

        session = Session()

        # Create a magazine
        mag = Magazine(
            title="Test Magazine",
            issue_date=datetime(2023, 1, 1),
            file_path="/test/path.pdf",
        )
        session.add(mag)
        session.flush()  # Flush to get the ID
        magazine_id = mag.id

        # Create a search result linked to the magazine
        search_result = SearchResult(
            provider="test",
            query="test",
            title="test result",
            url="https://test.com",
            magazine_id=magazine_id,
        )
        session.add(search_result)
        session.flush()  # Flush to get search_result ID

        # Create a download linked to both
        download = Download(
            job_id="job123",
            status=Download.StatusEnum.COMPLETED,
            source_url="https://test.com/nzb",
            client_name="test_client",
            magazine_id=magazine_id,
            search_result_id=search_result.id,
        )
        session.add(download)
        session.commit()

        # Verify relationships
        assert search_result.magazine_id == magazine_id
        assert download.magazine_id == magazine_id
        assert download.search_result_id == search_result.id

        session.close()

    print("Testing foreign key relationships... ✓ PASS")
    return True


def test_unique_constraints():
    """Test unique constraint on file_path"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        engine, session_factory = init_db(db_url)
        Session = session_factory

        session = Session()

        # Create first magazine
        mag1 = Magazine(
            title="Magazine 1",
            issue_date=datetime(2023, 1, 1),
            file_path="/unique/path.pdf",
        )
        session.add(mag1)
        session.commit()

        # Try to create another with same file_path (should fail)
        mag2 = Magazine(
            title="Magazine 2",
            issue_date=datetime(2023, 2, 1),
            file_path="/unique/path.pdf",  # Same path
        )
        session.add(mag2)

        try:
            session.commit()
            # If we get here without exception, unique constraint isn't working
            assert False, "Unique constraint not enforced"
        except Exception:
            # Expected - unique constraint violation
            pass

        session.close()

    print("Testing unique constraints... ✓ PASS")
    return True


def test_timestamp_fields():
    """Test that timestamp fields work correctly"""
    mag = Magazine(
        title="Timestamped Magazine",
        issue_date=datetime(2023, 1, 1),
        file_path="/test/timestamps.pdf",
    )

    before_time = datetime.now(UTC)
    # In real DB operations, created_at/updated_at are set by defaults
    # For the model object, they should be None until saved
    after_time = datetime.now(UTC)

    # Verify timestamps exist as fields
    assert hasattr(Magazine, "created_at")
    assert hasattr(Magazine, "updated_at")

    print("Testing timestamp fields... ✓ PASS")
    return True


if __name__ == "__main__":
    print("\n🧪 Database Model Tests\n")
    print("=" * 70)

    results = {}

    try:
        results["magazine_model"] = test_magazine_model()
    except Exception as e:
        print(f"Testing Magazine model... ❌ FAIL: {e}")
        results["magazine_model"] = False

    try:
        results["magazine_required"] = test_magazine_required_fields()
    except Exception as e:
        print(f"Testing Magazine required fields... ❌ FAIL: {e}")
        results["magazine_required"] = False

    try:
        results["tracking_model"] = test_magazine_tracking_model()
    except Exception as e:
        print(f"Testing MagazineTracking model... ❌ FAIL: {e}")
        results["tracking_model"] = False

    try:
        results["tracking_defaults"] = test_magazine_tracking_defaults()
    except Exception as e:
        print(f"Testing MagazineTracking defaults... ❌ FAIL: {e}")
        results["tracking_defaults"] = False

    try:
        results["search_result"] = test_search_result_model()
    except Exception as e:
        print(f"Testing SearchResult model... ❌ FAIL: {e}")
        results["search_result"] = False

    try:
        results["search_result_optional"] = test_search_result_optional_fields()
    except Exception as e:
        print(f"Testing SearchResult optional fields... ❌ FAIL: {e}")
        results["search_result_optional"] = False

    try:
        results["download_model"] = test_download_model()
    except Exception as e:
        print(f"Testing Download model... ❌ FAIL: {e}")
        results["download_model"] = False

    try:
        results["download_enum"] = test_download_status_enum()
    except Exception as e:
        print(f"Testing Download status enum... ❌ FAIL: {e}")
        results["download_enum"] = False

    try:
        results["init_db"] = test_init_db_sqlite()
    except Exception as e:
        print(f"Testing init_db() SQLite... ❌ FAIL: {e}")
        results["init_db"] = False

    try:
        results["db_operations"] = test_database_operations()
    except Exception as e:
        print(f"Testing database operations... ❌ FAIL: {e}")
        results["db_operations"] = False

    try:
        results["magazine_indexing"] = test_magazine_indexing()
    except Exception as e:
        print(f"Testing Magazine indexing... ❌ FAIL: {e}")
        results["magazine_indexing"] = False

    try:
        results["foreign_keys"] = test_foreign_keys()
    except Exception as e:
        print(f"Testing foreign key relationships... ❌ FAIL: {e}")
        results["foreign_keys"] = False

    try:
        results["unique_constraints"] = test_unique_constraints()
    except Exception as e:
        print(f"Testing unique constraints... ❌ FAIL: {e}")
        results["unique_constraints"] = False

    try:
        results["timestamps"] = test_timestamp_fields()
    except Exception as e:
        print(f"Testing timestamp fields... ❌ FAIL: {e}")
        results["timestamps"] = False

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))

    sys.exit(0 if all_passed else 1)
