"""
Unit tests for core.utils.db database utilities
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.utils.db import with_db_session, mark_json_modified, get_db_session


class TestWithDbSession:
    """Tests for with_db_session async utility"""

    @pytest.mark.asyncio
    async def test_with_db_session_success(self):
        """Test successful database operation with session cleanup"""
        # Mock session factory and session
        mock_session = Mock()
        mock_session_factory = Mock(return_value=mock_session)

        # Define a simple operation
        def operation(db):
            return {"result": "success"}

        # Execute
        result = await with_db_session(mock_session_factory, operation)

        # Verify
        assert result == {"result": "success"}
        mock_session_factory.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_db_session_exception(self):
        """Test that session is closed even when operation raises exception"""
        # Mock session factory and session
        mock_session = Mock()
        mock_session_factory = Mock(return_value=mock_session)

        # Define operation that raises exception
        def failing_operation(db):
            raise ValueError("Database error")

        # Execute and expect exception
        with pytest.raises(ValueError, match="Database error"):
            await with_db_session(mock_session_factory, failing_operation)

        # Verify session was still closed
        mock_session_factory.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_db_session_receives_session(self):
        """Test that operation receives the session as argument"""
        # Mock session
        mock_session = Mock()
        mock_session.query = Mock(return_value="query_result")
        mock_session_factory = Mock(return_value=mock_session)

        # Define operation that uses the session
        def operation(db):
            return db.query()

        # Execute
        result = await with_db_session(mock_session_factory, operation)

        # Verify
        assert result == "query_result"
        mock_session.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_db_session_no_auto_commit(self):
        """Test that session is NOT automatically committed"""
        # Mock session
        mock_session = Mock()
        mock_session_factory = Mock(return_value=mock_session)

        # Define operation
        def operation(db):
            return "result"

        # Execute
        await with_db_session(mock_session_factory, operation)

        # Verify commit was NOT called (user must call db.commit() explicitly)
        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()


class TestMarkJsonModified:
    """Tests for mark_json_modified utility"""

    @patch("core.utils.db.flag_modified")
    def test_mark_single_field(self, mock_flag_modified):
        """Test marking a single JSON field as modified"""
        # Create mock object
        mock_obj = Mock()

        # Execute
        mark_json_modified(mock_obj, "extra_metadata")

        # Verify
        mock_flag_modified.assert_called_once_with(mock_obj, "extra_metadata")

    @patch("core.utils.db.flag_modified")
    def test_mark_multiple_fields(self, mock_flag_modified):
        """Test marking multiple JSON fields as modified"""
        # Create mock object
        mock_obj = Mock()

        # Execute
        mark_json_modified(
            mock_obj, "extra_metadata", "derived_metadata", "custom_data"
        )

        # Verify all fields were marked
        assert mock_flag_modified.call_count == 3
        mock_flag_modified.assert_any_call(mock_obj, "extra_metadata")
        mock_flag_modified.assert_any_call(mock_obj, "derived_metadata")
        mock_flag_modified.assert_any_call(mock_obj, "custom_data")

    @patch("core.utils.db.flag_modified")
    def test_mark_no_fields(self, mock_flag_modified):
        """Test calling with no field names (should do nothing)"""
        # Create mock object
        mock_obj = Mock()

        # Execute
        mark_json_modified(mock_obj)

        # Verify no calls were made
        mock_flag_modified.assert_not_called()


class TestGetDbSession:
    """Tests for get_db_session context manager"""

    def test_context_manager_success(self):
        """Test successful database operation with automatic commit"""
        # Mock session
        mock_session = Mock()
        mock_session_factory = Mock(return_value=mock_session)

        # Use context manager
        with get_db_session(mock_session_factory) as session:
            assert session == mock_session

        # Verify commit and close were called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    def test_context_manager_exception(self):
        """Test that exception triggers rollback and still closes session"""
        # Mock session
        mock_session = Mock()
        mock_session_factory = Mock(return_value=mock_session)

        # Use context manager with exception
        with pytest.raises(ValueError, match="Test error"):
            with get_db_session(mock_session_factory) as session:
                raise ValueError("Test error")

        # Verify rollback and close were called, but not commit
        mock_session.commit.assert_not_called()
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    def test_context_manager_commit_failure(self):
        """Test that commit failure triggers rollback and closes session"""
        # Mock session with failing commit
        mock_session = Mock()
        mock_session.commit.side_effect = Exception("Commit failed")
        mock_session_factory = Mock(return_value=mock_session)

        # Use context manager
        with pytest.raises(Exception, match="Commit failed"):
            with get_db_session(mock_session_factory):
                pass

        # Verify rollback and close were called
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
