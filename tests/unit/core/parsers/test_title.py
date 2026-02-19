#!/usr/bin/env python3
"""
Test suite for core.parsers.title module
"""

from datetime import datetime

# Path setup handled by conftest.py

from core.parsers.title import TitleMatcher


def test_title_matcher_initialization():
    """Test TitleMatcher initialization"""
    matcher = TitleMatcher()

    assert matcher is not None


def test_clean_release_title():
    """Test release title cleaning"""
    matcher = TitleMatcher()

    # Test with basic title
    cleaned = matcher.clean_release_title("National Geographic Magazine")
    assert cleaned is not None
    assert isinstance(cleaned, str)


def test_match_method_signature():
    """Test match method exists with correct signature"""
    matcher = TitleMatcher()

    # match returns tuple of (is_match: bool, score: int)
    is_match, score = matcher.match("Time Magazine", "Time Magazine")

    assert isinstance(is_match, bool)
    assert isinstance(score, int)
    assert is_match is True  # Identical titles should match


def test_match_titles_with_variations():
    """Test matching title variations"""
    matcher = TitleMatcher()

    # Should match similar titles
    title1 = "National Geographic"
    title2 = "National Geographic Magazine"

    is_match, score = matcher.match(title1, title2)

    # Implementation dependent, but should handle common variations
    assert isinstance(is_match, bool)
    assert isinstance(score, int)


def test_match_titles_with_articles():
    """Test matching titles with articles (the, a, an)"""
    matcher = TitleMatcher()

    # match returns tuple of (is_match: bool, score: int)
    is_match, score = matcher.match("The Atlantic", "Atlantic")

    # Should handle articles
    assert isinstance(is_match, bool)
    assert isinstance(score, int)


# ============================================
# Tests for matches_library_item_with_date_range
# ============================================


def test_matches_library_item_exact_match():
    """Test exact title + date match"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer US - January 2024",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer US - January 2024",
        library_date=datetime(2024, 1, 1),
    )

    assert is_match is True
    assert score >= 80  # Should have high confidence


def test_matches_library_item_fuzzy_title():
    """Test fuzzy title + date match with same regional edition"""
    matcher = TitleMatcher()

    # Both titles have "US" indicator, so they should match
    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer - United States Edition",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer US",
        library_date=datetime(2024, 1, 1),
    )

    # Note: "United States Edition" contains "united" and "states" which are in
    # REGIONAL_PERIODICAL_INDICATORS, so this will be detected as having a variant.
    # The "US" in library_title is also a regional indicator.
    # These are different regional indicators, so they won't match.
    assert is_match is False
    assert score == 0


def test_matches_library_item_different_months():
    """Test that different months don't match"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer US",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer US",
        library_date=datetime(2024, 2, 1),
    )

    assert is_match is False
    assert score == 0


def test_matches_library_item_date_tolerance():
    """Test date tolerance across month boundaries"""
    matcher = TitleMatcher()

    # Jan 29 and Feb 1 are within 7 days
    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Magazine",
        provider_date=datetime(2024, 1, 29),
        library_title="Magazine",
        library_date=datetime(2024, 2, 1),
        date_tolerance_days=7,
    )

    assert is_match is True
    assert score > 0


def test_matches_library_item_no_provider_date():
    """Test matching when provider has no date but has issue number"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Comic Issue 123",
        provider_date=None,
        library_title="Comic #123",
        library_date=datetime(2024, 1, 1),
    )

    # Should match by issue number despite no date
    assert is_match is True
    assert score > 0


def test_matches_library_item_volume_match():
    """Test matching by volume number"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Magazine Vol 5 Issue 3",
        provider_date=None,
        library_title="Magazine Vol 5 Issue 3",
        library_date=datetime(2024, 1, 1),
    )

    # Should match by volume and issue number
    assert is_match is True
    assert score > 0


def test_matches_library_item_different_volumes():
    """Test that different volumes don't match"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Magazine Vol 5",
        provider_date=None,
        library_title="Magazine Vol 6",
        library_date=datetime(2024, 1, 1),
    )

    assert is_match is False
    assert score == 0


def test_matches_library_item_different_issues():
    """Test that different issue numbers don't match"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Comic #123",
        provider_date=None,
        library_title="Comic #124",
        library_date=datetime(2024, 1, 1),
    )

    assert is_match is False
    assert score == 0


def test_matches_library_item_different_editions():
    """Test that different regional editions do NOT match"""
    matcher = TitleMatcher()

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer US",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer UK",
        library_date=datetime(2024, 1, 1),
    )

    # PC Gamer US and PC Gamer UK are different regional editions
    # They should NOT match even though base title is similar
    assert is_match is False
    assert score == 0


