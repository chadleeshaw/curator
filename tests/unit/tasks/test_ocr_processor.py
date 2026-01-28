#!/usr/bin/env python3
"""
Test suite for scheduler.ocr_processor module
"""

import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tasks.ocr_processor import OCRProcessor


@pytest.fixture
def mock_session_factory():
    """Mock session factory"""
    return Mock()


def test_ocr_processor_initialization(mock_session_factory):
    """Test OCRProcessor initialization"""

    processor = OCRProcessor(mock_session_factory)

    assert processor is not None
    assert hasattr(processor, "session_factory")
