#!/usr/bin/env python3
"""
Test suite for services.file_importer module
"""

from pathlib import Path

# Path setup handled by conftest.py

from core.constants.files import IMPORT_MARKER_FILE
from services.importer.importer import FileImporter


def test_file_importer_initialization():
    """Test FileImporter initialization"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        assert importer is not None


def test_import_single_file():
    """Test importing a single file"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Should have import-related methods
        assert hasattr(importer, "title_matcher")
        assert hasattr(importer, "parser")
        assert hasattr(importer, "organizer")


def test_create_import_marker():
    """Test creating import marker file"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Create a test folder
        test_folder = downloads_dir / "test_import"
        test_folder.mkdir()

        # Create marker
        result = importer._create_import_marker(test_folder)

        assert result is True
        assert (test_folder / IMPORT_MARKER_FILE).exists()
        assert (test_folder / IMPORT_MARKER_FILE).is_file()


def test_remove_import_marker():
    """Test removing import marker file"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Create a test folder with marker
        test_folder = downloads_dir / "test_import"
        test_folder.mkdir()
        marker_file = test_folder / IMPORT_MARKER_FILE
        marker_file.touch()

        assert marker_file.exists()

        # Remove marker
        importer._remove_import_marker(test_folder)

        assert not marker_file.exists()
        assert test_folder.exists()  # Folder should still exist


def test_remove_nonexistent_marker():
    """Test removing marker when it doesn't exist (should not error)"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Create a test folder without marker
        test_folder = downloads_dir / "test_import"
        test_folder.mkdir()

        # Should not raise error
        importer._remove_import_marker(test_folder)

        assert test_folder.exists()


def test_marker_survives_file_operations():
    """Test that marker file persists during file operations"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Create a test folder with marker and some files
        test_folder = downloads_dir / "test_import"
        test_folder.mkdir()
        importer._create_import_marker(test_folder)

        # Add some files
        (test_folder / "file1.pdf").touch()
        (test_folder / "file2.txt").touch()

        # Marker should still exist
        assert (test_folder / IMPORT_MARKER_FILE).exists()

        # Remove a file
        (test_folder / "file2.txt").unlink()

        # Marker should still exist
        assert (test_folder / IMPORT_MARKER_FILE).exists()
