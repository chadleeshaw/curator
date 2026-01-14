#!/usr/bin/env python3
"""
Test suite for core.db_utils module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db_utils import get_db_session


def test_get_db_session_context_manager():
    """Test get_db_session as context manager"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_session_factory.return_value = mock_session

    with get_db_session(mock_session_factory) as session:
        assert session == mock_session

    # Session should be closed after context
    mock_session.close.assert_called_once()


def test_get_db_session_commit():
    """Test that get_db_session commits on successful exit"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_session_factory.return_value = mock_session

    with get_db_session(mock_session_factory) as session:
        session.add(Mock())

    # Should commit on successful exit
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_get_db_session_rollback_on_exception():
    """Test that get_db_session rolls back on exception"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_session_factory.return_value = mock_session

    try:
        with get_db_session(mock_session_factory) as session:
            raise ValueError("Test error")
    except ValueError:
        pass

    # Should rollback on exception
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
    # Should not commit
    mock_session.commit.assert_not_called()


def test_get_db_session_multiple_operations():
    """Test multiple database operations in one session"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_session_factory.return_value = mock_session

    with get_db_session(mock_session_factory) as session:
        session.add(Mock())
        session.add(Mock())
        session.query(Mock()).filter_by(id=1).first()

    # All operations should use the same session
    assert session.add.call_count == 2
    assert session.query.called
    mock_session.commit.assert_called_once()
