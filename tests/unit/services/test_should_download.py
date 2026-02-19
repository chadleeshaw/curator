"""
Tests for _should_download() tracking mode enforcement in IssueDiscoveryService.

Covers all three tracking modes:
- Watch Only (track_all_editions=False, track_new_only=False) → never download
- Download All (track_all_editions=True) → always download
- Latest Issue (track_new_only=True) → download only recent issues
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


from core.parsers import utc_now
from core.constants.app import NEW_ISSUE_THRESHOLD_DAYS
from models.database import DiscoveredIssue, PeriodicalTracking
from services.issue_discovery import IssueDiscoveryService


class TestShouldDownloadWatchOnly:
    """Watch Only mode: track_all_editions=False, track_new_only=False → never download"""

    @pytest.fixture
    def service(self):
        return IssueDiscoveryService()

    @pytest.fixture
    def tracking_watch_only(self):
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 1
        tracking.title = "Test Magazine"
        tracking.country = "US"
        tracking.track_all_editions = False
        tracking.track_new_only = False
        tracking.selected_years = []
        return tracking

    def test_watch_only_with_recent_issue(self, service, tracking_watch_only):
        """Watch Only should NOT download even recent issues"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine January 2026"
        issue.country = "US"
        issue.issue_date = utc_now() - timedelta(days=5)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_watch_only) is False

    def test_watch_only_with_old_issue(self, service, tracking_watch_only):
        """Watch Only should NOT download old issues"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine January 2020"
        issue.country = "US"
        issue.issue_date = datetime(2020, 1, 1)
        issue.year = 2020

        assert service._should_download(issue, tracking_watch_only) is False

    def test_watch_only_with_no_date(self, service, tracking_watch_only):
        """Watch Only should NOT download issues with no date"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine"
        issue.country = "US"
        issue.issue_date = None
        issue.year = None

        assert service._should_download(issue, tracking_watch_only) is False


class TestShouldDownloadAll:
    """Download All mode: track_all_editions=True → always download"""

    @pytest.fixture
    def service(self):
        return IssueDiscoveryService()

    @pytest.fixture
    def tracking_all(self):
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 1
        tracking.title = "Test Magazine"
        tracking.country = "US"
        tracking.track_all_editions = True
        tracking.track_new_only = False
        tracking.selected_years = []
        return tracking

    def test_download_all_recent_issue(self, service, tracking_all):
        """Download All should download recent issues"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine January 2026"
        issue.country = "US"
        issue.issue_date = utc_now() - timedelta(days=5)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_all) is True

    def test_download_all_old_issue(self, service, tracking_all):
        """Download All should download old issues"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine June 2018"
        issue.country = "US"
        issue.issue_date = datetime(2018, 6, 1)
        issue.year = 2018

        assert service._should_download(issue, tracking_all) is True

    def test_download_all_no_date(self, service, tracking_all):
        """Download All should download even without a date"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine Collection"
        issue.country = "US"
        issue.issue_date = None
        issue.year = None

        assert service._should_download(issue, tracking_all) is True

    def test_download_all_blocks_wrong_country(self, service, tracking_all):
        """Download All should still respect country filtering"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine UK Edition"
        issue.country = "UK"
        issue.issue_date = utc_now()
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_all) is False


class TestShouldDownloadNewOnly:
    """Latest Issue mode: track_new_only=True → download only recent issues"""

    @pytest.fixture
    def service(self):
        return IssueDiscoveryService()

    @pytest.fixture
    def tracking_new_only(self):
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 1
        tracking.title = "Test Magazine"
        tracking.country = "US"
        tracking.track_all_editions = False
        tracking.track_new_only = True
        tracking.selected_years = []
        return tracking

    def test_new_only_recent_issue_within_threshold(self, service, tracking_new_only):
        """Should download issues within the threshold window"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine February 2026"
        issue.country = "US"
        issue.issue_date = utc_now() - timedelta(days=15)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_new_only) is True

    def test_new_only_issue_at_threshold_boundary(self, service, tracking_new_only):
        """Should download issues exactly at the threshold boundary"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine"
        issue.country = "US"
        issue.issue_date = utc_now() - timedelta(days=NEW_ISSUE_THRESHOLD_DAYS)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_new_only) is True

    def test_new_only_issue_just_past_threshold(self, service, tracking_new_only):
        """Should NOT download issues just past the threshold"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine"
        issue.country = "US"
        issue.issue_date = utc_now() - timedelta(days=NEW_ISSUE_THRESHOLD_DAYS + 1)
        issue.year = utc_now().year - 1

        assert service._should_download(issue, tracking_new_only) is False

    def test_new_only_old_issue(self, service, tracking_new_only):
        """Should NOT download issues from years ago"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine January 2020"
        issue.country = "US"
        issue.issue_date = datetime(2020, 1, 1)
        issue.year = 2020

        assert service._should_download(issue, tracking_new_only) is False

    def test_new_only_future_issue(self, service, tracking_new_only):
        """Should download future-dated issues (advance releases)"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine March 2026"
        issue.country = "US"
        issue.issue_date = utc_now() + timedelta(days=30)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_new_only) is True

    def test_new_only_year_only_current_year(self, service, tracking_new_only):
        """Should download issues with year only if current year"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine 2026"
        issue.country = "US"
        issue.issue_date = None
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_new_only) is True

    def test_new_only_year_only_old_year(self, service, tracking_new_only):
        """Should NOT download issues with year only if old year"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine 2019"
        issue.country = "US"
        issue.issue_date = None
        issue.year = 2019

        assert service._should_download(issue, tracking_new_only) is False

    def test_new_only_no_date_at_all(self, service, tracking_new_only):
        """Should NOT download issues with no date information"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine Collection"
        issue.country = "US"
        issue.issue_date = None
        issue.year = None

        assert service._should_download(issue, tracking_new_only) is False

    def test_new_only_blocks_wrong_country(self, service, tracking_new_only):
        """Should still respect country filtering"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine UK February 2026"
        issue.country = "UK"
        issue.issue_date = utc_now() - timedelta(days=5)
        issue.year = utc_now().year

        assert service._should_download(issue, tracking_new_only) is False


class TestShouldDownloadSelectedYears:
    """Selected Years mode: selected_years=[2024, 2025] → download only those years"""

    @pytest.fixture
    def service(self):
        return IssueDiscoveryService()

    @pytest.fixture
    def tracking_selected(self):
        tracking = MagicMock(spec=PeriodicalTracking)
        tracking.id = 1
        tracking.title = "Test Magazine"
        tracking.country = "US"
        tracking.track_all_editions = False
        tracking.track_new_only = False
        tracking.selected_years = [2024, 2025]
        return tracking

    def test_selected_years_matching_year(self, service, tracking_selected):
        """Should download issues from selected years"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine March 2024"
        issue.country = "US"
        issue.issue_date = datetime(2024, 3, 1)
        issue.year = 2024

        assert service._should_download(issue, tracking_selected) is True

    def test_selected_years_non_matching_year(self, service, tracking_selected):
        """Should NOT download issues from non-selected years"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine June 2020"
        issue.country = "US"
        issue.issue_date = datetime(2020, 6, 1)
        issue.year = 2020

        assert service._should_download(issue, tracking_selected) is False

    def test_selected_years_no_year_on_issue(self, service, tracking_selected):
        """Should NOT download if issue has no year"""
        issue = MagicMock(spec=DiscoveredIssue)
        issue.title = "Test Magazine"
        issue.country = "US"
        issue.issue_date = None
        issue.year = None

        assert service._should_download(issue, tracking_selected) is False
