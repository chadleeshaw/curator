"""
Authentication module for managing login credentials
"""

from datetime import UTC, datetime, timedelta
from typing import Optional, Tuple

import jwt

from models.database import Credentials

# JWT configuration constants
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 24


class AuthManager:
    """Manages user authentication"""

    def __init__(self, session_factory, jwt_secret: str):
        self.session_factory = session_factory
        self.jwt_secret = jwt_secret

    def credentials_exist(self) -> bool:
        """Check if credentials have been set up"""
        session = self.session_factory()
        try:
            count = session.query(Credentials).count()
            return count > 0
        finally:
            session.close()

    def create_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Create the initial login credentials.
        Returns (success, message)
        """
        session = self.session_factory()
        try:
            # Check if credentials already exist
            existing = session.query(Credentials).first()
            if existing:
                return False, "Credentials already exist"

            # Create new credentials
            creds = Credentials(username=username)
            creds.set_password(password)
            session.add(creds)
            session.commit()
            return True, "Credentials created successfully"
        except Exception as e:
            session.rollback()
            return False, f"Error creating credentials: {str(e)}"
        finally:
            session.close()

    def verify_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Verify user credentials.
        Returns (success, message)
        """
        session = self.session_factory()
        try:
            creds = session.query(Credentials).filter_by(username=username).first()
            if not creds:
                return False, "Invalid username or password"

            if creds.verify_password(password):
                return True, "Credentials verified"
            else:
                return False, "Invalid username or password"
        except Exception as e:
            return False, f"Error verifying credentials: {str(e)}"
        finally:
            session.close()

    def create_token(self, username: str) -> str:
        """Create a JWT token for authenticated user"""
        payload = {
            "username": username,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=TOKEN_EXPIRATION_HOURS),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm=JWT_ALGORITHM)
        return token

    def verify_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Verify a JWT token.
        Returns (is_valid, username or None)
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM])
            username = payload.get("username")
            return True, username
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None

    def update_credentials(
        self, username: str, old_password: str, new_password: str
    ) -> Tuple[bool, str]:
        """
        Update the password.
        Returns (success, message)
        """
        session = self.session_factory()
        try:
            creds = session.query(Credentials).first()
            if not creds:
                return False, "No credentials exist"

            if not creds.verify_password(old_password):
                return False, "Current password is incorrect"

            creds.set_password(new_password)
            creds.updated_at = datetime.now(UTC)
            session.commit()
            return True, "Password updated successfully"
        except Exception as e:
            session.rollback()
            return False, f"Error updating password: {str(e)}"
        finally:
            session.close()

    def update_username(self, old_username: str, new_username: str) -> Tuple[bool, str]:
        """
        Update the username.
        Returns (success, message)
        """
        session = self.session_factory()
        try:
            creds = session.query(Credentials).filter_by(username=old_username).first()
            if not creds:
                return False, "User not found"

            # Check if new username already exists
            existing = (
                session.query(Credentials).filter_by(username=new_username).first()
            )
            if existing:
                return False, "Username already exists"

            creds.username = new_username
            creds.updated_at = datetime.now(UTC)
            session.commit()
            return True, "Username updated successfully"
        except Exception as e:
            session.rollback()
            return False, f"Error updating username: {str(e)}"
        finally:
            session.close()
