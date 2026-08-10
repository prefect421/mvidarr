"""
FastAPI Two-Factor Authentication Router
Migrated from Flask src/api/two_factor.py - Complete 2FA functionality
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import (
    require_admin,
    require_authentication,
)
from src.database.connection import get_db_session
from src.database.models import User
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.two_factor_service import TwoFactorService

logger = logging.getLogger("mvidarr.fastapi.two_factor")

router = APIRouter(
    prefix="/2fa",
    tags=["two-factor-auth"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class TwoFactorSetupResponse(BaseModel):
    """Two-factor authentication setup response"""

    success: bool
    message: str
    setup_data: Optional[Dict[str, Any]] = None


class TokenVerificationRequest(BaseModel):
    """Token verification request model"""

    token: str = Field(..., min_length=6, max_length=6, pattern="^[0-9]+$")


class TwoFactorStatusResponse(BaseModel):
    """Two-factor authentication status response"""

    enabled: bool
    last_used: Optional[datetime] = None
    backup_codes_remaining: int = 0
    setup_date: Optional[datetime] = None


class DisableTwoFactorRequest(BaseModel):
    """Disable two-factor authentication request"""

    password: str = Field(..., min_length=1)
    token: Optional[str] = None


class LoginVerificationRequest(BaseModel):
    """Login verification request model"""

    username: str = Field(..., min_length=1)
    token: str = Field(..., min_length=6, max_length=6)
    backup_code: Optional[str] = None


# ========================================================================================
# TWO-FACTOR AUTHENTICATION SETUP ENDPOINTS
# ========================================================================================


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(
    request: Request,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """2FA setup page"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if 2FA is already enabled
        if user.two_factor_enabled:
            # Return redirect response or info message
            return JSONResponse(
                content={
                    "message": "Two-factor authentication is already enabled for your account.",
                    "redirect": "/profile",
                },
                status_code=200,
            )

        # In a real implementation, this would render the 2FA setup template
        # For now, return setup instructions
        return JSONResponse(
            content={
                "message": "2FA setup page",
                "user_id": user.id,
                "username": user.username,
                "setup_required": True,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA setup page error: {e}")
        raise HTTPException(status_code=500, detail="Error loading 2FA setup")


@router.post("/api/setup", response_model=TwoFactorSetupResponse)
async def initiate_setup(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Initiate 2FA setup"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.two_factor_enabled:
            raise HTTPException(
                status_code=400, detail="Two-factor authentication is already enabled"
            )

        success, message, setup_data = TwoFactorService.setup_two_factor(user.id)

        if success:
            logger.info(f"2FA setup initiated for user {current_user.get('username')}")

            return TwoFactorSetupResponse(
                success=True,
                message=message,
                setup_data={
                    "qr_code": setup_data["qr_code"],
                    "manual_entry_key": setup_data["manual_entry_key"],
                    "backup_codes": setup_data["backup_codes"],
                },
            )
        else:
            raise HTTPException(status_code=400, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA setup initiation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate 2FA setup")


@router.post("/api/verify-setup")
async def verify_setup(
    token_request: TokenVerificationRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Verify and confirm 2FA setup"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        success, message = TwoFactorService.confirm_two_factor_setup(
            user.id, token_request.token
        )

        if success:
            logger.info(f"2FA setup verified for user {current_user.get('username')}")

            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=400, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA setup verification error: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify 2FA setup")


# ========================================================================================
# TWO-FACTOR AUTHENTICATION MANAGEMENT
# ========================================================================================


@router.post("/api/disable")
async def disable_two_factor(
    disable_request: DisableTwoFactorRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Disable 2FA for current user"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verify password
        username = current_user.get("username", "admin")
        auth_success, _, _, _, _ = AuthService.authenticate_user(
            username, disable_request.password, "127.0.0.1", "FastAPI-2FA-Disable"
        )

        if not auth_success:
            raise HTTPException(status_code=400, detail="Invalid password")

        # Disable 2FA
        success, message = TwoFactorService.disable_two_factor(
            user.id, disable_request.token
        )

        if success:
            logger.info(f"2FA disabled for user {current_user.get('username')}")

            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=400, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA disable error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable 2FA")


@router.post("/api/regenerate-codes")
async def regenerate_backup_codes(
    token_request: TokenVerificationRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Regenerate backup codes"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.two_factor_enabled:
            raise HTTPException(
                status_code=400, detail="Two-factor authentication is not enabled"
            )

        success, message, backup_codes = TwoFactorService.regenerate_backup_codes(
            user.id, token_request.token
        )

        if success:
            logger.info(
                f"Backup codes regenerated for user {current_user.get('username')}"
            )

            return {"success": True, "message": message, "backup_codes": backup_codes}
        else:
            raise HTTPException(status_code=400, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup codes regeneration error: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate backup codes")


@router.get("/api/status", response_model=TwoFactorStatusResponse)
async def get_two_factor_status(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get 2FA status for current user"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get user from database
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get status from service
        status_data = TwoFactorService.get_user_two_factor_status(user.id)

        return TwoFactorStatusResponse(
            enabled=status_data.get("enabled", False),
            last_used=status_data.get("last_used"),
            backup_codes_remaining=status_data.get("backup_codes_remaining", 0),
            setup_date=status_data.get("setup_date"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get 2FA status")


# ========================================================================================
# TWO-FACTOR AUTHENTICATION VERIFICATION (LOGIN)
# ========================================================================================


@router.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request):
    """2FA verification page for login"""
    try:
        # In a real implementation, this would render the 2FA verification template
        # For now, return verification instructions
        return JSONResponse(
            content={
                "message": "2FA verification required",
                "instructions": "Enter your 2FA token to complete login",
            }
        )

    except Exception as e:
        logger.error(f"2FA verify page error: {e}")
        raise HTTPException(status_code=500, detail="Error loading 2FA verification")


@router.post("/api/verify-login")
async def verify_login(
    verification_request: LoginVerificationRequest,
    request: Request,
    session: Session = Depends(get_db_session),
):
    """Complete login by verifying a 2FA token for a user pending verification"""
    try:
        user = (
            session.query(User)
            .filter(User.username == verification_request.username)
            .first()
        )
        if not user or not user.two_factor_enabled:
            raise HTTPException(status_code=401, detail="Invalid verification request")

        success, message = TwoFactorService.verify_two_factor_login(
            user.id, verification_request.token
        )

        if not success:
            raise HTTPException(status_code=401, detail=message)

        from src.services.session_store import SessionStore

        ip_address = request.client.host if request.client else "unknown"
        session_token = SessionStore.create_session(user.username, ip_address)

        from fastapi.responses import JSONResponse

        response = JSONResponse(
            content={"success": True, "message": "Login successful"}
        )
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA login verification error: {e}")
        raise HTTPException(
            status_code=500, detail="Verification failed due to internal error"
        )


# ========================================================================================
# ADMIN ENDPOINTS FOR 2FA MANAGEMENT
# ========================================================================================


@router.post("/admin/users/{user_id}/disable")
async def admin_disable_user_two_factor(
    user_id: int,
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Admin endpoint to disable 2FA for a user"""
    try:
        # Get target user
        target_user = session.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        if not target_user.two_factor_enabled:
            raise HTTPException(
                status_code=400,
                detail="Two-factor authentication is not enabled for this user",
            )

        # Admin disable (bypasses token verification)
        success, message = TwoFactorService.admin_disable_two_factor(user_id)

        if success:
            # Log admin action
            AuditService.log_event(
                event_type="2FA_ADMIN_DISABLED",
                user_id=current_user.get("user_id"),
                details={
                    "target_user_id": user_id,
                    "target_username": target_user.username,
                },
            )

            logger.info(
                f"Admin {current_user.get('username')} disabled 2FA for user {target_user.username}"
            )

            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin 2FA disable error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable 2FA")


@router.post("/admin/users/{user_id}/regenerate-codes")
async def admin_regenerate_user_backup_codes(
    user_id: int,
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Admin endpoint to regenerate backup codes for a user"""
    try:
        # Get target user
        target_user = session.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        if not target_user.two_factor_enabled:
            raise HTTPException(
                status_code=400,
                detail="Two-factor authentication is not enabled for this user",
            )

        # Admin regenerate (bypasses token verification)
        success, message, backup_codes = TwoFactorService.admin_regenerate_backup_codes(
            user_id
        )

        if success:
            # Log admin action
            AuditService.log_event(
                event_type="2FA_ADMIN_CODES_REGENERATED",
                user_id=current_user.get("user_id"),
                details={
                    "target_user_id": user_id,
                    "target_username": target_user.username,
                },
            )

            logger.info(
                f"Admin {current_user.get('username')} regenerated backup codes for user {target_user.username}"
            )

            return {"success": True, "message": message, "backup_codes": backup_codes}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin backup codes regeneration error: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate backup codes")


@router.get("/admin/users/{user_id}/status")
async def admin_get_user_two_factor_status(
    user_id: int,
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Admin endpoint to get 2FA status for a user"""
    try:
        # Get target user
        target_user = session.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get status from service
        status_data = TwoFactorService.get_user_two_factor_status(user_id)

        return {
            "user_id": user_id,
            "username": target_user.username,
            "two_factor_status": {
                "enabled": status_data.get("enabled", False),
                "last_used": status_data.get("last_used"),
                "backup_codes_remaining": status_data.get("backup_codes_remaining", 0),
                "setup_date": status_data.get("setup_date"),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin 2FA status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get 2FA status")


@router.get("/admin/overview")
async def admin_two_factor_overview(
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Admin overview of 2FA usage across all users"""
    try:
        # Get 2FA statistics
        overview_data = TwoFactorService.get_admin_overview()

        return {
            "two_factor_overview": overview_data,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Admin 2FA overview error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get 2FA overview")
