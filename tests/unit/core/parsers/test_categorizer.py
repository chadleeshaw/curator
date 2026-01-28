#!/usr/bin/env python3
"""
Test suite for file categorization utilities.
Tests categorizing files into Periodical, Comic, Graphic Novel, Book, Document.
"""


import pytest

# Add parent directory to path
# Path setup handled by conftest.py

from core.parsers import FileCategorizer
from core.constants.category import (
    CATEGORIES,
    CATEGORY_BOOK,
    CATEGORY_COMIC,
    CATEGORY_DOCUMENT,
    CATEGORY_GRAPHIC_NOVEL,
    CATEGORY_KEYWORDS,
    CATEGORY_MAGAZINE,
    DEFAULT_CATEGORY,
)


class TestFileCategorizer:
    """Test FileCategorizer class."""

    @pytest.fixture
    def categorizer(self):
        """Create a FileCategorizer instance for testing."""
        return FileCategorizer()

    def test_categorize_magazine(self, categorizer):
        """Test categorizing magazine files."""
        assert categorizer.categorize("Wired Magazine - Jan2024.pdf") == CATEGORY_MAGAZINE
        assert categorizer.categorize("National Geographic.pdf") == CATEGORY_MAGAZINE
        assert categorizer.categorize("TIME Magazine.pdf") == CATEGORY_MAGAZINE

    def test_categorize_comic(self, categorizer):
        """Test categorizing comic files."""
        result = categorizer.categorize("Batman Comic #1.pdf")
        assert result == CATEGORY_COMIC

    def test_categorize_graphic_novel(self, categorizer):
        """Test categorizing graphic novel files."""
        result = categorizer.categorize("Watchmen Graphic Novel.pdf")
        assert result == CATEGORY_GRAPHIC_NOVEL

    def test_categorize_book(self, categorizer):
        """Test categorizing book files."""
        result = categorizer.categorize("Fiction Novel Book.pdf")
        assert result == CATEGORY_BOOK

    def test_categorize_document(self, categorizer):
        """Test categorizing document files."""
        result = categorizer.categorize("Research Article 2024.pdf")
        assert result == CATEGORY_DOCUMENT

    def test_categorize_case_insensitive(self, categorizer):
        """Test that categorization is case-insensitive."""
        assert categorizer.categorize("WIRED MAGAZINE.pdf") == CATEGORY_MAGAZINE
        assert categorizer.categorize("wired magazine.pdf") == CATEGORY_MAGAZINE

    def test_categorize_default(self, categorizer):
        """Test that unknown files default to DEFAULT_CATEGORY."""
        result = categorizer.categorize("Unknown File.pdf")
        assert result == DEFAULT_CATEGORY

    def test_categorize_with_multiple_keywords(self, categorizer):
        """Test categorization when multiple keywords present."""
        # Should use first match
        result = categorizer.categorize("Magazine Comic Book.pdf")
        assert result in CATEGORIES

    def test_categorize_from_path(self, categorizer):
        """Test categorization from full file path."""
        path = "/downloads/magazines/Wired - Jan2024.pdf"
        result = categorizer.categorize(path)
        assert result == CATEGORY_MAGAZINE

    def test_categorize_without_extension(self, categorizer):
        """Test categorization of file without extension."""
        result = categorizer.categorize("Magazine Title")
        assert result is not None


class TestCategoryKeywords:
    """Test CATEGORY_KEYWORDS constant."""

    def test_category_keywords_exists(self):
        """Test that CATEGORY_KEYWORDS mapping exists."""
        assert CATEGORY_KEYWORDS is not None
        assert isinstance(CATEGORY_KEYWORDS, dict)

    def test_has_main_categories(self):
        """Test that main categories are defined."""
        # Should have exactly these categories
        expected_categories = [
            CATEGORY_MAGAZINE,
            CATEGORY_COMIC,
            CATEGORY_GRAPHIC_NOVEL,
            CATEGORY_BOOK,
            CATEGORY_DOCUMENT,
        ]

        for category in expected_categories:
            assert category in CATEGORY_KEYWORDS

    def test_keywords_are_lists(self):
        """Test that each category maps to a list of keywords."""
        for category, keywords in CATEGORY_KEYWORDS.items():
            assert isinstance(keywords, (list, tuple))
            assert len(keywords) > 0

    def test_keywords_are_strings(self):
        """Test that keywords are strings."""
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                assert isinstance(keyword, str)
                assert len(keyword) > 0


