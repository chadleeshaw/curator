"""
Middleware for the Curator web application
"""

from web.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
