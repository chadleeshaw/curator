"""
Authentication module for managing login credentials
"""

from datetime import timedelta
from hmac import compare_digest
from typing import Optional, Tuple

import jwt

from core.constants.app import TOKEN_EXPIRATION_HOURS
from core.parsers import utc_now
from core.utils.db import get_db_session
from models.database import Credentials

# JWT configuration constants
JWT_ALGORITHM = "HS256"


class AuthManager:
    """Manages user authentication"""

    def __init__(self, session_factory, jwt_secret: str):
        self.session_factory = session_factory
        self.jwt_secret = jwt_secret

    def credentials_exist(self) -> bool:
        """
        Check if credentials have been set up.

        Returns:
            True if credentials exist in database, False otherwise
        """
        with get_db_session(self.session_factory) as session:
            count = session.query(Credentials).count()
            return count > 0

    def create_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Create the initial login credentials.

        Args:
            username: Username for login
            password: Password for login (will be hashed before storage)

        Returns:
            Tuple of (success, message) where success is True if credentials created successfully
        """
        with get_db_session(self.session_factory) as session:
            # Check if credentials already exist
            existing = session.query(Credentials).first()
            if existing:
                return False, "Credentials already exist"

            # Create new credentials with lowercase username.
            # The first user is always admin.
            creds = Credentials(username=username.lower(), is_admin=True)
            creds.set_password(password)
            session.add(creds)
            return True, "Credentials created successfully"

    def verify_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Verify user credentials.

        Args:
            username: Username to verify
            password: Password to verify

        Returns:
            Tuple of (success, message) where success is True if credentials are valid
        """
        with get_db_session(self.session_factory) as session:
            # Query using lowercase username for case-insensitive comparison
            creds = session.query(Credentials).filter_by(username=username.lower()).first()
            if not creds:
                return False, "Invalid username or password"

            if creds.verify_password(password):
                return True, "Credentials verified"
            return False, "Invalid username or password"

    def create_token(self, username: str) -> str:
        """
        Create a JWT token for the authenticated user.

        The token includes both ``username`` (for display) and ``user_id``
        (for database filtering) so that queries can scope data per user.

        Args:
            username: Username to encode in the token

        Returns:
            JWT token string valid for TOKEN_EXPIRATION_HOURS hours

        Raises:
            ValueError: If the user does not exist in the database
        """
        user_id = self._get_user_id(username)
        if user_id is None:
            raise ValueError(f"Cannot create token: user '{username}' not found")
        payload = {
            "username": username,
            "user_id": user_id,
            "iat": utc_now(),
            "exp": utc_now() + timedelta(hours=TOKEN_EXPIRATION_HOURS),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm=JWT_ALGORITHM)
        return token

    def _get_user_id(self, username: str) -> Optional[int]:
        """Return the database ID for the given username, or None if not found."""
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).filter_by(username=username.lower()).first()
            return creds.id if creds else None

    def verify_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Verify a JWT token.

        Args:
            token: JWT token string to verify

        Returns:
            Tuple of (is_valid, username) where username is None if token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM])
            username = payload.get("username")
            return True, username
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None

    def get_user_id_from_token(self, token: str) -> Optional[int]:
        """
        Extract user_id from a valid JWT token.

        Returns:
            user_id integer if the token is valid and contains user_id, otherwise None.
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM])
            return payload.get("user_id")
        except jwt.InvalidTokenError:
            return None

    def verify_token_full(self, token: str) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Decode a JWT exactly once and return (is_valid, username, user_id).

        Prefer this over calling verify_token + get_user_id_from_token in sequence
        to avoid decoding the same token twice.

        Returns:
            (True, username, user_id) on success;
            (False, None, None) on any validation error.
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM])
            username = payload.get("username")
            user_id = payload.get("user_id")
            return True, username, user_id
        except jwt.ExpiredSignatureError:
            return False, None, None
        except jwt.InvalidTokenError:
            return False, None, None

    def update_credentials(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Update the password for the given user.

        Args:
            username: Username whose password should be updated
            old_password: Current password for verification
            new_password: New password to set

        Returns:
            Tuple of (success, message) where success is True if password updated successfully
        """
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).filter_by(username=username.lower()).first()
            if not creds:
                return False, "No credentials exist"

            if not creds.verify_password(old_password):
                return False, "Current password is incorrect"

            creds.set_password(new_password)
            creds.updated_at = utc_now()
            return True, "Password updated successfully"

    def update_username(self, old_username: str, new_username: str) -> Tuple[bool, str]:
        """
        Update the username.

        Args:
            old_username: Current username
            new_username: New username to set

        Returns:
            Tuple of (success, message) where success is True if username updated successfully
        """
        with get_db_session(self.session_factory) as session:
            # Query using lowercase username for case-insensitive comparison
            creds = session.query(Credentials).filter_by(username=old_username.lower()).first()
            if not creds:
                return False, "User not found"

            # Check if new username already exists (case-insensitive)
            existing = session.query(Credentials).filter_by(username=new_username.lower()).first()
            if existing:
                return False, "Username already exists"

            creds.username = new_username.lower()
            creds.updated_at = utc_now()
            return True, "Username updated successfully"

    def get_api_token(self) -> Tuple[bool, Optional[str]]:
        """
        Get the current API token.

        Returns:
            Tuple of (success, api_token) where api_token is None if doesn't exist
        """
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).first()
            if not creds:
                return False, None
            return True, creds.api_token

    def regenerate_api_token(self) -> Tuple[bool, Optional[str]]:
        """
        Regenerate and return a new API token.

        Returns:
            Tuple of (success, new_api_token) where new_api_token is the generated token
        """
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).first()
            if not creds:
                return False, None

            new_token = creds.generate_api_token()
            return True, new_token

    def verify_api_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Verify an API token and return the username if valid.

        Args:
            token: API token to verify

        Returns:
            Tuple of (is_valid, username) where username is None if token is invalid
        """
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).first()
            if not creds:
                return False, None

            # Use constant-time comparison to prevent timing attacks.
            # Guard against None api_token (user has never generated a token).
            if creds.api_token and compare_digest(creds.api_token, token):
                return True, creds.username
            return False, None

    # ------------------------------------------------------------------
    # Multi-user management
    # ------------------------------------------------------------------

    def is_admin(self, username: str) -> bool:
        """Return True if the given user has the is_admin flag set."""
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).filter_by(username=username.lower()).first()
            return bool(creds and creds.is_admin)

    def add_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Create an additional user account.

        Unlike ``create_credentials``, this method does not require that no
        users exist yet — it is used by an already-authenticated admin to
        invite additional users.

        Args:
            username: Username for the new account
            password: Plain-text password (will be hashed before storage)

        Returns:
            Tuple of (success, message)
        """
        with get_db_session(self.session_factory) as session:
            existing = session.query(Credentials).filter_by(username=username.lower()).first()
            if existing:
                return False, "Username already exists"

            creds = Credentials(username=username.lower())
            creds.set_password(password)
            session.add(creds)
            return True, "User created successfully"

    def list_users(self):
        """
        Return a list of all user accounts (without password hashes).

        Returns:
            List of dicts with id, username, created_at, updated_at
        """
        with get_db_session(self.session_factory) as session:
            users = session.query(Credentials).order_by(Credentials.id).all()
            return [u.to_public_dict() for u in users]

    def delete_user(self, user_id: int) -> Tuple[bool, str]:
        """
        Delete a user account by ID.

        Args:
            user_id: Primary key of the Credentials row to remove

        Returns:
            Tuple of (success, message)
        """
        with get_db_session(self.session_factory) as session:
            creds = session.query(Credentials).filter_by(id=user_id).first()
            if not creds:
                return False, "User not found"
            session.delete(creds)
            return True, f"User '{creds.username}' deleted successfully"
