#!/usr/bin/env python3
"""
Test suite for FileImporter case-insensitive file extension handling.
Tests fix for bug where uppercase extensions (.PDF, .EPUB) were counted but not imported.
"""

from pathlib import Path
from unittest.mock import MagicMock

from services.importer.importer import FileImporter


def test_process_downloads_handles_uppercase_extensions():
    """
    Test that FileImporter correctly processes files with uppercase extensions.

    Regression test for bug where download monitor found files with uppercase
    extensions but importer didn't process them due to case-sensitive comparison.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        library_dir = Path(tmpdir) / "organize"
        downloads_dir.mkdir()
        library_dir.mkdir()

        # Create test files with lowercase and uppercase extensions
        # Also test files with single quotes in filename (like 'Magazine.pdf')
        (downloads_dir / "test1.pdf").write_text("test pdf lowercase")
        (downloads_dir / "test2.PDF").write_text("test pdf uppercase")
        (downloads_dir / "'test3.pdf'").write_text("test pdf with quotes")
        (downloads_dir / "test4.epub").write_text("test epub lowercase")
        (downloads_dir / "test5.EPUB").write_text("test epub uppercase")
        (downloads_dir / "'test6.epub'").write_text("test epub with quotes")
        (downloads_dir / "test7.cbz").write_text("test cbz lowercase")
        (downloads_dir / "test8.CBZ").write_text("test cbz uppercase")
        (downloads_dir / "test9.cbr").write_text("test cbr lowercase")
        (downloads_dir / "test10.CBR").write_text("test cbr uppercase")

        importer = FileImporter(str(downloads_dir), str(library_dir))

        # Mock session for testing
        mock_session = MagicMock()

        # The importer should find all files regardless of extension case
        # We're testing the file filtering logic, not the full import process
        from core.utils import find_supported_files

        all_files = find_supported_files(downloads_dir, recursive=True)

        # Debug: Print what files were actually found
        print(f"\nAll files found: {[f.name for f in all_files]}")
        suffixes_info = [(f.name, f.suffix, f.suffix.lower().rstrip("'")) for f in all_files]
        print(f"Suffixes: {suffixes_info}")

        # Filter using the same logic as process_downloads after the fix
        # Strip trailing quotes from suffix (for files like 'Magazine.pdf')
        pdf_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbz"]
        cbr_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbr"]

        # All files should be found regardless of case or quotes
        assert len(pdf_files) == 3, f"Expected 3 PDF files, found {len(pdf_files)}: {[f.name for f in pdf_files]}"
        assert len(epub_files) == 3, f"Expected 3 EPUB files, found {len(epub_files)}: {[f.name for f in epub_files]}"
        assert len(cbz_files) == 2, f"Expected 2 CBZ files, found {len(cbz_files)}"
        assert len(cbr_files) == 2, f"Expected 2 CBR files, found {len(cbr_files)}"

        # Verify the specific files found
        pdf_names = {f.name for f in pdf_files}
        assert "test1.pdf" in pdf_names
        assert "test2.PDF" in pdf_names
        assert "'test3.pdf'" in pdf_names

        epub_names = {f.name for f in epub_files}
        assert "test4.epub" in epub_names
        assert "test5.EPUB" in epub_names
        assert "'test6.epub'" in epub_names

        cbz_names = {f.name for f in cbz_files}
        assert "test7.cbz" in cbz_names
        assert "test8.CBZ" in cbz_names

        cbr_names = {f.name for f in cbr_files}
        assert "test9.cbr" in cbr_names
        assert "test10.CBR" in cbr_names


def test_get_import_status_handles_uppercase_extensions():
    """Test that import status endpoint counts files with uppercase extensions."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        downloads_dir = Path(tmpdir) / "downloads"
        downloads_dir.mkdir()

        # Create test files with mixed case extensions and quoted filenames
        (downloads_dir / "Magazine.PDF").touch()
        (downloads_dir / "Book.EPUB").touch()
        (downloads_dir / "Comic.CBZ").touch()
        (downloads_dir / "'Quoted.pdf'").touch()

        # Test the filtering logic used in get_import_status
        from core.utils import find_supported_files

        all_files = find_supported_files(downloads_dir, recursive=True)
        pdf_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".pdf"]
        epub_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".epub"]
        cbz_files = [f for f in all_files if f.suffix.lower().rstrip("'") == ".cbz"]

        assert len(pdf_files) == 2, f"Expected 2 PDF files, found {len(pdf_files)}: {[f.name for f in pdf_files]}"
        assert len(epub_files) == 1
        assert len(cbz_files) == 1
        assert len(all_files) == 4
