#!/usr/bin/env python3
"""
Test suite for scheduler.cover_cleanup module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.cover_cleanup import CoverCleanupTask


def test_cover_cleanup_initialization():
    """Test CoverCleanupTask initialization"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanupTask(mock_session_factory, tmpdir, mock_file_importer)

        assert task is not None


def test_cleanup_task_has_run_method():
    """Test CoverCleanupTask has run method"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanupTask(mock_session_factory, tmpdir, mock_file_importer)

        # Should have async run method
        assert hasattr(task, 'run')


def test_cleanup_task_attributes():
    """Test CoverCleanupTask has expected attributes"""
    import tempfile

    mock_session_factory = Mock()
    mock_file_importer = Mock()
    with tempfile.TemporaryDirectory() as tmpdir:
        task = CoverCleanupTask(mock_session_factory, tmpdir, mock_file_importer)

        assert hasattr(task, 'session_factory')
        assert hasattr(task, 'organize_base_dir')
        assert hasattr(task, 'file_importer')


def test_task_has_run_method():
    """Test that CoverCleanupTask has async run method"""
    import inspect
    assert hasattr(CoverCleanupTask, 'run')
    assert inspect.iscoroutinefunction(CoverCleanupTask.run)
