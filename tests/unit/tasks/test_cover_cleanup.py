#!/usr/bin/env python3
"""
Test suite for scheduler.cover_cleanup module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tasks.cover_cleanup import CoverCleanup


def test_cover_cleanup_initialization():
    """Test CoverCleanup initialization"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanup(mock_session_factory, tmpdir, mock_file_importer)

        assert task is not None


def test_cleanup_task_has_run_method():
    """Test CoverCleanup has run method"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanup(mock_session_factory, tmpdir, mock_file_importer)

        # Should have async run method
        assert hasattr(task, "run")


def test_cleanup_task_attributes():
    """Test CoverCleanup has expected attributes"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanup(mock_session_factory, tmpdir, mock_file_importer)

        assert hasattr(task, "session_factory")
        assert hasattr(task, "library_base_dir")
        assert hasattr(task, "file_importer")


def test_task_has_run_method():
    """Test that CoverCleanup has async run method"""
    import inspect

    assert hasattr(CoverCleanup, "run")
    assert inspect.iscoroutinefunction(CoverCleanup.run)
