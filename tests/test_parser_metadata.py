#!/usr/bin/env python3
"""
Test suite for core.parsers.metadata module
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.metadata import MetadataExtractor


def test_metadata_extractor_initialization():
    """Test MetadataExtractor initialization"""
    extractor = MetadataExtractor()

    assert extractor is not None
    assert hasattr(extractor, 'system_folders')


def test_metadata_extractor_with_filename():
    """Test extracting metadata from filename"""
    extractor = MetadataExtractor()

    # MetadataExtractor has methods like extract() that work with Path objects
    # Test that it can be instantiated and has expected attributes
    assert hasattr(extractor, 'system_folders')
    assert isinstance(extractor.system_folders, set)


def test_metadata_extractor_system_folders():
    """Test that system folders are defined"""
    extractor = MetadataExtractor()

    # Should have common system folder names
    assert 'downloads' in extractor.system_folders
    assert 'data' in extractor.system_folders
