"""
Test suite for Internet Archive Download Client

Tests cover:
- Client initialization and configuration
- Job submission and tracking
- Download status management
- Completed downloads retrieval
- Download strategy selection (direct vs compress URL)
- Text PDF format prioritization
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Path setup handled by conftest.py

from clients.internet_archive import InternetArchiveClient, DownloadJob
from core.constants.internet_archive import (
    IA_TEXT_PDF_FORMATS,
    IA_COMPRESS_BASE_URL,
    IA_DOWNLOAD_BASE_URL,
)


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


class TestDownloadStrategy:
    """Test download strategy selection (direct vs compress URL)"""

    def _create_client(self, tmpdir):
        """Helper to create a client for testing."""
        config = {
            "name": "IA Client",
            "downloads_dir": tmpdir,
        }
        return InternetArchiveClient(config)

    def _create_metadata(self, identifier: str, files: list) -> dict:
        """Helper to create mock item metadata."""
        return {
            "metadata": {"identifier": identifier},
            "files": files,
        }

    def test_single_text_pdf_uses_direct_download(self):
        """Test single Text PDF uses direct download strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "test_mag",
                [
                    {"name": "magazine.pdf", "format": "Text PDF", "size": "1000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            assert strategy["strategy"] == "direct"
            assert strategy["format"] == "Text PDF"
            assert strategy["file_count"] == 1
            assert "test_mag/magazine.pdf" in strategy["url"]
            assert strategy["is_collection"] is False

    def test_multiple_text_pdfs_uses_compress_url(self):
        """Test 3+ Text PDFs uses compress URL strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "collection_mag",
                [
                    {"name": "issue1.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue2.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue3.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue4.pdf", "format": "Text PDF", "size": "1000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            assert strategy["strategy"] == "compress"
            assert strategy["format"] == "Text PDF"
            assert strategy["file_count"] == 4
            assert IA_COMPRESS_BASE_URL in strategy["url"]
            assert "TEXT%20PDF" in strategy["url"]
            assert strategy["is_collection"] is True

    def test_two_text_pdfs_uses_direct_download(self):
        """Test 2 Text PDFs uses direct download (below threshold)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "two_issue_mag",
                [
                    {"name": "issue1.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue2.pdf", "format": "Text PDF", "size": "1000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            # With 2 files, should use direct (first file)
            assert strategy["strategy"] == "direct"
            assert strategy["file_count"] == 2

    def test_text_pdf_prioritized_over_regular_pdf(self):
        """Test Text PDF is preferred over Image Container PDF."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "mixed_mag",
                [
                    {"name": "image.pdf", "format": "Image Container PDF", "size": "5000000"},
                    {"name": "text.pdf", "format": "Text PDF", "size": "1000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            assert strategy["format"] == "Text PDF"
            assert "text.pdf" in strategy["url"]

    def test_fallback_to_regular_pdf_when_no_text_pdf(self):
        """Test falls back to regular PDF when Text PDF not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "image_only_mag",
                [
                    {"name": "scan.pdf", "format": "Image Container PDF", "size": "5000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            assert strategy["strategy"] == "direct"
            assert "pdf" in strategy["format"].lower()

    def test_no_suitable_format_returns_none_strategy(self):
        """Test returns 'none' strategy when no suitable formats available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            metadata = self._create_metadata(
                "no_pdf_item",
                [
                    {"name": "metadata.xml", "format": "Metadata", "size": "1000"},
                    {"name": "thumb.jpg", "format": "JPEG Thumb", "size": "5000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)

            assert strategy["strategy"] == "none"

    def test_compress_threshold_configurable(self):
        """Test compress threshold is used correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            # Default threshold is 3
            assert client.compress_threshold == 3

            # Exactly 3 files should trigger compress
            metadata = self._create_metadata(
                "three_issue",
                [
                    {"name": "issue1.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue2.pdf", "format": "Text PDF", "size": "1000000"},
                    {"name": "issue3.pdf", "format": "Text PDF", "size": "1000000"},
                ],
            )

            strategy = client._get_download_strategy(metadata)
            assert strategy["strategy"] == "compress"


class TestTextPDFConstants:
    """Test Internet Archive constants for Text PDF handling"""

    def test_text_pdf_formats_defined(self):
        """Test IA_TEXT_PDF_FORMATS constant exists and has expected values."""
        assert "Text PDF" in IA_TEXT_PDF_FORMATS
        assert len(IA_TEXT_PDF_FORMATS) >= 1

    def test_compress_url_defined(self):
        """Test IA_COMPRESS_BASE_URL constant is properly defined."""
        assert IA_COMPRESS_BASE_URL == "https://archive.org/compress"

    def test_download_url_defined(self):
        """Test IA_DOWNLOAD_BASE_URL constant is properly defined."""
        assert IA_DOWNLOAD_BASE_URL == "https://archive.org/download"
