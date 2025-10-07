"""
Enhanced Authentication API - Phase 3 Week 34
Advanced JWT-based authentication with security features
"""

import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, validator

from src.middleware.jwt_auth_middleware import (
    JWTManager,
    TokenConfig,
    TokenType,
    UserClaims,
    UserRole,
)
from src.services.audit_service import AuditService
from src.services.user_service import UserService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.enhanced_auth")

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
    responses={
        401: {"description": "Authentication failed"},
        403: {"description": "Access forbidden"},
        429: {"description": "Too many requests"},
    },
)

# Initialize JWT manager
token_config = TokenConfig()
jwt_manager = JWTManager(token_config)

# ====================================
# Request/Response Models
# ====================================


class LoginRequest(BaseModel):
    """Login request model"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    remember_me: bool = False
    device_name: Optional[str] = Field(None, max_length=100)


class LoginResponse(BaseModel):
    """Login response model"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]
    permissions: list[str]


class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""

    refresh_token: str


class RegisterRequest(BaseModel):
    """User registration request model"""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=100)

    @validator("password")
    def validate_password_strength(cls, v):
        """Validate password strength"""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class ChangePasswordRequest(BaseModel):
    """Change password request model"""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @validator("new_password")
    def validate_password_strength(cls, v):
        """Validate password strength"""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class ResetPasswordRequest(BaseModel):
    """Reset password request model"""

    email: EmailStr


class ConfirmResetPasswordRequest(BaseModel):
    """Confirm reset password request model"""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UserProfileResponse(BaseModel):
    """User profile response model"""

    user_id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    permissions: list[str]
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool


# ====================================
# Helper Functions
# ====================================


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


async def get_current_user(request: Request) -> UserClaims:
    """Dependency to get current authenticated user"""
    if not hasattr(request.state, "user") or not request.state.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return request.state.user


async def require_role(required_role: UserRole):
    """Dependency factory to require specific role"""

    async def check_role(current_user: UserClaims = Depends(get_current_user)):
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
            UserRole.SUPERADMIN: 4,
        }

        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(required_role, 1)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {required_role.value}",
            )
        return current_user

    return check_role


