"""
Unit tests for core.utils.error_handling decorators
"""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.utils.error_handling import handle_api_errors


class TestHandleApiErrors:
    """Tests for handle_api_errors decorator"""

    def test_async_function_success(self):
        """Test decorator on successful async function"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        async def test_func():
            return {"result": "success"}

        # Execute
        import asyncio

        result = asyncio.run(test_func())

        # Verify
        assert result == {"result": "success"}
        logger.error.assert_not_called()

    def test_async_function_with_args(self):
        """Test decorator preserves function arguments"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        async def test_func(arg1, arg2, kwarg1=None):
            return {"arg1": arg1, "arg2": arg2, "kwarg1": kwarg1}

        # Execute
        import asyncio

        result = asyncio.run(test_func("value1", "value2", kwarg1="kwvalue"))

        # Verify
        assert result == {"arg1": "value1", "arg2": "value2", "kwarg1": "kwvalue"}

    def test_async_function_http_exception_reraised(self):
        """Test that HTTPException is re-raised without modification"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        async def test_func():
            raise HTTPException(status_code=404, detail="Not found")

        # Execute and verify exception is re-raised
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_func())

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"
        # Logger should not be called for HTTPException
        logger.error.assert_not_called()

    def test_async_function_generic_exception_converted(self):
        """Test that generic exceptions are logged and converted to HTTPException"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        async def test_func():
            raise ValueError("Something went wrong")

        # Execute
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_func())

        # Verify exception is converted to HTTPException
        assert exc_info.value.status_code == 500
        assert "Something went wrong" in str(exc_info.value.detail)

        # Verify error was logged
        logger.error.assert_called_once()
        call_args = logger.error.call_args
        assert "Test operation error" in call_args[0][0]
        assert call_args[1]["exc_info"] is True

    def test_sync_function_success(self):
        """Test decorator on successful sync function"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        def test_func():
            return {"result": "success"}

        # Execute
        result = test_func()

        # Verify
        assert result == {"result": "success"}
        logger.error.assert_not_called()

    def test_sync_function_http_exception_reraised(self):
        """Test that HTTPException is re-raised in sync function"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        def test_func():
            raise HTTPException(status_code=403, detail="Forbidden")

        # Execute and verify
        with pytest.raises(HTTPException) as exc_info:
            test_func()

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden"
        logger.error.assert_not_called()

    def test_sync_function_generic_exception_converted(self):
        """Test that generic exceptions are converted in sync function"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        def test_func():
            raise RuntimeError("Sync error")

        # Execute
        with pytest.raises(HTTPException) as exc_info:
            test_func()

        # Verify
        assert exc_info.value.status_code == 500
        assert "Sync error" in str(exc_info.value.detail)
        logger.error.assert_called_once()

    def test_preserves_function_name(self):
        """Test that decorator preserves function metadata"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Test operation", logger)
        async def my_test_function():
            """This is a docstring"""
            pass

        # Verify metadata is preserved
        assert my_test_function.__name__ == "my_test_function"
        assert my_test_function.__doc__ == "This is a docstring"

    def test_multiple_decorators(self):
        """Test that decorator works with multiple function calls"""
        logger = Mock(spec=logging.Logger)
        call_count = 0

        @handle_api_errors("Test operation", logger)
        async def test_func():
            nonlocal call_count
            call_count += 1
            return call_count

        # Execute multiple times
        import asyncio

        result1 = asyncio.run(test_func())
        result2 = asyncio.run(test_func())

        # Verify
        assert result1 == 1
        assert result2 == 2
        logger.error.assert_not_called()

    def test_custom_operation_name_in_log(self):
        """Test that custom operation name appears in log messages"""
        logger = Mock(spec=logging.Logger)

        @handle_api_errors("Delete magazine", logger)
        async def test_func():
            raise ValueError("Test error")

        # Execute
        import asyncio

        with pytest.raises(HTTPException):
            asyncio.run(test_func())

        # Verify custom operation name is in log
        logger.error.assert_called_once()
        call_args = logger.error.call_args
        assert "Delete magazine error" in call_args[0][0]
