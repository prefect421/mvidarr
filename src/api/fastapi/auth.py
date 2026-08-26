"""
FastAPI Authentication API for MVidarr
Session-based authentication using SimpleAuthService and SessionStore.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_admin
from src.database.connection import get_db_session
from src.database.models import UserRole
from src.services.audit_service import (
    AuditEventType,
    AuditService,
    log_login_failed,
    log_login_success,
    log_logout,
    log_oauth_login_failed,
    log_oauth_login_success,
)
from src.services.oauth_service import oauth_service
from src.services.session_store import SessionStore
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
# Role / permission helpers
# ====================================


def role_permissions(role_value: Optional[str]) -> dict:
    """
    Derive the API's coarse permission flags from a session's real role.

    Fails closed: an unknown/missing role is treated as READONLY.

    can_admin is deliberately ADMIN-only — stricter than
    User.can_access_admin() (ADMIN + MANAGER) — because the branch's actual
    admin gate (auth_dependencies.require_admin) is ADMIN-only. Advertising
    can_admin to a MANAGER would surface UI the backend then 403s.

    can_modify / can_delete mirror User.can_modify_content() /
    User.can_delete_content() so the login responses agree with the
    model-derived permissions returned by the OAuth callback.
    """
    role = role_value if role_value in {r.value for r in UserRole} else None
    if role is None:
        role = UserRole.READONLY.value

    return {
        "role": role,
        "can_admin": role == UserRole.ADMIN.value,
        "can_modify": role
        in (UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.USER.value),
        "can_delete": role in (UserRole.ADMIN.value, UserRole.MANAGER.value),
    }


def _session_role(session_token: str) -> Optional[str]:
    """Read the real role off a freshly created session, if resolvable."""
    try:
        data = SessionStore.validate_session(session_token)
        if data:
            return data.get("role")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not resolve session role: {e}")
    return None


# ====================================
# Authentication Endpoints
# ====================================


@router.post("/simple-login")
async def simple_login(
    login_data: LoginRequest,
    request: Request,
    session: Session = Depends(get_db_session),
):
    """Simple login endpoint using SimpleAuthService"""
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
            from src.database.models import User

            user = session.query(User).filter(User.username == username).first()
            if user and user.two_factor_enabled:
                from fastapi.responses import JSONResponse

                from src.services.two_factor_service import TwoFactorService

                ticket = TwoFactorService.create_pending_ticket(user.id)
                AuditService.log_event(
                    AuditEventType.TWO_FACTOR_REQUIRED,
                    "Password verified; two-factor authentication required to complete login",
                    user_id=user.id,
                    username=user.username,
                )
                return JSONResponse(
                    status_code=202,
                    content={
                        "success": False,
                        "requires_2fa": True,
                        "ticket": ticket,
                        "message": "Two-factor authentication required",
                    },
                )
            elif user is None:
                logger.warning(
                    f"SimpleAuthService authenticated '{username}' but no matching "
                    "User row exists — 2FA check skipped"
                )

            # Create real session via SessionStore
            ip_address = request.client.host if request.client else "unknown"
            session_token = SessionStore.create_session(username, ip_address)

            # Create response with session cookie
            from fastapi.responses import JSONResponse

            permissions = role_permissions(_session_role(session_token))

            response_data = {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": user.id if user else 1,
                    "username": username,
                    "email": f"{username}@mvidarr.local",
                    **permissions,
                },
                "session": {"token": session_token},
                "redirect_url": "/dashboard",
            }

            response = JSONResponse(content=response_data)
            is_https = request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                key="session_token",
                value=session_token,
                max_age=86400,  # 24 hours
                httponly=True,
                secure=is_https,
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
    session: Session = Depends(get_db_session),
):
    """User login endpoint using SimpleAuthService"""
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

        # Authenticate via SimpleAuthService
        from src.services.simple_auth_service import SimpleAuthService

        success, message = SimpleAuthService.authenticate(username, password)

        if success:
            from src.database.models import User

            user = session.query(User).filter(User.username == username).first()
            if user and user.two_factor_enabled:
                from fastapi.responses import JSONResponse

                from src.services.two_factor_service import TwoFactorService

                ticket = TwoFactorService.create_pending_ticket(user.id)
                AuditService.log_event(
                    AuditEventType.TWO_FACTOR_REQUIRED,
                    "Password verified; two-factor authentication required to complete login",
                    user_id=user.id,
                    username=user.username,
                )
                return JSONResponse(
                    status_code=202,
                    content={
                        "success": False,
                        "requires_2fa": True,
                        "ticket": ticket,
                        "message": "Two-factor authentication required",
                    },
                )
            elif user is None:
                logger.warning(
                    f"SimpleAuthService authenticated '{username}' but no matching "
                    "User row exists — 2FA check skipped"
                )

            # Create real session
            session_token = SessionStore.create_session(username, ip_address)

            # Log successful login
            from types import SimpleNamespace

            user_for_logging = SimpleNamespace(
                id=1,
                username=username,
                email=f"{username}@mvidarr.local",
            )
            log_login_success(user_for_logging)

            from fastapi.responses import JSONResponse

            permissions = role_permissions(_session_role(session_token))

            response_data = {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": user.id if user else 1,
                    "username": username,
                    "email": f"{username}@mvidarr.local",
                    **permissions,
                },
                "session": {"token": session_token},
            }

            response = JSONResponse(content=response_data)
            is_https = request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                key="session_token",
                value=session_token,
                max_age=86400,
                httponly=True,
                secure=is_https,
                samesite="lax",
            )
            return response

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
async def logout(request: Request):
    """User logout endpoint"""
    try:
        session_token = request.cookies.get("session_token")

        if session_token:
            # Validate to get username for logging
            user_data = SessionStore.validate_session(session_token)
            if user_data:
                from types import SimpleNamespace

                user_for_logging = SimpleNamespace(
                    id=user_data.get("user_id", 1),
                    username=user_data.get("username", "unknown"),
                    email=f"{user_data.get('username', 'unknown')}@mvidarr.local",
                )
                log_logout(user_for_logging)

            # Destroy the session
            SessionStore.destroy_session(session_token)

        from fastapi.responses import JSONResponse

        response = JSONResponse(
            content={"success": True, "message": "Logged out successfully"}
        )
        response.delete_cookie("session_token")
        return response

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Logout failed"
        )


@router.get("/check")
async def check_auth(request: Request):
    """Check authentication status"""
    try:
        session_token = request.cookies.get("session_token")

        if session_token:
            user_data = SessionStore.validate_session(session_token)
            if user_data:
                username = user_data.get("username", "admin")
                return {
                    "authenticated": True,
                    "user": {
                        "id": user_data.get("user_id", 1),
                        "username": username,
                        "email": f"{username}@mvidarr.local",
                        **role_permissions(user_data.get("role")),
                    },
                }

        return {"authenticated": False}

    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return {"authenticated": False}


@router.get("/session")
async def get_session_info(request: Request):
    """Get current session information"""
    try:
        session_token = request.cookies.get("session_token")

        if not session_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="No active session"
            )

        user_data = SessionStore.validate_session(session_token)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session invalid or expired",
            )

        permissions = role_permissions(user_data.get("role"))

        return {
            "session": {
                "token_preview": session_token[:16] + "...",
                "status": "active",
            },
            "user": {
                "id": user_data.get("user_id", 1),
                "username": user_data.get("username", "admin"),
                "role": permissions["role"],
            },
            "permissions": {
                "can_admin": permissions["can_admin"],
                "can_modify": permissions["can_modify"],
                "can_delete": permissions["can_delete"],
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
async def oauth_login(provider: str, request: Request):
    """Initiate OAuth login flow"""
    try:
        success, auth_url, state = oauth_service.initiate_oauth_flow(provider)

        if success:
            AuditService.log_oauth_event(
                AuditEventType.OAUTH_LOGIN_INITIATED,
                "OAuth login flow initiated",
                provider=provider,
                success=True,
            )

            from fastapi.responses import JSONResponse

            response = JSONResponse(content={"auth_url": auth_url, "state": state})
            is_https = request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                key="oauth_state",
                value=state,
                max_age=600,  # 10 minutes — matches the old dict's expiry window
                httponly=True,
                secure=is_https,
                samesite="lax",
            )
            return response
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
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle OAuth callback"""
    # This endpoint is only ever reached via a real, top-level browser
    # navigation — the OAuth provider's own server-side redirect after
    # the user authorizes (or denies) access, not a fetch()/XHR call
    # from MVidarr's frontend JS. Every failure path below redirects to
    # the login page with a readable reason instead of returning a raw
    # JSON error body, which previously left the user staring at a JSON
    # blob (#353 — same root cause as #347's success-path fix).
    from fastapi.responses import RedirectResponse

    def _oauth_error_redirect(reason: str) -> RedirectResponse:
        from urllib.parse import quote

        return RedirectResponse(
            url=f"/auth/login?oauth_error={quote(reason)}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        if error:
            log_oauth_login_failed(provider, f"OAuth provider error: {error}")
            return _oauth_error_redirect(f"OAuth error: {error}")

        if not code or not state:
            log_oauth_login_failed(provider, "Missing authorization code or state")
            return _oauth_error_redirect("Missing authorization code or state")

        cookie_state = request.cookies.get("oauth_state")
        if not cookie_state or cookie_state != state:
            log_oauth_login_failed(
                provider, "State parameter mismatch - possible CSRF attack"
            )
            return _oauth_error_redirect(
                "Invalid state parameter - possible CSRF attack"
            )

        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent")
        success, message, user, session_obj = oauth_service.handle_oauth_callback(
            provider, code, state, ip_address=ip_address, user_agent=user_agent
        )

        if success and user and session_obj:
            # Create session via SessionStore
            ip_address = request.client.host if request.client else "unknown"
            session_token = SessionStore.create_session(user.username, ip_address)

            log_oauth_login_success(user, provider)

            response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
            is_https = request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                key="session_token",
                value=session_token,
                max_age=86400,
                httponly=True,
                secure=is_https,
                samesite="lax",
            )
            response.delete_cookie("oauth_state")
            return response
        else:
            log_oauth_login_failed(provider, message)
            return _oauth_error_redirect(message)

    except Exception as e:
        # Deliberately generic — unlike the branches above, `e` is not
        # a message this codebase generated, so its text must not leak
        # into a redirect URL the user's browser will show.
        logger.error(f"OAuth callback error: {e}")
        log_oauth_login_failed(provider, str(e))
        return _oauth_error_redirect("OAuth authentication failed")


