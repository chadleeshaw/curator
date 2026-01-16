#!/usr/bin/env python3
"""
Test suite for web.middleware.rate_limit module
"""

import sys
from pathlib import Path
from unittest.mock import Mock

# Path setup handled by conftest.py

from web.middleware.rate_limit import RateLimitMiddleware


def test_rate_limit_middleware_initialization():
    """Test RateLimitMiddleware initialization"""
    app = Mock()
    middleware = RateLimitMiddleware(app, calls=60, period=60)

    assert middleware is not None
    assert middleware.calls == 60
    assert middleware.period == 60


def test_rate_limit_middleware_with_auth_params():
    """Test RateLimitMiddleware with auth-specific rate limits"""
    app = Mock()
    middleware = RateLimitMiddleware(app, calls=100, period=60, auth_calls=5, auth_period=60)

    assert middleware.calls == 100
    assert middleware.period == 60
    assert middleware.auth_calls == 5
    assert middleware.auth_period == 60


def test_rate_limit_middleware_has_client_storage():
    """Test that middleware has client storage for tracking requests"""
    app = Mock()
    middleware = RateLimitMiddleware(app, calls=10, period=60)

    # Should have clients dict for tracking
    assert hasattr(middleware, "clients")


def test_rate_limit_middleware_default_values():
    """Test RateLimitMiddleware default initialization values"""
    app = Mock()
    middleware = RateLimitMiddleware(app)

    # Check defaults
    assert middleware.calls == 10  # Default value
    assert middleware.period == 60  # Default value
    assert middleware.auth_calls == 5  # Default value
    assert middleware.auth_period == 60  # Default value
