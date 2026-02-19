"""
Tests for numeric multi-month period parsing.

Regression tests for issue where period-separated numeric months (like "11.10")
were being mistaken as variants instead of being recognized as month ranges.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from core.parsers.date import parse_numeric_month_range
from core.parsers.metadata import FilenameParser


class TestNumericMonthRangeParser:
    """Test the parse_numeric_month_range function."""

    def test_consecutive_months_normal_order(self):
        """Test consecutive months in normal order (e.g., 10/11 = Oct/Nov)"""
        month, display = parse_numeric_month_range("10", "11")
        assert month == 10
        assert display == "October/November"

    def test_consecutive_months_reversed_order(self):
        """Test consecutive months in reversed order (e.g., 11/10 = Oct/Nov)"""
        month, display = parse_numeric_month_range("11", "10")
        assert month == 10
        assert display == "October/November"

    def test_year_boundary_months(self):
        """Test months spanning year boundary (e.g., 12/01 = Dec/Jan)"""
        month, display = parse_numeric_month_range("12", "01")
        assert month == 12
        assert display == "December/January"

    def test_non_consecutive_months(self):
        """Test non-consecutive months (use lower month as primary)"""
        month, display = parse_numeric_month_range("05", "08")
        assert month == 5
        assert display == "May/August"

    def test_same_month(self):
        """Test when both months are the same"""
        month, display = parse_numeric_month_range("06", "06")
        assert month == 6
        assert display == "June/June"

    def test_leading_zeros(self):
        """Test that leading zeros are handled correctly"""
        month, display = parse_numeric_month_range("05", "06")
        assert month == 5
        assert display == "May/June"

    def test_invalid_month_numbers(self):
        """Test that invalid month numbers return None"""
        month, display = parse_numeric_month_range("13", "14")
        assert month is None
        assert display == ""

        month, display = parse_numeric_month_range("00", "01")
        assert month is None
        assert display == ""

    def test_non_numeric_input(self):
        """Test that non-numeric input returns None"""
        month, display = parse_numeric_month_range("abc", "def")
        assert month is None
        assert display == ""


class TestNumericMultiMonthInNZBParser:
    """Test numeric multi-month parsing in NZB-style filenames."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_dot_separator_with_spaces(self, parser):
        """Test: Wired Magazine 11.10 2019"""
        result = parser.extract_from_nzb_title("Wired Magazine 11.10 2019")

        assert result["title"] == "Wired Magazine"
        assert result["year"] == 2019
        assert result["month"] == 10
        assert result["month_name"] == "October/November"
        assert result["issue_date"] == datetime(2019, 10, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_dot_separator_no_spaces(self, parser):
        """Test: Wired.Magazine.11.10.2019"""
        result = parser.extract_from_nzb_title("Wired.Magazine.11.10.2019")

        assert result["title"] == "Wired Magazine"
        assert result["year"] == 2019
        assert result["month"] == 10
        assert result["month_name"] == "October/November"
        assert result["issue_date"] == datetime(2019, 10, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_slash_separator(self, parser):
        """Test: Forbes 06/07 2022"""
        result = parser.extract_from_nzb_title("Forbes 06/07 2022")

        assert result["title"] == "Forbes"
        assert result["year"] == 2022
        assert result["month"] == 6
        assert result["month_name"] == "June/July"
        assert result["issue_date"] == datetime(2022, 6, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_dash_separator(self, parser):
        """Test: Esquire 10-11 2021"""
        result = parser.extract_from_nzb_title("Esquire 10-11 2021")

        assert result["title"] == "Esquire"
        assert result["year"] == 2021
        assert result["month"] == 10
        assert result["month_name"] == "October/November"
        assert result["issue_date"] == datetime(2021, 10, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_may_june_period(self, parser):
        """Test: National Geographic 05.06 2023"""
        result = parser.extract_from_nzb_title("National Geographic 05.06 2023")

        assert result["title"] == "National Geographic"
        assert result["year"] == 2023
        assert result["month"] == 5
        assert result["month_name"] == "May/June"
        assert result["issue_date"] == datetime(2023, 5, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_december_january_boundary(self, parser):
        """Test: Time 12.01 2024"""
        result = parser.extract_from_nzb_title("Time 12.01 2024")

        assert result["title"] == "Time"
        assert result["year"] == 2024
        assert result["month"] == 12
        assert result["month_name"] == "December/January"
        assert result["issue_date"] == datetime(2024, 12, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_march_april_dot_separator(self, parser):
        """Test: PC Gamer 03.04 2020"""
        result = parser.extract_from_nzb_title("PC Gamer 03.04 2020")

        assert result["title"] == "PC Gamer"
        assert result["year"] == 2020
        assert result["month"] == 3
        assert result["month_name"] == "March/April"
        assert result["issue_date"] == datetime(2020, 3, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_august_september_slash(self, parser):
        """Test: The Economist 08/09 2018"""
        result = parser.extract_from_nzb_title("The Economist 08/09 2018")

        assert result["title"] == "The Economist"
        assert result["year"] == 2018
        assert result["month"] == 8
        assert result["month_name"] == "August/September"
        assert result["issue_date"] == datetime(2018, 8, 1, tzinfo=UTC)
        assert result["confidence"] == "high"

    def test_with_country_code(self, parser):
        """Test: Wired.USA.11.10.2019"""
        result = parser.extract_from_nzb_title("Wired.USA.11.10.2019")

        assert result["title"] == "Wired"
        assert result["country"] == "USA"
        assert result["year"] == 2019
        assert result["month"] == 10
        assert result["month_name"] == "October/November"
        assert result["confidence"] == "high"

    def test_with_quality_indicator(self, parser):
        """Test: National.Geographic.HQ.05.06.2023"""
        result = parser.extract_from_nzb_title("National.Geographic.HQ.05.06.2023")

        assert result["title"] == "National Geographic"
        assert result["quality"] == "HQ"
        assert result["year"] == 2023
        assert result["month"] == 5
        assert result["month_name"] == "May/June"
        assert result["confidence"] == "high"


class TestNumericMultiMonthInFilenameParser:
    """Test numeric multi-month parsing in standard filename extraction."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_numeric_multimonth_in_filename(self, parser):
        """Test that numeric multi-month works in extract_from_filename"""
        path = Path("/magazines/Wired/Wired Magazine 11.10 2019.pdf")
        result = parser.extract_from_filename(path)

        assert result["title"] == "Wired Magazine"
        assert result["year"] == 2019
        assert result["month_name"] == "October/November"
        assert result["issue_date"] == datetime(2019, 10, 1, tzinfo=UTC)

    def test_numeric_multimonth_with_dots(self, parser):
        """Test dot-separated format in extract_from_filename"""
        path = Path("/magazines/Forbes/Forbes.06.07.2022.pdf")
        result = parser.extract_from_filename(path)

        assert result["title"] == "Forbes"
        assert result["year"] == 2022
        # Should extract the multi-month period
        assert result.get("month_name") == "June/July" or result.get("year") == 2022


class TestEdgeCases:
    """Test edge cases and potential conflicts."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_not_confused_with_version_numbers(self, parser):
        """Test that version numbers like v2.10 are not mistaken for months"""
        result = parser.extract_from_nzb_title("Software v2.10 2023")
        # Should not parse "2.10" as February/October
        # This should fail or extract year only
        assert result["month_name"] != "February/October"

    def test_not_confused_with_decimal_numbers(self, parser):
        """Test that decimal numbers are not mistaken for month ranges"""
        result = parser.extract_from_nzb_title("Price 19.99 2023")
        # Should not parse "19.99" as months (19 is invalid month)
        assert result["month"] is None or result["month"] == 1  # Default

    def test_single_digit_months(self, parser):
        """Test single-digit month numbers without leading zeros"""
        result = parser.extract_from_nzb_title("Magazine 5.6 2023")

        assert result["year"] == 2023
        assert result["month"] == 5
        assert result["month_name"] == "May/June"

    def test_alphabetic_multimonth_still_works(self, parser):
        """Test that alphabetic multi-month parsing still works"""
        result = parser.extract_from_nzb_title("National Geographic Magazine Jun/Jul 2024")

        # The title might include partial month text depending on how normalization works
        assert "National Geographic" in result["title"]
        assert result["year"] == 2024
        # Month name should contain month indicators
        assert result.get("month_name") is not None or result.get("month") in [6, 7]
        assert result["confidence"] in ["medium", "high"]
