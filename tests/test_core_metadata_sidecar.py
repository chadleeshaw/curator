"""Tests for metadata sidecar file operations"""

import json
import tempfile
from pathlib import Path

from core.metadata_sidecar import (
    create_sidecar_file,
    read_sidecar_file,
    delete_sidecar_file,
    has_sidecar_file,
    SIDECAR_SUFFIX,
)


class TestMetadataSidecar:
    """Test sidecar metadata file operations"""

    def test_create_and_read_sidecar(self):
        """Test creating and reading a sidecar file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test_magazine.pdf"
            test_file.touch()

            # Create sidecar with minimal required fields
            result = create_sidecar_file(
                test_file,
                tracking_id=123,
                tracking_title="Test Magazine",
            )
            assert result is True

            # Read it back
            metadata = read_sidecar_file(test_file)
            assert metadata is not None
            assert metadata["tracking_id"] == 123
            assert metadata["tracking_title"] == "Test Magazine"
            assert "downloaded_at" in metadata
            assert metadata["original_filename"] == "test_magazine.pdf"

    def test_create_sidecar_with_all_fields(self):
        """Test creating sidecar with all optional fields"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            result = create_sidecar_file(
                test_file,
                tracking_id=456,
                tracking_title="Full Magazine",
                submission_id=789,
                category="Magazines",
                language="English",
                country="US",
            )
            assert result is True

            metadata = read_sidecar_file(test_file)
            assert metadata["tracking_id"] == 456
            assert metadata["tracking_title"] == "Full Magazine"
            assert metadata["submission_id"] == 789
            assert metadata["category"] == "Magazines"
            assert metadata["language"] == "English"
            assert metadata["country"] == "US"

    def test_read_nonexistent_sidecar(self):
        """Test reading when sidecar doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "nosidecar.pdf"
            test_file.touch()

            metadata = read_sidecar_file(test_file)
            assert metadata is None

    def test_read_invalid_json_sidecar(self):
        """Test reading sidecar with invalid JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            # Create invalid sidecar
            sidecar_path = test_file.with_suffix(test_file.suffix + SIDECAR_SUFFIX)
            with open(sidecar_path, "w") as f:
                f.write("{invalid json")

            metadata = read_sidecar_file(test_file)
            assert metadata is None

    def test_read_sidecar_missing_required_fields(self):
        """Test reading sidecar without required fields"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            # Create sidecar without required fields
            sidecar_path = test_file.with_suffix(test_file.suffix + SIDECAR_SUFFIX)
            with open(sidecar_path, "w") as f:
                json.dump({"some_field": "value"}, f)

            metadata = read_sidecar_file(test_file)
            assert metadata is None

    def test_delete_sidecar(self):
        """Test deleting sidecar file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            # Create sidecar
            create_sidecar_file(test_file, tracking_id=111, tracking_title="Test")
            assert has_sidecar_file(test_file) is True

            # Delete it
            result = delete_sidecar_file(test_file)
            assert result is True
            assert has_sidecar_file(test_file) is False

    def test_delete_nonexistent_sidecar(self):
        """Test deleting when sidecar doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            # Should succeed even if sidecar doesn't exist
            result = delete_sidecar_file(test_file)
            assert result is True

    def test_has_sidecar_file(self):
        """Test checking for sidecar existence"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.pdf"
            test_file.touch()

            # Initially no sidecar
            assert has_sidecar_file(test_file) is False

            # Create sidecar
            create_sidecar_file(test_file, tracking_id=222, tracking_title="Test")
            assert has_sidecar_file(test_file) is True

            # Delete and check again
            delete_sidecar_file(test_file)
            assert has_sidecar_file(test_file) is False

    def test_sidecar_with_complex_filename(self):
        """Test sidecar with complex filename containing special characters"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "Magazine (2024) [Special Edition].pdf"
            test_file.touch()

            create_sidecar_file(test_file, tracking_id=333, tracking_title="Complex")
            assert has_sidecar_file(test_file) is True

            metadata = read_sidecar_file(test_file)
            assert metadata is not None
            assert metadata["original_filename"] == "Magazine (2024) [Special Edition].pdf"

    def test_sidecar_with_epub_file(self):
        """Test sidecar with EPUB file extension"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "book.epub"
            test_file.touch()

            create_sidecar_file(test_file, tracking_id=444, tracking_title="EPUB Test")
            assert has_sidecar_file(test_file) is True

            # Check sidecar filename
            sidecar_path = test_file.with_suffix(test_file.suffix + SIDECAR_SUFFIX)
            assert sidecar_path.exists()
            assert sidecar_path.name == "book.epub.curator_meta.json"

            metadata = read_sidecar_file(test_file)
            assert metadata["tracking_id"] == 444
