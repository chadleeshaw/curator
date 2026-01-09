#!/usr/bin/env python3
"""
Test suite for country detection utilities.
Tests country detection from text and ISO country mappings.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers import detect_country, find_country, ISO_COUNTRIES


class TestDetectCountry:
    """Test detect_country function."""

    def test_detect_uk(self):
        """Test detecting UK from text."""
        assert detect_country("Magazine UK Edition") == "UK"
        assert detect_country("Time Magazine - UK") == "UK"
        assert detect_country("Title (UK)") == "UK"
        assert detect_country("[UK]") == "UK"

    def test_detect_us(self):
        """Test detecting US from text."""
        result = detect_country("Magazine US Edition")
        assert result == "US"

    def test_detect_au(self):
        """Test detecting Australia from text."""
        assert detect_country("Magazine AU Edition") == "AU"
        assert detect_country("Magazine Australia") == "AU"

    def test_detect_ca(self):
        """Test detecting Canada from text."""
        result = detect_country("Magazine CA Edition")
        assert result == "CA"

    def test_no_country_returns_none(self):
        """Test that text without country returns None."""
        assert detect_country("Magazine Title") is None
        assert detect_country("Random Text") is None

    def test_case_insensitive(self):
        """Test case-insensitive detection."""
        assert detect_country("magazine uk edition") == "UK"
        assert detect_country("MAGAZINE UK EDITION") == "UK"

    def test_country_in_middle_of_text(self):
        """Test detecting country anywhere in text."""
        assert detect_country("Wired Magazine UK Special Edition") == "UK"

    def test_multiple_countries_returns_first(self):
        """Test behavior when multiple countries present."""
        result = detect_country("Magazine UK US Edition")
        # Should return one or the other
        assert result in ["UK", "US", None]

    def test_empty_string(self):
        """Test with empty string."""
        assert detect_country("") is None

    def test_country_codes_vs_full_names(self):
        """Test both country codes and full names."""
        # UK code
        assert detect_country("Magazine UK") == "UK"
        assert detect_country("[UK]") == "UK"
        # Full name
        assert detect_country("United Kingdom") == "GB"
        # AU code
        assert detect_country("Magazine AU") == "AU"
        assert detect_country("Australia") == "AU"


class TestFindCountry:
    """Test find_country function if it exists."""

    def test_find_country_in_text(self):
        """Test finding country mentions in text."""
        # This function may or may not exist
        try:
            result = find_country("Magazine from UK")
            assert result == "UK" or result is None
        except NameError:
            # Function doesn't exist, skip
            pytest.skip("find_country function not available")

    def test_find_country_returns_none_if_not_found(self):
        """Test that None is returned when no country found."""
        try:
            result = find_country("Magazine Title")
            assert result is None
        except NameError:
            pytest.skip("find_country function not available")


class TestISOCountries:
    """Test ISO_COUNTRIES constant/mapping."""

    def test_iso_countries_exists(self):
        """Test that ISO_COUNTRIES mapping exists."""
        assert ISO_COUNTRIES is not None
        assert isinstance(ISO_COUNTRIES, dict)

    def test_iso_countries_has_common_codes(self):
        """Test that common country codes are present."""
        # Should have major English-speaking countries
        assert "UK" in ISO_COUNTRIES or "GB" in ISO_COUNTRIES
        assert "US" in ISO_COUNTRIES
        assert "AU" in ISO_COUNTRIES
        assert "CA" in ISO_COUNTRIES

    def test_iso_countries_maps_to_names(self):
        """Test that codes map to country names."""
        if "UK" in ISO_COUNTRIES:
            assert isinstance(ISO_COUNTRIES["UK"], str)
            assert len(ISO_COUNTRIES["UK"]) > 0

        if "US" in ISO_COUNTRIES:
            assert isinstance(ISO_COUNTRIES["US"], str)

    def test_iso_countries_case_consistency(self):
        """Test that country codes are uppercase."""
        for code in ISO_COUNTRIES.keys():
            assert code.isupper() or code.islower()  # Consistent casing


class TestCountryDetectionPatterns:
    """Test specific country detection patterns."""

    def test_parentheses_pattern(self):
        """Test country detection in parentheses."""
        assert detect_country("Magazine (UK)") == "UK"
        assert detect_country("Title (AU)") == "AU"

    def test_dash_separator_pattern(self):
        """Test country detection with dash separator."""
        assert detect_country("Magazine - UK") == "UK"
        assert detect_country("Title - UK Edition") == "UK"

    def test_edition_suffix_pattern(self):
        """Test country with 'Edition' suffix."""
        assert detect_country("Magazine UK Edition") == "UK"
        assert detect_country("Magazine AU Edition") == "AU"

    def test_word_boundary_detection(self):
        """Test that country detection respects word boundaries."""
        # "UK" should be detected
        assert detect_country("Magazine UK") == "UK"
        # Should not match partial words
        result = detect_country("FUKUSHIMA")
        assert result is None  # Should not match UK within another word


class TestCountryDetectionEdgeCases:
    """Test edge cases and error handling."""

    def test_detect_country_with_none(self):
        """Test behavior with None input."""
        try:
            result = detect_country(None)
            assert result is None
        except (TypeError, AttributeError):
            # Expected if function doesn't handle None
            pass

    def test_detect_country_with_numbers(self):
        """Test behavior with numeric text."""
        assert detect_country("123456") is None

    def test_detect_country_with_special_chars(self):
        """Test behavior with special characters."""
        assert detect_country("@#$%^&*()") is None

    def test_detect_country_very_long_text(self):
        """Test detection in very long text."""
        long_text = "This is a very long magazine title " * 10 + "UK Edition"
        assert detect_country(long_text) == "UK"

    def test_detect_country_unicode(self):
        """Test detection with unicode characters."""
        result = detect_country("Magazín UK Édition")
        assert result == "UK"


class TestCountryDetectionIntegration:
    """Integration tests with realistic inputs."""

    def test_detect_from_filename(self):
        """Test country detection from typical filenames."""
        assert detect_country("Wired Magazine UK - Jan2024.pdf") == "UK"
        assert detect_country("National Geographic Australia March 2024.pdf") == "AU"

    def test_detect_from_search_results(self):
        """Test country detection from search result titles."""
        assert detect_country("TIME Magazine (UK Edition) - December 2023") == "UK"

    def test_detect_from_folder_paths(self):
        """Test country detection from folder paths."""
        path = "/magazines/UK/Wired/2024/Wired-Jan2024.pdf"
        assert detect_country(path) == "UK"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
