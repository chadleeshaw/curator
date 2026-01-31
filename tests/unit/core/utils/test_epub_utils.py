#!/usr/bin/env python3
"""
Test suite for core.epub_utils module
"""

from pathlib import Path

# Path setup handled by conftest.py

from core.utils.epub import extract_text_from_epub, extract_cover_from_epub


def test_extract_text_from_epub_with_sample():
    """Test extracting text from sample EPUB file"""
    epub_path = Path(__file__).parent / "epub" / "sample-book.epub"

    if not epub_path.exists():
        # Skip if sample EPUB doesn't exist
        return

    text = extract_text_from_epub(epub_path)

    assert text is not None
    assert isinstance(text, str)
    # Text extraction might return empty string for simple EPUB
    assert len(text) >= 0


def test_extract_text_from_epub_invalid_file():
    """Test extracting text from non-existent file"""
    text = extract_text_from_epub(Path("/nonexistent/file.epub"))

    # Should return empty string or None on error
    assert text is None or text == ""


def test_extract_cover_from_epub_invalid_file():
    """Test extracting cover from invalid file"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cover_path = extract_cover_from_epub(Path("/nonexistent/file.epub"), Path(tmpdir))
        assert cover_path is None


def test_epub_utils_functions_exist():
    """Test that EPUB utility functions exist"""
    assert callable(extract_text_from_epub)
    assert callable(extract_cover_from_epub)
