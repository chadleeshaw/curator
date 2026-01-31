#!/usr/bin/env python3
"""
Test suite for web.middleware.auth module
"""

from unittest.mock import Mock
import pytest

# Path setup handled by conftest.py

from web.middleware.auth import AuthMiddleware
from fastapi import HTTPException


def test_auth_middleware_initialization():
    """Test AuthMiddleware initialization"""
    mock_auth_manager = Mock()
    middleware = AuthMiddleware(mock_auth_manager)

    assert middleware is not None
    assert middleware.auth_manager is mock_auth_manager


@pytest.mark.asyncio
async def test_verify_token_with_valid_jwt():
    """Test token verification with valid JWT"""
    mock_auth_manager = Mock()
    mock_auth_manager.verify_token.return_value = (True, "testuser")

    middleware = AuthMiddleware(mock_auth_manager)

    username = await middleware.verify_token("Bearer valid.jwt.token")

    assert username == "testuser"


@pytest.mark.asyncio
async def test_verify_token_missing():
    """Test that missing token raises HTTPException"""
    mock_auth_manager = Mock()
    middleware = AuthMiddleware(mock_auth_manager)

    with pytest.raises(HTTPException) as exc_info:
        await middleware.verify_token(None)

    assert exc_info.value.status_code == 401
    assert "Missing authentication token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_token_with_api_token():
    """Test token verification with API token fallback"""
    mock_auth_manager = Mock()
    mock_auth_manager.verify_token.return_value = (False, None)  # JWT fails
    mock_auth_manager.verify_api_token.return_value = (True, "apiuser")  # API token succeeds

    middleware = AuthMiddleware(mock_auth_manager)

    username = await middleware.verify_token("Bearer api.token.here")

    assert username == "apiuser"
