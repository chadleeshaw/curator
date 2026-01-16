#!/usr/bin/env python3
"""
Test suite for web.app module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from web.app import app


def test_app_exists():
    """Test FastAPI application exists"""
    assert app is not None

    assert app is not None


def test_app_has_routers():
    """Test that app includes routers"""
    # Should have routes registered
    assert hasattr(app, "routes")
    assert len(app.routes) > 0


def test_app_middleware():
    """Test that app has middleware stack"""
    # FastAPI apps have middleware_stack
    assert hasattr(app, "middleware_stack") or hasattr(app, "middleware")


def test_app_openapi_schema():
    """Test that app can generate OpenAPI schema"""
    # Should be able to get OpenAPI schema
    schema = app.openapi()
    assert schema is not None
    assert isinstance(schema, dict)
    assert "openapi" in schema or "info" in schema
