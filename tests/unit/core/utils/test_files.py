"""
Unit tests for core/utils/files.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.utils.files import (
    get_category_prefix,
    get_library_dir,
    get_periodical_file_and_cover_paths,
    resolve_periodical_file_path,
    verify_periodical_files_exist,
)


class TestGetLibraryDir:
    """Test get_library_dir function"""

    def test_with_config(self):
        """Test getting library dir from config"""
        config = {"library_dir": "/custom/library"}
        result = get_library_dir(config)
        assert result == Path("/custom/library").resolve()

    def test_with_default(self):
        """Test getting library dir with default"""
        result = get_library_dir(None)
        assert result == Path("./local/data").resolve()

    def test_with_custom_default(self):
        """Test getting library dir with custom default"""
        result = get_library_dir(None, "/other/default")
        assert result == Path("/other/default").resolve()


class TestGetCategoryPrefix:
    """Test get_category_prefix function"""

    def test_with_config(self):
        """Test getting category prefix from config"""
        config = {"category_prefix": "$"}
        result = get_category_prefix(config)
        assert result == "$"

    def test_with_default(self):
        """Test getting category prefix with default"""
        result = get_category_prefix(None)
        assert result == "_"

    def test_with_custom_default(self):
        """Test getting category prefix with custom default"""
        result = get_category_prefix(None, "@")
        assert result == "@"


class TestResolvePeriodicalFilePath:
    """Test resolve_periodical_file_path function"""

    @pytest.fixture
    def temp_library(self, tmp_path):
        """Create a temporary library structure"""
        library = tmp_path / "library"
        library.mkdir()

        # Create a test file in category structure
        magazine_dir = library / "_Magazines" / "Wired" / "2024"
        magazine_dir.mkdir(parents=True)

        test_file = magazine_dir / "Wired - January2024.pdf"
        test_file.write_text("test content")

        return library, test_file

    def test_resolve_existing_absolute_path(self, temp_library):
        """Test resolving a path that already exists"""
        library, test_file = temp_library
        result = resolve_periodical_file_path(str(test_file), library)
        assert result == test_file

    def test_resolve_with_category_marker(self, temp_library):
        """Test resolving path with category marker"""
        library, test_file = temp_library

        # Simulate a path from different environment
        fake_path = "/app/local/data/_Magazines/Wired/2024/Wired - January2024.pdf"

        result = resolve_periodical_file_path(fake_path, library, "_")
        assert result == test_file

    def test_resolve_not_found(self, tmp_path):
        """Test that FileNotFoundError is raised when file can't be resolved"""
        library = tmp_path / "library"
        library.mkdir()

        with pytest.raises(FileNotFoundError, match="Could not resolve file path"):
            resolve_periodical_file_path("/nonexistent/file.pdf", library)

    def test_resolve_by_filename(self, tmp_path):
        """Test resolving by filename as last resort"""
        library = tmp_path / "library"
        library.mkdir()

        # Create file directly in library (unusual but possible)
        test_file = library / "somefile.pdf"
        test_file.write_text("content")

        result = resolve_periodical_file_path("/some/other/path/somefile.pdf", library)
        assert result == test_file


class TestGetPeriodicalFileAndCoverPaths:
    """Test get_periodical_file_and_cover_paths function"""

    @pytest.fixture
    def temp_library(self, tmp_path):
        """Create a temporary library with file and cover"""
        library = tmp_path / "library"
        library.mkdir()

        magazine_dir = library / "_Magazines" / "Test" / "2024"
        magazine_dir.mkdir(parents=True)

        pdf_file = magazine_dir / "Test - January2024.pdf"
        pdf_file.write_text("pdf content")

        cover_file = magazine_dir / "Test - January2024.jpg"
        cover_file.write_text("cover content")

        return library, pdf_file, cover_file

    def test_get_both_paths(self, temp_library):
        """Test getting both file and cover paths"""
        library, pdf_file, cover_file = temp_library

        # Mock periodical object
        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = str(cover_file)

        file_path, cover_path = get_periodical_file_and_cover_paths(periodical, library)

        assert file_path == pdf_file
        assert cover_path == cover_file

    def test_get_file_only(self, temp_library):
        """Test getting file path when cover doesn't exist"""
        library, pdf_file, _ = temp_library

        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = None

        file_path, cover_path = get_periodical_file_and_cover_paths(periodical, library)

        assert file_path == pdf_file
        assert cover_path is None

    def test_get_with_missing_cover(self, temp_library):
        """Test getting paths when cover is specified but doesn't exist"""
        library, pdf_file, _ = temp_library

        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = "/nonexistent/cover.jpg"

        file_path, cover_path = get_periodical_file_and_cover_paths(periodical, library)

        assert file_path == pdf_file
        assert cover_path is None  # Should gracefully handle missing cover

    def test_get_with_missing_file(self, tmp_path):
        """Test that FileNotFoundError is raised when file doesn't exist"""
        library = tmp_path / "library"
        library.mkdir()

        periodical = MagicMock()
        periodical.file_path = "/nonexistent/file.pdf"
        periodical.cover_path = None

        with pytest.raises(FileNotFoundError):
            get_periodical_file_and_cover_paths(periodical, library)


class TestVerifyPeriodicalFilesExist:
    """Test verify_periodical_files_exist function"""

    @pytest.fixture
    def temp_library(self, tmp_path):
        """Create a temporary library with file and cover"""
        library = tmp_path / "library"
        library.mkdir()

        magazine_dir = library / "_Magazines" / "Verify" / "2024"
        magazine_dir.mkdir(parents=True)

        pdf_file = magazine_dir / "Verify - January2024.pdf"
        pdf_file.write_text("pdf content")

        cover_file = magazine_dir / "Verify - January2024.jpg"
        cover_file.write_text("cover content")

        return library, pdf_file, cover_file

    def test_both_files_exist(self, temp_library):
        """Test verification when both files exist"""
        library, pdf_file, cover_file = temp_library

        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = str(cover_file)

        file_exists, cover_exists = verify_periodical_files_exist(periodical, library)

        assert file_exists is True
        assert cover_exists is True

    def test_only_file_exists(self, temp_library):
        """Test verification when only file exists"""
        library, pdf_file, _ = temp_library

        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = None

        file_exists, cover_exists = verify_periodical_files_exist(periodical, library)

        assert file_exists is True
        assert cover_exists is False

    def test_file_missing(self, tmp_path):
        """Test verification when file is missing"""
        library = tmp_path / "library"
        library.mkdir()

        periodical = MagicMock()
        periodical.file_path = "/nonexistent/file.pdf"
        periodical.cover_path = None

        file_exists, cover_exists = verify_periodical_files_exist(periodical, library)

        assert file_exists is False
        assert cover_exists is False

    def test_cover_missing(self, temp_library):
        """Test verification when cover is missing"""
        library, pdf_file, _ = temp_library

        periodical = MagicMock()
        periodical.file_path = str(pdf_file)
        periodical.cover_path = "/nonexistent/cover.jpg"

        file_exists, cover_exists = verify_periodical_files_exist(periodical, library)

        assert file_exists is True
        assert cover_exists is False