# ====================================
# Credentials Management
# ====================================


@router.get("/credentials")
async def get_credentials(current_user: dict = Depends(require_admin)):
    """Get current stored username for simple auth (requires ADMIN role).

    Leaked the instance-wide login username to any unauthenticated caller
    before this fix. Only ever called from the admin-only credentials-
    change form on settings.html (frontend/static/main.js's
    loadCurrentCredentials()), matching its POST sibling below -- never
    from the login page.
    """
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
async def update_credentials(
    credentials: CredentialsRequest,
    current_user: dict = Depends(require_admin),
):
    """Update username and password for simple auth (requires ADMIN role).

    This changes the credential SimpleAuthService authenticates every
    browser login against — not just the caller's own account — so it must
    be gated on role, not merely on being logged in (found during dev
    testing ahead of v1.0.0: any authenticated USER/MANAGER/READONLY
    session could previously change the instance-wide login credentials).
    """
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


@router.get("/user")
async def get_current_user_info(request: Request):
    """Get current authenticated user information"""
    try:
        session_token = request.cookies.get("session_token")
        if session_token:
            user_data = SessionStore.validate_session(session_token)
            if user_data:
                username = user_data.get("username", "admin")
                return {
                    "success": True,
                    "user": {
                        "id": user_data.get("user_id", 1),
                        "username": username,
                        "email": f"{username}@mvidarr.local",
                        **role_permissions(user_data.get("role")),
                    },
                }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {e}")
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
            detail="Authentication system unhealthy",
        )


# ====================================
# Legacy Router Endpoints (for backward compatibility)
# ====================================


@legacy_router.get("/credentials")
async def get_credentials_legacy(current_user: dict = Depends(require_admin)):
    """Get current stored username for simple auth (legacy endpoint,
    requires ADMIN role -- see get_credentials() above)."""
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
