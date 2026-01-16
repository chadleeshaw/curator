#!/usr/bin/env python3
"""
Test suite for core.response_models module
"""

import sys
from pathlib import Path

# Path setup handled by conftest.py

from services.response_models import ErrorDetail, OperationResult, ErrorCodes


def test_error_detail():
    """Test ErrorDetail model"""
    error = ErrorDetail(code="DUPLICATE", message="Duplicate entry", retryable=False)

    assert error.code == "DUPLICATE"
    assert error.message == "Duplicate entry"
    assert error.retryable is False


def test_error_detail_to_dict():
    """Test ErrorDetail to_dict method"""
    error = ErrorDetail(code="ERR_001", message="Test error")
    error_dict = error.to_dict()

    assert error_dict["code"] == "ERR_001"
    assert error_dict["message"] == "Test error"
    assert "retryable" in error_dict


def test_operation_result_success():
    """Test OperationResult with success"""
    result = OperationResult(success=True)

    assert result.success is True
    assert isinstance(result.data, dict)


def test_operation_result_with_error():
    """Test OperationResult with error"""
    result = OperationResult(success=True)
    result.add_error(code="TIMEOUT", message="Request timeout")

    assert result.success is False  # Should be set to False when error is added
    assert len(result.errors) == 1
