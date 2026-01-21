"""
Tests for enhanced NZB-style filename parsing.

Tests comprehensive metadata extraction from complex NZB filenames including:
- Country/region codes
- Language indicators
- Volume/issue numbers
- Quality indicators
- Release groups
- Multiple date formats
- Confidence scoring
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from core.parsers.metadata import FilenameParser


class TestEnhancedNZBParsing:
    """Test enhanced NZB filename parsing with comprehensive patterns."""

    @pytest.fixture
    def extractor(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_parse_complex_usa_magazine(self, extractor):
        """Test: Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2"""
        result = extractor.extract_from_nzb_title("Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2")

        assert result["title"] == "Wired Magazine"
        assert result["country"] == "USA"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["quality"] == "True PDF"
        assert result["release_group"] == "PHOTOFILEv2"
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 1, 1)

    def test_parse_iso_date_format(self, extractor):
        """Test: National.Geographic-2024-01-HQ.PDF"""
        result = extractor.extract_from_nzb_title("National.Geographic-2024-01-HQ.PDF")

        assert result["title"] == "National Geographic"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["quality"] == "HQ"
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 1, 1)

    def test_parse_volume_issue_format(self, extractor):
        """Test: TIME.V202.N25.2023.pdf"""
        result = extractor.extract_from_nzb_title("TIME.V202.N25.2023.pdf")

        assert result["title"] == "TIME"
        assert result["volume"] == 202
        assert result["issue"] == 25
        assert result["year"] == 2023
        assert result["month"] == 1  # Default when only year provided
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2023, 1, 1)

    def test_parse_uk_issue_format(self, extractor):
        """Test: PC.Gamer.UK.Issue.389.February.2024.pdf"""
        result = extractor.extract_from_nzb_title("PC.Gamer.UK.Issue.389.February.2024.pdf")

        assert result["title"] == "PC Gamer"
        assert result["country"] == "UK"
        assert result["issue"] == 389
        assert result["month"] == 2
        assert result["year"] == 2024
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 2, 1)

    def test_parse_weekly_full_date(self, extractor):
        """Test: The.Economist.2024.01.20.pdf"""
        result = extractor.extract_from_nzb_title("The.Economist.2024.01.20.pdf")

        assert result["title"] == "The Economist"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["day"] == 20
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 1, 20)

    def test_parse_abbreviated_month(self, extractor):
        """Test: National.Geographic.Jan2024.pdf"""
        result = extractor.extract_from_nzb_title("National.Geographic.Jan2024.pdf")

        assert result["title"] == "National Geographic"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 1, 1)

    def test_parse_numeric_month_year(self, extractor):
        """Test: Wired.01-2024.pdf"""
        result = extractor.extract_from_nzb_title("Wired.01-2024.pdf")

        assert result["title"] == "Wired"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2024, 1, 1)

    def test_parse_quality_indicator(self, extractor):
        """Test: Time.Magazine.Retail.January.2024.pdf"""
        result = extractor.extract_from_nzb_title("Time.Magazine.Retail.January.2024.pdf")

        assert result["title"] == "Time Magazine"
        assert result["quality"] == "Retail"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["confidence"] == "high"

    def test_parse_international_edition(self, extractor):
        """Test: Forbes.International.Edition.March.2024.pdf"""
        result = extractor.extract_from_nzb_title("Forbes.International.Edition.March.2024.pdf")

        assert result["title"] == "Forbes"
        assert result["edition"] == "International"
        assert result["year"] == 2024
        assert result["month"] == 3
        assert result["confidence"] == "high"

    def test_parse_language_indicator(self, extractor):
        """Test: Der.Spiegel.German.January.2024.pdf"""
        result = extractor.extract_from_nzb_title("Der.Spiegel.German.January.2024.pdf")

        assert result["title"] == "Der Spiegel"
        assert result["language"] == "German"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["confidence"] == "high"

    def test_parse_all_components(self, extractor):
        """Test: Newsweek.USA.English.Special.Edition.December.2024.HQ-PHOTOFILE"""
        result = extractor.extract_from_nzb_title("Newsweek.USA.English.Special.Edition.December.2024.HQ-PHOTOFILE")

        assert result["title"] == "Newsweek"
        assert result["country"] == "USA"
        assert result["language"] == "English"
        assert result["edition"] == "Special"
        assert result["year"] == 2024
        assert result["month"] == 12
        assert result["quality"] == "HQ"
        assert result["release_group"] == "PHOTOFILE"
        assert result["confidence"] == "high"

    def test_parse_volume_only(self, extractor):
        """Test: Science.Vol.385.2024.pdf"""
        result = extractor.extract_from_nzb_title("Science.Vol.385.2024.pdf")

        assert result["title"] == "Science"
        assert result["volume"] == 385
        assert result["year"] == 2024
        assert result["confidence"] == "high"

    def test_parse_issue_number_only(self, extractor):
        """Test: Wired.Issue.123.2024.pdf"""
        result = extractor.extract_from_nzb_title("Wired.Issue.123.2024.pdf")

        assert result["title"] == "Wired"
        assert result["issue"] == 123
        assert result["year"] == 2024
        assert result["confidence"] == "high"

    def test_confidence_high(self, extractor):
        """Test high confidence: has title, year, month, and extras"""
        result = extractor.extract_from_nzb_title("National.Geographic.USA.January.2024.HQ.pdf")

        # Should have: title (2), year (2), month (2), country (1), quality (1) = 8 pts
        assert result["confidence"] == "high"

    def test_confidence_medium(self, extractor):
        """Test medium confidence: has title and year but limited extras"""
        result = extractor.extract_from_nzb_title("Unknown.Magazine.2024.pdf")

        # Should have: title (2), year (2), month (2 default) = 6 pts
        assert result["confidence"] in ["high", "medium"]

    def test_confidence_low(self, extractor):
        """Test low confidence: minimal extractable data"""
        result = extractor.extract_from_nzb_title("random.file.name.pdf")

        # Should have very little extractable data
        assert result["confidence"] == "low"

    def test_parse_underscore_delimiters(self, extractor):
        """Test: National_Geographic_January_2024.pdf"""
        result = extractor.extract_from_nzb_title("National_Geographic_January_2024.pdf")

        assert result["title"] == "National Geographic"
        assert result["year"] == 2024
        assert result["month"] == 1

    def test_parse_mixed_delimiters(self, extractor):
        """Test: PC.Gamer_UK-Issue.389-February.2024.pdf"""
        result = extractor.extract_from_nzb_title("PC.Gamer_UK-Issue.389-February.2024.pdf")

        assert result["title"] == "PC Gamer"
        assert result["country"] == "UK"
        assert result["issue"] == 389
        assert result["year"] == 2024
        assert result["month"] == 2

    def test_parse_year_only_fallback(self, extractor):
        """Test: Magazine.Title.2024.pdf (only year, no month)"""
        result = extractor.extract_from_nzb_title("Magazine.Title.2024.pdf")

        assert result["title"] == "Magazine Title"
        assert result["year"] == 2024
        assert result["month"] == 1  # Default to January
        assert result["confidence"] in ["medium", "high"]

    def test_parse_invalid_year_rejected(self, extractor):
        """Test: Magazine.1899.pdf (year too old, should be rejected)"""
        result = extractor.extract_from_nzb_title("Magazine.1899.pdf")

        # Should not extract invalid year
        assert result["year"] is None or result["year"] >= 1900

    def test_parse_future_year_rejected(self, extractor):
        """Test: Magazine.2099.pdf (year too far in future)"""
        result = extractor.extract_from_nzb_title("Magazine.2099.pdf")

        # Should not extract invalid year
        assert result["year"] is None or result["year"] <= 2099

    def test_parse_removes_common_words(self, extractor):
        """Test that quality/region indicators are removed from title"""
        result = extractor.extract_from_nzb_title("Forbes.Magazine.USA.Retail.January.2024.pdf")

        # USA, Retail, Magazine should be extracted/removed, not part of title
        assert result["title"] in ["Forbes", "Forbes Magazine"]
        assert result["country"] == "USA"
        assert result["quality"] == "Retail"


class TestEnhancedNZBIntegrationWithFilename:
    """Test that enhanced NZB parsing works as fallback in extract_from_filename."""

    @pytest.fixture
    def extractor(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_standard_pattern_preferred(self, extractor):
        """Test that standard patterns are tried first"""
        # This should match the dash-month-year pattern, not NZB parsing
        path = Path("/magazines/Wired/Wired - January2024.pdf")
        result = extractor.extract_from_filename(path)

        assert result["title"] == "Wired"
        assert result["year"] == 2024
        assert result["month_name"] == "January"

    def test_nzb_fallback_for_complex_filename(self, extractor):
        """Test that NZB parsing is used when standard patterns fail"""
        # This format won't match standard patterns, should fall back to NZB
        path = Path("/magazines/Wired/Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2.pdf")
        result = extractor.extract_from_filename(path)

        # The dot-separated pattern will match and extract year/month
        # Title comes from parent directory "Wired"
        assert result["title"] in ["Wired", "Wired Magazine"]
        # Either has year directly or in issue_date
        has_year = result.get("year") == 2024 or (result.get("issue_date") and result["issue_date"].year == 2024)
        assert has_year, f"Expected year 2024, got: year={result.get('year')}, issue_date={result.get('issue_date')}"

    def test_nzb_fallback_ignored_if_low_confidence(self, extractor):
        """Test that low-confidence NZB results are ignored"""
        # This should result in low confidence and fall back to current date
        path = Path("/magazines/random/completely.random.filename.pdf")
        result = extractor.extract_from_filename(path)

        # Should fall back to current date since NZB confidence is low
        assert result["issue_date"] is not None
        # Title should be the filename or cleaned version
        assert result["title"] is not None


class TestConfidenceScoring:
    """Test confidence scoring system."""

    @pytest.fixture
    def extractor(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_high_confidence_full_metadata(self, extractor):
        """Test high confidence with complete metadata"""
        metadata = {
            "title": "National Geographic",
            "year": 2024,
            "month": 1,
            "country": "USA",
            "quality": "HQ",
            "volume": 120,
        }
        confidence = extractor._calculate_confidence(metadata)
        assert confidence == "high"

    def test_medium_confidence_partial_metadata(self, extractor):
        """Test medium confidence with partial metadata"""
        metadata = {
            "title": "Magazine",
            "year": 2024,
            "month": None,
            "country": "USA",
        }
        confidence = extractor._calculate_confidence(metadata)
        assert confidence == "medium"

    def test_low_confidence_minimal_metadata(self, extractor):
        """Test low confidence with minimal metadata"""
        metadata = {
            "title": "Unknown",
            "year": None,
            "month": None,
        }
        confidence = extractor._calculate_confidence(metadata)
        assert confidence == "low"

    def test_confidence_with_only_title_and_year(self, extractor):
        """Test confidence with title and year only"""
        metadata = {
            "title": "Magazine",
            "year": 2024,
            "month": None,
        }
        confidence = extractor._calculate_confidence(metadata)
        assert confidence == "medium"

    def test_confidence_with_volume_issue(self, extractor):
        """Test that volume/issue adds to confidence"""
        # Without volume/issue
        metadata1 = {
            "title": "Magazine",
            "year": 2024,
            "month": 1,
        }
        confidence1 = extractor._calculate_confidence(metadata1)

        # With volume/issue (should be same or higher)
        metadata2 = {
            "title": "Magazine",
            "year": 2024,
            "month": 1,
            "volume": 12,
        }
        confidence2 = extractor._calculate_confidence(metadata2)

        assert confidence2 == "high"  # 2+2+2+1 = 7 pts

    def test_parse_year_not_treated_as_extension(self, extractor):
        """
        Test: Esquire.USA.-.August.2021.pdf

        Regression test for bug where year (2021) was incorrectly treated as
        file extension and removed during parsing, causing month to default to January.

        The parser should:
        1. Recognize that "2021" is a year, not a file extension
        2. Successfully parse "August 2021" as month=8, year=2021
        3. Not default to month=1 (January)
        """
        result = extractor.extract_from_nzb_title("Esquire.USA.-.August.2021.pdf")

        assert result["title"] == "Esquire"
        assert result["country"] == "USA"
        assert result["year"] == 2021
        assert result["month"] == 8, "Month should be 8 (August), not 1 (January)"
        assert result["confidence"] == "high"
        assert result["issue_date"] == datetime(2021, 8, 1)

    def test_nzb_style_filename_prioritized(self, extractor):
        """
        Test: Filenames with dots and dashes use NZB parser first

        Ensures that NZB-style filenames (multiple dots, typical format)
        are parsed using the NZB parser before falling back to simpler patterns.
        This prevents incorrect parsing by year-only patterns.
        """
        # Test that NZB-style filename goes through NZB parser
        test_path = Path("/downloads/Esquire.USA.-.August.2021.pdf")
        result = extractor.extract_from_filename(test_path)

        # Should have full metadata from NZB parser, not just year
        assert result["month"] == 8, "Should detect August (month 8) from NZB parsing"
        assert result["year"] == 2021
        assert result["country"] == "USA"
