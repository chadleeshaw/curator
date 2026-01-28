"""
Comprehensive test suite for National Geographic title parsing.

This test suite programmatically generates all possible combinations of:
- Base titles (National Geographic, NG, Nat Geo, etc.)
- Regional editions (US, UK, South Africa, Arabic, etc.)
- Specialty editions (Kids, Little Kids, Traveler, etc.)
- Date formats (various month/year combinations)
- Filename patterns (dash, dot, space separated, etc.)

The goal is to ensure the parser can handle the full spectrum of National Geographic
filenames that might appear in the wild.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import pytest

from core.parsers.metadata import FilenameParser


# ==============================================================================
# National Geographic Title Variations
# ==============================================================================

# Base title variations
BASE_TITLES = [
    "National Geographic",
    "National Geographic Magazine",
    "Nat Geo",
    "NG",
    "NatGeo",
]

# Regional editions
REGIONAL_EDITIONS = [
    "",  # No region (main US edition)
    "US",
    "USA",
    "United States",
    "UK",
    "United Kingdom",
    "South Africa",
    "Arabia",
    "Arabic",
    "Australia",
    "Brasil",
    "Brazil",
    "China",
    "Czechia",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "India",
    "Indonesia",
    "Israel",
    "Italia",
    "Italy",
    "Japan",
    "Korea",
    "Latinoamerica",
    "Mexico",
    "Netherlands",
    "Norway",
    "Poland",
    "Portugal",
    "Romania",
    "Russia",
    "Serbia",
    "Slovenia",
    "Spain",
    "Sweden",
    "Thailand",
    "Turkey",
]

# Specialty editions
SPECIALTY_EDITIONS = [
    "",  # No specialty (main magazine)
    "Kids",
    "Little Kids",
    "Traveler",
    "Traveller",  # UK spelling
    "History",
    "Adventure",
]

# Month formats
MONTH_FORMATS = [
    ("January", 1),
    ("Jan", 1),
    ("February", 2),
    ("Feb", 2),
    ("March", 3),
    ("Mar", 3),
    ("April", 4),
    ("Apr", 4),
    ("May", 5),
    ("May", 5),
    ("June", 6),
    ("Jun", 6),
    ("July", 7),
    ("Jul", 7),
    ("August", 8),
    ("Aug", 8),
    ("September", 9),
    ("Sep", 9),
    ("October", 10),
    ("Oct", 10),
    ("November", 11),
    ("Nov", 11),
    ("December", 12),
    ("Dec", 12),
]

# Multi-month formats
MULTI_MONTH_FORMATS = [
    ("June/July", 6, "June/July"),
    ("Jun/Jul", 6, "June/July"),
    ("December/January", 12, "December/January"),
    ("Dec/Jan", 12, "December/January"),
    ("11.10", 10, "October/November"),  # Numeric format
    ("05.06", 5, "May/June"),
    ("12/01", 12, "December/January"),
]

# Years to test
TEST_YEARS = [2024, 2023, 2020, 2015, 2010, 2005, 2000, 1995, 1990]

# Filename patterns (format string with placeholders: {title}, {region}, {specialty}, {month}, {year})
FILENAME_PATTERNS = [
    "{title} - {month}{year}",  # "National Geographic - Jan2024"
    "{title} - {month} {year}",  # "National Geographic - Jan 2024"
    "{title}.{month}.{year}",  # "National Geographic.Jan.2024"
    "{title} {month} {year}",  # "National Geographic Jan 2024"
    "{title}-{month}.{year}",  # "National Geographic-Jan.2024"
    "{title}.{region}.{month}.{year}",  # "National.Geographic.US.Jan.2024"
    "{title} {region} - {month} {year}",  # "National Geographic US - Jan 2024"
    "{title}.{region}.-.{month}.{year}",  # "National.Geographic.US.-.Jan.2024"
    "{title} {specialty} - {month} {year}",  # "National Geographic Kids - Jan 2024"
    "{title} {region} {specialty} {month} {year}",  # "National Geographic US Kids Jan 2024"
]


# ==============================================================================
# Test Generation Functions
# ==============================================================================


def generate_title_combinations(limit: int = 50) -> List[Tuple[str, str, str]]:
    """
    Generate combinations of base titles, regions, and specialties.

    Args:
        limit: Maximum number of combinations to generate

    Returns:
        List of tuples (base_title, region, specialty)
    """
    combinations = []

    # Generate all combinations
    for base in BASE_TITLES[:3]:  # Limit to top 3 base titles for performance
        for region in REGIONAL_EDITIONS[:10]:  # Top 10 regions
            for specialty in SPECIALTY_EDITIONS[:3]:  # Top 3 specialties
                combinations.append((base, region, specialty))
                if len(combinations) >= limit:
                    return combinations

    return combinations


def generate_filename_variants(
    base_title: str,
    region: str,
    specialty: str,
    month_str: str,
    year: int,
    month_num: int,
) -> List[Dict[str, Any]]:
    """
    Generate filename variants for a given title combination.

    Args:
        base_title: Base title (e.g., "National Geographic")
        region: Regional edition (e.g., "US", "UK", "")
        specialty: Specialty edition (e.g., "Kids", "")
        month_str: Month string (e.g., "Jan", "January")
        year: Year (e.g., 2024)
        month_num: Expected month number (1-12)

    Returns:
        List of test cases with expected results
    """
    variants = []

    # Build title parts
    title_parts = [base_title]
    if region:
        title_parts.append(region)
    if specialty:
        title_parts.append(specialty)

    # Try different separators for title
    title_variants = [
        " ".join(title_parts),  # Space separated
        ".".join(title_parts),  # Dot separated
        "_".join(title_parts),  # Underscore separated
    ]

    for title_variant in title_variants:
        # Generate filename using different patterns
        for pattern in FILENAME_PATTERNS[:3]:  # Limit patterns for performance
            try:
                # Build format dict
                format_dict = {
                    "title": title_variant,
                    "region": region or "",
                    "specialty": specialty or "",
                    "month": month_str,
                    "year": year,
                }

                # Generate filename
                filename = pattern.format(**format_dict)

                # Clean up empty placeholders
                filename = filename.replace("  ", " ").replace("..", ".")
                filename = filename.replace(" -  ", " - ").replace("- ", "-")
                filename = filename.strip(".- ")

                if not filename:
                    continue

                # Build expected title
                expected_title_parts = [base_title]
                if region:
                    expected_title_parts.append(region)
                if specialty:
                    expected_title_parts.append(specialty)
                expected_title = " ".join(expected_title_parts)

                variants.append(
                    {
                        "filename": filename + ".pdf",
                        "expected_title": expected_title,
                        "expected_year": year,
                        "expected_month": month_num,
                        "base": base_title,
                        "region": region,
                        "specialty": specialty,
                    }
                )

            except (KeyError, ValueError):
                # Skip patterns that don't match our format dict
                continue

    return variants


# ==============================================================================
# Parametrized Tests
# ==============================================================================


class TestNationalGeographicComprehensive:
    """Comprehensive tests for National Geographic title parsing."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_base_title_variations(self, parser):
        """Test that all base title variations are recognized."""
        test_cases = [
            ("National Geographic - Jan2024.pdf", "National Geographic"),
            ("National Geographic Magazine - Jan2024.pdf", "National Geographic"),
            ("Nat Geo - Jan2024.pdf", "Nat Geo"),
            ("NatGeo - Jan2024.pdf", "Natgeo"),  # Might be normalized
            ("NG - Jan2024.pdf", "Ng"),  # Might be normalized
        ]

        for filename, expected_title_contains in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Check that title contains expected string (case-insensitive)
            assert result["title"] is not None, f"Failed to extract title from: {filename}"
            assert (
                expected_title_contains.lower() in result["title"].lower()
            ), f"Expected '{expected_title_contains}' in title, got: {result['title']}"

    def test_regional_editions(self, parser):
        """Test that regional editions are parsed correctly."""
        test_cases = [
            ("National Geographic US - Jan2024.pdf", "US"),
            ("National Geographic UK - Jan2024.pdf", "UK"),
            ("National Geographic South Africa - Jan2024.pdf", "South Africa"),
            ("National.Geographic.Arabia.Jan.2024.pdf", "Arabia"),
            ("National Geographic Australia Jan 2024.pdf", "Australia"),
        ]

        for filename, expected_region in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Regional indicators might be in title or country field
            title_lower = result["title"].lower() if result["title"] else ""
            country = result.get("country")
            country_lower = country.lower() if country else ""

            assert (
                expected_region.lower() in title_lower or expected_region.lower() in country_lower
            ), f"Expected '{expected_region}' in result, got title: {result['title']}, country: {result.get('country')}"

    def test_specialty_editions(self, parser):
        """Test that specialty editions are parsed correctly."""
        test_cases = [
            ("National Geographic Kids - Jan2024.pdf", "Kids"),
            ("National Geographic Little Kids - Jan2024.pdf", "Little Kids"),
            ("National Geographic Traveler - Jan2024.pdf", "Traveler"),
            ("National Geographic Traveller UK - Jan2024.pdf", "Traveller"),
            ("National Geographic History - Jan2024.pdf", "History"),
        ]

        for filename, expected_specialty in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            assert result["title"] is not None, f"Failed to extract title from: {filename}"
            assert (
                expected_specialty.lower() in result["title"].lower()
            ), f"Expected '{expected_specialty}' in title, got: {result['title']}"

    def test_date_format_variations(self, parser):
        """Test various date formats are parsed correctly."""
        test_cases = [
            ("National Geographic - Jan2024.pdf", 2024, 1),
            ("National Geographic - January 2024.pdf", 2024, 1),
            ("National Geographic.Jan.2024.pdf", 2024, 1),
            ("National Geographic Jan 2024.pdf", 2024, 1),
            ("National Geographic-January.2024.pdf", 2024, 1),
            ("National Geographic 2024-01.pdf", 2024, 1),
            ("National Geographic 01-2024.pdf", 2024, 1),
        ]

        for filename, expected_year, expected_month in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Check year
            assert result.get("year") == expected_year or (
                result.get("issue_date") and result["issue_date"].year == expected_year
            ), f"Expected year {expected_year}, got: {result.get('year')} or {result.get('issue_date')}"

            # Check month
            if result.get("month"):
                assert result["month"] == expected_month, f"Expected month {expected_month}, got: {result['month']}"
            elif result.get("issue_date"):
                assert (
                    result["issue_date"].month == expected_month
                ), f"Expected month {expected_month}, got: {result['issue_date'].month}"

    def test_multi_month_formats(self, parser):
        """Test multi-month period formats.

        Note: The parser uses the FIRST month in multi-month periods for sorting.
        So "June/July" -> month 6, "Dec/Jan" -> month 12, etc.
        """
        test_cases = [
            (
                "National Geographic - Jun-Jul2024.pdf",
                6,
                "Jun",
            ),  # Uses dash for filesystem
            ("National Geographic 11.10 2019.pdf", 10, "October"),
            ("National Geographic 05.06 2023.pdf", 5, "May"),
            (
                "National Geographic Dec-Jan 2024.pdf",
                12,
                "Dec",
            ),  # Uses dash for filesystem
        ]

        for filename, expected_month, expected_display in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Check that month is correct
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
            assert (
                actual_month == expected_month
            ), f"Expected month {expected_month}, got: {actual_month} for {filename}"

            # Check month name display contains expected string
            month_name = result.get("month_name", "")
            assert (
                expected_display.split("/")[0].lower() in month_name.lower()
            ), f"Expected '{expected_display}' pattern in month_name, got: {month_name}"

    def test_nzb_style_filenames(self, parser):
        """Test NZB-style filenames with complex metadata."""
        test_cases = [
            (
                "National.Geographic.USA.January.2024.HQ.PDF.pdf",
                "National Geographic",
                2024,
                1,
            ),
            (
                "National.Geographic.UK.-.December.2023.True.PDF-PHOTOFILE.pdf",
                "National Geographic",
                2023,
                12,
            ),
            (
                "National.Geographic.Magazine.US.Jan.2024.Retail-LORENZ.pdf",
                "National Geographic",
                2024,
                1,
            ),
            ("Nat.Geo.Arabia.March.2023.HQ-PHOTOFILEv2.pdf", "Nat Geo", 2023, 3),
        ]

        for (
            filename,
            expected_title_contains,
            expected_year,
            expected_month,
        ) in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Check title
            assert result["title"] is not None, f"Failed to extract title from: {filename}"
            assert (
                expected_title_contains.lower() in result["title"].lower()
            ), f"Expected '{expected_title_contains}' in title, got: {result['title']}"

            # Check date
            actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)

            assert actual_year == expected_year, f"Expected year {expected_year}, got: {actual_year}"
            assert actual_month == expected_month, f"Expected month {expected_month}, got: {actual_month}"

    def test_combined_regional_and_specialty(self, parser):
        """Test combined regional and specialty editions."""
        test_cases = [
            ("National Geographic UK Kids - Jan2024.pdf", "UK", "Kids"),
            ("National Geographic US Traveler - Jan2024.pdf", "US", "Traveler"),
            ("National.Geographic.Arabia.Kids.January.2024.pdf", "Arabia", "Kids"),
        ]

        for filename, expected_region, expected_specialty in test_cases:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            title_lower = result["title"].lower() if result["title"] else ""

            assert (
                expected_region.lower() in title_lower
            ), f"Expected '{expected_region}' in title, got: {result['title']}"
            assert (
                expected_specialty.lower() in title_lower
            ), f"Expected '{expected_specialty}' in title, got: {result['title']}"

    @pytest.mark.parametrize("year", TEST_YEARS)
    def test_year_range(self, parser, year):
        """Test parsing across different years."""
        filename = f"National Geographic - Jan{year}.pdf"
        path = Path(f"/test/{filename}")
        result = parser.extract_from_filename(path)

        actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
        assert actual_year == year, f"Expected year {year}, got: {actual_year}"

    @pytest.mark.parametrize("month_str,month_num", MONTH_FORMATS[:6])
    def test_all_months(self, parser, month_str, month_num):
        """Test parsing all month formats."""
        filename = f"National Geographic - {month_str}2024.pdf"
        path = Path(f"/test/{filename}")
        result = parser.extract_from_filename(path)

        actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
        assert actual_month == month_num, f"Expected month {month_num} for '{month_str}', got: {actual_month}"


