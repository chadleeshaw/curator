"""
Rate limiting middleware for FastAPI
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent abuse

    Implements token bucket algorithm for rate limiting
    """

    def __init__(
        self,
        app,
        *,
        calls: int = 10,
        period: int = 60,
        auth_calls: int = 5,
        auth_period: int = 60,
    ):
        """
        Initialize rate limiter

        Args:
            app: FastAPI application
            calls: Number of calls allowed per period for regular endpoints
            period: Time period in seconds for regular endpoints
            auth_calls: Number of calls allowed for auth endpoints
            auth_period: Time period for auth endpoints
        """
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.auth_calls = auth_calls
        self.auth_period = auth_period

        # Storage: {client_ip: {endpoint: [timestamps]}}
        self.clients = defaultdict(lambda: defaultdict(list))

        # Cleanup old entries periodically
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request"""
        # Try to get real IP from headers (for proxy/load balancer scenarios)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"

    def _cleanup_old_entries(self):
        """Remove old entries to prevent memory bloat"""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        for client_id in list(self.clients.keys()):
            for endpoint in list(self.clients[client_id].keys()):
                # Remove timestamps older than max period
                max_period = max(self.period, self.auth_period)
                self.clients[client_id][endpoint] = [
                    ts
                    for ts in self.clients[client_id][endpoint]
                    if current_time - ts < max_period
                ]

                # Remove empty endpoint lists
                if not self.clients[client_id][endpoint]:
                    del self.clients[client_id][endpoint]

            # Remove empty client records
            if not self.clients[client_id]:
                del self.clients[client_id]

        self.last_cleanup = current_time

    def _is_auth_endpoint(self, path: str) -> bool:
        """Check if endpoint is an auth endpoint"""
        auth_paths = [
            "/api/auth/login",
            "/api/auth/setup",
            "/api/auth/change-password",
            "/api/auth/user/update",
        ]
        return any(path.startswith(auth_path) for auth_path in auth_paths)

    def _check_rate_limit(
        self, client_id: str, endpoint: str, is_auth: bool
    ) -> tuple[bool, dict]:
        """
        Check if request exceeds rate limit

        Returns:
            (allowed, headers) - allowed boolean and rate limit headers
        """
        current_time = time.time()
        calls_limit = self.auth_calls if is_auth else self.calls
        period = self.auth_period if is_auth else self.period

        # Get timestamps for this client and endpoint
        timestamps = self.clients[client_id][endpoint]

        # Remove old timestamps
        timestamps = [ts for ts in timestamps if current_time - ts < period]
        self.clients[client_id][endpoint] = timestamps

        # Check if limit exceeded
        if len(timestamps) >= calls_limit:
            # Calculate retry-after
            oldest = min(timestamps)
            retry_after = int(period - (current_time - oldest)) + 1

            headers = {
                "X-RateLimit-Limit": str(calls_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(oldest + period)),
                "Retry-After": str(retry_after),
            }
            return False, headers

        # Add current timestamp
        timestamps.append(current_time)

        # Return success with headers
        headers = {
            "X-RateLimit-Limit": str(calls_limit),
            "X-RateLimit-Remaining": str(calls_limit - len(timestamps)),
            "X-RateLimit-Reset": str(int(current_time + period)),
        }
        return True, headers

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting"""

        # Skip rate limiting for certain paths
        skip_paths = [
            "/api/health",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json",
            "/static",
            "/favicon.ico",
        ]

        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)

        # Periodic cleanup
        self._cleanup_old_entries()

        # Get client ID and endpoint
        client_id = self._get_client_id(request)
        endpoint = request.url.path
        is_auth = self._is_auth_endpoint(endpoint)

        # Check rate limit
        allowed, headers = self._check_rate_limit(client_id, endpoint, is_auth)

        if not allowed:
            # Rate limit exceeded
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "details": {
                        "limit": int(headers["X-RateLimit-Limit"]),
                        "retry_after": int(headers["Retry-After"]),
                    },
                },
                headers=headers,
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response
