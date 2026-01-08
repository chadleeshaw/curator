"""
Tests for special edition detection and grouping
"""

import pytest

from core.utils import is_special_edition


class TestSpecialEditionDetection:
    """Test special edition keyword detection"""

    def test_detects_special_keyword(self):
        """Test detection of 'special' keyword"""
        assert is_special_edition("Wired - Holiday Special 2024")
        assert is_special_edition("PC Gamer Special Edition")

    def test_detects_annual_keyword(self):
        """Test detection of 'annual' keyword"""
        assert is_special_edition("National Geographic Annual Edition")
        assert is_special_edition("Time Annual 2024")

    def test_detects_collector_keywords(self):
        """Test detection of collector edition keywords"""
        assert is_special_edition("Marvel Collector's Edition")
        assert is_special_edition("Star Wars Collectors Edition")

    def test_detects_holiday_keywords(self):
        """Test detection of holiday keywords"""
        assert is_special_edition("Vogue Christmas Special")
        assert is_special_edition("GQ Holiday Edition 2024")

    def test_detects_season_specials(self):
        """Test detection of seasonal specials"""
        assert is_special_edition("Outdoor Summer Special")
        assert is_special_edition("Winter Special Issue")
        assert is_special_edition("Spring Special 2024")
        assert is_special_edition("Fall Special Edition")

    def test_detects_commemorative_keywords(self):
        """Test detection of commemorative editions"""
        assert is_special_edition("Time Commemorative Edition")
        assert is_special_edition("50th Anniversary Special")

    def test_detects_best_of_keyword(self):
        """Test detection of 'best of' editions"""
        assert is_special_edition("Wired Best of 2024")

    def test_regular_issue_not_special(self):
        """Test that regular issues are not detected as special editions"""
        assert not is_special_edition("Wired - June 2024")
        assert not is_special_edition("PC Gamer - 2024-01")
        assert not is_special_edition("National Geographic January 2024")

    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive"""
        assert is_special_edition("WIRED SPECIAL EDITION")
        assert is_special_edition("Annual Edition")
        assert is_special_edition("collector's EDITION")

    def test_empty_string_not_special(self):
        """Test that empty string returns False"""
        assert not is_special_edition("")
        assert not is_special_edition(None)

    def test_yearbook_keyword(self):
        """Test detection of yearbook keyword"""
        assert is_special_edition("School Magazine Yearbook 2024")
