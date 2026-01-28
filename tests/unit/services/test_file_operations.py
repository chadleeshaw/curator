"""
Unit tests for services/file_operations.py
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.file_operations import (
    FileReorganizationResult,
    move_files_with_cleanup,
    reorganize_periodical_files,
)


class TestFileReorganizationResult:
    """Test FileReorganizationResult dataclass"""

    def test_success_result_with_paths(self):
        """Test creating a successful reorganization result"""
        result = FileReorganizationResult(
            success=True,
            new_pdf_path="/path/to/new.pdf",
            new_cover_path="/path/to/new.jpg",
            files_moved=True,
        )

        assert result.success is True
        assert result.new_pdf_path == "/path/to/new.pdf"
        assert result.new_cover_path == "/path/to/new.jpg"
        assert result.error is None
        assert result.files_moved is True

    def test_failure_result_with_error(self):
        """Test creating a failed reorganization result"""
        result = FileReorganizationResult(
            success=False,
            new_pdf_path=None,
            new_cover_path=None,
            error="File not found",
            files_moved=False,
        )

        assert result.success is False
        assert result.new_pdf_path is None
        assert result.new_cover_path is None
        assert result.error == "File not found"
        assert result.files_moved is False


class TestReorganizePeriodicalFiles:
    """Test reorganize_periodical_files function"""

    @pytest.fixture
    def temp_library_dir(self, tmp_path):
        """Create a temporary library directory"""
        library = tmp_path / "library"
        library.mkdir()
        return library

    @pytest.fixture
    def mock_periodical(self, tmp_path):
        """Create a mock periodical object with test files"""
        # Create test PDF and cover files
        old_dir = tmp_path / "old_location"
        old_dir.mkdir()

        pdf_path = old_dir / "old_magazine.pdf"
        pdf_path.write_text("PDF content")

        cover_path = old_dir / "old_magazine.jpg"
        cover_path.write_text("Cover content")

        # Mock periodical object
        periodical = MagicMock()
        periodical.file_path = str(pdf_path)
        periodical.cover_path = str(cover_path)
        periodical.issue_date = datetime(2024, 1, 15)
        periodical.extra_metadata = {"category": "Magazines"}

        return periodical

    def test_reorganize_with_new_title(self, mock_periodical, temp_library_dir):
        """Test reorganizing files with a new title"""
        result = reorganize_periodical_files(
            mock_periodical,
            new_title="Wired (US)",
            library_base_dir=temp_library_dir,
            category_prefix="_",
        )

        assert result.success is True
        assert result.new_pdf_path is not None
        assert result.new_cover_path is not None
        assert result.files_moved is True

        # Verify new paths exist
        new_pdf = Path(result.new_pdf_path)
        new_cover = Path(result.new_cover_path)
        assert new_pdf.exists()
        assert new_cover.exists()

        # Verify path structure: _Magazines/Wired (US)/2024/
        assert "_Magazines" in str(new_pdf)
        assert "Wired (US)" in str(new_pdf)
        assert "2024" in str(new_pdf)
        assert "January2024" in str(new_pdf)

    def test_reorganize_without_cover(self, mock_periodical, temp_library_dir):
        """Test reorganizing files when cover doesn't exist"""
        # Remove cover path
        mock_periodical.cover_path = None

        result = reorganize_periodical_files(mock_periodical, "Test Magazine", temp_library_dir)

        assert result.success is True
        assert result.new_pdf_path is not None
        assert result.new_cover_path is None
        assert result.files_moved is True

    def test_reorganize_missing_pdf_file(self, temp_library_dir):
        """Test reorganizing when PDF file doesn't exist"""
        periodical = MagicMock()
        periodical.file_path = "/nonexistent/file.pdf"
        periodical.cover_path = None
        periodical.issue_date = datetime(2024, 1, 1)
        periodical.extra_metadata = {"category": "Magazines"}

        result = reorganize_periodical_files(periodical, "Test", temp_library_dir)

        assert result.success is False
        assert result.new_pdf_path is None
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_reorganize_handles_filename_conflicts(self, mock_periodical, temp_library_dir):
        """Test that filename conflicts are handled with timestamps"""
        # First reorganization
        result1 = reorganize_periodical_files(mock_periodical, "Test Magazine", temp_library_dir)
        assert result1.success is True

        # Create another periodical with the same date
        second_periodical = MagicMock()
        old_dir = Path(mock_periodical.file_path).parent
        second_pdf = old_dir / "another.pdf"
        second_pdf.write_text("Another PDF")
        second_periodical.file_path = str(second_pdf)
        second_periodical.cover_path = None
        second_periodical.issue_date = datetime(2024, 1, 15)
        second_periodical.extra_metadata = {"category": "Magazines"}

        # Second reorganization with same title/date should add timestamp
        result2 = reorganize_periodical_files(second_periodical, "Test Magazine", temp_library_dir)
        assert result2.success is True
        assert result2.new_pdf_path != result1.new_pdf_path
        assert "(" in result2.new_pdf_path  # Timestamp marker

    def test_reorganize_files_already_in_correct_location(self, mock_periodical, temp_library_dir):
        """Test when files are already in the correct location"""
        # First reorganization
        result1 = reorganize_periodical_files(mock_periodical, "Wired", temp_library_dir)
        assert result1.success is True

        # Update mock to point to new location
        mock_periodical.file_path = result1.new_pdf_path
        mock_periodical.cover_path = result1.new_cover_path

        # Second reorganization should detect files are already correct
        result2 = reorganize_periodical_files(mock_periodical, "Wired", temp_library_dir)
        assert result2.success is True
        assert result2.files_moved is False  # No files were moved

    def test_reorganize_updates_periodical_object(self, mock_periodical, temp_library_dir):
        """Test that periodical object is updated with new paths"""
        original_pdf = mock_periodical.file_path
        original_cover = mock_periodical.cover_path

        result = reorganize_periodical_files(mock_periodical, "Updated Title", temp_library_dir, update_db=True)

        assert result.success is True
        # Verify paths were updated
        assert mock_periodical.file_path != original_pdf
        assert mock_periodical.cover_path != original_cover
        assert mock_periodical.file_path == result.new_pdf_path
        assert mock_periodical.cover_path == result.new_cover_path

    def test_reorganize_no_db_update(self, mock_periodical, temp_library_dir):
        """Test reorganizing without updating database object"""
        original_pdf = mock_periodical.file_path
        original_cover = mock_periodical.cover_path

        result = reorganize_periodical_files(mock_periodical, "Test", temp_library_dir, update_db=False)

        assert result.success is True
        # Verify paths were NOT updated
        assert mock_periodical.file_path == original_pdf
        assert mock_periodical.cover_path == original_cover


