#!/usr/bin/env python3
"""
Test suite for scheduler.ocr_cover_generator module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tasks.ocr_cover_generator import OCRCoverGenerator


@pytest.fixture
def mock_session_factory():
    """Mock session factory"""
    return Mock()


def test_ocr_cover_generator_initialization(mock_session_factory, tmpdir):
    """Test OCRCoverGenerator initialization"""

    generator = OCRCoverGenerator(mock_session_factory, tmpdir)

    assert generator is not None
    assert hasattr(generator, "session_factory")
    assert hasattr(generator, "organize_base_dir")
    assert hasattr(generator, "ocr_covers_dir")
