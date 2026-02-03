"""
Test suite for Internet Archive Download Client

Tests cover:
- Client initialization and configuration
- Job submission and tracking
- Download status management
- Completed downloads retrieval
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Path setup handled by conftest.py

from clients.internet_archive import InternetArchiveClient, DownloadJob


class TestInternetArchiveClientInitialization:
    """Test Internet Archive client initialization"""

    def test_initialization_with_defaults(self):
        """Test client initializes with default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }

            client = InternetArchiveClient(config)

            assert client.name == "IA Client"
            assert client.type == "internet_archive"
            assert client.max_concurrent == 3  # Default
            assert "PDF" in client.preferred_formats

    def test_initialization_with_custom_values(self):
        """Test client initializes with custom configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "Custom IA",
                "downloads_dir": tmpdir,
                "max_concurrent": 5,
                "file_formats": ["EPUB", "PDF"],
            }

            client = InternetArchiveClient(config)

            assert client.max_concurrent == 5
            assert client.preferred_formats == ["EPUB", "PDF"]

    def test_initialization_creates_downloads_dir(self):
        """Test client creates downloads directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloads_path = Path(tmpdir) / "new_downloads"
            config = {
                "name": "IA Client",
                "downloads_dir": str(downloads_path),
            }

            client = InternetArchiveClient(config)

            assert downloads_path.exists()


class TestInternetArchiveClientSubmit:
    """Test download submission functionality"""

    def test_submit_returns_job_id(self):
        """Test submit returns a job ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            # Mock the executor to prevent actual download
            with patch.object(client._executor, "submit"):
                job_id = client.submit("test_identifier", title="Test Magazine")

            assert job_id is not None
            assert len(job_id) > 0

    def test_submit_creates_job_entry(self):
        """Test submit creates a job tracking entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            with patch.object(client._executor, "submit"):
                job_id = client.submit("test_identifier", title="Test Magazine")

            assert job_id in client._jobs
            assert client._jobs[job_id].identifier == "test_identifier"
            assert client._jobs[job_id].title == "Test Magazine"


class TestInternetArchiveClientStatus:
    """Test download status functionality"""

    def test_get_status_unknown_job(self):
        """Test get_status returns unknown for non-existent job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            status = client.get_status("nonexistent_job_id")

            assert status["status"] == "unknown"
            assert status["progress"] == 0

    def test_get_status_pending_job(self):
        """Test get_status returns correct status for pending job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            # Create a job directly
            job = DownloadJob(
                job_id="test_job",
                identifier="test_id",
                title="Test",
                dest_path=tmpdir,
            )
            client._jobs["test_job"] = job

            status = client.get_status("test_job")

            assert status["status"] == "pending"
            assert status["progress"] == 0

    def test_get_status_completed_job(self):
        """Test get_status returns correct status for completed job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            # Create a completed job
            job = DownloadJob(
                job_id="test_job",
                identifier="test_id",
                title="Test",
                dest_path=tmpdir,
            )
            job.status = "completed"
            job.progress = 100
            job.file_path = "/path/to/file.pdf"
            client._jobs["test_job"] = job

            status = client.get_status("test_job")

            assert status["status"] == "completed"
            assert status["progress"] == 100
            assert status["file_path"] == "/path/to/file.pdf"


class TestInternetArchiveClientCompletedDownloads:
    """Test completed downloads retrieval"""

    def test_get_completed_downloads_empty(self):
        """Test get_completed_downloads returns empty list when no completions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            completed = client.get_completed_downloads()

            assert completed == []

    def test_get_completed_downloads_with_results(self):
        """Test get_completed_downloads returns completed jobs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            # Create a completed job
            job = DownloadJob(
                job_id="test_job",
                identifier="test_id",
                title="Test Magazine",
                dest_path=tmpdir,
            )
            job.status = "completed"
            job.file_path = "/path/to/file.pdf"
            client._jobs["test_job"] = job

            completed = client.get_completed_downloads()

            assert len(completed) == 1
            assert completed[0]["job_id"] == "test_job"
            assert completed[0]["title"] == "Test Magazine"
            assert completed[0]["file_path"] == "/path/to/file.pdf"


class TestInternetArchiveClientDelete:
    """Test job deletion functionality"""

    def test_delete_existing_job(self):
        """Test delete removes job from tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            # Create a job
            job = DownloadJob(
                job_id="test_job",
                identifier="test_id",
                title="Test",
                dest_path=tmpdir,
            )
            client._jobs["test_job"] = job

            result = client.delete("test_job")

            assert result is True
            assert "test_job" not in client._jobs

    def test_delete_nonexistent_job(self):
        """Test delete returns False for non-existent job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "name": "IA Client",
                "downloads_dir": tmpdir,
            }
            client = InternetArchiveClient(config)

            result = client.delete("nonexistent")

            assert result is False


class TestDownloadJob:
    """Test DownloadJob dataclass"""

    def test_download_job_creation(self):
        """Test DownloadJob initializes correctly."""
        job = DownloadJob(
            job_id="job123",
            identifier="magazine_2024",
            title="Test Magazine 2024",
            dest_path="/downloads",
        )

        assert job.job_id == "job123"
        assert job.identifier == "magazine_2024"
        assert job.title == "Test Magazine 2024"
        assert job.status == "pending"
        assert job.progress == 0
        assert job.file_path is None
        assert job.error is None