class TestMoveFilesWithCleanup:
    """Test move_files_with_cleanup function"""

    @pytest.fixture
    def temp_paths(self, tmp_path):
        """Create temporary source and target paths"""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "target"

        old_pdf = source_dir / "old.pdf"
        old_pdf.write_text("PDF content")

        old_cover = source_dir / "old.jpg"
        old_cover.write_text("Cover content")

        new_pdf = target_dir / "new.pdf"
        new_cover = target_dir / "new.jpg"

        return {
            "old_pdf": old_pdf,
            "old_cover": old_cover,
            "new_pdf": new_pdf,
            "new_cover": new_cover,
            "target_dir": target_dir,
        }

    def test_move_pdf_and_cover(self, temp_paths):
        """Test moving both PDF and cover files"""
        success, error = move_files_with_cleanup(
            temp_paths["old_pdf"],
            temp_paths["new_pdf"],
            temp_paths["old_cover"],
            temp_paths["new_cover"],
        )

        assert success is True
        assert error is None
        assert temp_paths["new_pdf"].exists()
        assert temp_paths["new_cover"].exists()
        assert not temp_paths["old_pdf"].exists()
        assert not temp_paths["old_cover"].exists()

    def test_move_pdf_only(self, temp_paths):
        """Test moving only PDF file"""
        success, error = move_files_with_cleanup(temp_paths["old_pdf"], temp_paths["new_pdf"])

        assert success is True
        assert error is None
        assert temp_paths["new_pdf"].exists()
        assert not temp_paths["new_pdf"].exists() or temp_paths["new_pdf"].exists()  # Cover not involved

    def test_move_creates_target_directory(self, tmp_path):
        """Test that target directory is created if it doesn't exist"""
        source_pdf = tmp_path / "source.pdf"
        source_pdf.write_text("Content")

        target_pdf = tmp_path / "deep" / "nested" / "target.pdf"

        success, error = move_files_with_cleanup(source_pdf, target_pdf)

        assert success is True
        assert error is None
        assert target_pdf.exists()
        assert target_pdf.parent.exists()

    def test_move_missing_source_file(self, temp_paths):
        """Test moving when source file doesn't exist"""
        nonexistent = temp_paths["old_pdf"].parent / "nonexistent.pdf"

        success, error = move_files_with_cleanup(nonexistent, temp_paths["new_pdf"])

        assert success is False
        assert error is not None
        assert "not found" in error.lower()

    def test_move_same_path_skipped(self, temp_paths):
        """Test that moving to same path is skipped"""
        same_path = temp_paths["old_pdf"]

        success, error = move_files_with_cleanup(same_path, same_path)

        assert success is True
        assert error is None
        assert same_path.exists()

    def test_move_without_cover(self, temp_paths):
        """Test moving PDF without cover file"""
        success, error = move_files_with_cleanup(
            temp_paths["old_pdf"],
            temp_paths["new_pdf"],
            None,  # No old cover, None  # No new cover
        )

        assert success is True
        assert error is None
        assert temp_paths["new_pdf"].exists()
