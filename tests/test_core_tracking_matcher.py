"""
Test the tracking matcher functionality
"""

import pytest
from core.tracking_matcher import TrackingMatcher


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

    score, breakdown = matcher.match_to_tracking(
        parsed_title="Wired US",
        tracking_title="Wired US"
    )

    assert score == 100
    assert breakdown['title'] == 100
    assert 'exact' in breakdown['title_match_type']


def test_fuzzy_title_match():
    """Test fuzzy title matching with variations"""
    matcher = TrackingMatcher()

    # Wired USA should match Wired US (after normalization)
    score, breakdown = matcher.match_to_tracking(
        parsed_title="Wired USA",
        tracking_title="Wired US"
    )

    # Should be high score due to similarity after normalization
    assert score >= 80
    assert breakdown['title'] >= 80


def test_language_matching():
    """Test language matching bonus"""
    matcher = TrackingMatcher()

    # With matching language
    score_with_lang, breakdown = matcher.match_to_tracking(
        parsed_title="Wired US",
        tracking_title="Wired US",
        parsed_language="English",
        tracking_language="English"
    )

    # Without language info
    score_without_lang, _ = matcher.match_to_tracking(
        parsed_title="Wired US",
        tracking_title="Wired US"
    )

    # Score with matching language should be higher
    assert score_with_lang > score_without_lang
    assert breakdown['language'] == 20


def test_country_matching():
    """Test country matching bonus"""
    matcher = TrackingMatcher()

    # With matching country
    score_with_country, breakdown = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="US"
    )

    # Without country info
    score_without_country, _ = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired"
    )

    # Score with matching country should be higher
    assert score_with_country > score_without_country
    assert breakdown['country'] == 15


def test_find_best_match():
    """Test finding the best match from multiple tracking records"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", "US", "Magazines"),
        MockTracking(2, "Wired US", "English", "US", "Magazines"),
        MockTracking(3, "Time", "English", "US", "Magazines"),
    ]

    # Should match Wired US
    result = matcher.find_best_match(
        parsed_title="[Magazine] Wired USA True",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="US",
        parsed_category="Magazines"
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 2
    assert "Wired" in result.tracking_title


def test_no_match_below_threshold():
    """Test that poor matches don't return a match"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", "US", "Magazines"),
        MockTracking(2, "Wired", "English", "US", "Magazines"),
    ]

    # Should NOT match any of these
    result = matcher.find_best_match(
        parsed_title="Sports Illustrated",
        tracking_records=tracking_records,
        parsed_language="English"
    )

    # Should either return None or a result with is_match=False
    assert result is None or not result.is_match


def test_matching_ignores_case():
    """Test that matching is case-insensitive"""
    matcher = TrackingMatcher()

    score, breakdown = matcher.match_to_tracking(
        parsed_title="wired us",
        tracking_title="Wired US"
    )

    assert score == 100
    assert 'exact' in breakdown['title_match_type']


def test_country_mismatch_penalty():
    """Test that mismatched countries block matching entirely"""
    matcher = TrackingMatcher()

    # Matching country
    score_match, _ = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="US"
    )

    # Mismatched country
    score_mismatch, breakdown = matcher.match_to_tracking(
        parsed_title="Wired",
        tracking_title="Wired",
        parsed_country="US",
        tracking_country="GB"
    )

    # Country mismatch now blocks matching entirely (score = 0)
    assert score_mismatch == 0
    assert breakdown['country'] == 'mismatch'


def test_regional_editions_dont_match():
    """Test that regional editions (e.g., GQ South Africa vs GQ US) don't match"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "GQ", "English", "US", "Magazines"),
    ]

    # GQ South Africa should NOT match GQ US
    result = matcher.find_best_match(
        parsed_title="GQ",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",  # South Africa
        parsed_category="Magazines"
    )

    # Should not match due to country mismatch blocking
    assert result is None or not result.is_match


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
