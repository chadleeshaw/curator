"""
Authentication routes
"""

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

if TYPE_CHECKING:
    from core.auth import AuthManager

from web.schemas import (
    APIError,
    APIResponse,
    APITokenResponse,
    ChangePasswordRequest,
    CreateCredentialsRequest,
    LoginRequest,
    UpdateUserRequest,
)
from web.middleware.auth import AuthMiddleware

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# This will be injected from the main app
_auth_manager: Optional["AuthManager"] = None
_auth_middleware: Optional[AuthMiddleware] = None


def set_auth_manager(auth_manager: "AuthManager") -> None:
    """Set the auth manager instance (called from main app)"""
    global _auth_manager, _auth_middleware
    _auth_manager = auth_manager
    _auth_middleware = AuthMiddleware(auth_manager)


async def get_verify_token(authorization: Optional[str] = Header(None)) -> str:
    """
    Dependency function to verify token and return username.
    
    Args:
        authorization: Authorization header value (injected by FastAPI)
        
    Returns:
        Username from verified token
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    if _auth_middleware is None:
        raise RuntimeError("Auth middleware not initialized")
    return await _auth_middleware.verify_token(authorization)


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
async def auth_status():
    """Check if credentials are set up"""
    return {"credentials_exist": _auth_manager.credentials_exist()}


@router.get("/login-mode")
async def get_login_mode():
    """Backend decides which login mode to show (setup or login)"""
    if _auth_manager.credentials_exist():
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
async def setup_credentials(request: CreateCredentialsRequest):
    """Set up initial login credentials"""
    if _auth_manager.credentials_exist():
        raise HTTPException(status_code=400, detail="Credentials already exist")

    success, message = _auth_manager.create_credentials(request.username, request.password)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.post("/login")
async def login(request: LoginRequest):
    """Authenticate user and return JWT token"""
    success, message = _auth_manager.verify_credentials(request.username, request.password)

    if not success:
        raise HTTPException(status_code=401, detail=message)

    token = _auth_manager.create_token(request.username)
    return {"success": True, "token": token, "message": "Login successful"}


@router.post("/change-password")
async def change_password(request: ChangePasswordRequest, username: str = Depends(get_verify_token)):
    """Change password for authenticated user"""
    success, message = _auth_manager.update_credentials(username, request.old_password, request.new_password)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.get("/user/info")
async def get_user_info(current_username: str = Depends(get_verify_token)):
    """Get current user information"""
    return {
        "success": True,
        "username": current_username,
        "has_password": True,  # Always true if authenticated
    }


@router.post("/user/update")
async def update_user(request: UpdateUserRequest, current_username: str = Depends(get_verify_token)):
    """Update username and/or password for authenticated user"""
    # Verify current password first
    success, message = _auth_manager.verify_credentials(current_username, request.current_password)
    if not success:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Update username if provided
    if request.username and request.username != current_username:
        success, message = _auth_manager.update_username(current_username, request.username)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        current_username = request.username  # Update for password change if needed

    # Update password if provided
    if request.new_password:
        success, message = _auth_manager.update_credentials(
            current_username, request.current_password, request.new_password
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": "Account updated successfully"}

@router.get("/api-token")
async def get_api_token(username: str = Depends(get_verify_token)):
    """Get the current API token for the authenticated user"""
    success, api_token = _auth_manager.get_api_token()
    
    if not success or not api_token:
        # If no token exists, generate one
        success, api_token = _auth_manager.regenerate_api_token()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate API token")
    
    return {"success": True, "api_token": api_token, "message": "API token retrieved successfully"}


@router.post("/api-token/regenerate")
async def regenerate_api_token(username: str = Depends(get_verify_token)):
    """Regenerate a new API token for the authenticated user"""
    success, new_token = _auth_manager.regenerate_api_token()
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to generate new API token")
    
    return {"success": True, "api_token": new_token, "message": "API token regenerated successfully"}