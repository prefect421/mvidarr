"""
Authentication-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all authentication and authorization operations.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import EmailStr, Field, validator

from .base import BaseRequest, BaseResponse, TimestampMixin


class UserRole(str, Enum):
    """Valid user roles"""

    USER = "USER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class OAuth2Provider(str, Enum):
    """Supported OAuth2 providers"""

    GOOGLE = "google"
    GITHUB = "github"
    AUTHENTIK = "authentik"
    MICROSOFT = "microsoft"


class SessionStatus(str, Enum):
    """Session status values"""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class LoginRequest(BaseRequest):
    """Request for user login"""

    username: str = Field(
        ..., min_length=1, max_length=100, description="Username or email address"
    )
    password: str = Field(
        ..., min_length=8, max_length=100, description="User password"
    )
    remember_me: bool = Field(
        default=False, description="Extend session duration if true"
    )

    @validator("username")
    def validate_username(cls, v):
        """Clean username"""
        return v.strip().lower()


class LoginResponse(BaseResponse):
    """Response for successful login"""

    user_id: int = Field(description="Unique user identifier")
    username: str = Field(description="Username")
    role: UserRole = Field(description="User role")
    session_id: str = Field(description="Session identifier")
    expires_at: datetime = Field(description="Session expiration time")
    is_2fa_required: bool = Field(
        default=False, description="Whether 2FA verification is required"
    )
    permissions: List[str] = Field(
        default_factory=list, description="List of user permissions"
    )

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "user_id": 123,
                "username": "johndoe",
                "role": "USER",
                "session_id": "abc123def456",
                "expires_at": "2024-01-01T12:00:00Z",
                "is_2fa_required": False,
                "permissions": ["videos:read", "videos:download"],
            }
        }


class CredentialsRequest(BaseRequest):
    """Request to update user credentials"""

    current_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Current password for verification",
    )
    new_password: str = Field(
        ..., min_length=8, max_length=100, description="New password to set"
    )
    confirm_password: str = Field(
        ..., min_length=8, max_length=100, description="Confirmation of new password"
    )

    @validator("confirm_password")
    def validate_passwords_match(cls, v, values):
        """Ensure new password and confirmation match"""
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("New password and confirmation do not match")
        return v

    @validator("new_password")
    def validate_password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v)

        strength_checks = sum([has_upper, has_lower, has_digit, has_special])
        if strength_checks < 3:
            raise ValueError(
                "Password must contain at least 3 of: uppercase letters, "
                "lowercase letters, digits, special characters"
            )

        return v


class UserSessionResponse(BaseResponse, TimestampMixin):
    """Response containing user session information"""

    session_id: str = Field(description="Session identifier")
    user_id: int = Field(description="User ID")
    username: str = Field(description="Username")
    role: UserRole = Field(description="User role")
    status: SessionStatus = Field(description="Session status")
    expires_at: datetime = Field(description="Session expiration")
    last_activity: datetime = Field(description="Last activity timestamp")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")
    is_current: bool = Field(
        default=False, description="Whether this is the current session"
    )


class TokenResponse(BaseResponse):
    """Response containing authentication tokens"""

    access_token: str = Field(description="Access token for API requests")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    scope: Optional[str] = Field(None, description="Token scope")

    class Config:
        schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": "def456ghi789...",
                "scope": "read write",
            }
        }


class OAuth2CallbackRequest(BaseRequest):
    """Request for OAuth2 callback handling"""

    code: str = Field(..., description="Authorization code from OAuth provider")
    state: str = Field(..., description="State parameter for CSRF protection")
    provider: OAuth2Provider = Field(..., description="OAuth2 provider")
    redirect_uri: Optional[str] = Field(
        None, description="Redirect URI used in auth request"
    )


class TwoFactorSetupRequest(BaseRequest):
    """Request to set up 2FA for user account"""

    password: str = Field(..., description="Current password for verification")
    method: str = Field(
        default="totp",
        pattern="^(totp|sms|email)$",
        description="2FA method: totp, sms, or email",
    )
    phone_number: Optional[str] = Field(
        None,
        pattern="^\\+?[1-9]\\d{1,14}$",
        description="Phone number for SMS 2FA (E.164 format)",
    )

    @validator("phone_number")
    def validate_phone_for_sms(cls, v, values):
        """Require phone number for SMS 2FA"""
        if values.get("method") == "sms" and not v:
            raise ValueError("Phone number is required for SMS 2FA")
        return v


class TwoFactorSetupResponse(BaseResponse):
    """Response for 2FA setup"""

    secret_key: Optional[str] = Field(None, description="TOTP secret key")
    qr_code_url: Optional[str] = Field(None, description="QR code image URL for TOTP")
    backup_codes: Optional[List[str]] = Field(None, description="One-time backup codes")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "secret_key": "JBSWY3DPEHPK3PXP",
                "qr_code_url": "/api/auth/2fa/qr/abc123",
                "backup_codes": ["123456789", "987654321"],
            }
        }


class TwoFactorVerifyRequest(BaseRequest):
    """Request to verify 2FA code"""

    code: str = Field(
        ..., pattern="^[0-9]{6}$", description="6-digit verification code"
    )
    backup_code: bool = Field(
        default=False, description="Whether this is a backup code"
    )


class PasswordResetRequest(BaseRequest):
    """Request to reset password"""

    email: EmailStr = Field(..., description="User email address")

    @validator("email")
    def validate_email_format(cls, v):
        """Normalize email address"""
        return v.lower().strip()


class PasswordResetConfirmRequest(BaseRequest):
    """Request to confirm password reset"""

    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ..., min_length=8, max_length=100, description="New password"
    )
    confirm_password: str = Field(
        ..., min_length=8, max_length=100, description="Password confirmation"
    )

    @validator("confirm_password")
    def validate_passwords_match(cls, v, values):
        """Ensure passwords match"""
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class SessionListResponse(BaseResponse):
    """Response containing list of user sessions"""

    sessions: List[UserSessionResponse] = Field(description="List of active sessions")
    total_count: int = Field(description="Total number of sessions")
    current_session_id: str = Field(description="Current session ID")


class PermissionResponse(BaseResponse):
    """Response containing user permissions"""

    user_id: int = Field(description="User ID")
    role: UserRole = Field(description="User role")
    permissions: List[str] = Field(description="List of specific permissions")
    granted_at: datetime = Field(description="When permissions were granted")
    expires_at: Optional[datetime] = Field(None, description="Permission expiration")


class AuthStatsResponse(BaseResponse):
    """Response containing authentication statistics"""

    total_users: int = Field(ge=0, description="Total registered users")
    active_sessions: int = Field(ge=0, description="Currently active sessions")
    recent_logins: int = Field(ge=0, description="Logins in the last 24 hours")
    failed_attempts: int = Field(ge=0, description="Failed login attempts in last hour")
    oauth_users: Dict[str, int] = Field(description="Count of users by OAuth provider")
    two_factor_enabled: int = Field(ge=0, description="Users with 2FA enabled")


class LogoutRequest(BaseRequest):
    """Request to logout (optional parameters)"""

    all_sessions: bool = Field(default=False, description="Logout from all sessions")
    session_id: Optional[str] = Field(
        None, description="Specific session ID to logout (admin only)"
    )


# Export all authentication models
__all__ = [
    "UserRole",
    "OAuth2Provider",
    "SessionStatus",
    "LoginRequest",
    "LoginResponse",
    "CredentialsRequest",
    "UserSessionResponse",
    "TokenResponse",
    "OAuth2CallbackRequest",
    "TwoFactorSetupRequest",
    "TwoFactorSetupResponse",
    "TwoFactorVerifyRequest",
    "PasswordResetRequest",
    "PasswordResetConfirmRequest",
    "SessionListResponse",
    "PermissionResponse",
    "AuthStatsResponse",
    "LogoutRequest",
]
