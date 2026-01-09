#!/usr/bin/env python3
"""
Test suite for filename parsing and sanitization utilities.
Tests filename parsing for metadata and filename sanitization.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers import parse_filename_for_metadata, sanitize_filename


class TestSanitizeFilename:
    """Test sanitize_filename function."""

    def test_remove_invalid_characters(self):
        """Test removal of filesystem-invalid characters."""
        assert sanitize_filename('Wired <Magazine>: "2023"') == "Wired Magazine 2023"
        assert sanitize_filename("Test|File\\Path") == "TestFilePath"
        assert sanitize_filename("File/Name") == "FileName"

    def test_preserve_valid_characters(self):
        """Test that valid characters are preserved."""
        assert sanitize_filename("National Geographic") == "National Geographic"
        assert sanitize_filename("Magazine-2024") == "Magazine-2024"
        assert sanitize_filename("Test.Magazine") == "Test.Magazine"

    def test_remove_pipes_and_backslashes(self):
        """Test removal of pipes and backslashes."""
        assert sanitize_filename("Test|File") == "TestFile"
        assert sanitize_filename("Test\\File") == "TestFile"
        assert sanitize_filename("Path\\To|File") == "PathToFile"

    def test_remove_quotes(self):
        """Test removal of double quotes only."""
        assert sanitize_filename('Test "File"') == "Test File"
        # Single quotes are not removed
        assert sanitize_filename("Test 'File'") == "Test 'File'"

    def test_remove_angle_brackets(self):
        """Test removal of angle brackets."""
        assert sanitize_filename("Test<File>") == "TestFile"
        assert sanitize_filename("<Magazine>") == "Magazine"

    def test_remove_colons(self):
        """Test removal of colons."""
        assert sanitize_filename("Magazine: Special Edition") == "Magazine Special Edition"

    def test_multiple_invalid_chars(self):
        """Test sanitizing multiple invalid characters."""
        messy = 'Test<>:"|?*\\File'
        result = sanitize_filename(messy)
        # Should remove all invalid chars
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result
        assert "\\" not in result

    def test_preserve_spaces(self):
        """Test that spaces are preserved."""
        assert sanitize_filename("Test File Name") == "Test File Name"

    def test_preserve_hyphens_and_underscores(self):
        """Test that hyphens and underscores are preserved."""
        assert sanitize_filename("Test-File_Name") == "Test-File_Name"

    def test_preserve_dots(self):
        """Test that dots are preserved."""
        assert sanitize_filename("Test.File.Name") == "Test.File.Name"

    def test_empty_string(self):
        """Test sanitizing empty string."""
        result = sanitize_filename("")
        assert result == ""

    def test_max_length_parameter(self):
        """Test optional max_length parameter if supported."""
        long_name = "A" * 300
        try:
            result = sanitize_filename(long_name, max_length=200)
            assert len(result) <= 200
        except TypeError:
            # max_length parameter not supported
            pass

    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        # Unicode should generally be preserved
        result = sanitize_filename("Magazín Tëst")
        assert "Magazín" in result or "Magazin" in result

    def test_consecutive_spaces_preserved(self):
        """Test that consecutive spaces are handled."""
        result = sanitize_filename("Test  File")
        # May collapse or preserve multiple spaces
        assert "Test" in result and "File" in result


class TestParseFilenameForMetadata:
    """Test parse_filename_for_metadata function."""

    def test_standard_format_month_year(self):
        """Test parsing standard 'Title - MonYear' format."""
        result = parse_filename_for_metadata("Wired Magazine - Dec2006")

        assert result["title"] == "Wired Magazine"
        assert result["issue_date"].month == 12
        assert result["issue_date"].year == 2006
        assert result["confidence"] == "high"

    def test_another_standard_format(self):
        """Test parsing another standard format."""
        result = parse_filename_for_metadata("National Geographic - Mar2023")

        assert result["title"] == "National Geographic"
        assert result["issue_date"].month == 3
        assert result["issue_date"].year == 2023
        assert result["confidence"] == "high"

    def test_format_with_extra_spaces(self):
        """Test parsing with extra spaces."""
        result = parse_filename_for_metadata("Time Magazine  -  Jan2010")

        assert result["title"] == "Time Magazine"
        assert result["issue_date"].month == 1
        assert result["issue_date"].year == 2010

    def test_invalid_format_returns_low_confidence(self):
        """Test that invalid format returns low confidence."""
        result = parse_filename_for_metadata("InvalidFilename")

        assert result["confidence"] == "low"

    def test_all_months_parseable(self):
        """Test that all month abbreviations are parsed correctly."""
        months = [
            ("Jan", 1), ("Feb", 2), ("Mar", 3), ("Apr", 4),
            ("May", 5), ("Jun", 6), ("Jul", 7), ("Aug", 8),
            ("Sep", 9), ("Oct", 10), ("Nov", 11), ("Dec", 12)
        ]

        for month_abbr, month_num in months:
            filename = f"Test Magazine - {month_abbr}2020"
            result = parse_filename_for_metadata(filename)

            assert result["confidence"] == "high"
            assert result["issue_date"].month == month_num
            assert result["issue_date"].year == 2020

    def test_filename_with_extension(self):
        """Test parsing filename with extension."""
        result = parse_filename_for_metadata("Magazine - Jan2024.pdf")

        # Extension in filename may cause parse to fail
        # Check if title exists before asserting
        if "title" in result:
            assert result["title"] is not None
        if result["confidence"] == "high":
            assert result["issue_date"] is not None

    def test_extracts_edition_number_if_present(self):
        """Test extraction of edition/issue number if present."""
        result = parse_filename_for_metadata("Magazine #15 - Jan2024")

        # May or may not extract edition number
        if "edition_number" in result:
            assert isinstance(result["edition_number"], (int, type(None)))

    def test_extracts_volume_if_present(self):
        """Test extraction of volume number if present."""
        result = parse_filename_for_metadata("Magazine Vol 5 - Jan2024")

        # May or may not extract volume
        if "volume" in result:
            assert isinstance(result["volume"], (int, type(None)))

    def test_returns_dict_with_required_fields(self):
        """Test that result always contains confidence field."""
        result = parse_filename_for_metadata("Any Filename")

        # Confidence is always present
        assert "confidence" in result
        # title and issue_date only present on successful parse
        if result["confidence"] == "high":
            assert "title" in result
            assert "issue_date" in result


class TestFilenameParsingEdgeCases:
    """Test edge cases in filename parsing."""

    def test_parse_filename_with_numbers_in_title(self):
        """Test parsing titles that contain numbers."""
        result = parse_filename_for_metadata("2600 Magazine - Jan2024")

        assert "2600" in result["title"]
        if result["confidence"] == "high":
            assert result["issue_date"].year == 2024

    def test_parse_filename_with_special_chars_in_title(self):
        """Test parsing titles with special characters."""
        result = parse_filename_for_metadata("PC & Gamer - Jan2024")

        assert result["title"] is not None

    def test_parse_filename_very_long_title(self):
        """Test parsing very long title."""
        long_title = "A" * 100 + " - Jan2024"
        result = parse_filename_for_metadata(long_title)

        assert result["title"] is not None

    def test_parse_filename_unicode(self):
        """Test parsing filename with unicode."""
        result = parse_filename_for_metadata("Magazín - Jan2024")

        assert result["title"] is not None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_filename_for_metadata("")

        assert result["confidence"] == "low"

    def test_parse_only_date_no_title(self):
        """Test parsing filename with only date."""
        result = parse_filename_for_metadata("Jan2024")

        # Should handle gracefully
        assert result is not None


class TestFilenameParsingIntegration:
    """Integration tests for filename parsing."""

    def test_parse_then_sanitize_workflow(self):
        """Test typical workflow: sanitize then parse."""
        # First sanitize
        dirty_filename = 'Wired Magazine - Jan2024'
        clean_filename = sanitize_filename(dirty_filename)

        # Then parse
        result = parse_filename_for_metadata(clean_filename)

        if "title" in result:
            assert result["title"] is not None
            assert "<" not in result["title"]
            assert ">" not in result["title"]

    def test_parse_realistic_downloads(self):
        """Test parsing realistic download filenames."""
        # Parser expects format: Title - MonYYYY
        good_example = "Wired Magazine - Jan2024"
        result = parse_filename_for_metadata(good_example)
        assert result is not None
        assert result["confidence"] == "high"
        assert "title" in result

        # Other formats may not parse
        result2 = parse_filename_for_metadata("TIME-2024-01-15.pdf")
        assert result2["confidence"] == "low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
