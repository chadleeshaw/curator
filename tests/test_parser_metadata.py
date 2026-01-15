#!/usr/bin/env python3
"""
Test suite for core.parsers.metadata module
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.metadata import MetadataExtractor, parse_month, parse_multi_month


def test_metadata_extractor_initialization():
    """Test MetadataExtractor initialization"""
    extractor = MetadataExtractor()

    assert extractor is not None
    assert hasattr(extractor, 'system_folders')


def test_metadata_extractor_with_filename():
    """Test extracting metadata from filename"""
    extractor = MetadataExtractor()

    # MetadataExtractor has methods like extract() that work with Path objects
    # Test that it can be instantiated and has expected attributes
    assert hasattr(extractor, 'system_folders')
    assert isinstance(extractor.system_folders, set)


def test_metadata_extractor_system_folders():
    """Test that system folders are defined"""
    extractor = MetadataExtractor()

    # Should have common system folder names
    assert 'downloads' in extractor.system_folders
    assert 'data' in extractor.system_folders


# ==============================================================================
# Test parse_month function
# ==============================================================================


class TestParseMonth:
    """Test parse_month function."""

    def test_parse_full_month_names(self):
        """Test parsing full month names."""
        assert parse_month("January") == 1
        assert parse_month("February") == 2
        assert parse_month("March") == 3
        assert parse_month("December") == 12

    def test_parse_month_abbreviations(self):
        """Test parsing month abbreviations."""
        assert parse_month("Jan") == 1
        assert parse_month("Feb") == 2
        assert parse_month("Mar") == 3
        assert parse_month("Dec") == 12

    def test_parse_month_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        assert parse_month("JANUARY") == 1
        assert parse_month("january") == 1
        assert parse_month("JaNuArY") == 1
        assert parse_month("DEC") == 12
        assert parse_month("dec") == 12

    def test_parse_seasons(self):
        """Test parsing seasonal names."""
        assert parse_month("Spring") == 3
        assert parse_month("Summer") == 6
        assert parse_month("Fall") == 9
        assert parse_month("Autumn") == 9
        assert parse_month("Winter") == 12

    def test_parse_invalid_month(self):
        """Test invalid month strings return None."""
        assert parse_month("InvalidMonth") is None
        assert parse_month("Xyz") is None
        assert parse_month("") is None
        assert parse_month("13") is None


# ==============================================================================
# Test parse_multi_month function
# ==============================================================================


class TestParseMultiMonth:
    """Test parse_multi_month function."""

    def test_parse_multi_month_slash(self):
        """Test parsing multi-month periods with slash."""
        month_num, display = parse_multi_month("June/July")
        assert month_num == 6
        assert display == "June/July"

    def test_parse_multi_month_dash(self):
        """Test parsing multi-month periods with dash."""
        month_num, display = parse_multi_month("December-January")
        assert month_num == 12
        assert display == "December/January"  # Normalized to slash

    def test_parse_multi_month_ampersand(self):
        """Test parsing multi-month periods with ampersand."""
        month_num, display = parse_multi_month("Aug&Sep")
        assert month_num == 8
        assert display == "Aug/Sep"  # Normalized to slash

    def test_parse_multi_month_abbreviations(self):
        """Test multi-month with abbreviations."""
        month_num, display = parse_multi_month("Jun/Jul")
        assert month_num == 6
        assert display == "Jun/Jul"

    def test_parse_multi_month_case_insensitive(self):
        """Test multi-month parsing is case-insensitive."""
        month_num, display = parse_multi_month("JUNE/JULY")
        assert month_num == 6
        assert "June" in display and "July" in display

    def test_parse_single_month(self):
        """Test that single months work correctly."""
        month_num, display = parse_multi_month("December")
        assert month_num == 12
        assert display == "December"

    def test_parse_multi_month_invalid(self):
        """Test invalid multi-month strings."""
        month_num, display = parse_multi_month("Invalid/Month")
        assert month_num is None
        assert display == "Invalid/Month"

    def test_parse_multi_month_empty(self):
        """Test empty string."""
        month_num, display = parse_multi_month("")
        assert month_num is None
        assert display == ""

    def test_parse_multi_season_period(self):
        """Test parsing multi-season periods."""
        month_num, display = parse_multi_month("Spring/Summer")
        assert month_num == 3  # Spring
        assert display == "Spring/Summer"

    def test_parse_multi_season_fall_winter(self):
        """Test parsing Fall/Winter season period."""
        month_num, display = parse_multi_month("Fall/Winter")
        assert month_num == 9  # Fall
        assert display == "Fall/Winter"

    def test_parse_single_season(self):
        """Test single season periods."""
        month_num, display = parse_multi_month("Spring")
        assert month_num == 3
        assert display == "Spring"

        month_num, display = parse_multi_month("Winter")
        assert month_num == 12
        assert display == "Winter"


# ==============================================================================
# Test MetadataExtractor with multi-month patterns
# ==============================================================================


class TestMetadataExtractorMultiMonth:
    """Test MetadataExtractor with multi-month period filenames."""

    def test_extract_multi_month_slash(self):
        """Test extracting metadata from multi-month filename with slash."""
        extractor = MetadataExtractor()
        # Use dash instead of slash for filesystem compatibility
        pdf_path = Path("/test/National Geographic - June-July 2003.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["title"] == "National Geographic"
        assert result["year"] == 2003
        assert result["month_name"] == "June/July"  # Normalized to slash
        assert result["issue_date"].year == 2003
        assert result["issue_date"].month == 6  # First month used for sorting

    def test_extract_multi_month_abbreviated(self):
        """Test extracting metadata from abbreviated multi-month filename."""
        extractor = MetadataExtractor()
        # Use dash for filesystem compatibility
        pdf_path = Path("/test/Wired - Jun-Jul2024.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert "Wired" in result["title"]
        assert result["year"] == 2024
        # Normalized to slash format
        assert result["month_name"] == "Jun/Jul"
        assert result["issue_date"].month == 6

    def test_extract_multi_month_december_january(self):
        """Test extracting year-crossing multi-month period."""
        extractor = MetadataExtractor()
        # Use dash for filesystem compatibility
        pdf_path = Path("/test/Magazine - December-January 2024.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2024
        # Normalized to slash format
        assert result["month_name"] == "December/January"
        assert result["issue_date"].month == 12  # Uses first month

    def test_extract_multi_month_with_dash(self):
        """Test multi-month with dash separator."""
        extractor = MetadataExtractor()
        pdf_path = Path("/test/PC Gamer - Aug-Sep2023.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2023
        assert result["month_name"] == "Aug/Sep"  # Normalized to slash
        assert result["issue_date"].month == 8

    def test_standard_single_month_still_works(self):
        """Test that standard single-month parsing still works."""
        extractor = MetadataExtractor()
        pdf_path = Path("/test/Wired - Dec2024.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert "Wired" in result["title"]
        assert result["issue_date"].year == 2024
        assert result["issue_date"].month == 12

    def test_seasonal_still_works(self):
        """Test that seasonal parsing still works."""
        extractor = MetadataExtractor()
        pdf_path = Path("/test/Magazine Winter 2024.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2024
        assert result["month_name"] == "Winter"
        assert result["issue_date"].month == 12  # Winter maps to December

    def test_extract_multi_season_period(self):
        """Test extracting multi-season periods like Spring/Summer."""
        extractor = MetadataExtractor()
        # Use dash for filesystem compatibility
        pdf_path = Path("/test/Fashion Magazine - Spring-Summer 2024.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2024
        # Normalized to slash format
        assert result["month_name"] == "Spring/Summer"
        assert result["issue_date"].month == 3  # Uses Spring (first season)

    def test_extract_fall_winter_period(self):
        """Test extracting Fall/Winter season period."""
        extractor = MetadataExtractor()
        # Use dash for filesystem compatibility
        pdf_path = Path("/test/Vogue - Fall-Winter 2023.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2023
        # Normalized to slash format
        assert result["month_name"] == "Fall/Winter"
        assert result["issue_date"].month == 9  # Uses Fall (first season)

    def test_extract_autumn_winter_period(self):
        """Test extracting Autumn/Winter (synonym for Fall/Winter)."""
        extractor = MetadataExtractor()
        # Use dash for filesystem compatibility
        pdf_path = Path("/test/Magazine - Autumn-Winter 2023.pdf")

        result = extractor.extract_from_filename(pdf_path)

        assert result["year"] == 2023
        # Normalized to slash format
        assert result["month_name"] == "Autumn/Winter"
        assert result["issue_date"].month == 9  # Uses Autumn (same as Fall)
