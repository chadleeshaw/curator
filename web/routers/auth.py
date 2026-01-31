"""
Authentication routes
"""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException, Request

if TYPE_CHECKING:
    from core.auth import AuthManager

from core.utils.error_handling import handle_api_errors
from web.schemas import (
    APIError,
    ChangePasswordRequest,
    CreateCredentialsRequest,
    LoginRequest,
    UpdateUserRequest,
)
from web.middleware.auth import AuthMiddleware
from web.utils.responses import success_response

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


def get_auth_manager(request: Request) -> "AuthManager":
    """
    Get auth manager from app state.

    Args:
        request: FastAPI request object

    Returns:
        AuthManager instance

    Raises:
        RuntimeError: If auth manager not initialized
    """
    if not hasattr(request.app.state, "auth_manager"):
        raise RuntimeError("Auth manager not initialized")
    return request.app.state.auth_manager


def get_auth_middleware(request: Request) -> AuthMiddleware:
    """
    Get auth middleware from app state.

    Args:
        request: FastAPI request object

    Returns:
        AuthMiddleware instance

    Raises:
        RuntimeError: If auth middleware not initialized
    """
    if not hasattr(request.app.state, "auth_middleware"):
        raise RuntimeError("Auth middleware not initialized")
    return request.app.state.auth_middleware


async def get_verify_token(
    authorization: str = Header(None),
    auth_middleware: AuthMiddleware = Depends(get_auth_middleware),
) -> str:
    """
    Dependency function to verify token and return username.

    Args:
        authorization: Authorization header value (injected by FastAPI)
        auth_middleware: Auth middleware instance (injected via Depends)

    Returns:
        Username from verified token

    Raises:
        HTTPException: If token is invalid or missing
    """
    return await auth_middleware.verify_token(authorization)


@router.get(
    "/status",
    summary="Check authentication status",
    description="Check if initial credentials have been set up",
    responses={
        200: {
            "description": "Authentication status retrieved",
            "content": {"application/json": {"example": {"credentials_exist": True}}},
        }
    },
)
@handle_api_errors("Check auth status", logger)
async def auth_status(auth_manager: "AuthManager" = Depends(get_auth_manager)):
    """Check if credentials are set up"""
    return {"credentials_exist": auth_manager.credentials_exist()}


@router.get("/login-mode")
@handle_api_errors("Get login mode", logger)
async def get_login_mode(auth_manager: "AuthManager" = Depends(get_auth_manager)):
    """Backend decides which login mode to show (setup or login)"""
    if auth_manager.credentials_exist():
        return {"mode": "login"}
    else:
        return {"mode": "setup"}


@router.post(
    "/setup",
    summary="Set up initial credentials",
    description="Create the first user account. Can only be called once.",
    responses={
        200: {"description": "Credentials created successfully"},
        400: {"description": "Credentials already exist", "model": APIError},
    },
)
@handle_api_errors("Setup credentials", logger)
async def setup_credentials(
    request: CreateCredentialsRequest,
    auth_manager: "AuthManager" = Depends(get_auth_manager),
):
    """Set up initial login credentials"""
    if auth_manager.credentials_exist():
        raise HTTPException(status_code=400, detail="Credentials already exist")

    success, message = auth_manager.create_credentials(request.username, request.password)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return success_response(message)


@router.post("/login")
@handle_api_errors("Login", logger)
async def login(request: LoginRequest, auth_manager: "AuthManager" = Depends(get_auth_manager)):
    """Authenticate user and return JWT token"""
    success, message = auth_manager.verify_credentials(request.username, request.password)

    if not success:
        raise HTTPException(status_code=401, detail=message)

    token = auth_manager.create_token(request.username)
    return success_response("Login successful", token=token)


@router.post("/change-password")
@handle_api_errors("Change password", logger)
async def change_password(
    request: ChangePasswordRequest,
    username: str = Depends(get_verify_token),
    auth_manager: "AuthManager" = Depends(get_auth_manager),
):
    """Change password for authenticated user"""
    success, message = auth_manager.update_credentials(username, request.old_password, request.new_password)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return success_response(message)


@router.get("/user/info")
@handle_api_errors("Get user info", logger)
async def get_user_info(current_username: str = Depends(get_verify_token)):
    """Get current user information"""
    return success_response(
        None,
        username=current_username,
        has_password=True,  # Always true if authenticated
    )


@router.post("/user/update")
@handle_api_errors("Update user", logger)
async def update_user(
    request: UpdateUserRequest,
    current_username: str = Depends(get_verify_token),
    auth_manager: "AuthManager" = Depends(get_auth_manager),
):
    """Update username and/or password for authenticated user"""
    # Verify current password first
    success, message = auth_manager.verify_credentials(current_username, request.current_password)
    if not success:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Update username if provided
    if request.username and request.username != current_username:
        success, message = auth_manager.update_username(current_username, request.username)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        current_username = request.username  # Update for password change if needed

    # Update password if provided
    if request.new_password:
        success, message = auth_manager.update_credentials(
            current_username, request.current_password, request.new_password
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)

    return success_response("Account updated successfully")


@router.get("/api-token")
@handle_api_errors("Get API token", logger)
async def get_api_token(
    username: str = Depends(get_verify_token),
    auth_manager: "AuthManager" = Depends(get_auth_manager),
):
    """Get the current API token for the authenticated user"""
    success, api_token = auth_manager.get_api_token()

    if not success or not api_token:
        # If no token exists, generate one
        success, api_token = auth_manager.regenerate_api_token()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate API token")

    return success_response(
        "API token retrieved successfully",
        api_token=api_token,
    )


@router.post("/api-token/regenerate")
@handle_api_errors("Regenerate API token", logger)
async def regenerate_api_token(
    username: str = Depends(get_verify_token),
    auth_manager: "AuthManager" = Depends(get_auth_manager),
):
    """Regenerate a new API token for the authenticated user"""
    success, new_token = auth_manager.regenerate_api_token()

    if not success:
        raise HTTPException(status_code=500, detail="Failed to generate new API token")

    return success_response(
        "API token regenerated successfully",
        api_token=new_token,
    )
