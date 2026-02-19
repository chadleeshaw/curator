"""
Rate limiter for provider API calls.

Implements a sliding window rate limiter to prevent exceeding
provider API rate limits, particularly for NZB file fetches.
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Optional

from core.constants.cache import DEFAULT_MAX_NZB_FETCHES_PER_HOUR, NZB_RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger(__name__)


class ProviderRateLimiter:
    """
    Sliding window rate limiter for provider API calls.

    Tracks request timestamps per provider and blocks requests
    that would exceed the configured rate limit.

    Thread-safe for use in multi-threaded environments.

    Args:
        max_requests: Maximum requests allowed per window (default from config)
        window_seconds: Time window duration in seconds (default 1 hour)
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_NZB_FETCHES_PER_HOUR,
        window_seconds: int = NZB_RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, provider_key: str = "default") -> bool:
        """
        Check if a request is allowed under the rate limit.

        Does NOT consume a request slot. Use `acquire()` to check and consume.

        Args:
            provider_key: Identifier for the provider (e.g., provider name or URL domain)

        Returns:
            True if a request would be allowed, False if rate limited
        """
        if self.max_requests <= 0:
            return True  # Rate limiting disabled

        with self._lock:
            self._cleanup_expired(provider_key)
            return len(self._timestamps[provider_key]) < self.max_requests

    def acquire(self, provider_key: str = "default") -> bool:
        """
        Attempt to acquire a rate limit slot.

        If allowed, records the request timestamp and returns True.
        If rate limited, returns False without recording.

        Args:
            provider_key: Identifier for the provider

        Returns:
            True if request was allowed and recorded, False if rate limited
        """
        if self.max_requests <= 0:
            return True  # Rate limiting disabled

        with self._lock:
            self._cleanup_expired(provider_key)
            if len(self._timestamps[provider_key]) >= self.max_requests:
                remaining = self._time_until_next_slot(provider_key)
                logger.warning(
                    f"[RateLimiter] Rate limit reached for '{provider_key}': "
                    f"{self.max_requests}/{self.window_seconds}s. "
                    f"Next slot in {remaining:.0f}s"
                )
                return False

            self._timestamps[provider_key].append(time.monotonic())
            return True

    def remaining(self, provider_key: str = "default") -> int:
        """
        Get the number of remaining requests allowed in the current window.

        Args:
            provider_key: Identifier for the provider

        Returns:
            Number of requests remaining before rate limit is hit
        """
        if self.max_requests <= 0:
            return float("inf")

        with self._lock:
            self._cleanup_expired(provider_key)
            return max(0, self.max_requests - len(self._timestamps[provider_key]))

    def wait_time(self, provider_key: str = "default") -> float:
        """
        Get seconds until the next request slot becomes available.

        Args:
            provider_key: Identifier for the provider

        Returns:
            Seconds to wait (0.0 if a slot is available now)
        """
        if self.max_requests <= 0:
            return 0.0

        with self._lock:
            self._cleanup_expired(provider_key)
            if len(self._timestamps[provider_key]) < self.max_requests:
                return 0.0
            return self._time_until_next_slot(provider_key)

    def get_stats(self, provider_key: Optional[str] = None) -> dict:
        """
        Get rate limiter statistics.

        Args:
            provider_key: Specific provider to get stats for, or None for all

        Returns:
            Dictionary with rate limit statistics
        """
        with self._lock:
            if provider_key:
                self._cleanup_expired(provider_key)
                return {
                    "provider": provider_key,
                    "requests_in_window": len(self._timestamps[provider_key]),
                    "max_requests": self.max_requests,
                    "remaining": max(0, self.max_requests - len(self._timestamps[provider_key])),
                    "window_seconds": self.window_seconds,
                }

            stats = {}
            for key in list(self._timestamps.keys()):
                self._cleanup_expired(key)
                stats[key] = {
                    "requests_in_window": len(self._timestamps[key]),
                    "max_requests": self.max_requests,
                    "remaining": max(0, self.max_requests - len(self._timestamps[key])),
                }
            return stats

    def _cleanup_expired(self, provider_key: str) -> None:
        """Remove timestamps outside the current window. Must be called with lock held."""
        cutoff = time.monotonic() - self.window_seconds
        self._timestamps[provider_key] = [ts for ts in self._timestamps[provider_key] if ts > cutoff]

    def _time_until_next_slot(self, provider_key: str) -> float:
        """Calculate time until oldest timestamp expires. Must be called with lock held."""
        if not self._timestamps[provider_key]:
            return 0.0
        oldest = self._timestamps[provider_key][0]
        expires_at = oldest + self.window_seconds
        return max(0.0, expires_at - time.monotonic())
