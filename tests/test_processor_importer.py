#!/usr/bin/env python3
"""Test FileImporter processor with various organization patterns"""
import sys

sys.path.insert(0, ".")

import logging
import tempfile
import shutil
from pathlib import Path  # noqa: E402
from datetime import datetime  # noqa: E402

logging.basicConfig(level=logging.WARNING)

print("\n🧪 Processor FileImporter Tests\n")
print("=" * 70)

results = {}

# Get the test PDF path
TEST_PDF = Path(__file__).parent / "pdf" / "NationalGeographic 2000-01.pdf"

# Test 1: Pattern parsing and file organization with real PDF
print("Testing FileImporter._organize_file() with real PDF...", end=" ")
try:
    from processor.file_importer import FileImporter

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy test PDF to temp directory
        temp_pdf = Path(tmpdir) / TEST_PDF.name
        shutil.copy2(TEST_PDF, temp_pdf)

        importer = FileImporter(downloads_dir=tmpdir, organize_base_dir=tmpdir)

        metadata = {"title": "National Geographic", "issue_date": datetime(2000, 1, 15)}

        # Test pattern: data/{category}/{title}/{year}/
        organized = importer._organize_file(
            temp_pdf, metadata, "Magazines", pattern="data/{category}/{title}/{year}/"
        )

        assert organized is not None
        assert "Magazines" in str(organized)
        assert "National Geographic" in str(organized)
        assert "2000" in str(organized)

        # Verify file was moved
        assert Path(organized).exists(), f"Organized file not found: {organized}"
        assert not temp_pdf.exists(), f"Original file still exists: {temp_pdf}"

        # Verify original test PDF still exists
        assert TEST_PDF.exists(), f"Test PDF was deleted: {TEST_PDF}"

        print("✓ PASS")
        results["_organize_file_with_pdf"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["_organize_file_with_pdf"] = False

# Test 2: Metadata extraction from filenames
print("Testing FileImporter._extract_metadata_from_filename()...", end=" ")
try:
    from processor.file_importer import FileImporter

    with tempfile.TemporaryDirectory() as tmpdir:
        importer = FileImporter(tmpdir, tmpdir)

        # Test Pattern 1: "Title - MonYear"
        test_path1 = Path(tmpdir) / "National Geographic - Dec2000.pdf"
        meta1 = importer._extract_metadata_from_filename(test_path1)
        assert meta1["title"] == "National Geographic"
        assert meta1["issue_date"].month == 12
        assert meta1["issue_date"].year == 2000

        # Test Pattern 3: "Title YYYY-MM"
        test_path3 = Path(tmpdir) / "National Geographic 2000-01.pdf"
        meta3 = importer._extract_metadata_from_filename(test_path3)
        assert meta3["title"] == "National Geographic"
        assert meta3["issue_date"].month == 1
        assert meta3["issue_date"].year == 2000

        print("✓ PASS")
        results["_extract_metadata_from_filename()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["_extract_metadata_from_filename()"] = False

# Test 3: File categorization
print("Testing FileImporter._categorize_file()...", end=" ")
try:
    from processor.file_importer import FileImporter

    with tempfile.TemporaryDirectory() as tmpdir:
        importer = FileImporter(tmpdir, tmpdir)

        # Test categorization
        cat1 = importer._categorize_file("National Geographic Magazine")
        assert cat1 == "Magazines"

        cat2 = importer._categorize_file("Marvel Comics")
        assert cat2 == "Comics"

        cat3 = importer._categorize_file("Science Daily News")
        assert cat3 == "News"

        print("✓ PASS")
        results["_categorize_file()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["_categorize_file()"] = False

# Test 5: Organization patterns with real PDF
print("Testing organization patterns with real PDF...", end=" ")
try:
    from processor.file_importer import FileImporter

    metadata = {"title": "National Geographic", "issue_date": datetime(2000, 1, 15)}

    # Test multiple pattern formats
    patterns = [
        "data/{category}/{title}/{year}/",
        "archive/{year}/{month}/{title}/",
        "{category}/{year}/{title}/",
        "periodicals/{category}/{title}/{year}/{month}/",
    ]

    for pattern in patterns:
        with tempfile.TemporaryDirectory() as tmpdir:
            importer = FileImporter(tmpdir, tmpdir)

            # Copy test PDF to temp directory
            temp_pdf = Path(tmpdir) / TEST_PDF.name
            shutil.copy2(TEST_PDF, temp_pdf)

            result = importer._organize_file(temp_pdf, metadata, "Magazines", pattern)
            assert result is not None, f"Pattern {pattern} failed"
            path_str = str(result)
            # Check that pattern variables were replaced
            assert "{" not in path_str, f"Unreplaced variables in {path_str}"
            assert "}" not in path_str, f"Unreplaced variables in {path_str}"
            # Verify organized file exists
            assert Path(result).exists(), f"Organized file not found: {result}"

    # Verify test PDF still exists
    assert TEST_PDF.exists(), f"Test PDF was deleted: {TEST_PDF}"

    print("✓ PASS")
    results["organization_patterns"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["organization_patterns"] = False

# Test 6: Config pattern from config.yaml with real PDF
print("Testing config.yaml pattern with real PDF...", end=" ")
try:
    from core.config import ConfigLoader
    from processor.file_importer import FileImporter

    config_loader = ConfigLoader(config_path="tests/config.test.yaml")
    import_config = config_loader.config.get("import", {})
    pattern = import_config.get(
        "organization_pattern", "data/{category}/{title}/{year}/"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        importer = FileImporter(tmpdir, tmpdir)

        metadata = {"title": "National Geographic", "issue_date": datetime(2000, 1, 15)}

        # Copy test PDF to temp directory
        temp_pdf = Path(tmpdir) / TEST_PDF.name
        shutil.copy2(TEST_PDF, temp_pdf)

        result = importer._organize_file(temp_pdf, metadata, "Magazines", pattern)
        assert result is not None
        assert "Magazines" in str(result)
        assert "National Geographic" in str(result) or "National_Geographic" in str(
            result
        )
        assert "2000" in str(result)

        # Verify file was moved
        assert Path(result).exists(), f"Organized file not found: {result}"
        assert not temp_pdf.exists(), f"Temp file still exists: {temp_pdf}"

        # Verify test PDF still exists
        assert TEST_PDF.exists(), f"Test PDF was deleted: {TEST_PDF}"

        print(f"✓ PASS (pattern: {pattern})")
        results["config_pattern"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["config_pattern"] = False

print("\n" + "=" * 70)
print("Test Summary")
print("=" * 70)
for test_name, passed in results.items():
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

all_passed = all(results.values())
print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))
print(f"\nTest PDF Location: {TEST_PDF}")
print(f"Test PDF Exists: {TEST_PDF.exists()}")
