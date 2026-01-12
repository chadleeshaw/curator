"""
Middleware for the Curator web application
"""

from web.middleware.auth import AuthMiddleware
from web.middleware.rate_limit import RateLimitMiddleware

__all__ = ["AuthMiddleware", "RateLimitMiddleware"]
