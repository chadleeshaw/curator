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

        # Try JWT token first
        is_valid, username = self.auth_manager.verify_token(token)
        if is_valid and username:
            return username

        # Fall back to API token
        is_valid, username = self.auth_manager.verify_api_token(token)
        if is_valid and username:
            return username

        raise HTTPException(status_code=401, detail="Invalid or expired token")

    def get_verify_token_dependency(self) -> Callable:
        """
        Get a dependency function for token verification.

        Returns a callable that can be used with FastAPI's Depends()
        """
        return self.verify_token
