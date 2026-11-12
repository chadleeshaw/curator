#!/usr/bin/env python3
"""
Test suite for scheduler.ocr_processor module
"""

import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from schedulers.ocr_processor import OCRProcessor


@pytest.fixture
def mock_session_factory():
    """Mock session factory"""
    return Mock()


def test_ocr_processor_initialization(mock_session_factory):
    """Test OCRProcessor initialization"""

    processor = OCRProcessor(mock_session_factory)

    assert processor is not None
    assert hasattr(processor, "session_factory")


def test_processor_uses_the_ocr_retry_limit(mock_session_factory):
    """Image timeouts use the OCR limit, not the single download attempt."""
    from core.constants.ocr import MAX_OCR_RETRIES

    processor = OCRProcessor(mock_session_factory)
    captured = {}

    def process_queue(db, batch_size=1, max_retries=1):
        captured["max_retries"] = max_retries
        return {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    processor.ocr_service.process_queue = process_queue
    session = Mock()
    processor.session_factory = Mock(return_value=session)

    processor._process_sync()

    assert captured["max_retries"] == MAX_OCR_RETRIES
    assert MAX_OCR_RETRIES > 1
    session.close.assert_called_once()
