"""
Test that video and unsupported file types are properly rejected during organization.

This test ensures that only supported file formats (.pdf, .epub, .cbz, .cbr) can be
organized into the library, preventing video files and other unsupported types from
being imported.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.file_organizer import FileOrganizer


@pytest.fixture
def organizer(tmp_path):
    """Create a FileOrganizer with a temporary library directory"""
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    return FileOrganizer(str(library_dir)), library_dir


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing"""
    return {
        "title": "Test Magazine",
        "issue_date": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "year": 2020,
        "month_name": "January",
        "language": "en",
        "volume": None,
        "issue_number": None,
    }


def test_organize_rejects_mkv_files(tmp_path, organizer, sample_metadata):
    """Test that .mkv video files are rejected during organization"""
    org, library_dir = organizer

    # Create a fake .mkv file
    test_mkv = tmp_path / "Test Video.mkv"
    test_mkv.write_text("fake video content")

    # Attempt to organize the .mkv file
    result = org.organize(test_mkv, sample_metadata, "Magazines")

    # Should return None (rejected)
    assert result is None

    # Original file should still exist
    assert test_mkv.exists()

    # Library should be empty (no files organized)
    organized_files = [f for f in library_dir.rglob("*") if f.is_file()]
    assert len(organized_files) == 0


@pytest.mark.parametrize(
    "extension", [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"]
)
def test_organize_rejects_video_formats(tmp_path, organizer, sample_metadata, extension):
    """Test that various video formats are rejected"""
    org, library_dir = organizer

    test_file = tmp_path / f"test{extension}"
    test_file.write_text("fake content")

    result = org.organize(test_file, sample_metadata, "Magazines")

    # Should be rejected
    assert result is None

    # Original file should still exist
    assert test_file.exists()

    # No files should be in library
    organized_files = [f for f in library_dir.rglob("*") if f.is_file()]
    assert len(organized_files) == 0


@pytest.mark.parametrize("extension", [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"])
def test_organize_rejects_audio_formats(tmp_path, organizer, sample_metadata, extension):
    """Test that audio formats are rejected"""
    org, library_dir = organizer

    test_file = tmp_path / f"test{extension}"
    test_file.write_text("fake content")

    result = org.organize(test_file, sample_metadata, "Magazines")

    # Should be rejected
    assert result is None
    assert test_file.exists()


@pytest.mark.parametrize("extension", [".pdf", ".epub", ".cbz", ".cbr"])
def test_organize_accepts_valid_formats(tmp_path, organizer, sample_metadata, extension):
    """Test that valid formats (.pdf, .epub, .cbz, .cbr) are accepted"""
    org, library_dir = organizer

    test_file = tmp_path / f"test{extension}"
    test_file.write_text("fake content")

    result = org.organize(test_file, sample_metadata, "Magazines")

    # Should be accepted and organized
    assert result is not None
    assert result.exists()
    assert result.suffix == extension

    # File should be in library
    organized_files = [f for f in library_dir.rglob(f"*{extension}") if f.is_file()]
    assert len(organized_files) == 1


def test_organize_rejects_exe_files(tmp_path, organizer, sample_metadata):
    """Test that executable files are rejected"""
    org, library_dir = organizer

    test_file = tmp_path / "malware.exe"
    test_file.write_text("fake exe")

    result = org.organize(test_file, sample_metadata, "Magazines")

    assert result is None
    assert test_file.exists()

    # Library should be empty
    organized_files = [f for f in library_dir.rglob("*") if f.is_file()]
    assert len(organized_files) == 0


def test_organize_rejects_zip_files(tmp_path, organizer, sample_metadata):
    """Test that .zip archive files are rejected (CBZ/CBR are the only supported archives)"""
    org, library_dir = organizer

    test_file = tmp_path / "archive.zip"
    test_file.write_text("fake zip")

    result = org.organize(test_file, sample_metadata, "Magazines")

    assert result is None
    assert test_file.exists()
