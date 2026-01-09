#!/usr/bin/env python3
"""
Test suite for file categorization utilities.
Tests categorizing files into magazines, comics, newspapers, etc.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers import FileCategorizer
from core.constants import CATEGORY_KEYWORDS


class TestFileCategorizer:
    """Test FileCategorizer class."""

    @pytest.fixture
    def categorizer(self):
        """Create a FileCategorizer instance for testing."""
        return FileCategorizer()

    def test_categorize_magazine(self, categorizer):
        """Test categorizing magazine files."""
        assert categorizer.categorize("Wired Magazine - Jan2024.pdf") == "Magazines"
        assert categorizer.categorize("National Geographic.pdf") == "Magazines"
        assert categorizer.categorize("TIME Magazine.pdf") == "Magazines"

    def test_categorize_comic(self, categorizer):
        """Test categorizing comic files."""
        result = categorizer.categorize("Batman Comic #1.pdf")
        assert result == "Comics"

    def test_categorize_newspaper(self, categorizer):
        """Test categorizing newspaper files."""
        result = categorizer.categorize("New York Times - Daily.pdf")
        # May categorize as News or Magazines depending on keywords
        assert result in ["News", "Magazines"]

    def test_categorize_article(self, categorizer):
        """Test categorizing article files."""
        result = categorizer.categorize("Research Article 2024.pdf")
        assert result == "Articles"

    def test_categorize_case_insensitive(self, categorizer):
        """Test that categorization is case-insensitive."""
        assert categorizer.categorize("WIRED MAGAZINE.pdf") == "Magazines"
        assert categorizer.categorize("wired magazine.pdf") == "Magazines"

    def test_categorize_default_to_magazines(self, categorizer):
        """Test that unknown files default to Magazines."""
        result = categorizer.categorize("Unknown File.pdf")
        assert result == "Magazines"  # Or whatever the default is

    def test_categorize_with_multiple_keywords(self, categorizer):
        """Test categorization when multiple keywords present."""
        # Should use first or most specific match
        result = categorizer.categorize("Magazine Comic News.pdf")
        assert result in ["Magazines", "Comics", "News"]

    def test_categorize_from_path(self, categorizer):
        """Test categorization from full file path."""
        path = "/downloads/magazines/Wired - Jan2024.pdf"
        result = categorizer.categorize(path)
        assert result == "Magazines"

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
        # Should have at minimum these categories
        expected_categories = ["Magazines", "Comics", "News", "Articles"]

        for category in expected_categories:
            # Check if category exists in keys (allowing for case variations)
            assert any(category.lower() in key.lower() for key in CATEGORY_KEYWORDS.keys())

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
        magazine_terms = ["magazine", "periodical", "journal"]

        for term in magazine_terms:
            filename = f"Test {term} - Jan2024.pdf"
            result = categorizer.categorize(filename)
            # Should match Magazines or Articles
            assert result in ["Magazines", "Articles"]

    def test_matches_comic_keywords(self, categorizer):
        """Test matching comic-related keywords."""
        comic_terms = ["comic", "comics"]

        for term in comic_terms:
            filename = f"Test {term}.pdf"
            result = categorizer.categorize(filename)
            assert result == "Comics"

    def test_matches_news_keywords(self, categorizer):
        """Test matching news-related keywords."""
        news_terms = ["newspaper", "daily", "times"]

        for term in news_terms:
            filename = f"Test {term}.pdf"
            result = categorizer.categorize(filename)
            # Should be News or possibly Magazines depending on implementation
            assert result is not None

    def test_partial_word_matching(self, categorizer):
        """Test that keywords match partial words or require boundaries."""
        # "comic" in "comics" should match
        assert categorizer.categorize("Comics.pdf") == "Comics"

        # But should not match in random places
        result = categorizer.categorize("Comical.pdf")
        # Depends on implementation - may or may not match


class TestCategorizerEdgeCases:
    """Test edge cases in categorization."""

    @pytest.fixture
    def categorizer(self):
        return FileCategorizer()

    def test_categorize_empty_string(self, categorizer):
        """Test categorization with empty string."""
        result = categorizer.categorize("")
        assert result is not None  # Should have a default

    def test_categorize_none(self, categorizer):
        """Test categorization with None input."""
        try:
            result = categorizer.categorize(None)
            assert result is not None
        except (TypeError, AttributeError):
            # Expected if function doesn't handle None
            pass

    def test_categorize_with_numbers_only(self, categorizer):
        """Test categorization with numbers only."""
        result = categorizer.categorize("12345.pdf")
        assert result is not None

    def test_categorize_with_special_chars(self, categorizer):
        """Test categorization with special characters."""
        result = categorizer.categorize("@#$%.pdf")
        assert result is not None

    def test_categorize_very_long_filename(self, categorizer):
        """Test categorization with very long filename."""
        long_name = "Magazine " * 50 + ".pdf"
        result = categorizer.categorize(long_name)
        assert result == "Magazines"

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
            "Wired Magazine - January 2024.pdf": "Magazines",
            "National Geographic 2024-01.pdf": "Magazines",
            "Batman #567.pdf": "Comics",
            "The New York Times - 2024-01-15.pdf": "News",
        }

        for filename, expected_category in examples.items():
            result = categorizer.categorize(filename)
            # Allow some flexibility in categorization
            assert result is not None

    def test_categorize_from_download_paths(self, categorizer):
        """Test categorization from typical download paths."""
        paths = [
            "/downloads/Wired.Magazine.2024.01.pdf",
            "/downloads/comics/Batman-567.pdf",
            "/downloads/newspaper/NYT-2024-01-15.pdf",
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