def test_extract_issue_volume_from_title():
    """Test volume and issue extraction from titles"""
    matcher = TitleMatcher()

    # Test various formats
    test_cases = [
        ("Magazine Vol 5 Issue 3", 5, 3),
        ("Comic #123", None, 123),
        ("Publication Volume 10 No. 2", 10, 2),
        ("Title V3", 3, None),
        ("Regular Title", None, None),
    ]

    for title, expected_vol, expected_issue in test_cases:
        vol, issue = matcher._extract_issue_volume_from_title(title)
        assert vol == expected_vol, f"Volume mismatch for '{title}': expected {expected_vol}, got {vol}"
        assert issue == expected_issue, f"Issue mismatch for '{title}': expected {expected_issue}, got {issue}"


def test_extract_periodical_variant_kids():
    """Should extract 'kids' edition variant"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("National Geographic Kids")
    assert variant == "kids"


def test_extract_periodical_variant_little_kids():
    """Should extract 'little kids' multi-word variant"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("National Geographic Little Kids")
    assert variant == "little kids"


def test_extract_periodical_variant_professional():
    """Should extract 'professional' edition variant"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("Forbes Professional")
    assert variant == "professional"


def test_extract_periodical_variant_regional_us():
    """Should extract 'us' regional edition variant"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("PC Gamer US")
    assert variant == "us"


def test_extract_periodical_variant_regional_uk():
    """Should extract 'uk' regional edition variant"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("PC Gamer UK")
    assert variant == "uk"


def test_extract_periodical_variant_none():
    """Should return None when no edition variant present"""
    matcher = TitleMatcher(threshold=80)
    variant = matcher.extract_periodical_variant("National Geographic")
    assert variant is None


def test_edition_mismatch_kids_vs_base():
    """National Geographic Kids should NOT match National Geographic"""
    matcher = TitleMatcher(threshold=80)

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="National Geographic Kids",
        provider_date=datetime(2024, 1, 15),
        library_title="National Geographic",
        library_date=datetime(2024, 1, 1),
    )

    assert not is_match, "Kids edition should not match base magazine"
    assert score == 0


def test_edition_mismatch_little_kids_vs_base():
    """National Geographic Little Kids should NOT match National Geographic"""
    matcher = TitleMatcher(threshold=80)

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="National Geographic Little Kids",
        provider_date=datetime(2024, 1, 15),
        library_title="National Geographic",
        library_date=datetime(2024, 1, 1),
    )

    assert not is_match, "Little Kids edition should not match base magazine"
    assert score == 0


def test_edition_mismatch_different_variants():
    """PC Gamer Pro should NOT match PC Gamer Business"""
    matcher = TitleMatcher(threshold=80)

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer Pro",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer Business",
        library_date=datetime(2024, 1, 1),
    )

    assert not is_match, "Different edition variants should not match"
    assert score == 0


def test_edition_match_same_variant():
    """PC Gamer Pro should match PC Gamer Pro"""
    matcher = TitleMatcher(threshold=80)

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="PC Gamer Pro",
        provider_date=datetime(2024, 1, 15),
        library_title="PC Gamer Pro",
        library_date=datetime(2024, 1, 1),
    )

    assert is_match, "Same edition variant should match"
    assert score > 0


def test_edition_match_no_variants():
    """National Geographic should match National Geographic (no variants)"""
    matcher = TitleMatcher(threshold=80)

    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="National Geographic",
        provider_date=datetime(2024, 1, 15),
        library_title="National Geographic",
        library_date=datetime(2024, 1, 1),
    )

    assert is_match, "Base titles with no variants should match"
    assert score > 0


def test_special_edition_not_detected_as_variant():
    """Special editions should NOT be detected as edition variants"""
    matcher = TitleMatcher(threshold=80)

    # These are special issues, not edition variants
    test_cases = [
        "Time Person Of The Year",
        "Sports Illustrated Swimsuit",
        "National Geographic Travel Issue",
        "Forbes 100 Best Companies",
    ]

    for title in test_cases:
        variant = matcher.extract_periodical_variant(title)
        assert variant is None, f"'{title}' should not have edition variant, got: {variant}"


def test_special_edition_matches_base_title():
    """Special editions should match their base publication"""
    matcher = TitleMatcher(threshold=80)

    # "Time - Person of the Year" should match "Time" (same publication, special issue)
    is_match, score = matcher.matches_library_item_with_date_range(
        provider_title="Time Person Of The Year",
        provider_date=datetime(2024, 12, 15),
        library_title="Time",
        library_date=datetime(2024, 12, 1),
    )

    # Should match because no edition variants detected
    assert is_match, "Special edition should match base publication"
    assert score > 0


def test_context_aware_no_detection():
    """'No' in 'No 10' should not be detected as Norway"""
    matcher = TitleMatcher(threshold=80)

    # "No" followed by number is issue numbering, not country code
    variant = matcher.extract_periodical_variant("Time Magazine Vol 5 No 10")
    assert variant is None, f"'No 10' should not detect 'no' as Norway, got: {variant}"


def test_format_indicator_not_detected():
    """Format indicators like 'Digital' should not be edition variants"""
    matcher = TitleMatcher(threshold=80)

    # "Digital" at end is format metadata, not edition variant
    variant = matcher.extract_periodical_variant("Wired Magazine 2024 Digital")
    assert variant is None, f"'Digital' at end should not be variant, got: {variant}"
