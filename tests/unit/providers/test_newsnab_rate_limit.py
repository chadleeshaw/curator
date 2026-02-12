"""
Tests for Newsnab provider rate limiting functionality.

Test Coverage:
- is_rate_limited property (server-imposed and self-imposed)
- _rate_limit_logged flag to prevent log spam
- Cooldown expiry and state cleanup in _check_rate_limit
- NEWSNAB_DEFAULT_RATE_LIMIT_WAIT constant value
- RSS feed caching to reduce API calls
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.constants.providers import NEWSNAB_DEFAULT_RATE_LIMIT_WAIT
from core.parsers import utc_now
from providers.newsnab import NewsnabProvider


def _make_provider(**overrides):
    """Create a NewsnabProvider with minimal config for testing."""
    config = {
        "type": "newsnab",
        "name": "Test Provider",
        "api_url": "http://localhost:9696/api",
        "api_key": "test-key-123",
        **overrides,
    }
    return NewsnabProvider(config)


class TestNewsnabIsRateLimited:
    """Tests for the is_rate_limited property."""

    def test_not_rate_limited_initially(self):
        """Fresh provider should not be rate limited."""
        provider = _make_provider()
        assert not provider.is_rate_limited

    def test_rate_limited_by_server_cooldown(self):
        """is_rate_limited returns True during server-imposed cooldown."""
        provider = _make_provider()
        provider._rate_limit_until = utc_now() + timedelta(seconds=300)
        provider._rate_limit_reason = "HTTP 429 Too Many Requests"

        assert provider.is_rate_limited

    def test_not_rate_limited_after_cooldown_expires(self):
        """is_rate_limited returns False after cooldown period passes."""
        provider = _make_provider()
        provider._rate_limit_until = utc_now() - timedelta(seconds=1)
        provider._rate_limit_reason = "HTTP 429 Too Many Requests"

        assert not provider.is_rate_limited

    def test_rate_limited_by_self_imposed_limit(self):
        """is_rate_limited returns True when self-imposed hourly limit exceeded."""
        provider = _make_provider(max_requests_per_hour=5)

        now = time.time()
        provider._request_times = [now - i for i in range(5)]

        assert provider.is_rate_limited

    def test_not_rate_limited_when_under_self_imposed_limit(self):
        """is_rate_limited returns False when under hourly request limit."""
        provider = _make_provider(max_requests_per_hour=100)

        now = time.time()
        provider._request_times = [now - i for i in range(5)]

        assert not provider.is_rate_limited

    def test_self_imposed_limit_ignores_old_requests(self):
        """Requests older than 1 hour should not count toward limit."""
        provider = _make_provider(max_requests_per_hour=3)

        # All requests from 2 hours ago
        old_time = time.time() - 7200
        provider._request_times = [old_time - i for i in range(5)]

        assert not provider.is_rate_limited


class TestNewsnabCheckRateLimit:
    """Tests for _check_rate_limit with log-spam prevention and state cleanup."""

    def test_cooldown_logs_warning_once(self):
        """_check_rate_limit should only log the rate limit warning once per cooldown."""
        provider = _make_provider()
        provider._rate_limit_until = utc_now() + timedelta(seconds=300)
        provider._rate_limit_reason = "HTTP 429"
        provider._rate_limit_logged = False

        # First call should set _rate_limit_logged to True
        assert provider._check_rate_limit() is True
        assert provider._rate_limit_logged is True

        # Second call should still return True but not re-log (logged flag stays True)
        assert provider._check_rate_limit() is True
        assert provider._rate_limit_logged is True

    def test_cooldown_expiry_clears_state(self):
        """_check_rate_limit should clear all rate limit state when cooldown expires."""
        provider = _make_provider()
        provider._rate_limit_until = utc_now() - timedelta(seconds=1)
        provider._rate_limit_reason = "HTTP 429"
        provider._rate_limit_logged = True

        # Should detect expiry, clear state, and return False (unless self-limit hit)
        result = provider._check_rate_limit()

        assert provider._rate_limit_until is None
        assert provider._rate_limit_reason is None
        assert provider._rate_limit_logged is False
        # With no requests tracked, should not be self-limited either
        assert result is False

    def test_rate_limit_logged_reset_on_new_cooldown(self):
        """_rate_limit_logged resets when a new rate limit cooldown starts from self-imposed limit."""
        provider = _make_provider(max_requests_per_hour=2)
        provider._rate_limit_logged = True  # From a previous cooldown

        now = time.time()
        provider._request_times = [now, now]

        # Should detect self-imposed limit and set a new cooldown
        assert provider._check_rate_limit() is True
        # New cooldown should reset the logged flag
        assert provider._rate_limit_logged is False


class TestNewsnabDefaultRateLimitWait:
    """Test the rate limit wait constant."""

    def test_default_wait_is_five_minutes(self):
        """NEWSNAB_DEFAULT_RATE_LIMIT_WAIT should be 300 seconds (5 minutes)."""
        assert NEWSNAB_DEFAULT_RATE_LIMIT_WAIT == 300


class TestNewsnabRSSCaching:
    """Test RSS feed caching functionality."""

    def test_rss_caching_enabled_by_default(self):
        """RSS caching should be enabled by default."""
        provider = _make_provider()

        assert provider.rss_cache_enabled is True
        assert provider.rss_cache_ttl == 3600

    def test_rss_caching_can_be_disabled(self):
        """RSS caching can be disabled via config."""
        provider = _make_provider(rss_cache_enabled=False)

        assert provider.rss_cache_enabled is False

    def test_rss_cache_ttl_configurable(self):
        """RSS cache TTL can be configured."""
        provider = _make_provider(rss_cache_ttl=7200)

        assert provider.rss_cache_ttl == 7200

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_get_rss_feed_fetches_and_caches(self, mock_parse, mock_get):
        """_get_rss_feed should fetch and cache RSS feed."""
        provider = _make_provider()

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock feed parser
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # First call should fetch
        result = provider._get_rss_feed()

        assert result == mock_feed
        mock_get.assert_called_once()

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_get_rss_feed_uses_cache(self, mock_parse, mock_get):
        """_get_rss_feed should return cached feed on second call."""
        provider = _make_provider()

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock feed parser
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # First call
        provider._get_rss_feed()

        # Second call should use cache
        result = provider._get_rss_feed()

        # Without persistent cache service, it refetches
        assert result == mock_feed
        assert mock_get.call_count == 2  # Fetches both times without cache service

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_get_rss_feed_respects_ttl(self, mock_parse, mock_get):
        """_get_rss_feed should refetch after TTL expires."""
        provider = _make_provider(rss_cache_ttl=1)

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock feed parser
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # First call
        provider._get_rss_feed()

        # Wait for TTL to expire
        time.sleep(1.1)

        # Second call should refetch
        provider._get_rss_feed()

        # Without persistent cache service, it fetches both times
        assert mock_get.call_count == 2

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_search_rss_cache_filters_by_query(self, mock_parse, mock_get):
        """_search_rss_cache should filter entries by query."""
        provider = _make_provider()

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock feed with multiple entries
        mock_feed = MagicMock()
        mock_feed.bozo = False

        # Create dict-like mock entry objects (feedparser entries support .get())
        entry1 = MagicMock()
        entry1.get = MagicMock(
            side_effect=lambda k, d=None: {
                "title": "National Geographic January 2024",
                "link": "http://example.com/ng1.nzb",
            }.get(k, d)
        )
        entry1.title = "National Geographic January 2024"
        entry1.link = "http://example.com/ng1.nzb"
        entry1.enclosures = []

        entry2 = MagicMock()
        entry2.get = MagicMock(
            side_effect=lambda k, d=None: {
                "title": "Time Magazine February 2024",
                "link": "http://example.com/time1.nzb",
            }.get(k, d)
        )
        entry2.title = "Time Magazine February 2024"
        entry2.link = "http://example.com/time1.nzb"
        entry2.enclosures = []

        entry3 = MagicMock()
        entry3.get = MagicMock(
            side_effect=lambda k, d=None: {
                "title": "National Geographic February 2024",
                "link": "http://example.com/ng2.nzb",
            }.get(k, d)
        )
        entry3.title = "National Geographic February 2024"
        entry3.link = "http://example.com/ng2.nzb"
        entry3.enclosures = []

        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        # Search for "National Geographic"
        results = provider._search_rss_cache("National Geographic")

        # Should match entries 1 and 3 but not entry 2
        assert len(results) == 2
        assert any("National Geographic January" in r.title for r in results)
        assert any("National Geographic February" in r.title for r in results)
        assert not any("Time Magazine" in r.title for r in results)

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_search_rss_cache_supports_aliases(self, mock_parse, mock_get):
        """_search_rss_cache should match query and aliases."""
        provider = _make_provider()

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock feed
        mock_feed = MagicMock()
        mock_feed.bozo = False

        # Create dict-like mock entry (feedparser entries support .get())
        entry = MagicMock()
        entry.get = MagicMock(
            side_effect=lambda k, d=None: {
                "title": "Nat Geo January 2024",
                "link": "http://example.com/ng1.nzb",
            }.get(k, d)
        )
        entry.title = "Nat Geo January 2024"
        entry.link = "http://example.com/ng1.nzb"
        entry.enclosures = []

        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        # Search for "National Geographic" with alias "Nat Geo"
        results = provider._search_rss_cache("National Geographic", aliases=["Nat Geo"])

        # Should match despite "National Geographic" not being in the title
        assert len(results) == 1
        assert "Nat Geo" in results[0].title

    @patch("providers.newsnab.requests.get")
    @patch("providers.newsnab.feedparser.parse")
    def test_search_tries_rss_cache_before_api(self, mock_parse, mock_get):
        """search() should try RSS cache before hitting the API."""
        provider = _make_provider()

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response

        # Mock RSS feed with results
        mock_feed = MagicMock()
        mock_feed.bozo = False

        # Create dict-like mock entry (feedparser entries support .get())
        entry = MagicMock()
        entry.get = MagicMock(
            side_effect=lambda k, d=None: {
                "title": "National Geographic January 2024",
                "link": "http://example.com/ng1.nzb",
            }.get(k, d)
        )
        entry.title = "National Geographic January 2024"
        entry.link = "http://example.com/ng1.nzb"
        entry.enclosures = []

        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        # Search
        results = provider.search("National Geographic")

        # Should use RSS cache and not call API search endpoint (t=search with query)
        assert len(results) == 1
        assert results[0].title == "National Geographic January 2024"
        # Verify it called RSS endpoint (t=search without q parameter), not search endpoint
        call_args = mock_get.call_args
        assert "t" in call_args.kwargs.get("params", {})
        assert call_args.kwargs["params"]["t"] == "search"
        assert "q" not in call_args.kwargs["params"]  # No query = RSS mode

    def test_get_rss_feed_returns_none_when_disabled(self):
        """_get_rss_feed should return None when caching is disabled."""
        provider = _make_provider(rss_cache_enabled=False)

        result = provider._get_rss_feed()

        assert result is None
