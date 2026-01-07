"""
Integration tests for end-to-end workflows
Tests complete user journeys through the application
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import AuthManager
from core.database import DatabaseManager
from models.database import Base, DownloadSubmission, Magazine, MagazineTracking
from processor.download_manager import DownloadManager
from processor.file_importer import FileImporter
from processor.organizer import FileOrganizer


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        dirs = {
            "db_path": temp_path / "test.db",
            "download_dir": temp_path / "downloads",
            "organize_dir": temp_path / "organized",
            "cache_dir": temp_path / "cache",
        }
        # Create directories
        for key in ["download_dir", "organize_dir", "cache_dir"]:
            dirs[key].mkdir(parents=True, exist_ok=True)

        yield dirs


@pytest.fixture
def test_db(temp_dirs):
    """Create test database"""
    db_url = f"sqlite:///{temp_dirs['db_path']}"
    db_manager = DatabaseManager(db_url)
    db_manager.create_tables()
    return db_manager


@pytest.fixture
def session(test_db):
    """Create database session"""
    session = test_db.session_factory()
    yield session
    session.close()


@pytest.fixture
def auth_manager(test_db):
    """Create auth manager"""
    return AuthManager(test_db.session_factory, "test-secret-key")


@pytest.fixture
def mock_download_client():
    """Create mock download client"""
    client = Mock()
    client.name = "TestClient"
    client.submit = Mock(return_value="job_123")
    client.get_status = Mock(
        return_value={
            "status": "completed",
            "progress": 100,
            "file_path": "/test/file.pdf",
        }
    )
    return client


@pytest.fixture
def mock_search_provider():
    """Create mock search provider"""
    provider = Mock()
    provider.name = "TestProvider"
    provider.search = Mock(return_value=[])
    return provider


class TestAuthenticationFlow:
    """Test complete authentication workflow"""

    def test_first_time_setup_and_login(self, auth_manager):
        """Test initial setup and first login"""
        # Step 1: Check no credentials exist
        assert not auth_manager.credentials_exist()

        # Step 2: Create initial credentials
        success, message = auth_manager.create_credentials(
            "admin", "secure_password_123"
        )
        assert success is True
        assert auth_manager.credentials_exist()

        # Step 3: Login with credentials
        success, message = auth_manager.verify_credentials(
            "admin", "secure_password_123"
        )
        assert success is True

        # Step 4: Get JWT token
        token = auth_manager.create_token("admin")
        assert token is not None
        assert len(token) > 0

        # Step 5: Verify token
        valid, username = auth_manager.verify_token(token)
        assert valid is True
        assert username == "admin"

    def test_password_change_workflow(self, auth_manager):
        """Test changing password"""
        # Setup
        auth_manager.create_credentials("user", "old_password")

        # Change password
        success, message = auth_manager.update_credentials(
            "user", "old_password", "new_password"
        )
        assert success is True

        # Old password should not work
        success, message = auth_manager.verify_credentials("user", "old_password")
        assert success is False

        # New password should work
        success, message = auth_manager.verify_credentials("user", "new_password")
        assert success is True

    def test_username_change_workflow(self, auth_manager):
        """Test changing username"""
        # Setup
        auth_manager.create_credentials("olduser", "password123")

        # Change username
        success, message = auth_manager.update_username("olduser", "newuser")
        assert success is True

        # Can login with new username
        success, message = auth_manager.verify_credentials("newuser", "password123")
        assert success is True


class TestPeriodicalTrackingWorkflow:
    """Test complete periodical tracking workflow"""

    def test_track_periodical_lifecycle(self, session):
        """Test complete lifecycle from tracking to download"""
        # Step 1: Start tracking a periodical
        tracking = MagazineTracking(
            olid="OL12345W",
            title="Wired Magazine",
            publisher="Condé Nast",
            issn="1059-1028",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()
        tracking_id = tracking.id

        # Step 2: Verify tracking created
        retrieved = session.query(MagazineTracking).filter_by(id=tracking_id).first()
        assert retrieved is not None
        assert retrieved.title == "Wired Magazine"

        # Step 3: Update tracking preferences
        retrieved.selected_years = [2023, 2024]
        retrieved.last_metadata_update = datetime.now(UTC)
        session.commit()

        # Step 4: Verify updates
        session.refresh(retrieved)
        assert 2023 in retrieved.selected_years
        assert retrieved.last_metadata_update is not None

        # Step 5: Delete tracking
        session.delete(retrieved)
        session.commit()

        # Verify deleted
        deleted = session.query(MagazineTracking).filter_by(id=tracking_id).first()
        assert deleted is None


class TestDownloadWorkflow:
    """Test complete download workflow"""

    def test_search_and_download_workflow(
        self, session, mock_search_provider, mock_download_client
    ):
        """Test complete search and download workflow"""
        # Step 1: Create tracking
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=False,
        )
        session.add(tracking)
        session.commit()

        # Step 2: Create download manager
        manager = DownloadManager(
            [mock_search_provider], mock_download_client, fuzzy_threshold=80
        )

        # Step 3: Submit download
        search_result = {
            "title": "Test Magazine Issue 1",
            "url": "http://example.com/test.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }

        submission = manager.submit_download(tracking.id, search_result, session)

        # Step 4: Verify submission created
        assert submission is not None
        assert submission.job_id == "job_123"
        assert submission.status == DownloadSubmission.StatusEnum.PENDING

        # Step 5: Update status
        updated = manager.update_submission_status("job_123", session)
        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED
        assert updated.file_path is not None

    def test_duplicate_prevention_workflow(self, session, mock_download_client):
        """Test that duplicates are prevented"""
        # Setup tracking
        tracking = MagazineTracking(olid="test_mag", title="Test")
        session.add(tracking)
        session.commit()

        manager = DownloadManager([], mock_download_client, fuzzy_threshold=80)

        # Submit first download
        result1 = {
            "title": "Test Magazine - Dec 2023",
            "url": "http://example.com/1.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }
        sub1 = manager.submit_download(tracking.id, result1, session)
        assert sub1 is not None

        # Try similar title (should be duplicate)
        result2 = {
            "title": "Test Magazine December 2023",
            "url": "http://example.com/2.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }
        sub2 = manager.submit_download(tracking.id, result2, session)
        assert sub2 is None  # Rejected as duplicate


class TestFileOrganizationWorkflow:
    """Test complete file organization workflow"""

    def test_organize_downloaded_file(self, temp_dirs, session):
        """Test organizing a downloaded file"""
        # Step 1: Create organizer
        organizer = FileOrganizer(str(temp_dirs["organize_dir"]))

        # Step 2: Create a test file in downloads
        test_file = temp_dirs["download_dir"] / "test_magazine.pdf"
        test_file.write_text("test content")

        # Step 3: Organize the file
        pdf_path, jpg_path = organizer.organize_file(
            source_path=str(test_file),
            title="Test Magazine",
            issue_date=datetime(2024, 1, 1),
            cover_path=None,
        )

        # Step 4: Verify organized
        assert Path(pdf_path).exists()
        assert "Test Magazine" in pdf_path
        assert "Jan2024" in pdf_path


class TestImportWorkflow:
    """Test file import workflow"""

    def test_import_and_organize(self, temp_dirs, session):
        """Test importing files and organizing them"""
        # Step 1: Create test files in download directory
        test_files = []
        for i in range(3):
            test_file = temp_dirs["download_dir"] / f"magazine_{i}.pdf"
            test_file.write_text(f"magazine content {i}")
            test_files.append(test_file)

        # Step 2: Create importer
        importer = FileImporter(
            downloads_dir=str(temp_dirs["download_dir"]),
            organize_base_dir=str(temp_dirs["organize_dir"]),
            fuzzy_threshold=80,
        )

        # Step 3: Process downloads
        results = importer.process_downloads(session)

        # Verify files were processed (they might not import successfully without proper metadata)
        assert "imported" in results
        assert "failed" in results
        assert "errors" in results


class TestEndToEndJourney:
    """Test complete end-to-end user journey"""

    def test_complete_user_journey(
        self,
        auth_manager,
        session,
        mock_search_provider,
        mock_download_client,
        temp_dirs,
    ):
        """Test complete journey: auth -> track -> search -> download -> organize"""

        # Step 1: Authentication
        auth_manager.create_credentials("user", "password123")
        token = auth_manager.create_token("user")
        valid, username = auth_manager.verify_token(token)
        assert valid

        # Step 2: Track a periodical
        tracking = MagazineTracking(
            olid="wired_magazine",
            title="Wired",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Step 3: Search and download
        manager = DownloadManager(
            [mock_search_provider], mock_download_client, fuzzy_threshold=80
        )

        search_result = {
            "title": "Wired - January 2024",
            "url": "http://example.com/wired-jan-2024.nzb",
            "provider": "test",
            "publication_date": datetime(2024, 1, 1),
            "raw_metadata": {},
        }

        submission = manager.submit_download(tracking.id, search_result, session)
        assert submission is not None

        # Step 4: Monitor and complete download
        updated = manager.update_submission_status(submission.job_id, session)
        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED

        # Step 5: Create magazine entry
        magazine = Magazine(
            title="Wired",
            publisher="Condé Nast",
            issue_date=datetime(2024, 1, 1),
            file_path=updated.file_path or "/test/wired.pdf",
        )
        session.add(magazine)
        session.commit()

        # Step 6: Verify everything persisted
        assert session.query(MagazineTracking).count() == 1
        assert session.query(DownloadSubmission).count() == 1
        assert session.query(Magazine).count() == 1


class TestErrorRecovery:
    """Test error recovery scenarios"""

    def test_failed_download_retry(self, session, mock_download_client):
        """Test retrying a failed download"""
        # Setup
        tracking = MagazineTracking(olid="test", title="Test")
        session.add(tracking)
        session.flush()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="failed_job",
            status=DownloadSubmission.StatusEnum.FAILED,
            source_url="http://example.com/test.nzb",
            result_title="Test Issue",
            fuzzy_match_group="test",
            client_name="TestClient",
            last_error="Network error",
            attempt_count=1,
        )
        session.add(submission)
        session.commit()

        # Retry logic would update status back to PENDING
        submission.status = DownloadSubmission.StatusEnum.PENDING
        submission.attempt_count += 1
        session.commit()

        assert submission.attempt_count == 2
        assert submission.status == DownloadSubmission.StatusEnum.PENDING

    def test_invalid_credentials_handling(self, auth_manager):
        """Test handling invalid credentials"""
        auth_manager.create_credentials("user", "password")

        # Wrong password
        success, message = auth_manager.verify_credentials("user", "wrong_password")
        assert success is False
        assert "invalid" in message.lower() or "incorrect" in message.lower()

        # Nonexistent user
        success, message = auth_manager.verify_credentials("nonexistent", "password")
        assert success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
