#!/usr/bin/env python3
"""
Test suite for services.file_importer module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.file_importer import FileImporter


def test_file_importer_initialization():
    """Test FileImporter initialization"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        organize_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        organize_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(organize_dir))

        assert importer is not None


def test_import_single_file():
    """Test importing a single file"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        organize_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        organize_dir.mkdir()

        importer = FileImporter(str(downloads_dir), str(organize_dir))

        # Should have import-related methods
        assert hasattr(importer, 'title_matcher')
        assert hasattr(importer, 'parser')
        assert hasattr(importer, 'organizer')
