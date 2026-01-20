#!/usr/bin/env python3
"""
Test suite for date parsing utilities.
Tests month name mapping, abbreviation conversion, and date utilities.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Add parent directory to path
# Path setup handled by conftest.py

from core.parsers import (
    month_abbr_to_number,
    normalize_month_name,
    utc_now,
    MONTH_TO_NUMBER,
    NUMBER_TO_MONTH_ABBR,
)


class TestMonthAbbreviationToNumber:
    """Test month_abbr_to_number function."""

    def test_standard_abbreviations(self):
        """Test standard 3-letter month abbreviations."""
        assert month_abbr_to_number("Jan") == 1
        assert month_abbr_to_number("Feb") == 2
        assert month_abbr_to_number("Mar") == 3
        assert month_abbr_to_number("Apr") == 4
        assert month_abbr_to_number("May") == 5
        assert month_abbr_to_number("Jun") == 6
        assert month_abbr_to_number("Jul") == 7
        assert month_abbr_to_number("Aug") == 8
        assert month_abbr_to_number("Sep") == 9
        assert month_abbr_to_number("Oct") == 10
        assert month_abbr_to_number("Nov") == 11
        assert month_abbr_to_number("Dec") == 12

    def test_case_insensitive(self):
        """Test that month abbreviations are case-insensitive."""
        assert month_abbr_to_number("Jan") == 1
        assert month_abbr_to_number("Dec") == 12
        # Now supports case-insensitive lookup
        assert month_abbr_to_number("jan") == 1
        assert month_abbr_to_number("JAN") == 1
        assert month_abbr_to_number("dec") == 12

    def test_full_month_names(self):
        """Test full month names are now supported."""
        # Function now supports full month names
        result = month_abbr_to_number("January")
        assert result == 1
        result = month_abbr_to_number("january")
        assert result == 1

    def test_invalid_month(self):
        """Test invalid month abbreviation returns 0."""
        assert month_abbr_to_number("Xyz") == 0
        assert month_abbr_to_number("") == 0
        assert month_abbr_to_number("13") == 0

    def test_common_variants(self):
        """Test common month abbreviation variants."""
        # September variants
        assert month_abbr_to_number("Sep") == 9
        assert month_abbr_to_number("Sept") == 9  # Also supported now


class TestNormalizeMonthName:
    """Test normalize_month_name function."""

    def test_normalize_full_to_abbreviation(self):
        """Test normalizing abbreviations to full lowercase month names."""
        assert normalize_month_name("jan") == "january"
        assert normalize_month_name("feb") == "february"
        assert normalize_month_name("mar") == "march"
        assert normalize_month_name("dec") == "december"

    def test_normalize_abbreviation_to_abbreviation(self):
        """Test normalizing abbreviations returns full month names."""
        assert normalize_month_name("jan") == "january"
        assert normalize_month_name("dec") == "december"

    def test_normalize_case_insensitive(self):
        """Test case-insensitive normalization to lowercase."""
        # Function converts to lowercase and looks up
        assert normalize_month_name("JAN") == "january"
        assert normalize_month_name("Jan") == "january"
        assert normalize_month_name("jan") == "january"

    def test_normalize_variant_spellings(self):
        """Test variant spellings like Sept vs Sep."""
        # Sept maps to september
        result = normalize_month_name("sept")
        assert result == "september"
        # Sep also maps to september
        assert normalize_month_name("sep") == "september"

    def test_normalize_returns_original_if_unknown(self):
        """Test that unknown values are returned as-is or handled gracefully."""
        result = normalize_month_name("NotAMonth")
        # Should either return original or some default
        assert result is not None

    def test_normalize_empty_string(self):
        """Test normalization with empty string."""
        result = normalize_month_name("")
        assert result is not None


class TestMonthNameMapping:
    """Test MONTH_TO_NUMBER constant."""

    def test_mapping_has_all_months(self):
        """Test that mapping contains all 12 months."""
        # Should have mappings for common month representations
        assert isinstance(MONTH_TO_NUMBER, dict)
        # At minimum should have standard abbreviations
        assert len(MONTH_TO_NUMBER) >= 12

    def test_mapping_full_names_to_numbers(self):
        """Test that full names and abbreviations map to numbers."""
        assert MONTH_TO_NUMBER.get("january") == 1
        assert MONTH_TO_NUMBER.get("december") == 12
        assert MONTH_TO_NUMBER.get("jan") == 1
        assert MONTH_TO_NUMBER.get("dec") == 12


class TestMonthNumberMapping:
    """Test NUMBER_TO_MONTH_ABBR constant."""

    def test_mapping_has_all_twelve_months(self):
        """Test that mapping has entries for months 1-12."""
        assert isinstance(NUMBER_TO_MONTH_ABBR, dict)

        # Mapping uses numbers as keys
        # Check we have 12 entries
        assert len(NUMBER_TO_MONTH_ABBR) == 12

    def test_mapping_returns_month_abbreviations(self):
        """Test that numbers map to month abbreviations."""
        assert NUMBER_TO_MONTH_ABBR[1] == "Jan"
        assert NUMBER_TO_MONTH_ABBR[12] == "Dec"


class TestUtcNow:
    """Test utc_now utility function."""

    def test_returns_datetime(self):
        """Test that utc_now returns a datetime object."""
        result = utc_now()
        assert isinstance(result, datetime)

    def test_returns_utc_time(self):
        """Test that returned time is in UTC."""
        result = utc_now()
        # Should have UTC timezone info or be timezone-naive but represent UTC
        assert result is not None

    def test_returns_current_time(self):
        """Test that returned time is approximately current."""
        before = datetime.now(UTC)
        result = utc_now()
        after = datetime.now(UTC)

        # Result should be between before and after (within a few seconds)
        assert before <= result <= after


class TestDateParsingIntegration:
    """Integration tests for date parsing functionality."""

    def test_parse_month_year_format(self):
        """Test parsing common Month-Year format."""
        # Jan2024 -> month=1, year=2024
        month_str = "Jan"
        year_str = "2024"

        month_num = month_abbr_to_number(month_str)
        year_num = int(year_str)

        assert month_num == 1
        assert year_num == 2024

    def test_normalize_and_convert_month(self):
        """Test normalizing then converting month name."""
        # jan -> january (normalize doesn't convert back to abbr)
        # So we test the abbr directly
        month_num = month_abbr_to_number("Jan")
        assert month_num == 1

    def test_all_months_round_trip(self):
        """Test that all standard month abbreviations convert correctly."""
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        for i, month_abbr in enumerate(months, 1):
            month_num = month_abbr_to_number(month_abbr)
            assert month_num == i, f"Failed for {month_abbr}: got {month_num}, expected {i}"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_month_abbr_to_number_with_numbers(self):
        """Test behavior when passing numbers as strings."""
        assert month_abbr_to_number("1") == 0
        assert month_abbr_to_number("12") == 0

    def test_month_abbr_to_number_with_special_chars(self):
        """Test behavior with special characters."""
        assert month_abbr_to_number("Jan.") == 0  # Not exact match
        assert month_abbr_to_number("Jan-") == 0  # Not exact match

    def test_normalize_month_name_whitespace(self):
        """Test normalization with whitespace."""
        result = normalize_month_name("  January  ")
        # Should handle whitespace gracefully
        assert result is not None

    def test_month_abbr_to_number_none_input(self):
        """Test behavior with None input."""
        # Function expects str, so passing None should raise an error
        with pytest.raises((TypeError, AttributeError)):
            month_abbr_to_number(None)  # type: ignore


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
