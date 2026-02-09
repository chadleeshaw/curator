"""
Tests for Newsnab provider rate limiting functionality.

Test Coverage:
- is_rate_limited property (server-imposed and self-imposed)
- _rate_limit_logged flag to prevent log spam
- Cooldown expiry and state cleanup in _check_rate_limit
- NEWSNAB_DEFAULT_RATE_LIMIT_WAIT constant value
"""

import time
from datetime import datetime, timedelta

import pytest

from core.constants.providers import NEWSNAB_DEFAULT_RATE_LIMIT_WAIT
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
        provider._rate_limit_until = datetime.now() + timedelta(seconds=300)
        provider._rate_limit_reason = "HTTP 429 Too Many Requests"

        assert provider.is_rate_limited

    def test_not_rate_limited_after_cooldown_expires(self):
        """is_rate_limited returns False after cooldown period passes."""
        provider = _make_provider()
        provider._rate_limit_until = datetime.now() - timedelta(seconds=1)
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
        provider._rate_limit_until = datetime.now() + timedelta(seconds=300)
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
        provider._rate_limit_until = datetime.now() - timedelta(seconds=1)
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
