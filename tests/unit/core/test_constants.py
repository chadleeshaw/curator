#!/usr/bin/env python3
"""
Test suite for core.constants module
"""


# Path setup handled by conftest.py

from core import constants


def test_ocr_constants_exist():
    """Test that OCR-related constants are defined"""
    assert hasattr(constants, "OCR_RESIZE_WIDTH")
    assert hasattr(constants, "OCR_CONTRAST_ENHANCE")
    assert hasattr(constants, "OCR_DENOISE_H")
    assert hasattr(constants, "OCR_SHARPEN_KERNEL")
    assert hasattr(constants, "MAX_IMAGE_PIXELS")


def test_ocr_numeric_constants():
    """Test OCR numeric constant values"""
    assert isinstance(constants.OCR_RESIZE_WIDTH, int)
    assert constants.OCR_RESIZE_WIDTH > 0

    assert isinstance(constants.OCR_CONTRAST_ENHANCE, float)
    assert constants.OCR_CONTRAST_ENHANCE > 0

    assert isinstance(constants.OCR_DENOISE_H, int)
    assert constants.OCR_DENOISE_H > 0

    assert isinstance(constants.MAX_IMAGE_PIXELS, int)
    assert constants.MAX_IMAGE_PIXELS > 0


def test_ocr_sharpen_kernel():
    """Test OCR sharpening kernel is valid"""
    kernel = constants.OCR_SHARPEN_KERNEL

    assert isinstance(kernel, list)
    assert len(kernel) == 3
    assert all(len(row) == 3 for row in kernel)
    assert all(isinstance(val, int) for row in kernel for val in row)


def test_ocr_disable_env_values():
    """Test OCR disable environment values"""
    disable_values = constants.OCR_DISABLE_ENV_VALUES

    assert isinstance(disable_values, tuple)
    assert "true" in disable_values
    assert "1" in disable_values
    assert "yes" in disable_values


def test_ocr_patterns_exist():
    """Test that OCR pattern constants exist"""
    assert hasattr(constants, "OCR_ISSUE_PATTERNS")
    assert hasattr(constants, "OCR_YEAR_PATTERN")
    assert hasattr(constants, "OCR_VOLUME_PATTERNS")


def test_ocr_issue_patterns():
    """Test OCR issue patterns are valid regex patterns"""
    patterns = constants.OCR_ISSUE_PATTERNS

    assert isinstance(patterns, list)
    assert len(patterns) > 0

    # Test that patterns can be compiled
    import re

    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error:
            assert False, f"Invalid regex pattern: {pattern}"


def test_ocr_year_pattern():
    """Test OCR year pattern"""
    import re

    pattern = constants.OCR_YEAR_PATTERN

    # Should match 4-digit years from 1900-2099
    assert re.search(pattern, "Published in 2026")
    assert re.search(pattern, "Copyright 1999")
    assert not re.search(pattern, "Year 1899")  # Too old
    assert not re.search(pattern, "Year 2100")  # Too far in future


def test_ocr_month_names():
    """Test OCR month names mapping"""
    months = constants.OCR_MONTH_NAMES

    assert isinstance(months, dict)
    # Test English month names
    assert months["JANUARY"] == 1
    assert months["FEBRUARY"] == 2
    assert months["DECEMBER"] == 12
    # Test abbreviated forms
    assert months["JAN"] == 1
    assert months["DEC"] == 12
    # Test multilingual support (German, Spanish, French, etc.)
    assert months["JANUAR"] == 1  # German
    assert months["ENERO"] == 1  # Spanish
    assert months["JANVIER"] == 1  # French
    assert months["DEZEMBRO"] == 12  # Portuguese
    # Should have at least 24 entries (English) plus multilingual
    assert len(months) >= 24


def test_token_expiration():
    """Test authentication token expiration constant"""
    assert hasattr(constants, "TOKEN_EXPIRATION_HOURS")
    assert isinstance(constants.TOKEN_EXPIRATION_HOURS, int)
    assert constants.TOKEN_EXPIRATION_HOURS > 0


def test_ocr_thresholds():
    """Test OCR detection thresholds"""
    assert hasattr(constants, "OCR_TEXT_DETECTION_THRESHOLD")
    assert hasattr(constants, "OCR_TEXT_UNCLIP_RATIO")

    threshold = constants.OCR_TEXT_DETECTION_THRESHOLD
    assert isinstance(threshold, float)
    assert 0 < threshold < 1

    ratio = constants.OCR_TEXT_UNCLIP_RATIO
    assert isinstance(ratio, float)
    assert ratio > 0


def test_volume_patterns():
    """Test volume detection patterns"""
    import re

    patterns = constants.OCR_VOLUME_PATTERNS

    assert isinstance(patterns, list)
    assert len(patterns) > 0

    # Test patterns match expected volume formats
    for pattern in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        assert compiled.search("Volume 5") or compiled.search("Vol. 5") or compiled.search("V. 5")


def test_constants_immutability():
    """Test that key constants are of immutable types"""
    # Numeric constants should be immutable
    assert isinstance(constants.OCR_RESIZE_WIDTH, int)
    assert isinstance(constants.OCR_CONTRAST_ENHANCE, float)

    # String patterns should be strings
    assert isinstance(constants.OCR_YEAR_PATTERN, str)

    # Tuples are immutable
    assert isinstance(constants.OCR_DISABLE_ENV_VALUES, tuple)
