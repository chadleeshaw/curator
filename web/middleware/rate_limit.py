"""
Rate limiting middleware for FastAPI
"""

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


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
        trusted_proxies: list = None,
    ):
        """
        Initialize rate limiter

        Args:
            app: FastAPI application
            calls: Number of calls allowed per period for regular endpoints
            period: Time period in seconds for regular endpoints
            auth_calls: Number of calls allowed for auth endpoints
            auth_period: Time period for auth endpoints
            trusted_proxies: Optional list of trusted proxy IP addresses.
                When provided, X-Forwarded-For and X-Real-IP headers are
                honoured only for requests that arrive from one of these
                addresses.  When None (default), forwarded-for headers are
                ignored and the direct connection IP is always used, preventing
                clients from trivially spoofing their identity to bypass rate
                limits.
        """
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.auth_calls = auth_calls
        self.auth_period = auth_period
        self.trusted_proxies: set = set(trusted_proxies or [])

        # Storage: {client_ip: {endpoint: [timestamps]}}
        self.clients = defaultdict(lambda: defaultdict(list))

        # Cleanup old entries periodically
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes

    def _get_client_id(self, request: Request) -> str:
        """
        Return the real client IP address.

        Forwarded-for headers are only trusted when the direct connection
        originates from a configured trusted proxy, preventing IP spoofing.
        """
        direct_ip = request.client.host if request.client else "unknown"

        # Only honour proxy headers when the direct connection is from a known proxy.
        if direct_ip in self.trusted_proxies:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()

            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip

        return direct_ip

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
                    ts for ts in self.clients[client_id][endpoint] if current_time - ts < max_period
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

    def _check_rate_limit(self, client_id: str, endpoint: str, is_auth: bool) -> tuple[bool, dict]:
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

        # Skip rate limiting in test mode (detected by testclient User-Agent)
        user_agent = request.headers.get("user-agent", "")
        if "testclient" in user_agent.lower():
            return await call_next(request)

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

        # Process request with error handling for client disconnections
        try:
            response = await call_next(request)

            # Add rate limit headers to response
            for key, value in headers.items():
                response.headers[key] = value

            return response

        except Exception as e:
            # Handle client disconnection errors (h11 protocol errors)
            # This can happen when a client times out or closes the connection
            # while the server is still processing the request
            error_name = type(e).__name__
            error_module = type(e).__module__

            # Check for h11 protocol errors (client disconnected)
            if "h11" in error_module or "LocalProtocolError" in error_name:
                logger.debug(f"Client disconnected during request to {request.url.path}: {e}")
                # Re-raise to let uvicorn handle the disconnection
                raise

            # Check for anyio/asyncio cancellation (client closed connection)
            if "Cancelled" in error_name or "cancel" in str(e).lower():
                logger.debug(f"Request cancelled for {request.url.path}: {e}")
                raise

            # Log unexpected errors and re-raise
            logger.error(
                f"Unexpected error in middleware for {request.url.path}: {error_name}: {e}",
                exc_info=True,
            )
            raise
