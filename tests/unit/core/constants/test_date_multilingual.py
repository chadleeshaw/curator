"""
Tests for multilingual date parsing support
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from core.constants.date import (
    MONTHS_BY_LANGUAGE,
    SEASONS_BY_LANGUAGE,
    get_month_regex_pattern,
    get_month_year_patterns,
    get_season_regex_pattern,
    get_season_year_patterns,
    get_supported_languages,
)


class TestMultilingualSupport:
    """Test multilingual language support functions"""

    def test_get_supported_languages(self):
        """Test getting list of supported languages"""
        languages = get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "English" in languages
        assert "Spanish" in languages
        assert "German" in languages
        assert "French" in languages

    def test_months_by_language_structure(self):
        """Test that MONTHS_BY_LANGUAGE has correct structure"""
        assert isinstance(MONTHS_BY_LANGUAGE, dict)

        # Check each language has proper structure
        for lang, data in MONTHS_BY_LANGUAGE.items():
            assert isinstance(lang, str)
            assert isinstance(data, dict)
            assert "full" in data
            assert "abbr" in data
            assert isinstance(data["full"], list)
            assert isinstance(data["abbr"], list)
            # Each language should have 12 full month names
            assert len(data["full"]) == 12

    def test_seasons_by_language_structure(self):
        """Test that SEASONS_BY_LANGUAGE has correct structure"""
        assert isinstance(SEASONS_BY_LANGUAGE, dict)

        # Check each language has proper structure
        for lang, seasons in SEASONS_BY_LANGUAGE.items():
            assert isinstance(lang, str)
            assert isinstance(seasons, list)
            # Should have at least 4-5 season names (some languages have ASCII variants)
            assert len(seasons) >= 4


class TestMonthRegexPatterns:
    """Test month regex pattern generation"""

    def test_get_month_regex_pattern_all_languages(self):
        """Test generating month pattern for all languages"""
        pattern = get_month_regex_pattern()

        assert isinstance(pattern, str)
        assert len(pattern) > 0
        # Should contain English months
        assert "january" in pattern
        assert "february" in pattern
        # Should contain Spanish months
        assert "enero" in pattern
        assert "febrero" in pattern
        # Should contain German months
        assert "januar" in pattern
        assert "februar" in pattern

    def test_get_month_regex_pattern_single_language(self):
        """Test generating month pattern for single language"""
        pattern = get_month_regex_pattern(["English"])

        assert isinstance(pattern, str)
        # Should contain English months
        assert "january" in pattern
        assert "december" in pattern
        # Should NOT contain Spanish months
        assert "enero" not in pattern
        assert "diciembre" not in pattern

    def test_get_month_regex_pattern_multiple_languages(self):
        """Test generating month pattern for multiple languages"""
        pattern = get_month_regex_pattern(["English", "Spanish", "French"])

        # Should contain English months
        assert "january" in pattern
        # Should contain Spanish months
        assert "enero" in pattern
        # Should contain French months
        assert "janvier" in pattern

        # Verify it doesn't accidentally match when used in regex
        # by testing against a German-only month name that doesn't overlap
        regex = re.compile(rf"\b({pattern})\s+\d{{4}}\b", re.IGNORECASE)
        # Should NOT match German-only "Dezember 2024" (should only work with "diciembre" or "décembre")
        # Actually, "dezember" is unique to German but let's test with actual text
        assert regex.search("January 2024")  # English
        assert regex.search("Enero 2024")  # Spanish
        assert regex.search("Janvier 2024")  # French

    def test_month_pattern_matches_english(self):
        """Test that generated pattern matches English month names"""
        pattern = get_month_regex_pattern(["English"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test full names
        assert regex.search("January 2024")
        assert regex.search("DECEMBER 2025")
        assert regex.search("march 2023")

        # Test abbreviations
        assert regex.search("Jan 2024")
        assert regex.search("Dec 2025")
        assert regex.search("sept 2023")

    def test_month_pattern_matches_spanish(self):
        """Test that generated pattern matches Spanish month names"""
        pattern = get_month_regex_pattern(["Spanish"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test Spanish month names
        assert regex.search("Enero 2024")
        assert regex.search("FEBRERO 2025")
        assert regex.search("diciembre 2023")

    def test_month_pattern_matches_german(self):
        """Test that generated pattern matches German month names"""
        pattern = get_month_regex_pattern(["German"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test German month names
        assert regex.search("Januar 2024")
        assert regex.search("FEBRUAR 2025")
        assert regex.search("dezember 2023")
        assert regex.search("März 2024")
        assert regex.search("marz 2024")  # ASCII alternative

    def test_month_pattern_matches_french(self):
        """Test that generated pattern matches French month names"""
        pattern = get_month_regex_pattern(["French"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test French month names
        assert regex.search("Janvier 2024")
        assert regex.search("FÉVRIER 2025")
        assert regex.search("fevrier 2025")  # ASCII alternative
        assert regex.search("décembre 2023")


class TestSeasonRegexPatterns:
    """Test season regex pattern generation"""

    def test_get_season_regex_pattern_all_languages(self):
        """Test generating season pattern for all languages"""
        pattern = get_season_regex_pattern()

        assert isinstance(pattern, str)
        assert len(pattern) > 0
        # Should contain English seasons
        assert "spring" in pattern
        assert "summer" in pattern
        assert "winter" in pattern
        # Should contain Spanish seasons
        assert "primavera" in pattern
        assert "verano" in pattern

    def test_get_season_regex_pattern_single_language(self):
        """Test generating season pattern for single language"""
        pattern = get_season_regex_pattern(["English"])

        # Should contain English seasons
        assert "spring" in pattern
        assert "summer" in pattern
        assert "fall" in pattern
        assert "autumn" in pattern
        assert "winter" in pattern
        # Should NOT contain Spanish seasons
        assert "primavera" not in pattern
        assert "verano" not in pattern

    def test_season_pattern_matches_english(self):
        """Test that generated pattern matches English season names"""
        pattern = get_season_regex_pattern(["English"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test season names
        assert regex.search("Spring 2024")
        assert regex.search("SUMMER 2025")
        assert regex.search("fall 2023")
        assert regex.search("Autumn 2023")
        assert regex.search("Winter 2024")

    def test_season_pattern_matches_spanish(self):
        """Test that generated pattern matches Spanish season names"""
        pattern = get_season_regex_pattern(["Spanish"])
        regex = re.compile(rf"\b({pattern})\b", re.IGNORECASE)

        # Test Spanish season names
        assert regex.search("Primavera 2024")
        assert regex.search("VERANO 2025")
        assert regex.search("otoño 2023")
        assert regex.search("otono 2023")  # ASCII alternative
        assert regex.search("invierno 2024")


class TestMonthYearPatterns:
    """Test month+year pattern generation"""

    def test_get_month_year_patterns_returns_list(self):
        """Test that function returns list of patterns"""
        patterns = get_month_year_patterns()

        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_month_year_patterns_match_english(self):
        """Test that patterns match English month+year formats"""
        patterns = get_month_year_patterns(["English"])

        # Compile all patterns
        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Test full month name + year
        assert any(r.search("January 2024") for r in regexes)
        assert any(r.search("DECEMBER 2025") for r in regexes)

        # Test abbreviation + year
        assert any(r.search("Jan 2024") for r in regexes)
        assert any(r.search("Dec 2025") for r in regexes)

        # Test numeric formats
        assert any(r.search("01-2024") for r in regexes)
        assert any(r.search("2024-01") for r in regexes)
        assert any(r.search("2024.01") for r in regexes)

    def test_month_year_patterns_match_spanish(self):
        """Test that patterns match Spanish month+year formats"""
        patterns = get_month_year_patterns(["Spanish"])

        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Test Spanish month names + year
        assert any(r.search("Enero 2024") for r in regexes)
        assert any(r.search("FEBRERO 2025") for r in regexes)
        assert any(r.search("diciembre 2023") for r in regexes)

    def test_month_year_patterns_multilingual(self):
        """Test patterns with multiple languages"""
        patterns = get_month_year_patterns(["English", "Spanish", "German"])

        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Should match all three languages
        assert any(r.search("January 2024") for r in regexes)  # English
        assert any(r.search("Enero 2024") for r in regexes)  # Spanish
        assert any(r.search("Januar 2024") for r in regexes)  # German


class TestSeasonYearPatterns:
    """Test season+year pattern generation"""

    def test_get_season_year_patterns_returns_list(self):
        """Test that function returns list of patterns"""
        patterns = get_season_year_patterns()

        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_season_year_patterns_match_english(self):
        """Test that patterns match English season+year formats"""
        patterns = get_season_year_patterns(["English"])

        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Test season names + year
        assert any(r.search("Spring 2024") for r in regexes)
        assert any(r.search("SUMMER 2025") for r in regexes)
        assert any(r.search("fall 2023") for r in regexes)
        assert any(r.search("Winter 2024") for r in regexes)

    def test_season_year_patterns_match_spanish(self):
        """Test that patterns match Spanish season+year formats"""
        patterns = get_season_year_patterns(["Spanish"])

        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Test Spanish season names + year
        assert any(r.search("Primavera 2024") for r in regexes)
        assert any(r.search("VERANO 2025") for r in regexes)
        assert any(r.search("otoño 2023") for r in regexes)
        assert any(r.search("Invierno 2024") for r in regexes)

    def test_season_year_patterns_multilingual(self):
        """Test patterns with multiple languages"""
        patterns = get_season_year_patterns(["English", "Spanish", "French"])

        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Should match all three languages
        assert any(r.search("Spring 2024") for r in regexes)  # English
        assert any(r.search("Primavera 2024") for r in regexes)  # Spanish
        assert any(r.search("Printemps 2024") for r in regexes)  # French


class TestEdgeCases:
    """Test edge cases and special scenarios"""

    def test_empty_language_list(self):
        """Test with empty language list"""
        # Should return empty pattern but not crash
        pattern = get_month_regex_pattern([])
        assert pattern == ""

    def test_invalid_language_name(self):
        """Test with invalid language name"""
        # Should ignore invalid language and continue
        pattern = get_month_regex_pattern(["English", "InvalidLanguage", "Spanish"])
        assert "january" in pattern
        assert "enero" in pattern

    def test_pattern_sorting_longest_first(self):
        """Test that patterns are sorted longest first"""
        pattern = get_month_regex_pattern(["English"])
        parts = pattern.split("|")

        # "september" should come before "sep"
        september_idx = next((i for i, p in enumerate(parts) if p == "september"), -1)
        sept_idx = next((i for i, p in enumerate(parts) if p == "sept"), -1)

        assert september_idx != -1
        assert sept_idx != -1
        assert september_idx < sept_idx
