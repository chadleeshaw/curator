#!/usr/bin/env python3
"""
Test suite for FileProcessor (Organizer)
"""

import sys
import shutil
import tempfile
from pathlib import Path  # noqa: E402
from datetime import datetime  # noqa: E402

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from processor.organizer import FileProcessor  # noqa: E402
from core.utils import sanitize_filename  # noqa: E402


def test_sanitize_filename():
    """Test sanitizing filenames"""
    # Test with invalid characters
    result = sanitize_filename('Wired <Magazine>: "2023"')
    assert result == "Wired Magazine 2023"

    # Test with valid filename
    result = sanitize_filename("National Geographic")
    assert result == "National Geographic"

    # Test with pipes and backslashes
    result = sanitize_filename("Test|File\\Path")
    assert result == "TestFilePath"

    print("Testing sanitize_filename()... ✓ PASS")
    pass


def test_parse_filename_for_metadata():
    """Test parsing metadata from filenames"""
    processor = FileProcessor(tempfile.gettempdir())

    # Valid format: "Title - MonYear"
    result = processor.parse_filename_for_metadata("Wired Magazine - Dec2006")
    assert result["title"] == "Wired Magazine"
    assert result["issue_date"].month == 12
    assert result["issue_date"].year == 2006
    assert result["confidence"] == "high"

    # Another valid format
    result = processor.parse_filename_for_metadata("National Geographic - Mar2023")
    assert result["title"] == "National Geographic"
    assert result["issue_date"].month == 3
    assert result["issue_date"].year == 2023
    assert result["confidence"] == "high"

    # Invalid format
    result = processor.parse_filename_for_metadata("InvalidFilename")
    assert result["confidence"] == "low"

    # Test with extra spaces
    result = processor.parse_filename_for_metadata("Time Magazine  -  Jan2010")
    assert result["title"] == "Time Magazine"
    assert result["issue_date"].month == 1
    assert result["issue_date"].year == 2010

    print("Testing FileProcessor.parse_filename_for_metadata()... ✓ PASS")
    pass


def test_organize_file():
    """Test organizing files with proper naming"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileProcessor(tmpdir)

        # Create a temporary PDF file
        test_pdf = Path(tmpdir) / "source.pdf"
        test_pdf.write_text("fake pdf content")

        # Organize the file
        title = "Wired Magazine"
        issue_date = datetime(2006, 12, 1)
        pdf_path, jpg_path = processor.organize_file(str(test_pdf), title, issue_date)

        # Verify PDF was renamed and moved
        assert Path(pdf_path).exists()
        assert Path(pdf_path).name == "Wired Magazine - Dec2006.pdf"
        assert "Dec2006" in Path(pdf_path).name

        # Verify source file no longer exists
        assert not test_pdf.exists()

        print("Testing FileProcessor.organize_file()... ✓ PASS")
        pass


def test_organize_file_with_cover():
    """Test organizing file with cover art"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileProcessor(tmpdir)

        # Create temporary files
        test_pdf = Path(tmpdir) / "source.pdf"
        test_pdf.write_text("fake pdf content")

        test_jpg = Path(tmpdir) / "cover.jpg"
        test_jpg.write_text("fake jpg content")

        # Organize the file with cover
        title = "National Geographic"
        issue_date = datetime(2023, 3, 1)
        pdf_path, jpg_path = processor.organize_file(
            str(test_pdf), title, issue_date, cover_path=str(test_jpg)
        )

        # Verify both files were organized
        assert Path(pdf_path).exists()
        assert Path(jpg_path).exists()
        assert Path(pdf_path).name == "National Geographic - Mar2023.pdf"
        assert Path(jpg_path).name == "National Geographic - Mar2023.jpg"

        # Verify source files moved
        assert not test_pdf.exists()
        assert not test_jpg.exists()

        print("Testing FileProcessor.organize_file() with cover... ✓ PASS")
        pass


