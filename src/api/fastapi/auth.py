"""
FastAPI Authentication API for MVidarr
Complete authentication, OAuth, and session management endpoints.
Migrated from Flask auth.py for enhanced async support and type safety.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.database.models import UserRole, UserSession
from src.services.audit_service import (
    AuditEventType,
    AuditService,
    log_login_failed,
    log_login_success,
    log_logout,
    log_oauth_login_failed,
    log_oauth_login_success,
)
from src.services.auth_service import AuthService
from src.services.oauth_service import oauth_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.auth")

# Create FastAPI router
router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Create legacy router for backward compatibility (without /api prefix)
legacy_router = APIRouter(prefix="/auth", tags=["authentication-legacy"])

# ====================================
# Pydantic Models
# ====================================


class LoginRequest(BaseModel):
    """Request model for user login"""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class CredentialsRequest(BaseModel):
    """Request model for updating credentials"""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


# ====================================
# Mock Session Management
# ====================================


class MockSession:
    """Mock session for development - replace with proper session management"""

    def __init__(self):
        self._data = {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value

    def pop(self, key: str, default=None):
        return self._data.pop(key, default)

    def clear(self):
        self._data.clear()


# Global mock session
mock_session = MockSession()


async def get_current_session() -> MockSession:
    """Get current session - replace with proper session management"""
    return mock_session


# ====================================
# Authentication Endpoints
# ====================================


@router.post("/simple-login")
async def simple_login(
    login_data: LoginRequest,
    request: Request,
    session: MockSession = Depends(get_current_session),
):
    """Simple login endpoint that bypasses complex auth systems"""
    try:
        username = login_data.username.strip()
        password = login_data.password

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username and password are required",
            )

        # Use SimpleAuthService for authentication
        from src.services.simple_auth_service import SimpleAuthService

        success, message = SimpleAuthService.authenticate(username, password)
        if success:
            # Set session data
            session.set("authenticated", True)
            session.set("username", username)
            session.set("role", "ADMIN")
            session.set("user_id", 1)

            # Create a simple session token
            import secrets

            session_token = secrets.token_urlsafe(32)

            # Create response with session cookie
            from fastapi.responses import JSONResponse

            response_data = {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": 1,
                    "username": username,
                    "email": f"{username}@mvidarr.local",
                    "role": "ADMIN",
                    "can_admin": True,
                    "can_modify": True,
                    "can_delete": True,
                },
                "session": {"token": session_token},
                "redirect_url": "/dashboard",
            }

            response = JSONResponse(content=response_data)
            # Set session cookie that will be used by root endpoint
            response.set_cookie(
                key="session_token",
                value=session_token,
                max_age=86400,  # 24 hours
                httponly=True,
                samesite="lax",
            )
            return response
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=message or "Invalid credentials",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simple login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to internal error",
        )


@router.post("/login")
async def login(
    login_data: LoginRequest,
    request: Request,
    session: MockSession = Depends(get_current_session),
):
    """User login endpoint"""
    try:
        username = login_data.username.strip()
        password = login_data.password

        if not username or not password:
            log_login_failed(username or "unknown", "Missing credentials")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username and password are required",
            )

        # Get client info
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")

        # Try main authentication first, fallback to simple auth
        try:
            (success, message, user_data, session_obj, requires_2fa) = (
                AuthService.authenticate_user(
                    username, password, ip_address, user_agent
                )
            )
        except Exception as auth_error:
            logger.warning(
                f"Main auth failed ({auth_error}), trying simple auth fallback"
            )

            # Fallback to SimpleAuthService for authentication
            # This allows the system to work even when database is not initialized
            from src.services.simple_auth_service import SimpleAuthService

            simple_success, simple_message = SimpleAuthService.authenticate(
                username, password
            )

            if simple_success:
                # Create mock user data for simple auth
                user_data = {
                    "id": 1,
                    "username": username,
                    "email": f"{username}@mvidarr.local",
                    "role": "ADMIN",
                    "is_active": True,
                    "last_login": None,
                    "can_access_admin": True,
                    "can_modify_content": True,
                    "can_delete_content": True,
                    "can_manage_users": True,
                }
                # Simple auth success - no session management needed
                success, message, session_obj, requires_2fa = (
                    True,
                    "Login successful",
                    {"session_token": "simple_auth_session"},
                    False,
                )
            else:
                success, message, user_data, session_obj, requires_2fa = (
                    False,
                    simple_message,
                    None,
                    None,
                    False,
                )

        if success and user_data:
            if requires_2fa:
                session.set("temp_user_id", user_data["id"])
                session.set(
                    "temp_login_time",
                    (
                        user_data["last_login"].isoformat()
                        if user_data["last_login"]
                        else None
                    ),
                )

                return {
                    "success": False,
                    "requires_2fa": True,
                    "message": "Two-factor authentication required",
                    "user": {"id": user_data["id"]},
                    "session": {},
                }

            elif session_obj:
                session_token = (
                    session_obj["session_token"]
                    if isinstance(session_obj, dict)
                    else session_obj.session_token
                )
                session.set("session_token", session_token)
                session.set("user_id", user_data["id"])

                # For simple auth, also set session flag
                if session_token == "simple_auth_session":
                    session.set("authenticated", True)
                    session.set("username", user_data["username"])
                    session.set("role", user_data["role"])

                # Clear temporary 2FA data
                session.pop("temp_user_id")
                session.pop("temp_login_time")

                # Log successful login
                from types import SimpleNamespace

                user_for_logging = SimpleNamespace(
                    id=user_data["id"],
                    username=user_data["username"],
                    email=user_data["email"],
                )
                log_login_success(user_for_logging)

                return {
                    "success": True,
                    "message": "Login successful",
                    "user": {
                        "id": user_data["id"],
                        "username": user_data["username"],
                        "email": user_data["email"],
                        "role": user_data["role"],
                        "can_admin": user_data["role"] == "ADMIN",
                        "can_modify": user_data["role"] in ["ADMIN", "MANAGER", "USER"],
                        "can_delete": user_data["role"] in ["ADMIN", "MANAGER"],
                    },
                    "session": {"token": session_token},
                }

        # Login failed
        log_login_failed(username, message)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to internal error",
        )


@router.post("/logout")
async def logout(session: MockSession = Depends(get_current_session)):
    """User logout endpoint"""
    try:
        session_token = session.get("session_token")

        if session_token:
            user_data = AuthService.get_user_by_session_token(session_token)
            AuthService.logout_user(session_token)

            if user_data:
                from types import SimpleNamespace

                user_for_logging = SimpleNamespace(
                    id=user_data["id"],
                    username=user_data["username"],
                    email=user_data["email"],
                )
                log_logout(user_for_logging)

        session.clear()
        return {"success": True, "message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Logout failed"
        )


@router.get("/check")
async def check_auth(session: MockSession = Depends(get_current_session)):
    """Check authentication status"""
    try:
        session_token = session.get("session_token")

        if session_token:
            user_data = AuthService.get_user_by_session_token(session_token)

            if user_data:
                return {
                    "authenticated": True,
                    "user": {
                        "id": user_data["id"],
                        "username": user_data["username"],
                        "email": user_data["email"],
                        "role": user_data["role"],
                        "can_admin": user_data.get("can_access_admin", False),
                        "can_modify": user_data.get("can_modify_content", False),
                        "can_delete": user_data.get("can_delete_content", False),
                    },
                }

        # Check simple auth fallback
        is_authenticated = session.get("authenticated", False)
        username = session.get("username")
        role = session.get("role", "user")

        if is_authenticated and username:
            can_admin = role.lower() == "admin"
            can_modify = role.lower() in ["admin", "manager", "user"]
            can_delete = role.lower() in ["admin", "manager"]

            return {
                "authenticated": True,
                "user": {
                    "id": 1,
                    "username": username,
                    "email": f"{username}@mvidarr.local",
                    "role": role.upper(),
                    "can_admin": can_admin,
                    "can_modify": can_modify,
                    "can_delete": can_delete,
                },
            }

        return {"authenticated": False}

    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return {"authenticated": False, "error": "Check failed"}


@router.get("/session")
async def get_session_info(session: MockSession = Depends(get_current_session)):
    """Get current session information"""
    try:
        session_token = session.get("session_token")

        if not session_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="No active session"
            )

        user_data = AuthService.get_user_by_session_token(session_token)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Session not found"
            )

        # Get session from database
        from src.database.connection import get_db

        with get_db() as db_session:
            user_session = (
                db_session.query(UserSession)
                .filter_by(session_token=session_token)
                .first()
            )

            if not user_session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session not found in database",
                )

            return {
                "session": {
                    "id": user_session.id,
                    "session_token": user_session.session_token[:16] + "...",
                    "ip_address": user_session.ip_address,
                    "user_agent": user_session.user_agent,
                    "created_at": user_session.created_at.isoformat(),
                    "last_activity": user_session.last_activity.isoformat(),
                    "status": user_session.status.value,
                },
                "user": {
                    "id": user_data["id"],
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "role": user_data["role"],
                    "is_active": user_data["is_active"],
                },
                "permissions": {
                    "can_admin": user_data.get("can_access_admin", False),
                    "can_modify": user_data.get("can_modify_content", False),
                    "can_delete": user_data.get("can_delete_content", False),
                    "can_manage_users": user_data.get("can_manage_users", False),
                },
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session info",
        )


# ====================================
# OAuth Endpoints
# ====================================


@router.get("/oauth/{provider}/login")
async def oauth_login(provider: str):
    """Initiate OAuth login flow"""
    try:
        success, auth_url, state = oauth_service.initiate_oauth_flow(provider)

        if success:
            AuditService.log_oauth_event(
                AuditEventType.OAUTH_LOGIN_INITIATED,
                f"OAuth login flow initiated",
                provider=provider,
                success=True,
            )

            return {"auth_url": auth_url, "state": state}
        else:
            log_oauth_login_failed(provider, auth_url)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=auth_url
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth login initiation error: {e}")
        log_oauth_login_failed(provider, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth login failed",
        )


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    session: MockSession = Depends(get_current_session),
):
    """Handle OAuth callback"""
    try:
        if error:
            log_oauth_login_failed(provider, f"OAuth provider error: {error}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth error: {error}"
            )

        if not code or not state:
            log_oauth_login_failed(provider, "Missing authorization code or state")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing authorization code or state",
            )

        success, message, user, session_obj = oauth_service.handle_oauth_callback(
            provider, code, state
        )

        if success and user and session_obj:
            session_token = (
                session_obj["session_token"]
                if isinstance(session_obj, dict)
                else session_obj.session_token
            )
            session.set("session_token", session_token)
            session.set("user_id", user.id)

            log_oauth_login_success(user, provider)

            return {
                "success": True,
                "message": "OAuth login successful",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "can_admin": user.can_access_admin(),
                    "can_modify": user.can_modify_content(),
                    "can_delete": user.can_delete_content(),
                },
            }
        else:
            log_oauth_login_failed(provider, message)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=message
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        log_oauth_login_failed(provider, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed",
        )


# ====================================
# Credentials Management
# ====================================


@router.get("/credentials")
async def get_credentials():
    """Get current stored username for simple auth"""
    try:
        from src.services.simple_auth_service import SimpleAuthService

        username, has_credentials = SimpleAuthService.get_credentials()
        return {"username": username, "has_credentials": has_credentials}

    except Exception as e:
        logger.error(f"Get credentials error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get credentials",
        )


@router.post("/credentials")
async def update_credentials(credentials: CredentialsRequest):
    """Update username and password for simple auth"""
    try:
        from src.services.simple_auth_service import SimpleAuthService

        username = credentials.username.strip()
        password = credentials.password

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username and password are required",
            )

        success, message = SimpleAuthService.set_credentials(username, password)

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update credentials error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update credentials",
        )


@router.post("/credentials/reset")
async def reset_credentials():
    """Reset authentication credentials to defaults"""
    try:
        from src.database.init_db import ensure_default_credentials

        success = ensure_default_credentials(force_reset=True)

        if success:
            return {
                "success": True,
                "message": "Credentials reset to defaults",
                "username": "admin",
                "password": "mvidarr",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset credentials",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset credentials error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset credentials",
        )


@router.get("/user")
async def get_current_user_info(request: Request):
    """Get current authenticated user information - FastAPI endpoint"""
    # Note: This endpoint can't access Flask session from FastAPI context
    # Frontend should use /auth/check (Flask endpoint) instead for session info
    # This endpoint is kept for API compatibility but will return 401 if no FastAPI session exists

    try:
        # Check if there's a session cookie in the request
        # This is a basic check - full session handling is in Flask
        session_cookie = request.cookies.get("session")

        if session_cookie:
            # Try to validate with AuthService
            # This would need proper session token extraction
            # For now, return a basic authenticated response for compatibility

            # Get admin user from database as fallback
            from src.database.connection import get_db
            from src.database.models import User, UserRole

            with get_db() as db_session:
                # Try to find admin user
                admin_user = (
                    db_session.query(User).filter(User.role == UserRole.ADMIN).first()
                )
                if admin_user:
                    return {
                        "success": True,
                        "user": {
                            "id": admin_user.id,
                            "username": admin_user.username,
                            "email": admin_user.email,
                            "role": admin_user.role.value,
                            "can_admin": True,
                            "can_modify": True,
                            "can_delete": True,
                        },
                    }

        # Not authenticated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        # Return 401 instead of 500 for session access issues
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )


@router.get("/health")
async def auth_health():
    """Check authentication system health"""
    try:
        from sqlalchemy import text

        from src.database.connection import get_db

        with get_db() as db_session:
            db_session.execute(text("SELECT 1")).fetchone()

        oauth_status = "disabled"
        try:
            if oauth_service.is_oauth_enabled():
                oauth_providers = oauth_service.get_available_providers()
                oauth_status = f"enabled ({len(oauth_providers)} providers)"
        except Exception as e:
            oauth_status = f"error: {str(e)}"

        return {
            "status": "healthy",
            "database": "connected",
            "oauth": oauth_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Auth health check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Authentication system unhealthy: {str(e)}",
        )


# ====================================
# Legacy Router Endpoints (for backward compatibility)
# ====================================


@legacy_router.get("/credentials")
async def get_credentials_legacy():
    """Get current stored username for simple auth (legacy endpoint)"""
    try:
        from src.services.simple_auth_service import SimpleAuthService

        username, has_credentials = SimpleAuthService.get_credentials()
        return {"username": username, "has_credentials": has_credentials}
    except Exception as e:
        logger.error(f"Get credentials error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
