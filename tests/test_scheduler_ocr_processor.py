#!/usr/bin/env python3
"""
Test suite for scheduler.ocr_processor module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.ocr_processor import OCRProcessorTask


def test_ocr_processor_initialization():
    """Test OCRProcessorTask initialization"""
    mock_session_factory = Mock()
    processor = OCRProcessorTask(mock_session_factory)

    assert processor is not None
    assert hasattr(processor, 'session_factory')
