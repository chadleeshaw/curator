#!/usr/bin/env python3
"""
Test suite for scheduler.ocr_cover_generator module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.ocr_cover_generator import OCRCoverGeneratorTask


def test_ocr_cover_generator_initialization():
    """Test OCRCoverGeneratorTask initialization"""
    mock_session_factory = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = OCRCoverGeneratorTask(mock_session_factory, tmpdir)

        assert generator is not None
        assert hasattr(generator, 'session_factory')
        assert hasattr(generator, 'organize_base_dir')
        assert hasattr(generator, 'ocr_covers_dir')
