"""
Test the tracking matcher functionality
"""

import pytest
from core.constants.category import CATEGORY_MAGAZINE
from services.importer.matcher import TrackingMatcher


class MockTracking:
    """Mock MagazineTracking record for testing"""

    def __init__(self, id, title, language=None, country=None, category=None):
        self.id = id
        self.title = title
        self.language = language
        self.country = country
        self.category = category


def test_normalize_title_removes_prefixes():
    """Test that normalize_title removes common prefixes"""
    matcher = TrackingMatcher()

    assert matcher.normalize_title("[Magazine] Wired") == "Wired"
    assert matcher.normalize_title("[Comic] Batman") == "Batman"
    assert matcher.normalize_title("[Newspaper] Times") == "Times"
    assert matcher.normalize_title("Wired Magazine") == "Wired"


def test_normalize_title_handles_country_codes():
    """Test that country codes are normalized"""
    matcher = TrackingMatcher()

    assert matcher.normalize_title("Wired USA") == "Wired US"
    assert matcher.normalize_title("Wired U.S.A.") == "Wired US"
    assert matcher.normalize_title("Times UK") == "Times GB"


def test_normalize_country():
    """Test country normalization"""
    matcher = TrackingMatcher()

    assert matcher.normalize_country("USA") == "US"
    assert matcher.normalize_country("U.S.A.") == "US"
    assert matcher.normalize_country("United States") == "US"
    assert matcher.normalize_country("UK") == "GB"
    assert matcher.normalize_country("United Kingdom") == "GB"


def test_exact_title_match():
    """Test exact title matching"""
    matcher = TrackingMatcher()

    score, breakdown = matcher.match_to_tracking(parsed_title="Wired US", tracking_title="Wired US")

    assert score == 100
    assert breakdown["title"] == 100
    assert "exact" in breakdown["title_match_type"]


def test_fuzzy_title_match():
    """Test fuzzy title matching with variations"""
    matcher = TrackingMatcher()

    # Wired USA should match Wired US (after normalization)
    score, breakdown = matcher.match_to_tracking(parsed_title="Wired USA", tracking_title="Wired US")

    # Should be high score due to similarity after normalization
    assert score >= 80
    assert breakdown["title"] >= 80


def test_language_matching():
    """Test language matching bonus"""
    matcher = TrackingMatcher()

    # With matching language
    score_with_lang, breakdown = matcher.match_to_tracking(
        parsed_title="Wired US",
        tracking_title="Wired US",
        parsed_language="English",
        tracking_language="English",
    )

    # Without language info
    score_without_lang, _ = matcher.match_to_tracking(parsed_title="Wired US", tracking_title="Wired US")

    # Score with matching language should be higher
    assert score_with_lang > score_without_lang
    assert breakdown["language"] == 20


def test_country_matching():
    """Test country matching bonus"""
    matcher = TrackingMatcher()

    # With matching country
    score_with_country, breakdown = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="US",
    )

    # Without country info
    score_without_country, _ = matcher.match_to_tracking(parsed_title="Wired", tracking_title="Wired")

    # Score with matching country should be higher
    assert score_with_country > score_without_country
    assert breakdown["country"] == 15


def test_find_best_match():
    """Test finding the best match from multiple tracking records"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", "US", CATEGORY_MAGAZINE),
        MockTracking(2, "Wired US", "English", "US", CATEGORY_MAGAZINE),
        MockTracking(3, "Time", "English", "US", CATEGORY_MAGAZINE),
    ]

    # Should match Wired US
    result = matcher.find_best_match(
        parsed_title="[Magazine] Wired USA True",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="US",
        parsed_category=CATEGORY_MAGAZINE,
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 2
    assert "Wired" in result.tracking_title


def test_no_match_below_threshold():
    """Test that poor matches don't return a match"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", "US", CATEGORY_MAGAZINE),
        MockTracking(2, "Wired", "English", "US", CATEGORY_MAGAZINE),
    ]

    # Should NOT match any of these
    result = matcher.find_best_match(
        parsed_title="Sports Illustrated",
        tracking_records=tracking_records,
        parsed_language="English",
    )

    # Should either return None or a result with is_match=False
    assert result is None or not result.is_match


def test_matching_ignores_case():
    """Test that matching is case-insensitive"""
    matcher = TrackingMatcher()

    score, breakdown = matcher.match_to_tracking(parsed_title="wired us", tracking_title="Wired US")

    assert score == 100
    assert "exact" in breakdown["title_match_type"]


def test_country_mismatch_penalty():
    """Test that mismatched countries apply penalty instead of blocking"""
    matcher = TrackingMatcher()

    # Matching country
    score_match, _ = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="US",
    )

    # Mismatched country - now applies penalty instead of blocking
    score_mismatch, breakdown = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="GB",
    )

    # Country mismatch applies -30 penalty (100 - 30 = 70, still matches at threshold)
    assert score_mismatch == 70
    assert breakdown["country"] == "mismatch"
    # Matching country gets bonus
    assert score_match == 115


def test_regional_editions_with_title_differences_dont_match():
    """Test that regional editions with different titles don't match due to fuzzy + penalty"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "GQ US", "English", "US", CATEGORY_MAGAZINE),
    ]

    # GQ South Africa should NOT match GQ US (different titles)
    result = matcher.find_best_match(
        parsed_title="GQ South Africa",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",
        parsed_category=CATEGORY_MAGAZINE,
    )

    # Should not match due to title difference + country penalty
    assert result is None or not result.is_match


def test_exact_title_with_wrong_metadata_country_still_matches():
    """Test that exact title match with wrong metadata country still matches (bug fix)"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Wired", "English", "US", CATEGORY_MAGAZINE),
    ]

    # File with exact title match but wrong country metadata should still match
    result = matcher.find_best_match(
        parsed_title="Wired",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="UK",  # Wrong metadata
        parsed_category=CATEGORY_MAGAZINE,
    )

    # Should match despite country mismatch (100 + 20 + 10 - 30 = 100)
    assert result is not None
    assert result.is_match
    assert result.score == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
