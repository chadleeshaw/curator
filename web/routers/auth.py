"""
Authentication routes
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from web.schemas import (
    APIError,
    APIResponse,
    ChangePasswordRequest,
    CreateCredentialsRequest,
    LoginRequest,
    UpdateUserRequest,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# This will be injected from the main app
_auth_manager = None


def set_auth_manager(auth_manager):
    """Set the auth manager instance (called from main app)"""
    global _auth_manager
    _auth_manager = auth_manager


async def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """Dependency to verify JWT token from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]
    is_valid, username = _auth_manager.verify_token(token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return username


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

    success, message = _auth_manager.create_credentials(
        request.username, request.password
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.post("/login")
async def login(request: LoginRequest):
    """Authenticate user and return JWT token"""
    success, message = _auth_manager.verify_credentials(
        request.username, request.password
    )

    if not success:
        raise HTTPException(status_code=401, detail=message)

    token = _auth_manager.create_token(request.username)
    return {"success": True, "token": token, "message": "Login successful"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest, username: str = Depends(verify_token)
):
    """Change password for authenticated user"""
    success, message = _auth_manager.update_credentials(
        username, request.old_password, request.new_password
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.get("/user/info")
async def get_user_info(username: str = Depends(verify_token)):
    """Get current user information"""
    return {
        "success": True,
        "username": username,
        "has_password": True,  # Always true if authenticated
    }


@router.post("/user/update")
async def update_user(
    request: UpdateUserRequest, current_username: str = Depends(verify_token)
):
    """Update username and/or password for authenticated user"""
    # Verify current password first
    success, message = _auth_manager.verify_credentials(
        current_username, request.current_password
    )
    if not success:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Update username if provided
    if request.username and request.username != current_username:
        success, message = _auth_manager.update_username(
            current_username, request.username
        )
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
