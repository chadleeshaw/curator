"""
Test suite for ProviderRateLimiter utility.

Tests sliding window rate limiting behavior for NZB fetch operations.
"""

import sys
import time

sys.path.insert(0, ".")

from core.utils.rate_limiter import ProviderRateLimiter


class TestProviderRateLimiter:
    """Test ProviderRateLimiter sliding window rate limiter."""

    def test_basic_allow(self):
        """Test that requests are allowed under the limit."""
        limiter = ProviderRateLimiter(max_requests=5, window_seconds=60)
        assert limiter.acquire("test") is True
        assert limiter.remaining("test") == 4

    def test_rate_limit_reached(self):
        """Test that requests are blocked when limit is reached."""
        limiter = ProviderRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.acquire("test") is True
        assert limiter.acquire("test") is True
        assert limiter.acquire("test") is True
        # Fourth request should be denied
        assert limiter.acquire("test") is False
        assert limiter.remaining("test") == 0

    def test_is_allowed_does_not_consume(self):
        """Test that is_allowed() checks without consuming a slot."""
        limiter = ProviderRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("test") is True
        assert limiter.is_allowed("test") is True  # Still allowed
        assert limiter.remaining("test") == 1  # Nothing consumed

    def test_separate_provider_keys(self):
        """Test that different provider keys have independent limits."""
        limiter = ProviderRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.acquire("provider_a") is True
        assert limiter.acquire("provider_a") is True
        assert limiter.acquire("provider_a") is False  # A is limited

        # B should still have slots
        assert limiter.acquire("provider_b") is True
        assert limiter.remaining("provider_b") == 1

    def test_disabled_rate_limiting(self):
        """Test that max_requests=0 disables rate limiting."""
        limiter = ProviderRateLimiter(max_requests=0, window_seconds=60)
        for _ in range(100):
            assert limiter.acquire("test") is True
        assert limiter.is_allowed("test") is True

    def test_window_expiry(self):
        """Test that old timestamps expire and free up slots."""
        limiter = ProviderRateLimiter(max_requests=2, window_seconds=0.1)  # 100ms window
        assert limiter.acquire("test") is True
        assert limiter.acquire("test") is True
        assert limiter.acquire("test") is False

        # Wait for window to expire
        time.sleep(0.15)
        assert limiter.acquire("test") is True
        assert limiter.remaining("test") == 1

    def test_wait_time_zero_when_available(self):
        """Test wait_time returns 0.0 when slots available."""
        limiter = ProviderRateLimiter(max_requests=5, window_seconds=60)
        assert limiter.wait_time("test") == 0.0

    def test_wait_time_positive_when_limited(self):
        """Test wait_time returns positive value when rate limited."""
        limiter = ProviderRateLimiter(max_requests=1, window_seconds=60)
        limiter.acquire("test")
        wait = limiter.wait_time("test")
        assert wait > 0
        assert wait <= 60

    def test_wait_time_disabled(self):
        """Test wait_time returns 0.0 when rate limiting disabled."""
        limiter = ProviderRateLimiter(max_requests=0, window_seconds=60)
        assert limiter.wait_time("test") == 0.0

    def test_get_stats_single_provider(self):
        """Test stats for a single provider."""
        limiter = ProviderRateLimiter(max_requests=10, window_seconds=60)
        limiter.acquire("test")
        limiter.acquire("test")

        stats = limiter.get_stats("test")
        assert stats["provider"] == "test"
        assert stats["requests_in_window"] == 2
        assert stats["max_requests"] == 10
        assert stats["remaining"] == 8

    def test_get_stats_all_providers(self):
        """Test stats for all providers."""
        limiter = ProviderRateLimiter(max_requests=10, window_seconds=60)
        limiter.acquire("a")
        limiter.acquire("b")
        limiter.acquire("b")

        stats = limiter.get_stats()
        assert "a" in stats
        assert "b" in stats
        assert stats["a"]["requests_in_window"] == 1
        assert stats["b"]["requests_in_window"] == 2

    def test_remaining_with_disabled(self):
        """Test remaining returns infinity when disabled."""
        limiter = ProviderRateLimiter(max_requests=0, window_seconds=60)
        assert limiter.remaining("test") == float("inf")
