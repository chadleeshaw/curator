#!/usr/bin/env python3
"""
Test suite for web.docs module
"""


# Path setup handled by conftest.py

from web.docs import OPENAPI_METADATA, OPENAPI_TAGS


def test_openapi_metadata():
    """Test OPENAPI_METADATA structure"""
    docs = OPENAPI_METADATA

    assert docs is not None
    assert isinstance(docs, dict)

    # Should have standard OpenAPI fields
    expected_keys = ["title", "description", "version"]
    has_key = any(key in docs for key in expected_keys)
    assert has_key, f"Documentation should contain at least one of: {expected_keys}"


def test_openapi_tags_exists():
    """Test OPENAPI_TAGS is defined"""
    # Should be a list of tag definitions
    assert OPENAPI_TAGS is not None
    assert isinstance(OPENAPI_TAGS, list)
