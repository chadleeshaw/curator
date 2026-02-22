"""
Test suite for Internet Archive Download Client

Tests cover:
- Client initialization and configuration
- Job submission and tracking
- Download status management
- Completed downloads retrieval
- Download strategy selection (direct vs compress URL)
- Text PDF format prioritization
- Archive extraction (ZIP, TAR, TAR.GZ, GZIP)
- Download resume via HTTP Range requests
- Part meta sidecar file management
- Interrupted download recovery on startup
"""

import gzip
import json
import tarfile
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Path setup handled by conftest.py

from clients.internet_archive import InternetArchiveClient, DownloadJob
from core.constants.internet_archive import (
    IA_TEXT_PDF_FORMATS,
    IA_COMPRESS_BASE_URL,
    IA_DOWNLOAD_BASE_URL,
    IA_PART_META_EXTENSION,
    IA_DOWNLOAD_RESUME_ENABLED,
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
                    {
                        "name": "image.pdf",
                        "format": "Image Container PDF",
                        "size": "5000000",
                    },
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
                    {
                        "name": "scan.pdf",
                        "format": "Image Container PDF",
                        "size": "5000000",
                    },
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


class TestArchiveExtraction:
    """Test archive extraction functionality for ZIP, TAR, TAR.GZ, GZIP formats"""

    def _create_client(self, tmpdir: str) -> InternetArchiveClient:
        """Helper to create client with config."""
        config = {
            "name": "IA Client",
            "downloads_dir": tmpdir,
        }
        return InternetArchiveClient(config)

    def test_extract_zip_single_pdf(self):
        """Test extracting a single PDF from a ZIP archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create test ZIP with a PDF
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("magazine_issue1.pdf", b"fake pdf content")

            extracted = client._extract_zip(zip_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "magazine_issue1.pdf"
            assert extracted[0].exists()

    def test_extract_zip_multiple_pdfs(self):
        """Test extracting multiple PDFs from a ZIP archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create test ZIP with multiple PDFs
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("issue1.pdf", b"pdf 1")
                zf.writestr("issue2.pdf", b"pdf 2")
                zf.writestr("issue3.epub", b"epub content")

            extracted = client._extract_zip(zip_path, dest_dir)

            assert len(extracted) == 3
            names = {f.name for f in extracted}
            assert "issue1.pdf" in names
            assert "issue2.pdf" in names
            assert "issue3.epub" in names

    def test_extract_zip_filters_unsupported(self):
        """Test that extraction filters out unsupported file types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create ZIP with mixed content
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("document.pdf", b"pdf content")
                zf.writestr("image.jpg", b"jpg data")
                zf.writestr("metadata.xml", b"<xml/>")
                zf.writestr("readme.txt", b"text")

            extracted = client._extract_zip(zip_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "document.pdf"

    def test_extract_zip_skips_hidden_files(self):
        """Test that extraction skips hidden and system files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create ZIP with hidden files
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("document.pdf", b"pdf content")
                zf.writestr(".hidden.pdf", b"hidden pdf")
                zf.writestr("__MACOSX/document.pdf", b"macos resource")

            extracted = client._extract_zip(zip_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "document.pdf"

    def test_extract_zip_handles_duplicates(self):
        """Test that extraction handles duplicate filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create ZIP with nested structure (same base names)
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("folder1/issue.pdf", b"pdf 1")
                zf.writestr("folder2/issue.pdf", b"pdf 2")

            extracted = client._extract_zip(zip_path, dest_dir)

            assert len(extracted) == 2
            # One should have _1 suffix
            names = [f.name for f in extracted]
            assert "issue.pdf" in names
            assert "issue_1.pdf" in names

    def test_extract_tar_gz(self):
        """Test extracting PDFs from a TAR.GZ archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create TAR.GZ with PDFs
            tar_gz_path = Path(tmpdir) / "test.tar.gz"
            with tarfile.open(tar_gz_path, "w:gz") as tf:
                # Create a temp PDF file to add
                pdf_path = Path(tmpdir) / "temp_issue.pdf"
                pdf_path.write_bytes(b"fake pdf data")
                tf.add(pdf_path, arcname="magazine_2024.pdf")

            extracted = client._extract_tar_gz(tar_gz_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "magazine_2024.pdf"
            assert extracted[0].exists()

    def test_extract_tar(self):
        """Test extracting PDFs from a plain TAR archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create TAR with PDF
            tar_path = Path(tmpdir) / "test.tar"
            with tarfile.open(tar_path, "w") as tf:
                pdf_path = Path(tmpdir) / "temp_issue.pdf"
                pdf_path.write_bytes(b"fake pdf data")
                tf.add(pdf_path, arcname="archive_doc.pdf")

            extracted = client._extract_tar(tar_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "archive_doc.pdf"

    def test_extract_gzip_single_file(self):
        """Test extracting a GZIP compressed file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create GZIP with PDF
            gz_path = Path(tmpdir) / "document.pdf.gz"
            with gzip.open(gz_path, "wb") as f:
                f.write(b"fake pdf content")

            extracted = client._extract_gzip(gz_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "document.pdf"
            assert extracted[0].exists()

    def test_extract_gzip_default_extension(self):
        """Test GZIP extraction defaults to .pdf when no extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create GZIP with no extension in stem
            gz_path = Path(tmpdir) / "document.gz"
            with gzip.open(gz_path, "wb") as f:
                f.write(b"fake pdf content")

            extracted = client._extract_gzip(gz_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].name == "document.pdf"

    def test_extract_archive_dispatcher_zip(self):
        """Test _extract_archive correctly dispatches to ZIP handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create test ZIP
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("file.pdf", b"content")

            extracted = client._extract_archive(zip_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0].suffix == ".pdf"
            # Archive should be deleted after extraction
            assert not zip_path.exists()

    def test_extract_archive_dispatcher_tar_gz(self):
        """Test _extract_archive correctly dispatches to TAR.GZ handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create TAR.GZ
            tar_gz_path = Path(tmpdir) / "test.tar.gz"
            with tarfile.open(tar_gz_path, "w:gz") as tf:
                pdf_path = Path(tmpdir) / "temp.pdf"
                pdf_path.write_bytes(b"pdf data")
                tf.add(pdf_path, arcname="doc.pdf")

            extracted = client._extract_archive(tar_gz_path, dest_dir)

            assert len(extracted) == 1
            assert not tar_gz_path.exists()  # Archive deleted

    def test_extract_archive_unknown_format(self):
        """Test _extract_archive returns original for unknown formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create file with unknown extension
            unknown_path = Path(tmpdir) / "file.xyz"
            unknown_path.write_bytes(b"some data")

            extracted = client._extract_archive(unknown_path, dest_dir)

            assert len(extracted) == 1
            assert extracted[0] == unknown_path
            assert unknown_path.exists()  # Original preserved

    def test_extract_archive_handles_error(self):
        """Test _extract_archive returns original on extraction error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            dest_dir = Path(tmpdir) / "extracted"
            dest_dir.mkdir()

            # Create invalid ZIP file
            bad_zip = Path(tmpdir) / "bad.zip"
            bad_zip.write_bytes(b"not a real zip")

            extracted = client._extract_archive(bad_zip, dest_dir)

            # Should return original on error
            assert len(extracted) == 1
            assert extracted[0] == bad_zip
            assert bad_zip.exists()


class TestDownloadResume:  # pylint: disable=too-many-public-methods
    """Test download resume via HTTP Range requests and .part.meta sidecar files"""

    def _create_client(self, tmpdir: str) -> InternetArchiveClient:
        """Helper to create client with config."""
        config = {
            "name": "IA Client",
            "downloads_dir": tmpdir,
        }
        return InternetArchiveClient(config)

    # --- Part meta helpers ---

    def test_save_and_load_part_meta(self):
        """Test saving and loading resume metadata round-trips correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta_path = Path(tmpdir) / "test.pdf.part.meta"

            client._save_part_meta(
                meta_path,
                download_url="https://archive.org/download/test/file.pdf",
                expected_size=1048576,
                etag='"abc123"',
                last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
            )

            meta = client._load_part_meta(meta_path)

            assert meta is not None
            assert meta["url"] == "https://archive.org/download/test/file.pdf"
            assert meta["expected_size"] == 1048576
            assert meta["etag"] == '"abc123"'
            assert meta["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"
            assert "created_at" in meta

    def test_load_part_meta_missing_file(self):
        """Test loading meta from a non-existent file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta_path = Path(tmpdir) / "nonexistent.part.meta"

            result = client._load_part_meta(meta_path)

            assert result is None

    def test_load_part_meta_corrupt_json(self):
        """Test loading corrupt meta file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta_path = Path(tmpdir) / "corrupt.part.meta"
            meta_path.write_text("not valid json {{{", encoding="utf-8")

            result = client._load_part_meta(meta_path)

            assert result is None

    def test_load_part_meta_missing_required_fields(self):
        """Test loading meta with missing required fields returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta_path = Path(tmpdir) / "incomplete.part.meta"
            meta_path.write_text(json.dumps({"etag": "abc"}), encoding="utf-8")

            result = client._load_part_meta(meta_path)

            assert result is None

    # --- Part meta validation ---

    def test_validate_part_meta_matching_etag(self):
        """Test validation passes when ETag matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta = {"etag": '"abc123"', "expected_size": 1000}
            headers = {"ETag": '"abc123"', "Content-Length": "1000"}

            assert client._validate_part_meta(meta, headers) is True

    def test_validate_part_meta_mismatched_etag(self):
        """Test validation fails when ETag differs (content changed on server)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta = {"etag": '"abc123"', "expected_size": 1000}
            headers = {"ETag": '"def456"', "Content-Length": "1000"}

            assert client._validate_part_meta(meta, headers) is False

    def test_validate_part_meta_mismatched_content_length(self):
        """Test validation fails when Content-Length differs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta = {"etag": None, "expected_size": 1000}
            headers = {"Content-Length": "2000"}

            assert client._validate_part_meta(meta, headers) is False

    def test_validate_part_meta_no_etag_same_length(self):
        """Test validation passes when no ETag but Content-Length matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta = {"etag": None, "expected_size": 5000}
            headers = {"Content-Length": "5000"}

            assert client._validate_part_meta(meta, headers) is True

    def test_validate_part_meta_no_headers(self):
        """Test validation passes when server provides no comparable headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            meta = {"etag": None, "expected_size": None}
            headers = {}

            assert client._validate_part_meta(meta, headers) is True

    # --- Resume support check ---

    def test_check_resume_support_accepts_bytes(self):
        """Test resume check detects Accept-Ranges: bytes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            mock_resp = Mock()
            mock_resp.headers = {"Accept-Ranges": "bytes"}

            with patch("clients.internet_archive.requests.head", return_value=mock_resp):
                assert client._check_resume_support("https://example.com/file.pdf") is True

    def test_check_resume_support_no_ranges(self):
        """Test resume check returns False when server doesn't support ranges."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            mock_resp = Mock()
            mock_resp.headers = {"Accept-Ranges": "none"}

            with patch("clients.internet_archive.requests.head", return_value=mock_resp):
                assert client._check_resume_support("https://example.com/file.pdf") is False

    def test_check_resume_support_head_fails(self):
        """Test resume check returns False when HEAD request fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            import requests

            with patch(
                "clients.internet_archive.requests.head",
                side_effect=requests.exceptions.ConnectionError("timeout"),
            ):
                assert client._check_resume_support("https://example.com/file.pdf") is False

    # --- Cleanup helpers ---

    def test_cleanup_part_files_removes_both(self):
        """Test cleanup removes both .part and .part.meta files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file = Path(tmpdir) / "test.pdf.part"
            meta_file = Path(tmpdir) / "test.pdf.part.meta"

            part_file.write_bytes(b"partial data")
            meta_file.write_text('{"url": "test"}', encoding="utf-8")

            client._cleanup_part_files(part_file)

            assert not part_file.exists()
            assert not meta_file.exists()

    def test_cleanup_part_files_missing_meta(self):
        """Test cleanup works when only .part file exists (no .meta)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file = Path(tmpdir) / "test.pdf.part"
            part_file.write_bytes(b"partial data")

            # Should not raise
            client._cleanup_part_files(part_file)

            assert not part_file.exists()

    # --- Recovery on startup ---

    def test_recover_finds_valid_part_meta_pairs(self):
        """Test recovery finds and resubmits interrupted downloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            # Create a valid .part + .part.meta pair
            part_file = Path(tmpdir) / "Magazine_Title.pdf.part"
            meta_file = Path(tmpdir) / "Magazine_Title.pdf.part.meta"
            part_file.write_bytes(b"x" * 1024)  # 1KB partial
            meta = {
                "url": "https://archive.org/download/test_mag/magazine.pdf",
                "expected_size": 10240,
                "etag": '"abc"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 1
            assert mock_submit.call_count == 1

            # Verify a job was created
            assert len(client._jobs) == 1
            job = list(client._jobs.values())[0]
            assert job.identifier == "test_mag"
            assert job.download_url == meta["url"]

    def test_recover_skips_orphaned_meta_without_part(self):
        """Test recovery cleans up .meta files with no corresponding .part file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            # Only create .meta, no .part
            meta_file = Path(tmpdir) / "Orphan.pdf.part.meta"
            meta = {
                "url": "https://archive.org/download/orphan/file.pdf",
                "expected_size": 5000,
                "etag": None,
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with patch.object(client._executor, "submit"):
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert not meta_file.exists()  # Orphaned meta cleaned up

    def test_recover_skips_corrupt_meta(self):
        """Test recovery cleans up corrupt meta files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            part_file = Path(tmpdir) / "Bad.pdf.part"
            meta_file = Path(tmpdir) / "Bad.pdf.part.meta"
            part_file.write_bytes(b"partial")
            meta_file.write_text("not json", encoding="utf-8")

            with patch.object(client._executor, "submit"):
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert not part_file.exists()  # Cleaned up
            assert not meta_file.exists()  # Cleaned up

    def test_recover_returns_zero_when_resume_disabled(self):
        """Test recovery returns 0 when resume is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            with patch("clients.internet_archive.IA_DOWNLOAD_RESUME_ENABLED", False):
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0

    def test_recover_multiple_interrupted_downloads(self):
        """Test recovery handles multiple interrupted downloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            for i in range(3):
                part_file = Path(tmpdir) / f"Magazine_{i}.pdf.part"
                meta_file = Path(tmpdir) / f"Magazine_{i}.pdf.part.meta"
                part_file.write_bytes(b"x" * 512)
                meta = {
                    "url": f"https://archive.org/download/mag_{i}/file.pdf",
                    "expected_size": 10240,
                    "etag": None,
                    "last_modified": None,
                    "created_at": 1000000,
                }
                meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with patch.object(client._executor, "submit"):
                recovered = client.recover_interrupted_downloads()

            assert recovered == 3
            assert len(client._jobs) == 3

    # --- Constants ---

    def test_resume_constants_defined(self):
        """Test resume-related constants are properly defined."""
        assert IA_DOWNLOAD_RESUME_ENABLED is True
        assert IA_PART_META_EXTENSION == ".part.meta"

    def test_part_meta_in_incomplete_patterns(self):
        """Test .part.meta is in INCOMPLETE_DOWNLOAD_PATTERNS."""
        from core.constants.files import INCOMPLETE_DOWNLOAD_PATTERNS

        assert ".part.meta" in INCOMPLETE_DOWNLOAD_PATTERNS


class TestDownloadResumeDownloadFilePaths:  # pylint: disable=too-many-public-methods
    """
    Test the resume-specific branches inside _download_file that are NOT covered
    by TestDownloadResume. These tests drive _download_file directly by mocking
    the HTTP layer and the IA metadata call so we never hit the network.
    """

    def _create_client(self, tmpdir: str) -> InternetArchiveClient:
        config = {"name": "IA Client", "downloads_dir": tmpdir}
        return InternetArchiveClient(config)

    def _make_strategy(self, tmpdir: str, filename: str = "file.pdf") -> dict:
        """Return a minimal 'direct' strategy dict for a single PDF."""
        return {
            "strategy": "direct",
            "format": "Text PDF",
            "files": [{"name": filename, "format": "Text PDF", "size": "10240"}],
            "url": f"https://archive.org/download/test_mag/{filename}",
            "is_collection": False,
            "file_count": 1,
            "file_info": {"name": filename, "format": "Text PDF", "size": "10240"},
        }

    def _make_job(self, tmpdir: str, title: str = "Test Magazine") -> "DownloadJob":
        return DownloadJob(
            job_id="test_job_id",
            identifier="test_mag",
            title=title,
            dest_path=tmpdir,
        )

    # ------------------------------------------------------------------
    # 1. Fresh download: no .part file → _save_part_meta called once
    # ------------------------------------------------------------------

    def test_fresh_download_saves_part_meta(self):
        """On first attempt with no existing .part file, _save_part_meta is
        called once with the response headers (ETag, Last-Modified)."""
        from requests.structures import CaseInsensitiveDict

        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            mock_response = Mock()
            mock_response.status_code = 200
            # Use CaseInsensitiveDict so .get("content-length") works like real requests
            mock_response.headers = CaseInsensitiveDict(
                {
                    "Content-Length": "10240",
                    "ETag": '"etag123"',
                    "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                }
            )
            # Stream: emit one chunk then stop
            mock_response.iter_content = Mock(return_value=iter([b"x" * 10240]))
            mock_response.raise_for_status = Mock()

            with (
                patch("clients.internet_archive.get_item"),
                patch("clients.internet_archive.requests.get", return_value=mock_response),
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch.object(client, "_save_part_meta") as mock_save_meta,
            ):
                client._download_file(job)

            # _save_part_meta must be called exactly once
            mock_save_meta.assert_called_once()
            call_kwargs = mock_save_meta.call_args
            assert call_kwargs.kwargs["etag"] == '"etag123"'
            assert call_kwargs.kwargs["expected_size"] == 10240
            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED

    # ------------------------------------------------------------------
    # 2. Server returns 200 instead of 206 after Range request → overwrite
    # ------------------------------------------------------------------

    def test_server_returns_200_after_range_request_restarts_download(self):
        """
        When a .part + .meta exist and _check_resume_support / _validate_part_meta
        both pass, we send a Range header. If the server responds 200 (instead of
        206), the code must:
          - reset resume_offset to 0
          - use 'wb' (overwrite) file mode
          - re-save part meta with fresh Content-Length
        """
        from requests.structures import CaseInsensitiveDict

        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            partial_file.write_bytes(b"x" * 1024)  # 1 KB already downloaded
            saved_meta = {
                "url": "https://archive.org/download/test_mag/file.pdf",
                "expected_size": 10240,
                "etag": '"etag123"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(saved_meta), encoding="utf-8")

            # HEAD for _check_resume_support
            head_resp_support = Mock()
            head_resp_support.headers = {"Accept-Ranges": "bytes"}

            # HEAD for staleness check inside loop
            head_resp_stale = Mock()
            head_resp_stale.headers = CaseInsensitiveDict({"ETag": '"etag123"', "Content-Length": "10240"})

            # GET: server ignores Range, returns 200 with full content
            get_response = Mock()
            get_response.status_code = 200  # NOT 206
            get_response.headers = CaseInsensitiveDict(
                {
                    "Content-Length": "10240",
                    "ETag": '"etag123"',
                    "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                }
            )
            get_response.iter_content = Mock(return_value=iter([b"y" * 10240]))
            get_response.raise_for_status = Mock()

            # The dedup while-loop checks partial_file.exists() before the download
            # loop starts. We skip it by returning False on the first call for .part
            # paths (dedup check), then True on subsequent calls (resume check).
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch("clients.internet_archive.get_item"),
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch(
                    "clients.internet_archive.requests.head",
                    side_effect=[head_resp_support, head_resp_stale],
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED
            # When server returns 200 after a resume attempt, resume_offset is reset
            # to 0 and downloaded_size reflects the full 10240 bytes.
            assert job.downloaded_size == 10240

    # ------------------------------------------------------------------
    # 3. HEAD staleness check fails with RequestException → clean up & restart
    # ------------------------------------------------------------------

    def test_inner_head_request_exception_cleans_up_and_restarts(self):
        """
        When the inner HEAD request (for staleness validation inside the retry loop)
        raises RequestException, the partial download is cleaned up and a fresh
        download proceeds without a Range header.
        """
        import requests as req_lib

        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            partial_file.write_bytes(b"x" * 512)
            saved_meta = {
                "url": "https://archive.org/download/test_mag/file.pdf",
                "expected_size": 10240,
                "etag": '"etag"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(saved_meta), encoding="utf-8")

            cleanup_called = []

            original_cleanup = client._cleanup_part_files

            def tracking_cleanup(pf):
                cleanup_called.append(str(pf))
                original_cleanup(pf)

            get_response = Mock()
            get_response.status_code = 200
            get_response.headers = {"Content-Length": "10240"}
            get_response.iter_content = Mock(return_value=iter([b"z" * 10240]))
            get_response.raise_for_status = Mock()

            # Skip the dedup loop's .part existence check on first call
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch.object(client, "_cleanup_part_files", side_effect=tracking_cleanup),
                patch(
                    "clients.internet_archive.requests.head",
                    side_effect=[
                        Mock(headers={"Accept-Ranges": "bytes"}),
                        req_lib.exceptions.ConnectionError("timeout"),
                    ],
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            # _cleanup_part_files must have been called (to discard the stale partial)
            assert len(cleanup_called) >= 1, "Expected _cleanup_part_files to be called"
            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED

    # ------------------------------------------------------------------
    # 4. _validate_part_meta returns False → clean up & restart from 0
    # ------------------------------------------------------------------

    def test_stale_content_triggers_cleanup_and_full_restart(self):
        """
        When _validate_part_meta returns False (ETag mismatch), the partial
        download is cleaned up and a fresh full download is started (no Range header).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            partial_file.write_bytes(b"x" * 512)
            saved_meta = {
                "url": "https://archive.org/download/test_mag/file.pdf",
                "expected_size": 10240,
                "etag": '"old-etag"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(saved_meta), encoding="utf-8")

            # Server now returns a different ETag → content changed
            head_for_support = Mock(headers={"Accept-Ranges": "bytes"})
            head_for_stale = Mock(headers={"ETag": '"new-etag"', "Content-Length": "12000"})

            get_response = Mock()
            get_response.status_code = 200
            get_response.headers = {"Content-Length": "12000"}
            get_response.iter_content = Mock(return_value=iter([b"z" * 12000]))
            get_response.raise_for_status = Mock()

            cleanup_called = []

            # Skip the dedup loop's .part existence check on first call
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch.object(
                    client,
                    "_cleanup_part_files",
                    side_effect=lambda pf: cleanup_called.append(str(pf)),
                ),
                patch(
                    "clients.internet_archive.requests.head",
                    side_effect=[head_for_support, head_for_stale],
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            assert len(cleanup_called) >= 1, "Expected _cleanup_part_files on stale content"
            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED

    # ------------------------------------------------------------------
    # 5. _check_resume_support returns False → clean up & restart
    # ------------------------------------------------------------------

    def test_server_no_range_support_cleans_up_and_restarts(self):
        """
        When _check_resume_support returns False, the existing .part file is
        cleaned up and the download restarts without a Range header.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            partial_file.write_bytes(b"x" * 512)
            saved_meta = {
                "url": "https://archive.org/download/test_mag/file.pdf",
                "expected_size": 10240,
                "etag": '"etag"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(saved_meta), encoding="utf-8")

            get_response = Mock()
            get_response.status_code = 200
            get_response.headers = {"Content-Length": "10240"}
            get_response.iter_content = Mock(return_value=iter([b"z" * 10240]))
            get_response.raise_for_status = Mock()

            cleanup_called = []

            # Skip the dedup loop's .part existence check on first call
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch.object(
                    client,
                    "_cleanup_part_files",
                    side_effect=lambda pf: cleanup_called.append(str(pf)),
                ),
                # HEAD returns "none" → server does not support Range
                patch(
                    "clients.internet_archive.requests.head",
                    return_value=Mock(headers={"Accept-Ranges": "none"}),
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            assert len(cleanup_called) >= 1, "Expected cleanup when server has no Range support"
            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED

    # ------------------------------------------------------------------
    # 6. .part exists but meta is missing/corrupt → clean up & restart
    # ------------------------------------------------------------------

    def test_part_file_without_valid_meta_cleans_up_and_restarts(self):
        """
        When a .part file exists but _load_part_meta returns None (missing or
        corrupt meta), _cleanup_part_files is called and the download restarts
        from the beginning.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            partial_file.write_bytes(b"x" * 512)
            meta_file.write_text("not valid json {{", encoding="utf-8")  # corrupt

            get_response = Mock()
            get_response.status_code = 200
            get_response.headers = {"Content-Length": "10240"}
            get_response.iter_content = Mock(return_value=iter([b"z" * 10240]))
            get_response.raise_for_status = Mock()

            cleanup_called = []

            # Skip the dedup loop's .part existence check on first call
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch.object(
                    client,
                    "_cleanup_part_files",
                    side_effect=lambda pf: cleanup_called.append(str(pf)),
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            assert len(cleanup_called) >= 1, "Expected cleanup for corrupt meta"
            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED

    # ------------------------------------------------------------------
    # 7. Compress download: .part cleaned up between retries
    # ------------------------------------------------------------------

    def test_compress_download_cleans_part_on_request_exception(self):
        """
        For compress (dynamic ZIP) downloads, can_resume is False.  On a
        RequestException the .part file must be cleaned up between retries
        (not preserved like direct downloads).
        """
        import requests as req_lib

        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)

            compress_strategy = {
                "strategy": "compress",
                "format": "Text PDF",
                "files": [
                    {"name": "a.pdf", "format": "Text PDF", "size": "5120"},
                    {"name": "b.pdf", "format": "Text PDF", "size": "5120"},
                    {"name": "c.pdf", "format": "Text PDF", "size": "5120"},
                ],
                "url": "https://archive.org/compress/test_mag/formats=TEXT%20PDF",
                "is_collection": True,
                "file_count": 3,
            }

            cleanup_called = []

            with (
                patch.object(client, "_get_download_strategy", return_value=compress_strategy),
                patch.object(
                    client,
                    "_cleanup_part_files",
                    side_effect=lambda pf: cleanup_called.append(str(pf)),
                ),
                patch(
                    "clients.internet_archive.requests.get",
                    side_effect=req_lib.exceptions.ConnectionError("network down"),
                ),
                patch("clients.internet_archive.time.sleep"),  # skip retry delays
            ):
                client._download_file(job)

            from core.constants.internet_archive import IA_STATUS_FAILED

            assert job.status == IA_STATUS_FAILED
            # cleanup must be called on every failed attempt for compress downloads
            assert len(cleanup_called) > 0, "Expected .part cleanup for compress failure"

    # ------------------------------------------------------------------
    # 8. 206 with no Content-Length → expected_size unchanged
    # ------------------------------------------------------------------

    def test_206_without_content_length_keeps_existing_expected_size(self):
        """
        When server returns 206 but omits Content-Length, job.expected_size
        should remain at its prior value (from metadata) rather than being reset.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            # safe_title preserves spaces: "Test Magazine" → "Test Magazine.pdf.part"
            partial_file = Path(tmpdir) / "Test Magazine.pdf.part"
            meta_file = Path(tmpdir) / "Test Magazine.pdf.part.meta"
            resume_offset = 2048
            partial_file.write_bytes(b"x" * resume_offset)
            saved_meta = {
                "url": "https://archive.org/download/test_mag/file.pdf",
                "expected_size": 10240,
                "etag": '"etag"',
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(saved_meta), encoding="utf-8")

            get_response = Mock()
            get_response.status_code = 206  # Resume accepted
            get_response.headers = {}  # No Content-Length in 206 response
            remaining = 10240 - resume_offset
            get_response.iter_content = Mock(return_value=iter([b"y" * remaining]))
            get_response.raise_for_status = Mock()

            # Skip the dedup loop's .part existence check on first call
            _part_exists_calls = [0]
            _real_exists = Path.exists

            def _selective_exists(self_path):
                if str(self_path).endswith(".part"):
                    _part_exists_calls[0] += 1
                    if _part_exists_calls[0] == 1:
                        return False  # dedup loop: pretend .part doesn't exist yet
                return _real_exists(self_path)

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch(
                    "clients.internet_archive.requests.head",
                    side_effect=[
                        Mock(headers={"Accept-Ranges": "bytes"}),
                        Mock(headers={"ETag": '"etag"', "Content-Length": "10240"}),
                    ],
                ),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("pathlib.Path.exists", _selective_exists),
            ):
                client._download_file(job)

            from core.constants.internet_archive import IA_STATUS_COMPLETED

            assert job.status == IA_STATUS_COMPLETED
            # expected_size must not have been zeroed out; it should remain ≥ the
            # offset we started from (the 206 path only updates it when Content-Length present)
            assert job.expected_size >= resume_offset

    # ------------------------------------------------------------------
    # 9. Empty file after streaming raises IOError
    # ------------------------------------------------------------------

    def test_empty_download_raises_ioerror_and_marks_failed(self):
        """
        If all streaming chunks are empty so the .part file ends up 0 bytes,
        the download must be marked failed (IOError path at line 828).
        """
        import requests as req_lib

        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            job = self._make_job(tmpdir)
            strategy = self._make_strategy(tmpdir)

            get_response = Mock()
            get_response.status_code = 200
            get_response.headers = {"Content-Length": "10240"}
            # No chunks at all → file stays at 0 bytes
            get_response.iter_content = Mock(return_value=iter([]))
            get_response.raise_for_status = Mock()

            with (
                patch.object(client, "_get_download_strategy", return_value=strategy),
                patch("clients.internet_archive.requests.get", return_value=get_response),
                patch("clients.internet_archive.time.sleep"),
            ):
                client._download_file(job)

            from core.constants.internet_archive import IA_STATUS_FAILED

            assert job.status == IA_STATUS_FAILED


class TestRecoverInterruptedDownloadsSSRFGuards:
    """
    Test the SSRF-prevention guards added to recover_interrupted_downloads.
    These are the most security-critical paths in the resume feature.
    """

    def _create_client(self, tmpdir: str) -> InternetArchiveClient:
        config = {"name": "IA Client", "downloads_dir": tmpdir}
        return InternetArchiveClient(config)

    def _write_part_and_meta(self, tmpdir: str, filename: str, url: str):
        """Create a .part + .meta pair with the given URL."""
        part_file = Path(tmpdir) / filename
        meta_file = Path(tmpdir) / (filename + ".meta")
        part_file.write_bytes(b"x" * 512)
        meta = {
            "url": url,
            "expected_size": 10240,
            "etag": None,
            "last_modified": None,
            "created_at": 1000000,
        }
        meta_file.write_text(json.dumps(meta), encoding="utf-8")
        return part_file, meta_file

    # ------------------------------------------------------------------
    # URL prefix guard
    # ------------------------------------------------------------------

    def test_recover_rejects_non_archive_org_url(self):
        """Meta file with a URL pointing to a non-archive.org host is
        rejected and both files are cleaned up (SSRF guard)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file, meta_file = self._write_part_and_meta(
                tmpdir,
                "Evil.pdf.part",
                "https://evil.example.com/download/test_mag/file.pdf",
            )

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert mock_submit.call_count == 0
            # Both files must be cleaned up
            assert not part_file.exists(), "Expected .part to be cleaned up"
            assert not meta_file.exists(), "Expected .meta to be cleaned up"

    def test_recover_rejects_url_without_download_segment(self):
        """Meta file with a well-formed archive.org URL that lacks /download/
        cannot yield an identifier and must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file, meta_file = self._write_part_and_meta(
                tmpdir,
                "Bad.pdf.part",
                "https://archive.org/details/test_mag/file.pdf",  # /details/ not /download/
            )

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert mock_submit.call_count == 0
            assert not part_file.exists()
            assert not meta_file.exists()

    # ------------------------------------------------------------------
    # Identifier regex guard
    # ------------------------------------------------------------------

    def test_recover_rejects_path_traversal_identifier(self):
        """Meta file URL with a path-traversal identifier (../etc) is
        rejected (identifier regex guard)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file, meta_file = self._write_part_and_meta(
                tmpdir,
                "Traversal.pdf.part",
                "https://archive.org/download/../etc/passwd/file.pdf",
            )

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert mock_submit.call_count == 0
            assert not part_file.exists()
            assert not meta_file.exists()

    def test_recover_rejects_identifier_with_shell_chars(self):
        """Identifier containing shell metacharacters is rejected by the
        identifier regex guard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)
            part_file, meta_file = self._write_part_and_meta(
                tmpdir,
                "Shell.pdf.part",
                "https://archive.org/download/evil;rm -rf /;/file.pdf",
            )

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert mock_submit.call_count == 0
            assert not part_file.exists()
            assert not meta_file.exists()

    def test_recover_accepts_valid_identifier_formats(self):
        """Valid IA identifier formats (alphanumeric, dots, dashes, underscores)
        pass the regex guard and are successfully recovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            valid_identifiers = [
                "simple",
                "with-dashes",
                "with_underscores",
                "with.dots",
                "Mixed123",
                "A1B2C3",
            ]

            for identifier in valid_identifiers:
                filename = f"{identifier}.pdf.part"
                part_file = Path(tmpdir) / filename
                meta_file = Path(tmpdir) / (filename + ".meta")
                part_file.write_bytes(b"x" * 512)
                meta = {
                    "url": f"https://archive.org/download/{identifier}/file.pdf",
                    "expected_size": 10240,
                    "etag": None,
                    "last_modified": None,
                    "created_at": 1000000,
                }
                meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with patch.object(client._executor, "submit"):
                recovered = client.recover_interrupted_downloads()

            assert recovered == len(valid_identifiers)

    # ------------------------------------------------------------------
    # Zero-byte .part file
    # ------------------------------------------------------------------

    def test_recover_skips_zero_byte_part_file(self):
        """A .part file that exists but is 0 bytes is treated as an orphan
        and only the .meta is cleaned up (no resubmit)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._create_client(tmpdir)

            part_file = Path(tmpdir) / "Zero.pdf.part"
            meta_file = Path(tmpdir) / "Zero.pdf.part.meta"
            part_file.write_bytes(b"")  # Zero bytes
            meta = {
                "url": "https://archive.org/download/zero_mag/file.pdf",
                "expected_size": 10240,
                "etag": None,
                "last_modified": None,
                "created_at": 1000000,
            }
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with patch.object(client._executor, "submit") as mock_submit:
                recovered = client.recover_interrupted_downloads()

            assert recovered == 0
            assert mock_submit.call_count == 0
            # The orphaned meta must be cleaned up
            assert not meta_file.exists(), "Expected orphaned .meta to be removed"
