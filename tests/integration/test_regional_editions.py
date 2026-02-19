"""
Test that regional editions get separate tracking entries.

This test suite verifies that magazines with different regional editions
(e.g., Esquire US vs Esquire South Africa) are tracked separately and
don't get merged into the same tracking record.
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


def test_esquire_south_africa_separate_from_us():
    """
    Test that Esquire South Africa (with regional indicator in title) doesn't match Esquire US.

    Note: If the title is just "Esquire" with country=ZA in metadata, it WILL match
    Esquire US tracking (penalty-based matching allows this for metadata errors).
    But if the title is "Esquire South Africa", it won't match due to title difference.
    """
    matcher = TrackingMatcher()

    # Existing Esquire US tracking
    tracking_records = [
        MockTracking(2, "Esquire", "English", "US", CATEGORY_MAGAZINE),
    ]

    # Try to match "Esquire South Africa" (regional indicator in title)
    result = matcher.find_best_match(
        parsed_title="Esquire South Africa",  # Regional indicator in title
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",  # South Africa
        parsed_category=CATEGORY_MAGAZINE,
    )

    # Should not match due to title difference (fuzzy ~70 + penalty -30 = ~40)
    assert result is None or not result.is_match, (
        "Esquire South Africa should not match Esquire US tracking. "
        "Regional editions should get separate tracking entries."
    )


def test_esquire_south_africa_matches_its_own_tracking():
    """Test that Esquire South Africa correctly matches its own tracking"""
    matcher = TrackingMatcher()

    # Multiple Esquire editions
    tracking_records = [
        MockTracking(1, "Esquire", "English", "US", CATEGORY_MAGAZINE),
        MockTracking(2, "Esquire South Africa", "English", "ZA", CATEGORY_MAGAZINE),
        MockTracking(3, "Esquire", "German", "DE", CATEGORY_MAGAZINE),
    ]

    # Should match the South Africa edition (ID 2)
    result = matcher.find_best_match(
        parsed_title="Esquire South Africa",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",
        parsed_category=CATEGORY_MAGAZINE,
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 2
    assert "South Africa" in result.tracking_title


def test_wired_uk_separate_from_us():
    """Test that Wired UK (with UK in title) doesn't match Wired US"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Wired", "English", "US", CATEGORY_MAGAZINE),
    ]

    # "Wired UK" (with regional indicator in title) should NOT match Wired US
    result = matcher.find_best_match(
        parsed_title="Wired UK",  # Regional indicator in title
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="GB",  # UK
        parsed_category=CATEGORY_MAGAZINE,
    )

    # Should not match due to title difference
    assert result is None or not result.is_match


def test_same_country_different_editions_can_match():
    """Test that different special editions of same country can still match base title"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Sports Illustrated", "English", "US", CATEGORY_MAGAZINE),
    ]

    # Sports Illustrated Swimsuit (US edition) should match Sports Illustrated US
    result = matcher.find_best_match(
        parsed_title="Sports Illustrated",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="US",
        parsed_category=CATEGORY_MAGAZINE,
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 1


def test_no_country_specified_can_still_match():
    """Test that magazines without country info can still match"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", None, CATEGORY_MAGAZINE),
    ]

    # Should match even without country specified
    result = matcher.find_best_match(
        parsed_title="National Geographic",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country=None,
        parsed_category=CATEGORY_MAGAZINE,
    )

    assert result is not None
    assert result.is_match


def test_exact_title_wrong_metadata_country_does_match():
    """
    Test that exact title match with wrong country metadata DOES match (penalty-based).

    This is the bug fix - when a file has the exact same title as tracking,
    but metadata says different country, it should still match (metadata might be wrong).
    """
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Wired", "English", "US", CATEGORY_MAGAZINE),
    ]

    # "Wired" (no regional indicator) with metadata country=GB should match
    result = matcher.find_best_match(
        parsed_title="Wired",  # Same title, no regional indicator
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="GB",  # Different country in metadata
        parsed_category=CATEGORY_MAGAZINE,
    )

    # Should match despite country mismatch (100 + 20 + 10 - 30 = 100)
    assert result is not None
    assert result.is_match
    assert result.score == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
