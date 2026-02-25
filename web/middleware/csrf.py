"""
CSRF protection middleware using the double-submit cookie pattern.

How it works:
  1. On every response, the server sets a non-HttpOnly cookie named ``csrf_token``
     with a random token value (refreshed every 24 hours via a per-session token).
  2. For state-changing requests (POST, PUT, PATCH, DELETE), the client must echo
     that token back in the ``X-CSRF-Token`` request header.
  3. The middleware compares the header value to the cookie value and rejects the
     request with 403 if they don't match.

JavaScript reads the cookie and includes it as a header:
    const csrfToken = document.cookie
        .split('; ')
        .find(r => r.startsWith('csrf_token='))
        ?.split('=')[1];
    headers['X-CSRF-Token'] = csrfToken;

Paths excluded from CSRF checks:
  - GET / HEAD / OPTIONS requests (safe methods)
  - /api/auth/login  (before token exists)
  - /api/auth/setup  (first-run setup)
  - Static files
"""

import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_TOKEN_BYTES = 32

# Methods that do not change server state — no CSRF check needed.
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# Paths that are exempt from CSRF protection (auth bootstrap endpoints).
_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/setup",
    "/api/auth/status",
    "/api/auth/login-mode",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie CSRF middleware.

    Attach after CORSMiddleware in the middleware stack so that CORS preflight
    OPTIONS requests are handled before CSRF checks run.

    Args:
        secure: Set the CSRF cookie's Secure flag.  Pass ``True`` when the
                application is served over HTTPS so the cookie is only sent
                over encrypted connections.  Defaults to ``False`` for local
                HTTP deployments.
    """

    def __init__(self, app, *, secure: bool = False):
        super().__init__(app)
        self._secure = secure

    async def dispatch(self, request: Request, call_next) -> Response:
        # Retrieve or generate the CSRF token from the incoming cookie.
        token = request.cookies.get(CSRF_COOKIE_NAME)
        if not token:
            token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)

        # Enforce CSRF on state-changing requests to API endpoints.
        if request.method not in _SAFE_METHODS and request.url.path.startswith("/api"):
            if request.url.path not in _EXEMPT_PATHS:
                request_token = request.headers.get(CSRF_HEADER_NAME, "")
                if not secrets.compare_digest(request_token, token):
                    logger.warning(
                        f"CSRF check failed: {request.method} {request.url.path} "
                        f"(header={'<missing>' if not request_token else '<present>'})"
                    )
                    return Response(
                        content='{"detail":"CSRF token missing or invalid"}',
                        status_code=403,
                        media_type="application/json",
                    )

        response = await call_next(request)

        # Refresh the cookie on every response so it stays alive.
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            httponly=False,  # Must be readable by JavaScript
            samesite="strict",
            secure=self._secure,
            path="/",
        )
        return response
