#!/usr/bin/env python3
"""
Test suite for core.auth module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import AuthManager
from models.database import Credentials


def test_auth_manager_initialization():
    """Test AuthManager initialization"""
    mock_session_factory = Mock()
    jwt_secret = "test-secret-key"

    auth_manager = AuthManager(mock_session_factory, jwt_secret)

    assert auth_manager.session_factory == mock_session_factory
    assert auth_manager.jwt_secret == jwt_secret


def test_credentials_exist_false():
    """Test credentials_exist when no credentials"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_query = Mock()
    mock_query.count.return_value = 0
    mock_session.query.return_value = mock_query
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)

    with patch('core.auth.get_db_session') as mock_get_session:
        mock_get_session.return_value = mock_session

        auth_manager = AuthManager(mock_session_factory, "secret")
        result = auth_manager.credentials_exist()

        assert result is False


def test_credentials_exist_true():
    """Test credentials_exist when credentials exist"""
    mock_session_factory = Mock()
    mock_session = Mock()
    mock_query = Mock()
    mock_query.count.return_value = 1
    mock_session.query.return_value = mock_query
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)

    with patch('core.auth.get_db_session') as mock_get_session:
        mock_get_session.return_value = mock_session

        auth_manager = AuthManager(mock_session_factory, "secret")
        result = auth_manager.credentials_exist()

        assert result is True


def test_create_credentials_success():
    """Test creating new credentials"""
    mock_session = Mock()
    mock_session.query.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.create_credentials("testuser", "testpass")

    assert success is True
    assert "successfully" in message.lower()
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_create_credentials_already_exist():
    """Test creating credentials when they already exist"""
    mock_session = Mock()
    mock_session.query.return_value.first.return_value = Mock()  # Credentials exist
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.create_credentials("testuser", "testpass")

    assert success is False
    assert "already exist" in message


def test_verify_credentials_valid():
    """Test verifying valid credentials"""
    mock_session = Mock()
    mock_creds = Mock()
    mock_creds.verify_password.return_value = True
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creds
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.verify_credentials("testuser", "testpass")

    assert success is True
    assert "verified" in message.lower()


def test_verify_credentials_invalid_username():
    """Test verifying with invalid username"""
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.verify_credentials("wronguser", "testpass")

    assert success is False
    assert "invalid" in message.lower()


def test_verify_credentials_invalid_password():
    """Test verifying with invalid password"""
    mock_session = Mock()
    mock_creds = Mock()
    mock_creds.verify_password.return_value = False
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creds
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.verify_credentials("testuser", "wrongpass")

    assert success is False
    assert "invalid" in message.lower()


def test_create_token():
    """Test JWT token creation"""
    mock_session_factory = Mock()
    jwt_secret = "test-secret-key"

    auth_manager = AuthManager(mock_session_factory, jwt_secret)
    token = auth_manager.create_token("testuser")

    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_verify_token_valid():
    """Test verifying valid JWT token"""
    mock_session_factory = Mock()
    jwt_secret = "test-secret-key"

    auth_manager = AuthManager(mock_session_factory, jwt_secret)
    token = auth_manager.create_token("testuser")

    is_valid, username = auth_manager.verify_token(token)

    assert is_valid is True
    assert username == "testuser"


def test_verify_token_invalid():
    """Test verifying invalid JWT token"""
    mock_session_factory = Mock()
    jwt_secret = "test-secret-key"

    auth_manager = AuthManager(mock_session_factory, jwt_secret)

    is_valid, message = auth_manager.verify_token("invalid-token")

    assert is_valid is False


def test_username_case_insensitive():
    """Test that usernames are case-insensitive"""
    mock_session = Mock()
    mock_session.query.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    auth_manager.create_credentials("TestUser", "password")

    # Verify that username was stored as lowercase
    call_args = mock_session.add.call_args
    credentials_obj = call_args[0][0]
    assert credentials_obj.username == "testuser"