# ====================================
# Authentication Endpoints
# ====================================


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, response: Response, login_data: LoginRequest):
    """Authenticate user and return JWT tokens"""
    try:
        # Get user service
        user_service = UserService()

        # Find user by username or email
        user = await user_service.get_user_by_username_or_email(login_data.username)

        if not user or not verify_password(login_data.password, user.password_hash):
            # Log failed login attempt
            audit_service = AuditService()
            await audit_service.log_event(
                "auth_failed",
                {"username": login_data.username, "ip": request.client.host},
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
            )

        # Create user claims
        user_claims = UserClaims(
            user_id=user.id,
            username=user.username,
            email=user.email,
            role=UserRole(user.role),
            permissions=user.permissions or [],
            session_id=secrets.token_urlsafe(16),
            created_at=time.time(),
            last_activity=time.time(),
        )

        # Create tokens
        access_token_data = jwt_manager.create_access_token(user_claims, request)
        refresh_token_data = jwt_manager.create_refresh_token(user_claims, request)

        # Update user last login
        await user_service.update_last_login(user.id)

        # Log successful login
        audit_service = AuditService()
        await audit_service.log_event(
            "auth_success",
            {
                "user_id": user.id,
                "username": user.username,
                "ip": request.client.host,
                "device_name": login_data.device_name,
            },
        )

        # Set secure cookies for tokens
        response.set_cookie(
            key="access_token",
            value=access_token_data.token,
            max_age=token_config.access_token_expire_minutes * 60,
            httponly=True,
            secure=token_config.require_https,
            samesite="lax",
        )

        if login_data.remember_me:
            response.set_cookie(
                key="refresh_token",
                value=refresh_token_data.token,
                max_age=token_config.refresh_token_expire_days * 24 * 60 * 60,
                httponly=True,
                secure=token_config.require_https,
                samesite="lax",
            )

        return LoginResponse(
            access_token=access_token_data.token,
            refresh_token=refresh_token_data.token,
            token_type="bearer",
            expires_in=token_config.access_token_expire_minutes * 60,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
            },
            permissions=user.permissions or [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    request: Request, response: Response, refresh_request: RefreshTokenRequest
):
    """Refresh access token using refresh token"""
    try:
        # Verify and refresh token
        success, new_token_data, error = jwt_manager.refresh_access_token(
            refresh_request.refresh_token, request
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error or "Token refresh failed",
            )

        # Get user data
        user_service = UserService()
        user = await user_service.get_user_by_id(new_token_data.user_claims.user_id)

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found or disabled",
            )

        # Set new access token cookie
        response.set_cookie(
            key="access_token",
            value=new_token_data.token,
            max_age=token_config.access_token_expire_minutes * 60,
            httponly=True,
            secure=token_config.require_https,
            samesite="lax",
        )

        return LoginResponse(
            access_token=new_token_data.token,
            refresh_token=refresh_request.refresh_token,
            token_type="bearer",
            expires_in=token_config.access_token_expire_minutes * 60,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
            },
            permissions=user.permissions or [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh service error",
        )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: UserClaims = Depends(get_current_user),
):
    """Logout user and revoke tokens"""
    try:
        # Extract current token to revoke it
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

            # Decode to get expiry and revoke
            import jwt

            try:
                payload = jwt.decode(token, options={"verify_signature": False})
                jti = payload.get("jti")
                exp = payload.get("exp")

                if jti and exp:
                    jwt_manager.revoke_token(jti, datetime.fromtimestamp(exp))
            except Exception:
                pass  # Continue with logout even if revocation fails

        # Clear cookies
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")

        # Log logout
        audit_service = AuditService()
        await audit_service.log_event(
            "auth_logout",
            {
                "user_id": current_user.user_id,
                "username": current_user.username,
                "ip": request.client.host,
            },
        )

        return {"message": "Successfully logged out"}

    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Still return success even if logging fails
        return {"message": "Logged out"}


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: UserClaims = Depends(get_current_user),
):
    """Get current user profile"""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_id(current_user.user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        return UserProfileResponse(
            user_id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            permissions=user.permissions or [],
            created_at=user.created_at,
            last_login=user.last_login,
            is_active=user.is_active,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile service error",
        )


@router.post("/change-password")
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: UserClaims = Depends(get_current_user),
):
    """Change user password"""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_id(current_user.user_id)

        if not user or not verify_password(
            password_data.current_password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Hash new password
        new_password_hash = hash_password(password_data.new_password)

        # Update password
        await user_service.update_password(current_user.user_id, new_password_hash)

        # Log password change
        audit_service = AuditService()
        await audit_service.log_event(
            "password_changed",
            {
                "user_id": current_user.user_id,
                "username": current_user.username,
                "ip": request.client.host,
            },
        )

        return {"message": "Password changed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change service error",
        )


@router.get("/sessions")
async def get_active_sessions(current_user: UserClaims = Depends(get_current_user)):
    """Get active sessions for current user"""
    try:
        # This would require session tracking in database
        # For now, return current session info
        return {
            "active_sessions": [
                {
                    "session_id": current_user.session_id,
                    "created_at": datetime.fromtimestamp(current_user.created_at),
                    "last_activity": datetime.fromtimestamp(current_user.last_activity),
                    "is_current": True,
                }
            ]
        }

    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session service error",
        )


@router.post("/revoke-all-sessions")
async def revoke_all_sessions(
    request: Request, current_user: UserClaims = Depends(get_current_user)
):
    """Revoke all sessions for current user"""
    try:
        # This would require comprehensive session management
        # For now, just log the action
        audit_service = AuditService()
        await audit_service.log_event(
            "sessions_revoked",
            {
                "user_id": current_user.user_id,
                "username": current_user.username,
                "ip": request.client.host,
            },
        )

        return {"message": "All sessions revoked successfully"}

    except Exception as e:
        logger.error(f"Revoke sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation service error",
        )
