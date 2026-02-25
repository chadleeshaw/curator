"""
Test suite for authentication router endpoints
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Path setup handled by conftest.py

from core.auth import AuthManager
from models.database import (
    Base,
    Credentials,
)  # Import Credentials to register with Base
from web.routers import auth


@pytest.fixture(scope="module")
def test_db():
    """Create in-memory test database"""
    # Use named in-memory database with check_same_thread=False for sharing across threads
    engine = create_engine(
        "sqlite:///file:test_db?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    yield engine, session_factory
    engine.dispose()


@pytest.fixture(scope="module")
def test_auth_manager(test_db):
    """Create test auth manager with in-memory database"""
    engine, session_factory = test_db
    jwt_secret = "test-secret-key-for-testing-only"
    auth_manager = AuthManager(session_factory, jwt_secret)
    return auth_manager


@pytest.fixture(scope="module")
def test_app(test_auth_manager):
    """Create test FastAPI app with auth router"""
    from web.middleware.auth import AuthMiddleware

    app = FastAPI(title="Test App")
    # Store auth_manager in app state so it can be accessed by dependency injection
    app.state.auth_manager = test_auth_manager
    # Create and store auth middleware
    app.state.auth_middleware = AuthMiddleware(test_auth_manager)
    app.include_router(auth.router)
    return app


@pytest.fixture
def test_client(test_auth_manager, test_app):
    """Create test client with auth manager injected"""
    # Auth manager is already set in test_app fixture
    with TestClient(test_app, raise_server_exceptions=True) as client:
        yield client
        # Clean up credentials after each test to ensure isolation
        session = test_auth_manager.session_factory()
        try:
            session.query(Credentials).delete()
            session.commit()
        finally:
            session.close()


class TestAuthStatus:
    """Test authentication status endpoint"""

    def test_status_no_credentials(self, test_client):
        """Test status when no credentials exist"""
        response = test_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert "credentials_exist" in data
        assert data["credentials_exist"] is False

    def test_status_with_credentials(self, test_client, test_auth_manager):
        """Test status when credentials exist"""
        test_auth_manager.create_credentials("testuser", "testpass123")
        response = test_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["credentials_exist"] is True


class TestLoginMode:
    """Test login mode endpoint"""

    def test_login_mode_setup(self, test_client):
        """Test login mode returns setup when no credentials"""
        response = test_client.get("/api/auth/login-mode")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "setup"

    def test_login_mode_login(self, test_client, test_auth_manager):
        """Test login mode returns login when credentials exist"""
        test_auth_manager.create_credentials("testuser", "testpass123")
        response = test_client.get("/api/auth/login-mode")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "login"


class TestSetupCredentials:
    """Test initial credentials setup"""

    def test_setup_success(self, test_client):
        """Test successful credentials setup"""
        response = test_client.post("/api/auth/setup", json={"username": "admin", "password": "admin123"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "created" in data["message"].lower()

    def test_setup_duplicate(self, test_client, test_auth_manager):
        """Test setup fails when credentials already exist"""
        test_auth_manager.create_credentials("existing", "password123")
        response = test_client.post("/api/auth/setup", json={"username": "admin", "password": "admin123"})
        assert response.status_code == 400
        data = response.json()
        assert "already exist" in data["detail"].lower()


class TestLogin:
    """Test login endpoint"""

    def test_login_success(self, test_client, test_auth_manager):
        """Test successful login"""
        test_auth_manager.create_credentials("testuser", "testpass123")
        response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "testpass123"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "token" in data
        assert data["token"] is not None
        assert len(data["token"]) > 0

    def test_login_wrong_password(self, test_client, test_auth_manager):
        """Test login with wrong password"""
        test_auth_manager.create_credentials("testuser", "testpass123")
        response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "wrongpass"})
        assert response.status_code == 401
        data = response.json()
        assert "invalid" in data["detail"].lower()

    def test_login_nonexistent_user(self, test_client):
        """Test login with nonexistent username"""
        response = test_client.post("/api/auth/login", json={"username": "nouser", "password": "somepass"})
        assert response.status_code == 401
        data = response.json()
        assert "invalid" in data["detail"].lower()


class TestTokenVerification:
    """Test token verification"""

    def test_verify_valid_token(self, test_client, test_auth_manager):
        """Test accessing protected endpoint with valid token"""
        test_auth_manager.create_credentials("testuser", "testpass123")
        login_response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "testpass123"})
        token = login_response.json()["token"]

        response = test_client.get("/api/auth/user/info", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"

    def test_verify_missing_token(self, test_client):
        """Test accessing protected endpoint without token"""
        response = test_client.get("/api/auth/user/info")
        assert response.status_code == 401

    def test_verify_invalid_token(self, test_client):
        """Test accessing protected endpoint with invalid token"""
        response = test_client.get("/api/auth/user/info", headers={"Authorization": "Bearer invalid-token"})
        assert response.status_code == 401

    def test_verify_malformed_header(self, test_client):
        """Test accessing protected endpoint with malformed auth header"""
        response = test_client.get("/api/auth/user/info", headers={"Authorization": "NotBearer token"})
        assert response.status_code == 401


class TestChangePassword:
    """Test password change endpoint"""

    def test_change_password_success(self, test_client, test_auth_manager):
        """Test successful password change"""
        test_auth_manager.create_credentials("testuser", "oldpass123")
        login_response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "oldpass123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "oldpass123", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify can login with new password
        new_login = test_client.post("/api/auth/login", json={"username": "testuser", "password": "newpass123"})
        assert new_login.status_code == 200

    def test_change_password_wrong_old_password(self, test_client, test_auth_manager):
        """Test password change with wrong old password"""
        test_auth_manager.create_credentials("testuser", "oldpass123")
        login_response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "oldpass123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "wrongpass", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400


class TestUpdateUser:
    """Test user update endpoint"""

    def test_update_username(self, test_client, test_auth_manager):
        """Test updating username"""
        test_auth_manager.create_credentials("olduser", "password123")
        login_response = test_client.post("/api/auth/login", json={"username": "olduser", "password": "password123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/user/update",
            json={"current_password": "password123", "username": "newuser"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_update_password(self, test_client, test_auth_manager):
        """Test updating password through user update endpoint"""
        test_auth_manager.create_credentials("testuser", "oldpass123")
        login_response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "oldpass123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/user/update",
            json={"current_password": "oldpass123", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # Verify new password works
        new_login = test_client.post("/api/auth/login", json={"username": "testuser", "password": "newpass123"})
        assert new_login.status_code == 200

    def test_update_both(self, test_client, test_auth_manager):
        """Test updating both username and password"""
        test_auth_manager.create_credentials("olduser", "oldpass123")
        login_response = test_client.post("/api/auth/login", json={"username": "olduser", "password": "oldpass123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/user/update",
            json={
                "current_password": "oldpass123",
                "username": "newuser",
                "new_password": "newpass123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # Verify new credentials work
        new_login = test_client.post("/api/auth/login", json={"username": "newuser", "password": "newpass123"})
        assert new_login.status_code == 200

    def test_update_wrong_current_password(self, test_client, test_auth_manager):
        """Test update fails with wrong current password"""
        test_auth_manager.create_credentials("testuser", "password123")
        login_response = test_client.post("/api/auth/login", json={"username": "testuser", "password": "password123"})
        token = login_response.json()["token"]

        response = test_client.post(
            "/api/auth/user/update",
            json={"current_password": "wrongpass", "username": "newuser"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestMultiUserManagement:
    """Test multi-user management endpoints (list, create, delete)."""

    def _get_token(self, client, auth_manager, username="admin", password="adminpass1"):
        """Helper: create a user and return a valid JWT."""
        auth_manager.create_credentials(username, password)
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        return resp.json()["token"]

    # ------------------------------------------------------------------
    # GET /api/auth/users
    # ------------------------------------------------------------------

    def test_list_users_requires_auth(self, test_client):
        """List users endpoint must reject unauthenticated requests."""
        response = test_client.get("/api/auth/users")
        assert response.status_code == 401

    def test_list_users_returns_current_user(self, test_client, test_auth_manager):
        """Authenticated request returns at least the current user."""
        token = self._get_token(test_client, test_auth_manager)
        response = test_client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert any(u["username"] == "admin" for u in data["users"])

    # ------------------------------------------------------------------
    # POST /api/auth/users
    # ------------------------------------------------------------------

    def test_create_user_requires_auth(self, test_client):
        """Create user endpoint must reject unauthenticated requests."""
        response = test_client.post("/api/auth/users", json={"username": "bob", "password": "bobpass123"})
        assert response.status_code == 401

    def test_create_user_success(self, test_client, test_auth_manager):
        """Authenticated admin can create a new user."""
        token = self._get_token(test_client, test_auth_manager)
        response = test_client.post(
            "/api/auth/users",
            json={"username": "newuser", "password": "newuserpass"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "created" in data["message"].lower()

    def test_create_user_duplicate_rejected(self, test_client, test_auth_manager):
        """Creating a user with an existing username returns 400."""
        token = self._get_token(test_client, test_auth_manager)
        # Create once
        test_client.post(
            "/api/auth/users",
            json={"username": "dupuser", "password": "dupuserpass"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Try again with the same username
        response = test_client.post(
            "/api/auth/users",
            json={"username": "dupuser", "password": "anotherpass"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_create_user_new_user_can_login(self, test_client, test_auth_manager):
        """A user created via the admin endpoint can log in."""
        token = self._get_token(test_client, test_auth_manager)
        test_client.post(
            "/api/auth/users",
            json={"username": "logintest", "password": "logintestpass"},
            headers={"Authorization": f"Bearer {token}"},
        )
        login = test_client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "logintestpass"},
        )
        assert login.status_code == 200
        assert login.json()["success"] is True

    # ------------------------------------------------------------------
    # DELETE /api/auth/users/{user_id}
    # ------------------------------------------------------------------

    def test_delete_user_requires_auth(self, test_client, test_auth_manager):
        """Delete user endpoint must reject unauthenticated requests."""
        # Create a user to get a valid ID
        test_auth_manager.create_credentials("victim", "victimpass1")
        users = test_auth_manager.list_users()
        victim_id = next(u["id"] for u in users if u["username"] == "victim")
        response = test_client.delete(f"/api/auth/users/{victim_id}")
        assert response.status_code == 401

    def test_delete_user_success(self, test_client, test_auth_manager):
        """Authenticated admin can delete another user."""
        token = self._get_token(test_client, test_auth_manager)
        # Create a user to delete
        test_auth_manager.add_user("todelete", "todeletepass")
        users = test_auth_manager.list_users()
        target_id = next(u["id"] for u in users if u["username"] == "todelete")

        response = test_client.delete(
            f"/api/auth/users/{target_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_user_not_found(self, test_client, test_auth_manager):
        """Deleting a non-existent user ID returns 404."""
        token = self._get_token(test_client, test_auth_manager)
        response = test_client.delete(
            "/api/auth/users/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_delete_self_rejected(self, test_client, test_auth_manager):
        """A user cannot delete their own account."""
        token = self._get_token(test_client, test_auth_manager)
        users = test_auth_manager.list_users()
        own_id = next(u["id"] for u in users if u["username"] == "admin")
        response = test_client.delete(
            f"/api/auth/users/{own_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        assert "own account" in response.json()["detail"].lower()


class TestCrossUserIsolation:
    """
    Cross-user data isolation tests.

    These tests ensure that authenticated operations are strictly scoped to
    the requesting user and cannot read or modify another user's data.
    """

    def _login(self, client, username: str, password: str) -> str:
        """Return a JWT for the given credentials (which must already exist)."""
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
        return resp.json()["token"]

    def test_change_password_only_affects_own_account(self, test_client, test_auth_manager):
        """POST /api/auth/change-password must update only the requesting user's password."""
        # Create two users
        test_auth_manager.create_credentials("user_a", "pass_a_old")
        test_auth_manager.add_user("user_b", "pass_b")

        token_a = self._login(test_client, "user_a", "pass_a_old")

        # user_a changes their own password
        resp = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "pass_a_old", "new_password": "pass_a_new"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # user_b's password must be unchanged
        ok, _ = test_auth_manager.verify_credentials("user_b", "pass_b")
        assert ok is True, "user_b's password should not have been changed"

        # user_a's old password no longer works
        ok, _ = test_auth_manager.verify_credentials("user_a", "pass_a_old")
        assert ok is False, "user_a's old password should be invalid"

    def test_update_user_does_not_rename_other_account(self, test_client, test_auth_manager):
        """POST /api/auth/user/update must rename only the requesting user."""
        test_auth_manager.create_credentials("user_a", "pass_a")
        test_auth_manager.add_user("user_b", "pass_b")

        token_a = self._login(test_client, "user_a", "pass_a")

        # user_a updates their own username
        resp = test_client.post(
            "/api/auth/user/update",
            json={"current_password": "pass_a", "username": "user_a_renamed"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # user_b is unaffected
        ok, _ = test_auth_manager.verify_credentials("user_b", "pass_b")
        assert ok is True, "user_b should still exist with original credentials"

        # Old name is gone
        ok, _ = test_auth_manager.verify_credentials("user_a", "pass_a")
        assert ok is False, "Old username user_a should no longer exist"

    def test_user_info_returns_own_data_only(self, test_client, test_auth_manager):
        """GET /api/auth/user/info must return the requesting user's own info."""
        test_auth_manager.create_credentials("user_a", "pass_a")
        test_auth_manager.add_user("user_b", "pass_b")

        token_a = self._login(test_client, "user_a", "pass_a")
        token_b = self._login(test_client, "user_b", "pass_b")

        resp_a = test_client.get("/api/auth/user/info", headers={"Authorization": f"Bearer {token_a}"})
        resp_b = test_client.get("/api/auth/user/info", headers={"Authorization": f"Bearer {token_b}"})

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["username"] == "user_a"
        assert resp_b.json()["username"] == "user_b"
        # Each token returns its own user, not the other's
        assert resp_a.json()["username"] != resp_b.json()["username"]

    def test_non_admin_cannot_list_users(self, test_client, test_auth_manager):
        """A non-admin user must receive 403 when attempting to list users."""
        test_auth_manager.create_credentials("admin_user", "adminpass")
        test_auth_manager.add_user("regular_user", "regularpass")

        # regular_user is not admin (add_user sets is_admin=False)
        token = self._login(test_client, "regular_user", "regularpass")

        resp = test_client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_non_admin_cannot_create_user(self, test_client, test_auth_manager):
        """A non-admin user must receive 403 when attempting to create a user."""
        test_auth_manager.create_credentials("admin_user", "adminpass")
        test_auth_manager.add_user("regular_user", "regularpass")

        token = self._login(test_client, "regular_user", "regularpass")

        resp = test_client.post(
            "/api/auth/users",
            json={"username": "new_victim", "password": "victimpass"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_non_admin_cannot_delete_user(self, test_client, test_auth_manager):
        """A non-admin user must receive 403 when attempting to delete a user."""
        test_auth_manager.create_credentials("admin_user", "adminpass")
        test_auth_manager.add_user("regular_user", "regularpass")

        token = self._login(test_client, "regular_user", "regularpass")

        # Try to delete someone — even a non-existent ID
        resp = test_client.delete(
            "/api/auth/users/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
