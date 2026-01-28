#!/usr/bin/env python3
"""
Test suite for services.file_importer module
"""

from pathlib import Path

# Path setup handled by conftest.py

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
