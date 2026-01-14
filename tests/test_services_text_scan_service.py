#!/usr/bin/env python3
"""
Test suite for services.text_scan_service module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.text_scan_service import TextScanService


def test_text_scan_service_initialization():
    """Test TextScanService initialization"""
    service = TextScanService()

    assert service is not None


def test_text_scan_service_methods():
    """Test TextScanService has static methods"""
    # All methods are static methods
    assert hasattr(TextScanService, 'extract_text_from_pdf')
    assert hasattr(TextScanService, 'extract_text_from_epub')
    assert hasattr(TextScanService, 'scan_document')
    assert hasattr(TextScanService, 'is_pdf_available')
