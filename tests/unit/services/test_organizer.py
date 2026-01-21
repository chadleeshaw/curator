#!/usr/bin/env python3
"""
Test suite for FileOrganizer (Organizer)
"""

import sys
import shutil
import tempfile
from pathlib import Path  # noqa: E402
from datetime import datetime  # noqa: E402

# Add parent directory to path
# Path setup handled by conftest.py

from services import FileOrganizer  # noqa: E402
from core.parsers import sanitize_filename  # noqa: E402
from core.constants.category import CATEGORY_MAGAZINE  # noqa: E402


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


def test_organize_file():
    """Test organizing files with proper naming"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileOrganizer(tmpdir)

        # Create a temporary PDF file
        test_pdf = Path(tmpdir) / "source.pdf"
        test_pdf.write_text("fake pdf content")

        # Organize the file
        title = "Wired Magazine"
        issue_date = datetime(2006, 12, 1)
        pdf_path, jpg_path = processor.organize_file(str(test_pdf), title, issue_date)

        # Verify PDF was renamed and moved
        assert Path(pdf_path).exists()
        assert Path(pdf_path).name == "Wired Magazine - December2006.pdf"
        assert "December2006" in Path(pdf_path).name

        # Verify source file no longer exists
        assert not test_pdf.exists()

        print("Testing FileOrganizer.organize_file()... ✓ PASS")


def test_organize_file_with_cover():
    """Test organizing file with cover art"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileOrganizer(tmpdir)

        # Create temporary files
        test_pdf = Path(tmpdir) / "source.pdf"
        test_pdf.write_text("fake pdf content")

        test_jpg = Path(tmpdir) / "cover.jpg"
        test_jpg.write_text("fake jpg content")

        # Organize the file with cover
        title = "National Geographic"
        issue_date = datetime(2023, 3, 1)
        pdf_path, jpg_path = processor.organize_file(str(test_pdf), title, issue_date, cover_path=str(test_jpg))

        # Verify both files were organized
        assert Path(pdf_path).exists()
        assert Path(jpg_path).exists()
        assert Path(pdf_path).name == "National Geographic - March2023.pdf"
        assert Path(jpg_path).name == "National Geographic - March2023.jpg"

        # Verify source files moved
        assert not test_pdf.exists()
        assert not test_jpg.exists()

        print("Testing FileOrganizer.organize_file() with cover... ✓ PASS")


def test_organize_file_non_pdf():
    """Test that non-PDF files are not moved"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileOrganizer(tmpdir)

        # Create a non-PDF file
        test_file = Path(tmpdir) / "source.txt"
        test_file.write_text("not a pdf")

        title = "Some Title"
        issue_date = datetime(2020, 1, 1)
        pdf_path, jpg_path = processor.organize_file(str(test_file), title, issue_date)

        # Verify non-PDF was not moved
        assert test_file.exists()
        assert pdf_path == "None"

        print("Testing FileOrganizer.organize_file() with non-PDF... ✓ PASS")


def test_organize_directory_creation():
    """Test that organize directory is created automatically"""
    with tempfile.TemporaryDirectory() as tmpdir:
        organize_path = Path(tmpdir) / "organized" / "magazines"

        # Path shouldn't exist yet
        assert not organize_path.exists()

        # Create processor
        processor = FileOrganizer(str(organize_path))

        # Path should now exist
        assert organize_path.exists()
        assert organize_path.is_dir()

        print("Testing FileOrganizer directory creation... ✓ PASS")


def test_filename_patterns():
    """Test organizing with different date patterns"""
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileOrganizer(tmpdir)

        test_cases = [
            ("Wired", datetime(2006, 1, 1), "Wired - January2006"),
            ("Time Magazine", datetime(2015, 12, 1), "Time Magazine - December2015"),
            (
                "National Geographic",
                datetime(2023, 7, 1),
                "National Geographic - July2023",
            ),
            (
                "Scientific American",
                datetime(2010, 2, 1),
                "Scientific American - February2010",
            ),
        ]

        for title, date, expected_base in test_cases:
            test_pdf = Path(tmpdir) / f"test_{title}.pdf"
            test_pdf.write_text("fake pdf")

            pdf_path, _ = processor.organize_file(str(test_pdf), title, date)

            # Verify naming pattern
            assert Path(pdf_path).name == f"{expected_base}.pdf"

        print("Testing FileOrganizer filename patterns... ✓ PASS")


def test_parse_all_months():
    """Test parsing all month abbreviations"""
    # This test is no longer applicable as parse_filename_for_metadata() was removed
    # Month parsing functionality is tested in test_date.py
    print("Testing month parsing... ✓ SKIPPED (tested in test_date.py)")


def test_organize_pattern():
    """Test the organized filename pattern"""
    processor = FileOrganizer(tempfile.gettempdir())

    expected_pattern = "{title} - {month}{year}"
    assert processor.ORGANIZED_PATTERN == expected_pattern

    print("Testing FileOrganizer pattern... ✓ PASS")


def test_category_prefix_default():
    """Test that category prefix defaults to underscore"""
    processor = FileOrganizer(tempfile.gettempdir())

    # Default prefix should be underscore
    assert processor.category_prefix == "_"

    # Test with organize method
    with tempfile.TemporaryDirectory() as tmpdir:
        processor = FileOrganizer(tmpdir)
        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_text("test content")

        metadata = {"title": "Wired", "issue_date": datetime(2024, 1, 1)}

        result_path = processor.organize(
            test_pdf,
            metadata,
            category=CATEGORY_MAGAZINE,
            pattern="{category}/{title}/{year}/",
        )

        # Verify prefix was applied
        assert f"_{CATEGORY_MAGAZINE}" in str(result_path)

    print("Testing FileOrganizer category_prefix default... ✓ PASS")


def test_category_prefix_custom():
    """Test custom category prefix"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with custom prefix
        processor = FileOrganizer(tmpdir, category_prefix="PREFIX_")

        assert processor.category_prefix == "PREFIX_"

        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_text("test content")

        metadata = {"title": "National Geographic", "issue_date": datetime(2024, 6, 1)}

        result_path = processor.organize(
            test_pdf,
            metadata,
            category=CATEGORY_MAGAZINE,
            pattern="{category}/{title}/{year}/",
        )

        # Verify custom prefix was applied
        result_str = str(result_path)
        assert f"PREFIX_{CATEGORY_MAGAZINE}" in result_str
        # Verify it doesn't start with just f"_{CATEGORY_MAGAZINE}" (should have PREFIX_)
        assert not result_str.startswith(str(tmpdir) + f"/_{CATEGORY_MAGAZINE}")

    print("Testing FileOrganizer custom category_prefix... ✓ PASS")


