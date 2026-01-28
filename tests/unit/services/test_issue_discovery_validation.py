"""
Tests for periodical validation in issue discovery service.

Tests the validation logic that prevents downloading non-periodicals (books, collections, etc.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from services.issue_discovery import IssueDiscoveryService


# pylint: disable=too-many-public-methods
class TestPeriodicalValidation:
    """Test validation of periodical vs non-periodical content."""

    @pytest.fixture
    def service(self):
        """Create issue discovery service instance."""
        return IssueDiscoveryService()

    # ===================================================================
    # Test Periodical Patterns (should ACCEPT)
    # ===================================================================

    def test_accepts_full_month_name_format(self, service):
        """Test: 'Wired Magazine January 2024'"""
        result = {"title": "Wired Magazine January 2024"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_abbreviated_month_format(self, service):
        """Test: 'National Geographic Jan 2024'"""
        result = {"title": "National Geographic Jan 2024"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_iso_date_format(self, service):
        """Test: 'The Economist 2024-01-20'"""
        result = {"title": "The Economist 2024-01-20"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_dot_date_format(self, service):
        """Test: 'TIME.2024.01.pdf'"""
        result = {"title": "TIME.2024.01.pdf"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_issue_number_format(self, service):
        """Test: 'PC Gamer Issue 389'"""
        result = {"title": "PC Gamer Issue 389"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_hash_issue_format(self, service):
        """Test: 'Spider-Man #123'"""
        result = {"title": "Spider-Man #123"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_volume_issue_format(self, service):
        """Test: 'Journal of Science Vol 12 No 3'"""
        result = {"title": "Journal of Science Vol 12 No 3"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_volume_shorthand_format(self, service):
        """Test: 'TIME V202 N25 2023'"""
        result = {"title": "TIME V202 N25 2023"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_seasonal_format(self, service):
        """Test: 'Quarterly Review Spring 2024'"""
        result = {"title": "Quarterly Review Spring 2024"}
        assert service._validate_is_periodical(result) is True

    def test_accepts_complex_nzb_format(self, service):
        """Test: 'Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2'"""
        result = {"title": "Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2"}
        assert service._validate_is_periodical(result) is True

    # ===================================================================
    # Test Anti-Periodical Patterns (should REJECT)
    # ===================================================================

    def test_rejects_complete_collection(self, service):
        """Test: 'Amazing Spider-Man Complete Collection'"""
        result = {"title": "Amazing Spider-Man Complete Collection"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_full_series(self, service):
        """Test: 'Batman Full Series 1940-2020' - Updated: no longer rejected (not video content)"""
        result = {"title": "Batman Full Series 1940-2020"}
        # Note: Book/collection patterns removed - only rejecting video/TV/audiobooks
        assert service._validate_is_periodical(result) is True  # Now accepted as potential periodical

    def test_rejects_anthology(self, service):
        """Test: 'Science Fiction Anthology'"""
        result = {"title": "Science Fiction Anthology"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_omnibus(self, service):
        """Test: 'The Walking Dead Omnibus'"""
        result = {"title": "The Walking Dead Omnibus"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_volume_range(self, service):
        """Test: 'National Geographic Volumes 1-5'"""
        result = {"title": "National Geographic Volumes 1-5"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_issue_range(self, service):
        """Test: 'Wired Issues 10-20'"""
        result = {"title": "Wired Issues 10-20"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_year_pack(self, service):
        """Test: 'TIME Magazine Year 2023 Pack'"""
        result = {"title": "TIME Magazine Year 2023 Pack"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_book_format(self, service):
        """Test: 'The Great Gatsby Paperback'"""
        result = {"title": "The Great Gatsby Paperback"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_novel_series(self, service):
        """Test: 'Harry Potter Book 1'"""
        result = {"title": "Harry Potter Book 1"}
        assert service._validate_is_periodical(result) is False

    def test_rejects_trilogy(self, service):
        """Test: 'Lord of the Rings Trilogy'"""
        result = {"title": "Lord of the Rings Trilogy"}
        assert service._validate_is_periodical(result) is False

    # ===================================================================
    # Test Newsnab Category Validation
    # ===================================================================

    def test_rejects_book_category(self, service):
        """Test: Newsnab book category should reject even with date in title"""
        result = {
            "title": "Something January 2024",
            "category": "7000",
        }  # Books category
        assert service._validate_is_periodical(result) is False

    def test_accepts_magazine_category(self, service):
        """Test: Newsnab magazine category should accept"""
        result = {
            "title": "Something January 2024",
            "category": "8010",
        }  # Mags category
        assert service._validate_is_periodical(result) is True

    def test_rejects_magazine_category_with_anti_pattern(self, service):
        """Test: Rejects if magazine category but has video anti-patterns (not book patterns)"""
        result = {"category": "8010", "title": "Movie Title 2024 1080p BluRay"}
        assert service._validate_is_periodical(result) is False

    # ===================================================================
    # Test File Size Validation
    # ===================================================================

    def test_rejects_suspiciously_small_file(self, service):
        """Test: Files under 5MB are likely articles/ebooks, not periodicals"""
        result = {"title": "Wired January 2024", "size": 2 * 1024 * 1024}  # 2MB
        assert service._validate_is_periodical(result) is False

    def test_rejects_suspiciously_large_file(self, service):
        """Test: Files over 1000MB are likely collections/packs"""
        result = {"title": "Wired January 2024", "size": 1500 * 1024 * 1024}  # 1500MB
        assert service._validate_is_periodical(result) is False

    def test_accepts_typical_magazine_size(self, service):
        """Test: 100MB file is typical for magazines"""
        result = {"title": "Wired January 2024", "size": 100 * 1024 * 1024}  # 100MB
        assert service._validate_is_periodical(result) is True

    def test_accepts_unknown_file_size(self, service):
        """Test: Unknown size (0 or missing) should not reject"""
        result = {"title": "Wired January 2024", "size": 0}
        assert service._validate_is_periodical(result) is True

        result_no_size = {"title": "Wired January 2024"}
        assert service._validate_is_periodical(result_no_size) is True

    # ===================================================================
    # Test Pattern Detection Methods
    # ===================================================================

    def test_has_periodical_patterns_with_date(self, service):
        """Test _has_periodical_patterns detects date patterns"""
        assert service._has_periodical_patterns("Magazine January 2024") is True
        assert service._has_periodical_patterns("Magazine 2024-01") is True
        assert service._has_periodical_patterns("Magazine Jan2024") is True

    def test_has_periodical_patterns_with_issue(self, service):
        """Test _has_periodical_patterns detects issue numbers"""
        assert service._has_periodical_patterns("Comic #123") is True
        assert service._has_periodical_patterns("Magazine Issue 45") is True
        assert service._has_periodical_patterns("Journal No. 67") is True

    def test_has_periodical_patterns_returns_false(self, service):
        """Test _has_periodical_patterns returns False for generic titles"""
        assert service._has_periodical_patterns("Random Book Title") is False
        assert service._has_periodical_patterns("Complete Collection") is False

    def test_has_anti_periodical_patterns(self, service):
        """Test _has_anti_periodical_patterns detects video/movie/TV indicators"""
        assert service._has_anti_periodical_patterns("Movie 2024 1080p BluRay") is True
        assert service._has_anti_periodical_patterns("TV Show S01E01 720p") is True
        assert service._has_anti_periodical_patterns("Documentary 2024 4K") is True

    def test_has_anti_periodical_patterns_returns_false(self, service):
        """Test _has_anti_periodical_patterns returns False for normal titles"""
        assert service._has_anti_periodical_patterns("Magazine January 2024") is False
        assert service._has_anti_periodical_patterns("Comic #123") is False

    # ===================================================================
    # Test Edge Cases
    # ===================================================================

    def test_case_insensitive_matching(self, service):
        """Test: Pattern matching is case-insensitive"""
        result = {"title": "WIRED MAGAZINE JANUARY 2024"}
        assert service._validate_is_periodical(result) is True

        result_reject = {"title": "MOVIE 2024 1080P BLURAY"}
        assert service._validate_is_periodical(result_reject) is False

    def test_handles_special_characters(self, service):
        """Test: Handles dots, underscores, dashes in titles"""
        result = {"title": "Wired.Magazine.January.2024.pdf"}
        assert service._validate_is_periodical(result) is True

        result2 = {"title": "National_Geographic-Jan-2024"}
        assert service._validate_is_periodical(result2) is True

    def test_empty_title(self, service):
        """Test: Empty title should fail validation gracefully"""
        result = {"title": ""}
        # Empty title will be caught before validation, but test anyway
        assert service._validate_is_periodical(result) is False

    def test_title_with_only_year(self, service):
        """Test: Title with only year (no month) should be rejected"""
        result = {"title": "Some Publication 2024"}
        # Year alone is not a strong enough indicator
        assert service._validate_is_periodical(result) is False

    # ===================================================================
    # Test Volume/Issue Number vs Date Disambiguation
    # ===================================================================

    def test_volume_number_with_year_not_confused_with_date(self, service):
        """Test: 'Magazine Vol. 01 2024' should be recognized as periodical (volume+year, not month-year)"""
        # The "Vol." keyword makes this clearly a volume number, not month 01
        result = {"title": "Magazine Vol. 01 2024"}
        assert service._validate_is_periodical(result) is True

    def test_issue_number_with_year_not_confused_with_date(self, service):
        """Test: 'Magazine No. 01 2024' should be recognized as periodical (issue+year, not month-year)"""
        # The "No." keyword makes this clearly an issue number, not month 01
        result = {"title": "Magazine No. 01 2024"}
        assert service._validate_is_periodical(result) is True

    def test_volume_number_without_keyword_accepted_as_date(self, service):
        """Test: 'Magazine 01 2024' (without Vol/No) is interpreted as date (January 2024)"""
        # Without keywords, "01 2024" is ambiguous but assumed to be month-year (common format)
        result = {"title": "Magazine 01 2024"}
        assert service._validate_is_periodical(result) is True

    def test_issue_keyword_followed_by_date_format(self, service):
        """Test: 'Magazine Issue 389 January 2024' has both issue number and date"""
        # Contains both issue number pattern and date pattern - should be accepted
        result = {"title": "Magazine Issue 389 January 2024"}
        assert service._validate_is_periodical(result) is True

    def test_numeric_date_with_dash_separator(self, service):
        """Test: 'Magazine 01-2024' recognized as date (dash separator)"""
        # Dash-separated numeric dates are clear month-year indicators
        result = {"title": "Magazine 01-2024"}
        assert service._validate_is_periodical(result) is True

    def test_numeric_date_with_slash_separator(self, service):
        """Test: 'Magazine 01/2024' recognized as date (slash separator)"""
        # Slash-separated numeric dates are clear month-year indicators
        result = {"title": "Magazine 01/2024"}
        assert service._validate_is_periodical(result) is True

    def test_numeric_date_with_space_separator(self, service):
        """Test: 'Magazine 01 2024' recognized as date (space separator)"""
        # Space-separated numeric dates should also be recognized (common in adult magazines)
        result = {"title": "Magazine 01 2024"}
        assert service._validate_is_periodical(result) is True

    def test_volume_and_issue_combined(self, service):
        """Test: 'Journal Vol. 12 No. 3' recognized as periodical"""
        # Combined volume + issue is a very strong periodical indicator
        result = {"title": "Journal Vol. 12 No. 3"}
        assert service._validate_is_periodical(result) is True

    def test_volume_shorthand_with_date(self, service):
        """Test: 'Magazine V12 N3 January 2024' has volume, issue, and date"""
        # Contains multiple periodical patterns - should be strongly accepted
        result = {"title": "Magazine V12 N3 January 2024"}
        assert service._validate_is_periodical(result) is True