class TestCategorizerKeywordMatching:
    """Test keyword matching logic."""

    @pytest.fixture
    def categorizer(self):
        return FileCategorizer()

    def test_matches_magazine_keywords(self, categorizer):
        """Test matching various magazine-related keywords."""
        magazine_terms = ["magazine", "wired", "time"]

        for term in magazine_terms:
            filename = f"Test {term} - Jan2024.pdf"
            result = categorizer.categorize(filename)
            assert result == CATEGORY_MAGAZINE

    def test_matches_comic_keywords(self, categorizer):
        """Test matching comic-related keywords."""
        comic_terms = ["comic", "comics", "marvel"]

        for term in comic_terms:
            filename = f"Test {term}.pdf"
            result = categorizer.categorize(filename)
            assert result == CATEGORY_COMIC

    def test_matches_document_keywords(self, categorizer):
        """Test matching document-related keywords."""
        document_terms = ["article", "paper", "journal", "report"]

        for term in document_terms:
            filename = f"Test {term}.pdf"
            result = categorizer.categorize(filename)
            assert result == CATEGORY_DOCUMENT

    def test_partial_word_matching(self, categorizer):
        """Test that keywords match partial words."""
        # "comic" in "comics" should match
        assert categorizer.categorize("Comics.pdf") == CATEGORY_COMIC


class TestCategorizerEdgeCases:
    """Test edge cases in categorization."""

    @pytest.fixture
    def categorizer(self):
        return FileCategorizer()

    def test_categorize_empty_string(self, categorizer):
        """Test categorization with empty string."""
        result = categorizer.categorize("")
        assert result == DEFAULT_CATEGORY

    def test_categorize_none(self, categorizer):
        """Test categorization with None input."""
        try:
            result = categorizer.categorize(None)
            assert result == DEFAULT_CATEGORY
        except (TypeError, AttributeError):
            # Expected if function doesn't handle None gracefully
            pass

    def test_categorize_with_numbers_only(self, categorizer):
        """Test categorization with numbers only."""
        result = categorizer.categorize("12345.pdf")
        assert result == DEFAULT_CATEGORY

    def test_categorize_with_special_chars(self, categorizer):
        """Test categorization with special characters."""
        result = categorizer.categorize("@#$%.pdf")
        assert result == DEFAULT_CATEGORY

    def test_categorize_very_long_filename(self, categorizer):
        """Test categorization with very long filename."""
        long_name = "Magazine " * 50 + ".pdf"
        result = categorizer.categorize(long_name)
        assert result == CATEGORY_MAGAZINE

    def test_categorize_unicode(self, categorizer):
        """Test categorization with unicode characters."""
        result = categorizer.categorize("Magazín Tëst.pdf")
        assert result is not None


class TestCategorizerIntegration:
    """Integration tests for categorization."""

    @pytest.fixture
    def categorizer(self):
        return FileCategorizer()

    def test_categorize_realistic_filenames(self, categorizer):
        """Test categorization with realistic filenames."""
        examples = {
            "Wired Magazine - January 2024.pdf": CATEGORY_MAGAZINE,
            "National Geographic 2024-01.pdf": CATEGORY_MAGAZINE,
            "Batman #567.pdf": CATEGORY_COMIC,
            "Watchmen Omnibus.pdf": CATEGORY_GRAPHIC_NOVEL,
        }

        for filename, expected_category in examples.items():
            result = categorizer.categorize(filename)
            assert result == expected_category

    def test_categorize_from_download_paths(self, categorizer):
        """Test categorization from typical download paths."""
        paths = [
            "/downloads/Wired.Magazine.2024.01.pdf",
            "/downloads/comics/Batman-567.pdf",
            "/downloads/documents/Research-Paper.pdf",
        ]

        for path in paths:
            result = categorizer.categorize(path)
            assert result is not None

    def test_categorize_matches_folder_organization(self, categorizer):
        """Test that categorization matches expected folder structure."""
        # Categories should align with folder names
        magazine_result = categorizer.categorize("Magazine.pdf")

        # Result should be a valid category name
        assert isinstance(magazine_result, str)
        assert len(magazine_result) > 0
        assert magazine_result in CATEGORIES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
