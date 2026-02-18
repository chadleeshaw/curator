"""
Tests for video extension filtering in anti-periodical patterns.

These tests verify that video files (mp4, avi, mkv, etc.) are correctly rejected
while legitimate magazines with similar names (MP Weekly, etc.) are accepted.
"""

import pytest
from core.parsers import Parser
from core.parsers.metadata import FilenameParser


class TestVideoExtensionFiltering:
    """Test that video file extensions are correctly filtered out"""

    @pytest.fixture
    def parser(self):
        """Create a Parser instance for testing"""
        return Parser()

    @pytest.fixture
    def filename_parser(self):
        """Create a FilenameParser instance for testing"""
        return FilenameParser()

    def test_rejects_simple_mp4_extension(self, parser):
        """Test that simple .mp4 extension is rejected"""
        result = parser.parse_search_result(
            title="Magazine.Jan.2024.mp4",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject .mp4 extension"

    def test_rejects_mp4_in_nzb_filename(self, parser):
        """Test that .mp4 in middle of NZB filename is rejected"""
        result = parser.parse_search_result(
            title="Magazine.Jan.2024.mp4.nzb",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject .mp4 even with .nzb extension"

    def test_rejects_mp4_in_release_group(self, parser):
        """
        Test that mp4 in release group names is rejected.

        This was the original bug: titles like "Magazine.Jan.2024-MP4GROUP"
        were being accepted because "MP4GROUP" is a single word without
        boundaries around "MP4".
        """
        result = parser.parse_search_result(
            title="Magazine.Jan.2024-MP4GROUP",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject mp4 in release group names like MP4GROUP"

    def test_rejects_uppercase_mp4(self, parser):
        """Test that uppercase MP4 is rejected"""
        result = parser.parse_search_result(
            title="Magazine.Jan.2024.MP4",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject uppercase .MP4"

    def test_rejects_avi_extension(self, parser):
        """Test that .avi extension is rejected"""
        result = parser.parse_search_result(
            title="Test.Magazine.2024.avi",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject .avi extension"

    def test_rejects_mkv_extension(self, parser):
        """Test that .mkv extension is rejected"""
        result = parser.parse_search_result(
            title="Test.mkv.Jan.2024",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject .mkv extension"

    def test_accepts_magazine_with_mp_in_name(self, parser):
        """Test that magazines with MP in the name are accepted"""
        result = parser.parse_search_result(
            title="MP.Weekly.Jan.2024.pdf",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is not None, "Should accept magazines with MP in name"
        assert "mp" in result.title.lower(), "Title should contain MP"

    def test_accepts_example_mp_magazine(self, parser):
        """Test that 'Example MP Magazine' is accepted"""
        result = parser.parse_search_result(
            title="Example.MP.Magazine.Jan.2024.pdf",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is not None, "Should accept magazine with MP in middle of name"

    def test_accepts_computer_mp_review(self, parser):
        """Test that 'Computer MP Review' is accepted"""
        result = parser.parse_search_result(
            title="Computer.MP.Review.Jan.2024.pdf",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is not None, "Should accept magazine with MP in title"

    def test_filename_parser_rejects_video_extensions(self, filename_parser):
        """Test that FilenameParser rejects video extensions"""
        test_cases = [
            "Magazine.Jan.2024.mp4",
            "Magazine-mp4",
            "Test.avi",
            "Video.mkv.nzb",
        ]

        for title in test_cases:
            result = filename_parser.extract_from_nzb_title(title)
            assert result is None, f"FilenameParser should reject '{title}'"

    def test_filename_parser_accepts_legitimate_magazines(self, filename_parser):
        """Test that FilenameParser accepts legitimate magazines"""
        test_cases = [
            "MP.Weekly.Jan.2024.pdf",
            "Example.MP.Magazine.Jan.2024.pdf",
        ]

        for title in test_cases:
            result = filename_parser.extract_from_nzb_title(title)
            assert result is not None, f"FilenameParser should accept '{title}'"
            assert result.get("title"), f"Should extract title from '{title}'"


class TestVideoExtensionEdgeCases:
    """Test edge cases for video extension filtering"""

    @pytest.fixture
    def parser(self):
        """Create a Parser instance for testing"""
        return Parser()

    def test_rejects_video_with_quality_indicators(self, parser):
        """Test that video files with quality indicators are rejected"""
        result = parser.parse_search_result(
            title="Movie.2024.1080p.BluRay.mp4",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject video with quality indicators"

    def test_rejects_mp4_with_dash_separator(self, parser):
        """Test that mp4 with dash separator is rejected"""
        result = parser.parse_search_result(
            title="Magazine-mp4-Jan-2024",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject mp4 with dash separator"

    def test_rejects_mp4_with_underscore_separator(self, parser):
        """Test that mp4 with underscore separator is rejected"""
        result = parser.parse_search_result(
            title="Magazine_mp4_Jan_2024",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject mp4 with underscore separator"

    def test_rejects_mp4_at_end_of_title(self, parser):
        """Test that mp4 at end of title is rejected"""
        result = parser.parse_search_result(
            title="Test Magazine Jan 2024 mp4",
            url="http://example.com/test.nzb",
            provider="test",
            publication_date=None,
            raw_metadata={},
        )
        assert result is None, "Should reject mp4 at end of title"

    def test_rejects_mixed_case_mp4(self, parser):
        """Test that mixed case mp4 variants are rejected"""
        test_cases = [
            "Magazine.Mp4",
            "Magazine.mP4",
            "Magazine.MP4",
        ]

        for title in test_cases:
            result = parser.parse_search_result(
                title=title, url="http://example.com/test.nzb", provider="test", publication_date=None, raw_metadata={}
            )
            assert result is None, f"Should reject mixed case variant '{title}'"
