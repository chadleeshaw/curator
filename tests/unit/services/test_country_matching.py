"""
Tests for country matching in issue discovery.

Ensures that different country editions are treated as separate periodicals.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from models.database import DiscoveredIssue, PeriodicalTracking
from services.issue_discovery import IssueDiscoveryService


class TestCountryMatching:
    """Test country matching logic in issue discovery"""

    @pytest.fixture
    def service(self):
        """Create issue discovery service"""
        return IssueDiscoveryService()

    @pytest.fixture
    def tracking_us(self):
        """Create US tracking record"""
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 1
        tracking.title = "National Geographic"
        tracking.country = "US"
        tracking.language = "English"
        tracking.track_all_editions = True
        return tracking

    @pytest.fixture
    def tracking_uk(self):
        """Create UK tracking record"""
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 2
        tracking.title = "National Geographic"
        tracking.country = "UK"
        tracking.language = "English"
        tracking.track_all_editions = True
        return tracking

    @pytest.fixture
    def tracking_none(self):
        """Create tracking record with no country (should default to US)"""
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 3
        tracking.title = "National Geographic"
        tracking.country = None  # No country = USA
        tracking.language = "English"
        tracking.track_all_editions = True
        return tracking

    def test_us_issue_matches_us_tracking(self, service, tracking_us):
        """US issue should match US tracking"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic USA January 2024"
        issue.country = "US"
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_us)
        assert result is True

    def test_uk_issue_does_not_match_us_tracking(self, service, tracking_us):
        """UK issue should NOT match US tracking"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic UK January 2024"
        issue.country = "UK"
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_us)
        assert result is False

    def test_us_issue_does_not_match_uk_tracking(self, service, tracking_uk):
        """US issue should NOT match UK tracking"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic USA January 2024"
        issue.country = "US"
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_uk)
        assert result is False

    def test_uk_issue_matches_uk_tracking(self, service, tracking_uk):
        """UK issue should match UK tracking"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic UK January 2024"
        issue.country = "UK"
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_uk)
        assert result is True

    def test_no_country_defaults_to_us(self, service, tracking_us):
        """Issue with no country should default to US and match US tracking"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic January 2024"
        issue.country = None  # No country = USA
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_us)
        assert result is True

    def test_tracking_no_country_defaults_to_us(self, service, tracking_none):
        """Tracking with no country should default to US"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic USA January 2024"
        issue.country = "US"
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_none)
        assert result is True

    def test_both_no_country_match(self, service, tracking_none):
        """Both issue and tracking with no country should match (both default to US)"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "National Geographic January 2024"
        issue.country = None  # Defaults to US
        issue.issue_date = datetime(2024, 1, 1)

        result = service._should_download(issue, tracking_none)
        assert result is True

    def test_usa_normalized_to_us(self, service):
        """USA should be normalized to US"""
        normalized = service._normalize_country("USA")
        assert normalized == "US"

    def test_us_stays_us(self, service):
        """US should stay as US"""
        normalized = service._normalize_country("US")
        assert normalized == "US"

    def test_united_states_normalized_to_us(self, service):
        """'United States' should be normalized to US"""
        normalized = service._normalize_country("United States")
        assert normalized == "US"

    def test_uk_stays_uk(self, service):
        """UK should stay as UK"""
        normalized = service._normalize_country("UK")
        assert normalized == "UK"

    def test_united_kingdom_normalized_to_uk(self, service):
        """'United Kingdom' should be normalized to UK"""
        normalized = service._normalize_country("United Kingdom")
        assert normalized == "UK"

    def test_none_defaults_to_us(self, service):
        """None should default to US"""
        normalized = service._normalize_country(None)
        assert normalized == "US"

    def test_empty_string_defaults_to_us(self, service):
        """Empty string should default to US"""
        normalized = service._normalize_country("")
        assert normalized == "US"

    def test_australia_normalized(self, service):
        """AUS should be normalized to AU"""
        normalized = service._normalize_country("AUS")
        assert normalized == "AU"
