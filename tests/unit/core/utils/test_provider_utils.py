#!/usr/bin/env python3
"""
Test suite for core.provider_utils module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from core.utils.provider import handle_provider_errors


def test_handle_provider_errors_decorator():
    """Test handle_provider_errors decorator exists"""
    # handle_provider_errors is a decorator for class methods
    assert callable(handle_provider_errors)


def test_handle_provider_errors_is_decorator():
    """Test that handle_provider_errors is a valid decorator"""
    # It should be a function that returns a function
    import inspect

    assert inspect.isfunction(handle_provider_errors)