def test_organize_file_non_pdf():
    """Test that non-PDF files are not moved"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileProcessor(tmpdir)

        # Create a non-PDF file
        test_file = Path(tmpdir) / "source.txt"
        test_file.write_text("not a pdf")

        title = "Some Title"
        issue_date = datetime(2020, 1, 1)
        pdf_path, jpg_path = processor.organize_file(str(test_file), title, issue_date)

        # Verify non-PDF was not moved
        assert test_file.exists()
        assert pdf_path == "None"

        print("Testing FileProcessor.organize_file() with non-PDF... ✓ PASS")
        pass


def test_organize_directory_creation():
    """Test that organize directory is created automatically"""
    with tempfile.TemporaryDirectory() as tmpdir:
        organize_path = Path(tmpdir) / "organized" / "magazines"

        # Path shouldn't exist yet
        assert not organize_path.exists()

        # Create processor
        processor = FileProcessor(str(organize_path))

        # Path should now exist
        assert organize_path.exists()
        assert organize_path.is_dir()

        print("Testing FileProcessor directory creation... ✓ PASS")
        pass


def test_filename_patterns():
    """Test organizing with different date patterns"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileProcessor(tmpdir)

        test_cases = [
            ("Wired", datetime(2006, 1, 1), "Wired - Jan2006"),
            ("Time Magazine", datetime(2015, 12, 1), "Time Magazine - Dec2015"),
            (
                "National Geographic",
                datetime(2023, 7, 1),
                "National Geographic - Jul2023",
            ),
            (
                "Scientific American",
                datetime(2010, 2, 1),
                "Scientific American - Feb2010",
            ),
        ]

        for title, date, expected_base in test_cases:
            test_pdf = Path(tmpdir) / f"test_{title}.pdf"
            test_pdf.write_text("fake pdf")

            pdf_path, _ = processor.organize_file(str(test_pdf), title, date)

            # Verify naming pattern
            assert Path(pdf_path).name == f"{expected_base}.pdf"

        print("Testing FileProcessor filename patterns... ✓ PASS")
        pass


def test_parse_all_months():
    """Test parsing all month abbreviations"""
    processor = FileProcessor(tempfile.gettempdir())

    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    for month_num, month_abbr in enumerate(months, 1):
        filename = f"Test Magazine - {month_abbr}2020"
        result = processor.parse_filename_for_metadata(filename)

        assert result["confidence"] == "high"
        assert result["issue_date"].month == month_num
        assert result["issue_date"].year == 2020

    print("Testing FileProcessor all month parsing... ✓ PASS")
    pass


def test_organize_pattern():
    """Test the organized filename pattern"""
    processor = FileProcessor(tempfile.gettempdir())

    expected_pattern = "{title} - {month}{year}"
    assert processor.ORGANIZED_PATTERN == expected_pattern

    print("Testing FileProcessor pattern... ✓ PASS")
    pass


if __name__ == "__main__":
    print("\n🧪 File Organizer Tests\n")
    print("=" * 70)

    results = {}

    try:
        results["sanitize_filename"] = test_sanitize_filename()
    except Exception as e:
        print(f"Testing FileProcessor._sanitize_filename()... ❌ FAIL: {e}")
        results["sanitize_filename"] = False

    try:
        results["parse_filename"] = test_parse_filename_for_metadata()
    except Exception as e:
        print(f"Testing FileProcessor.parse_filename_for_metadata()... ❌ FAIL: {e}")
        results["parse_filename"] = False

    try:
        results["organize_file"] = test_organize_file()
    except Exception as e:
        print(f"Testing FileProcessor.organize_file()... ❌ FAIL: {e}")
        results["organize_file"] = False

    try:
        results["organize_with_cover"] = test_organize_file_with_cover()
    except Exception as e:
        print(f"Testing FileProcessor.organize_file() with cover... ❌ FAIL: {e}")
        results["organize_with_cover"] = False

    try:
        results["non_pdf"] = test_organize_file_non_pdf()
    except Exception as e:
        print(f"Testing FileProcessor.organize_file() with non-PDF... ❌ FAIL: {e}")
        results["non_pdf"] = False

    try:
        results["directory_creation"] = test_organize_directory_creation()
    except Exception as e:
        print(f"Testing FileProcessor directory creation... ❌ FAIL: {e}")
        results["directory_creation"] = False

    try:
        results["filename_patterns"] = test_filename_patterns()
    except Exception as e:
        print(f"Testing FileProcessor filename patterns... ❌ FAIL: {e}")
        results["filename_patterns"] = False

    try:
        results["all_months"] = test_parse_all_months()
    except Exception as e:
        print(f"Testing FileProcessor all month parsing... ❌ FAIL: {e}")
        results["all_months"] = False

    try:
        results["organize_pattern"] = test_organize_pattern()
    except Exception as e:
        print(f"Testing FileProcessor pattern... ❌ FAIL: {e}")
        results["organize_pattern"] = False

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))

    sys.exit(0 if all_passed else 1)
