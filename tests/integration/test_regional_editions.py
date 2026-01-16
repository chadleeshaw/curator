"""
Test that regional editions get separate tracking entries.

This test suite verifies that magazines with different regional editions
(e.g., Esquire US vs Esquire South Africa) are tracked separately and
don't get merged into the same tracking record.
"""

import pytest
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
    Test that Esquire South Africa doesn't match Esquire US tracking.

    This was a real bug where "Esquire South Africa - January2011.pdf"
    was being matched to Esquire US tracking (tracking_id: 2) instead of
    creating its own tracking entry.
    """
    matcher = TrackingMatcher()

    # Existing Esquire US tracking
    tracking_records = [
        MockTracking(2, "Esquire", "English", "US", "Magazines"),
    ]

    # Try to match Esquire South Africa
    # With country mismatch blocking, this should NOT match
    result = matcher.find_best_match(
        parsed_title="Esquire",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",  # South Africa
        parsed_category="Magazines",
    )

    # Should not match due to country mismatch
    assert result is None or not result.is_match, (
        "Esquire South Africa should not match Esquire US tracking. "
        "Regional editions should get separate tracking entries."
    )


def test_esquire_south_africa_matches_its_own_tracking():
    """Test that Esquire South Africa correctly matches its own tracking"""
    matcher = TrackingMatcher()

    # Multiple Esquire editions
    tracking_records = [
        MockTracking(1, "Esquire", "English", "US", "Magazines"),
        MockTracking(2, "Esquire South Africa", "English", "ZA", "Magazines"),
        MockTracking(3, "Esquire", "German", "DE", "Magazines"),
    ]

    # Should match the South Africa edition (ID 2)
    result = matcher.find_best_match(
        parsed_title="Esquire South Africa",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="ZA",
        parsed_category="Magazines",
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 2
    assert "South Africa" in result.tracking_title


def test_wired_uk_separate_from_us():
    """Test that Wired UK doesn't match Wired US"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Wired", "English", "US", "Magazines"),
    ]

    # Wired UK should NOT match Wired US
    result = matcher.find_best_match(
        parsed_title="Wired",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="GB",  # UK
        parsed_category="Magazines",
    )

    assert result is None or not result.is_match


def test_same_country_different_editions_can_match():
    """Test that different special editions of same country can still match base title"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "Sports Illustrated", "English", "US", "Magazines"),
    ]

    # Sports Illustrated Swimsuit (US edition) should match Sports Illustrated US
    result = matcher.find_best_match(
        parsed_title="Sports Illustrated",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country="US",
        parsed_category="Magazines",
    )

    assert result is not None
    assert result.is_match
    assert result.tracking_id == 1


def test_no_country_specified_can_still_match():
    """Test that magazines without country info can still match"""
    matcher = TrackingMatcher()

    tracking_records = [
        MockTracking(1, "National Geographic", "English", None, "Magazines"),
    ]

    # Should match even without country specified
    result = matcher.find_best_match(
        parsed_title="National Geographic",
        tracking_records=tracking_records,
        parsed_language="English",
        parsed_country=None,
        parsed_category="Magazines",
    )

    assert result is not None
    assert result.is_match


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