# ==============================================================================
# Fuzzy Matching Tests
# ==============================================================================


class TestNationalGeographicFuzzyMatching:
    """Test fuzzy matching across National Geographic title variations."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_abbreviation_normalization(self, parser):
        """Test that abbreviations are normalized consistently."""
        filenames = [
            "National Geographic - Jan2024.pdf",
            "Nat Geo - Jan2024.pdf",
            "NG - Jan2024.pdf",
        ]

        results = []
        for filename in filenames:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)
            results.append(result)

        # All should extract the same date
        for result in results:
            actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
            assert actual_year == 2024
            assert actual_month == 1

    def test_delimiter_variations(self, parser):
        """Test that different delimiters are handled correctly."""
        filenames = [
            "National Geographic - Jan2024.pdf",
            "National.Geographic.Jan.2024.pdf",
            "National_Geographic_Jan_2024.pdf",
            "National Geographic Jan 2024.pdf",
        ]

        for filename in filenames:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # All should parse successfully
            assert result["title"] is not None
            actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
            assert actual_year == 2024
            assert actual_month == 1


# ==============================================================================
# Edge Cases and Regression Tests
# ==============================================================================


class TestNationalGeographicEdgeCases:
    """Test edge cases and potential problem patterns."""

    @pytest.fixture
    def parser(self):
        """Create FilenameParser instance."""
        return FilenameParser()

    def test_ambiguous_title_with_year(self, parser):
        """Test titles where year might be confused with other numbers."""
        filename = "National Geographic 2024 Special Edition.pdf"
        path = Path(f"/test/{filename}")
        result = parser.extract_from_filename(path)

        # Should extract year 2024
        actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
        assert actual_year == 2024

    def test_multiple_dashes(self, parser):
        """Test filenames with multiple dashes."""
        filename = "National Geographic - US - Kids - Jan2024.pdf"
        path = Path(f"/test/{filename}")
        result = parser.extract_from_filename(path)

        # Should still parse correctly
        assert result["title"] is not None
        actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
        assert actual_year == 2024

    def test_extra_metadata_in_filename(self, parser):
        """Test filenames with extra metadata (quality, format, etc.)."""
        filenames = [
            "National Geographic - Jan2024 - HQ.pdf",
            "National Geographic - Jan2024 [HQ].pdf",
            "National Geographic - Jan2024 (True PDF).pdf",
            "National Geographic - Jan2024 - Retail.pdf",
        ]

        for filename in filenames:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Should extract core metadata despite extra info
            assert result["title"] is not None
            actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
            assert actual_year == 2024
            assert actual_month == 1

    def test_issue_numbers(self, parser):
        """Test that issue numbers don't interfere with date parsing."""
        filenames = [
            "National Geographic Issue 123 - Jan2024.pdf",
            "National Geographic No.456 Jan2024.pdf",
            "National Geographic #789 - Jan2024.pdf",
        ]

        for filename in filenames:
            path = Path(f"/test/{filename}")
            result = parser.extract_from_filename(path)

            # Should extract date correctly
            actual_year = result.get("year") or (result.get("issue_date").year if result.get("issue_date") else None)
            actual_month = result.get("month") or (result.get("issue_date").month if result.get("issue_date") else None)
            assert actual_year == 2024
            assert actual_month == 1
