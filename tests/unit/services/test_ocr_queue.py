#!/usr/bin/env python3
"""
Test suite for services.ocr_queue module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from services.ocr_queue import OCRQueueService


def test_ocr_queue_initialization():
    """Test OCRQueueService initialization"""
    # OCRQueueService takes max_workers parameter
    queue = OCRQueueService(max_workers=2)

    assert queue is not None


def test_ocr_queue_service_has_methods():
    """Test OCRQueueService has expected methods"""
    queue = OCRQueueService()

    # Should have queue management methods (static methods)
    assert hasattr(OCRQueueService, "queue_ocr_job")
    assert hasattr(queue, "process_queue")