def test_category_prefix_empty():
    """Test empty category prefix"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with no prefix
        processor = FileOrganizer(tmpdir, category_prefix="")

        assert processor.category_prefix == ""

        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_text("test content")

        metadata = {"title": "PC Gamer", "issue_date": datetime(2024, 3, 1)}

        result_path = processor.organize(
            test_pdf,
            metadata,
            category=CATEGORY_MAGAZINE,
            pattern="{category}/{title}/{year}/",
        )

        # Verify no prefix (just "Magazine", not "_Magazine")
        assert f"/{CATEGORY_MAGAZINE}/" in str(result_path)
        assert f"/_{CATEGORY_MAGAZINE}/" not in str(result_path)

    print("Testing FileOrganizer empty category_prefix... ✓ PASS")


if __name__ == "__main__":
    print("\n🧪 File Organizer Tests\n")
    print("=" * 70)

    results = {}

    try:
        test_sanitize_filename()
        results["sanitize_filename"] = True
    except Exception as e:
        print(f"Testing FileOrganizer._sanitize_filename()... ❌ FAIL: {e}")
        results["sanitize_filename"] = False

    try:
        test_organize_file()
        results["organize_file"] = True
    except Exception as e:
        print(f"Testing FileOrganizer.organize_file()... ❌ FAIL: {e}")
        results["organize_file"] = False

    try:
        test_organize_file_with_cover()
        results["organize_with_cover"] = True
    except Exception as e:
        print(f"Testing FileOrganizer.organize_file() with cover... ❌ FAIL: {e}")
        results["organize_with_cover"] = False

    try:
        test_organize_file_non_pdf()
        results["non_pdf"] = True
    except Exception as e:
        print(f"Testing FileOrganizer.organize_file() with non-PDF... ❌ FAIL: {e}")
        results["non_pdf"] = False

    try:
        test_organize_directory_creation()
        results["directory_creation"] = True
    except Exception as e:
        print(f"Testing FileOrganizer directory creation... ❌ FAIL: {e}")
        results["directory_creation"] = False

    try:
        test_filename_patterns()
        results["filename_patterns"] = True
    except Exception as e:
        print(f"Testing FileOrganizer filename patterns... ❌ FAIL: {e}")
        results["filename_patterns"] = False

    try:
        test_parse_all_months()
        results["all_months"] = True
    except Exception as e:
        print(f"Testing FileOrganizer all month parsing... ❌ FAIL: {e}")
        results["all_months"] = False

    try:
        test_organize_pattern()
        results["organize_pattern"] = True
    except Exception as e:
        print(f"Testing FileOrganizer pattern... ❌ FAIL: {e}")
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
