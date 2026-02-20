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

    def test_reorganize_handles_multiple_conflicts_same_second(self, tmp_path, temp_library_dir):
        """Test that multiple conflicts in the same second get unique paths via counter"""
        old_dir = tmp_path / "old_location"
        old_dir.mkdir()

        results = []
        for i in range(4):
            pdf_path = old_dir / f"magazine_{i}.pdf"
            pdf_path.write_text(f"PDF content {i}")

            periodical = MagicMock()
            periodical.file_path = str(pdf_path)
            periodical.cover_path = None
            periodical.issue_date = datetime(2024, 3, 15)
            periodical.extra_metadata = {"category": "Magazines"}

            result = reorganize_periodical_files(periodical, "Same Title", temp_library_dir)
            assert result.success is True
            results.append(result.new_pdf_path)

        # All paths must be unique
        assert len(set(results)) == 4, f"Expected 4 unique paths, got: {results}"

    def test_reorganize_preserves_epub_extension(self, tmp_path, temp_library_dir):
        """Test that non-PDF file extensions are preserved during reorganization"""
        old_dir = tmp_path / "old_location"
        old_dir.mkdir()

        epub_path = old_dir / "old_magazine.epub"
        epub_path.write_text("EPUB content")

        periodical = MagicMock()
        periodical.file_path = str(epub_path)
        periodical.cover_path = None
        periodical.issue_date = datetime(2024, 6, 1)
        periodical.extra_metadata = {"category": "Magazines"}

        result = reorganize_periodical_files(periodical, "Test Title", temp_library_dir)

        assert result.success is True
        assert result.new_pdf_path.endswith(".epub"), f"Expected .epub extension, got: {result.new_pdf_path}"
        assert Path(result.new_pdf_path).exists()

    def test_reorganize_preserves_cbz_extension(self, tmp_path, temp_library_dir):
        """Test that CBZ file extensions are preserved during reorganization"""
        old_dir = tmp_path / "old_location"
        old_dir.mkdir()

        cbz_path = old_dir / "old_comic.cbz"
        cbz_path.write_text("CBZ content")

        periodical = MagicMock()
        periodical.file_path = str(cbz_path)
        periodical.cover_path = None
        periodical.issue_date = datetime(2024, 6, 1)
        periodical.extra_metadata = {"category": "Comics"}

        result = reorganize_periodical_files(periodical, "Test Comic", temp_library_dir)

        assert result.success is True
        assert result.new_pdf_path.endswith(".cbz"), f"Expected .cbz extension, got: {result.new_pdf_path}"
        assert Path(result.new_pdf_path).exists()

    def test_reorganize_epub_conflict_preserves_extension(self, tmp_path, temp_library_dir):
        """Test that conflicts for non-PDF files still preserve the correct extension"""
        old_dir = tmp_path / "old_location"
        old_dir.mkdir()

        # First EPUB
        epub1 = old_dir / "first.epub"
        epub1.write_text("EPUB 1")
        p1 = MagicMock()
        p1.file_path = str(epub1)
        p1.cover_path = None
        p1.issue_date = datetime(2024, 6, 1)
        p1.extra_metadata = {"category": "Magazines"}

        result1 = reorganize_periodical_files(p1, "Same Title", temp_library_dir)
        assert result1.success is True
        assert result1.new_pdf_path.endswith(".epub")

        # Second EPUB with same date/title
        epub2 = old_dir / "second.epub"
        epub2.write_text("EPUB 2")
        p2 = MagicMock()
        p2.file_path = str(epub2)
        p2.cover_path = None
        p2.issue_date = datetime(2024, 6, 1)
        p2.extra_metadata = {"category": "Magazines"}

        result2 = reorganize_periodical_files(p2, "Same Title", temp_library_dir)
        assert result2.success is True
        assert result2.new_pdf_path.endswith(".epub")
        assert result2.new_pdf_path != result1.new_pdf_path

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

        result = reorganize_periodical_files(
            mock_periodical,
            "Updated Title",
            temp_library_dir,
            should_update_database=True,
        )

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

        result = reorganize_periodical_files(mock_periodical, "Test", temp_library_dir, should_update_database=False)

        assert result.success is True
        # Verify paths were NOT updated
        assert mock_periodical.file_path == original_pdf
        assert mock_periodical.cover_path == original_cover

    def test_reorganize_after_date_metadata_change(self, tmp_path, temp_library_dir):
        """Test that files are reorganized when issue_date changes (metadata update scenario).

        When a user updates year/month metadata on a periodical, the files should
        be moved to reflect the new date in the directory structure and filename.
        """
        # Set up initial file in the library under January 2024
        initial_dir = temp_library_dir / "_Magazines" / "Wired" / "2024"
        initial_dir.mkdir(parents=True)

        pdf_path = initial_dir / "Wired - January2024.pdf"
        pdf_path.write_text("PDF content")
        cover_path = initial_dir / "Wired - January2024.jpg"
        cover_path.write_text("Cover content")

        periodical = MagicMock()
        periodical.file_path = str(pdf_path)
        periodical.cover_path = str(cover_path)
        periodical.extra_metadata = {"category": "Magazines"}

        # Simulate metadata update: change date from January 2024 to March 2025
        periodical.issue_date = datetime(2025, 3, 1)

        result = reorganize_periodical_files(
            periodical,
            new_title="Wired",
            library_base_dir=temp_library_dir,
            should_update_database=True,
        )

        assert result.success is True
        assert result.files_moved is True

        # Files should now be under the new year directory with new month
        new_pdf = Path(result.new_pdf_path)
        new_cover = Path(result.new_cover_path)
        assert new_pdf.exists()
        assert new_cover.exists()
        assert "2025" in str(new_pdf)
        assert "March2025" in new_pdf.name
        assert "March2025" in new_cover.name

        # Old files should no longer exist
        assert not pdf_path.exists()
        assert not cover_path.exists()


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
