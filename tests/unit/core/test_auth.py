#!/usr/bin/env python3
"""
Test suite for core.auth module
"""

from unittest.mock import Mock, patch

# Path setup handled by conftest.py

from core.auth import AuthManager


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

    with patch("core.auth.get_db_session") as mock_get_session:
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

    with patch("core.auth.get_db_session") as mock_get_session:
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
    mock_creds = Mock()
    mock_creds.id = 1
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creds
    mock_session_factory = Mock(return_value=mock_session)
    jwt_secret = "test-secret-key"

    auth_manager = AuthManager(mock_session_factory, jwt_secret)
    token = auth_manager.create_token("testuser")

    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_verify_token_valid():
    """Test verifying valid JWT token"""
    mock_creds = Mock()
    mock_creds.id = 1
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creds
    mock_session_factory = Mock(return_value=mock_session)
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


# ==============================================================================
# Multi-user management
# ==============================================================================


def test_add_user_success():
    """Test adding a new user when no conflict exists"""
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.add_user("newuser", "password123")

    assert success is True
    assert "created" in message.lower()
    mock_session.add.assert_called_once()


def test_add_user_duplicate():
    """Test that add_user rejects a duplicate username"""
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = Mock()
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.add_user("existinguser", "password123")

    assert success is False
    assert "already exists" in message.lower()
    mock_session.add.assert_not_called()


def test_add_user_stores_lowercase():
    """Test that add_user normalises the username to lowercase"""
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    auth_manager.add_user("NewUser", "password123")

    credentials_obj = mock_session.add.call_args[0][0]
    assert credentials_obj.username == "newuser"


def test_list_users_returns_dicts():
    """Test that list_users returns a list of dicts without password hashes"""
    mock_user1 = Mock()
    mock_user1.to_public_dict.return_value = {
        "id": 1,
        "username": "alice",
        "is_admin": True,
    }
    mock_user2 = Mock()
    mock_user2.to_public_dict.return_value = {
        "id": 2,
        "username": "bob",
        "is_admin": False,
    }

    mock_session = Mock()
    mock_session.query.return_value.order_by.return_value.all.return_value = [
        mock_user1,
        mock_user2,
    ]
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    users = auth_manager.list_users()

    assert len(users) == 2
    assert users[0]["username"] == "alice"
    assert users[1]["username"] == "bob"
    # Must not expose password hashes
    for u in users:
        assert "password_hash" not in u


def test_delete_user_success():
    """Test deleting a user that exists"""
    mock_creds = Mock()
    mock_creds.username = "alice"
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creds
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.delete_user(1)

    assert success is True
    assert "alice" in message
    mock_session.delete.assert_called_once_with(mock_creds)


def test_delete_user_not_found():
    """Test deleting a user that does not exist"""
    mock_session = Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session_factory = Mock(return_value=mock_session)

    auth_manager = AuthManager(mock_session_factory, "secret")
    success, message = auth_manager.delete_user(999)

    assert success is False
    assert "not found" in message.lower()
    mock_session.delete.assert_not_called()


# ==============================================================================
# Cross-user data isolation
# ==============================================================================


def test_update_credentials_only_updates_target_user():
    """update_credentials must not change another user's password."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.database import Base

    engine = create_engine(
        "sqlite:///file:iso_update_creds?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    auth = AuthManager(factory, "secret")
    auth.create_credentials("alice", "alice_pass")
    auth.add_user("bob", "bob_pass")

    # Change only alice's password
    success, _ = auth.update_credentials("alice", "alice_pass", "alice_new")
    assert success is True

    # Bob's original password still works
    ok, _ = auth.verify_credentials("bob", "bob_pass")
    assert ok is True, "Bob's password should be unchanged"

    # Alice's old password no longer works
    ok, _ = auth.verify_credentials("alice", "alice_pass")
    assert ok is False, "Alice's old password should no longer be valid"

    engine.dispose()


def test_update_username_does_not_affect_other_user():
    """update_username must not alter another user's username."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.database import Base

    engine = create_engine(
        "sqlite:///file:iso_update_username?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    auth = AuthManager(factory, "secret")
    auth.create_credentials("alice", "pass")
    auth.add_user("bob", "pass")

    # Rename alice only
    success, _ = auth.update_username("alice", "alice_renamed")
    assert success is True

    # Bob is untouched
    ok, _ = auth.verify_credentials("bob", "pass")
    assert ok is True, "Bob's account should still exist with original username"

    # alice no longer exists under old name
    ok, _ = auth.verify_credentials("alice", "pass")
    assert ok is False, "Old username 'alice' should no longer exist"

    engine.dispose()


def test_delete_user_does_not_affect_other_user():
    """delete_user must remove only the target row, not other users."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.database import Base

    engine = create_engine(
        "sqlite:///file:iso_delete_user?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    auth = AuthManager(factory, "secret")
    auth.create_credentials("alice", "pass")
    auth.add_user("bob", "pass")

    # Find bob's ID and delete him
    users = auth.list_users()
    bob_id = next(u["id"] for u in users if u["username"] == "bob")
    success, _ = auth.delete_user(bob_id)
    assert success is True

    # Alice is unaffected
    ok, _ = auth.verify_credentials("alice", "pass")
    assert ok is True, "Alice's account should survive bob's deletion"

    # Bob is gone
    users_after = auth.list_users()
    assert not any(u["username"] == "bob" for u in users_after)

    engine.dispose()


def test_list_users_does_not_expose_password_hash():
    """list_users must never include password_hash in any returned dict."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.database import Base

    engine = create_engine(
        "sqlite:///file:iso_list_users?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    auth = AuthManager(factory, "secret")
    auth.create_credentials("alice", "pass1")
    auth.add_user("bob", "pass2")

    users = auth.list_users()
    assert len(users) == 2
    for user in users:
        assert "password_hash" not in user, "password_hash must not be exposed"
        assert "api_token" not in user, "api_token must not be exposed"
        assert "is_admin" in user, "is_admin should be present in public dict"

    engine.dispose()
