"""
Authentication middleware for handling JWT token and API token verification
"""

from typing import Callable, Optional

from fastapi import HTTPException


class AuthMiddleware:
    """Middleware for authentication token verification"""

    def __init__(self, auth_manager):
        """Initialize with auth manager instance"""
        self.auth_manager = auth_manager

    async def verify_token(self, authorization: Optional[str]) -> str:
        """
        Verify JWT token from Authorization header.

        This method is designed to be used as a FastAPI dependency.

        Args:
            authorization: Authorization header value (should be "Bearer <token>")

        Returns:
            Username from the verified token

        Raises:
            HTTPException: If token is missing, invalid, or expired
        """
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authentication token")

        # Extract token from "Bearer <token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization header")

        token = parts[1]

        # Try JWT token first — returns both username and user_id
        is_valid, username = self.auth_manager.verify_token(token)
        if is_valid and username:
            return username

        # Fall back to API token
        is_valid, username = self.auth_manager.verify_api_token(token)
        if is_valid and username:
            return username

        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async def verify_token_with_id(self, authorization: Optional[str]):
        """
        Like verify_token but returns a (username, user_id) tuple.

        Use this dependency in routes that need to scope queries by user_id.
        For the current single-user deployment, user_id is always 1.

        The JWT is decoded exactly once; both username and user_id are extracted
        from the same payload to avoid a redundant decode call.
        """
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authentication token")

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization header")

        token = parts[1]

        # Decode the JWT a single time and pull out both fields together.
        is_valid, username, user_id = self.auth_manager.verify_token_full(token)
        if is_valid and username:
            return username, user_id

        is_valid, username = self.auth_manager.verify_api_token(token)
        if is_valid and username:
            user_id = self.auth_manager._get_user_id(username)
            return username, user_id

        raise HTTPException(status_code=401, detail="Invalid or expired token")

    def get_verify_token_dependency(self) -> Callable:
        """
        Get a dependency function for token verification.

        Returns a callable that can be used with FastAPI's Depends()
        """
        return self.verify_token
