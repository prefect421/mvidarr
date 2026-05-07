"""
Two-Factor Authentication Service for MVidarr
Provides TOTP (Time-based One-Time Password) authentication functionality.
"""

import base64
import io
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pyotp
import qrcode

from src.database.connection import get_db
from src.database.models import User
from src.services.audit_service import AuditService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.two_factor")


class TwoFactorService:
    """Two-factor authentication service using TOTP"""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret"""
        return pyotp.random_base32()

    @staticmethod
    def generate_backup_codes(count: int = 8) -> List[str]:
        """Generate backup codes for 2FA recovery"""
        codes = []
        for _ in range(count):
            # Generate 8-character backup code
            code = "".join(
                secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8)
            )
            codes.append(code)
        return codes

    @staticmethod
    def get_qr_code_uri(user: User, secret: str) -> str:
        """Generate QR code URI for TOTP setup"""
        service_name = "MVidarr"
        account_name = f"{user.username}@mvidarr"

        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=account_name, issuer_name=service_name)

    @staticmethod
    def generate_qr_code_image(uri: str) -> str:
        """Generate QR code image as base64 string"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/png;base64,{img_str}"

        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            raise

    @staticmethod
    def verify_totp_token(secret: str, token: str) -> bool:
        """Verify TOTP token"""
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(token, valid_window=1)  # Allow 1 window tolerance
        except Exception as e:
            logger.error(f"Error verifying TOTP token: {e}")
            return False

    @staticmethod
    def setup_two_factor(user_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Initialize 2FA setup for user"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found", None

                if user.two_factor_enabled:
                    return False, "Two-factor authentication is already enabled", None

                # Generate new secret and backup codes
                secret = TwoFactorService.generate_secret()
                backup_codes = TwoFactorService.generate_backup_codes()

                # Generate QR code
                qr_uri = TwoFactorService.get_qr_code_uri(user, secret)
                qr_image = TwoFactorService.generate_qr_code_image(qr_uri)

                # Store secret temporarily (not enabled yet)
                user.two_factor_secret = secret
                user.backup_codes = json.dumps(backup_codes)
                session.commit()

                setup_data = {
                    "secret": secret,
                    "qr_code": qr_image,
                    "backup_codes": backup_codes,
                    "manual_entry_key": secret,
                }

                logger.info(f"2FA setup initiated for user {user.username}")

                return True, "2FA setup initiated", setup_data

        except Exception as e:
            logger.error(f"Error setting up 2FA for user {user_id}: {e}")
            return False, f"Setup failed: {e}", None

    @staticmethod
    def confirm_two_factor_setup(
        user_id: int, token: str, admin_user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Confirm and enable 2FA after user verifies token"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found"

                if user.two_factor_enabled:
                    return False, "Two-factor authentication is already enabled"

                if not user.two_factor_secret:
                    return False, "2FA setup not initiated. Please start setup first."

                # Verify the token
                if not TwoFactorService.verify_totp_token(
                    user.two_factor_secret, token
                ):
                    # Log failed verification attempt
                    AuditService.log_security_event(
                        "2fa_verification_failed",
                        user=user,
                        additional_data={
                            "setup_confirmation": True,
                            "provided_token": token,
                        },
                    )
                    return False, "Invalid verification code. Please try again."

                # Enable 2FA
                user.two_factor_enabled = True
                user.updated_at = datetime.now(timezone.utc)
                session.commit()

                # Log successful 2FA setup
                AuditService.log_user_action(
                    "2fa_enabled",
                    user=user,
                    admin_user_id=admin_user_id,
                    additional_data={
                        "setup_timestamp": datetime.now(timezone.utc).isoformat()
                    },
                )

                logger.info(f"2FA enabled for user {user.username}")

                return True, "Two-factor authentication enabled successfully"

        except Exception as e:
            logger.error(f"Error confirming 2FA setup for user {user_id}: {e}")
            return False, f"Confirmation failed: {e}"

    @staticmethod
    def disable_two_factor(
        user_id: int, password: str, admin_user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Disable 2FA for user (requires password confirmation)"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found"

                if not user.two_factor_enabled:
                    return False, "Two-factor authentication is not enabled"

                # Verify password (unless admin is disabling)
                if admin_user_id is None:
                    from werkzeug.security import check_password_hash

                    if not check_password_hash(user.password_hash, password):
                        AuditService.log_security_event(
                            "2fa_disable_failed",
                            user=user,
                            additional_data={"reason": "incorrect_password"},
                        )
                        return False, "Incorrect password"

                # Disable 2FA
                user.two_factor_enabled = False
                user.two_factor_secret = None
                user.backup_codes = None
                user.updated_at = datetime.now(timezone.utc)
                session.commit()

                # Log 2FA disable
                AuditService.log_user_action(
                    "2fa_disabled",
                    user=user,
                    admin_user_id=admin_user_id,
                    additional_data={
                        "disabled_by_admin": admin_user_id is not None,
                        "disable_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                logger.info(f"2FA disabled for user {user.username}")

                return True, "Two-factor authentication disabled successfully"

        except Exception as e:
            logger.error(f"Error disabling 2FA for user {user_id}: {e}")
            return False, f"Disable failed: {e}"

    @staticmethod
    def verify_two_factor_login(user_id: int, token: str) -> Tuple[bool, str]:
        """Verify 2FA token during login"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found"

                if not user.two_factor_enabled:
                    return False, "Two-factor authentication is not enabled"

                # Check if token is a backup code
                if user.backup_codes:
                    try:
                        backup_codes = (
                            json.loads(user.backup_codes)
                            if isinstance(user.backup_codes, str)
                            else user.backup_codes
                        )
                        if token.upper() in backup_codes:
                            # Remove used backup code
                            backup_codes.remove(token.upper())
                            user.backup_codes = json.dumps(backup_codes)
                            session.commit()

                            # Log backup code usage
                            AuditService.log_security_event(
                                "2fa_backup_code_used",
                                user=user,
                                additional_data={"remaining_codes": len(backup_codes)},
                            )

                            return True, "Backup code accepted"
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Verify TOTP token
                if TwoFactorService.verify_totp_token(user.two_factor_secret, token):
                    AuditService.log_security_event("2fa_login_success", user=user)
                    return True, "Two-factor authentication successful"
                else:
                    AuditService.log_security_event(
                        "2fa_login_failed",
                        user=user,
                        additional_data={"provided_token": token},
                    )
                    return False, "Invalid verification code"

        except Exception as e:
            logger.error(f"Error verifying 2FA login for user {user_id}: {e}")
            return False, f"Verification failed: {e}"

    @staticmethod
    def regenerate_backup_codes(
        user_id: int, password: str, admin_user_id: Optional[int] = None
    ) -> Tuple[bool, str, Optional[List[str]]]:
        """Regenerate backup codes for user"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found", None

                if not user.two_factor_enabled:
                    return False, "Two-factor authentication is not enabled", None

                # Verify password (unless admin is regenerating)
                if admin_user_id is None:
                    from werkzeug.security import check_password_hash

                    if not check_password_hash(user.password_hash, password):
                        return False, "Incorrect password", None

                # Generate new backup codes
                new_codes = TwoFactorService.generate_backup_codes()
                user.backup_codes = json.dumps(new_codes)
                user.updated_at = datetime.now(timezone.utc)
                session.commit()

                # Log backup code regeneration
                AuditService.log_user_action(
                    "2fa_backup_codes_regenerated",
                    user=user,
                    admin_user_id=admin_user_id,
                    additional_data={
                        "regenerated_by_admin": admin_user_id is not None,
                        "regenerate_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                logger.info(f"Backup codes regenerated for user {user.username}")

                return True, "Backup codes regenerated successfully", new_codes

        except Exception as e:
            logger.error(f"Error regenerating backup codes for user {user_id}: {e}")
            return False, f"Regeneration failed: {e}", None

    @staticmethod
    def get_two_factor_status(user_id: int) -> Dict[str, Any]:
        """Get 2FA status for user"""
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return {"error": "User not found"}

                backup_codes_count = 0
                if user.backup_codes:
                    try:
                        backup_codes = (
                            json.loads(user.backup_codes)
                            if isinstance(user.backup_codes, str)
                            else user.backup_codes
                        )
                        backup_codes_count = len(backup_codes) if backup_codes else 0
                    except (json.JSONDecodeError, TypeError):
                        backup_codes_count = 0

                return {
                    "enabled": user.two_factor_enabled,
                    "secret_configured": user.two_factor_secret is not None,
                    "backup_codes_count": backup_codes_count,
                    "setup_pending": user.two_factor_secret is not None
                    and not user.two_factor_enabled,
                }

        except Exception as e:
            logger.error(f"Error getting 2FA status for user {user_id}: {e}")
            return {"error": f"Status check failed: {e}"}

    @staticmethod
    def require_two_factor_for_action(
        user: User, sensitive_action: str = "sensitive_operation"
    ) -> bool:
        """Check if 2FA should be required for a sensitive action"""
        # If user has 2FA enabled, require it for sensitive operations
        if user.two_factor_enabled:
            # Check if user has recently provided 2FA (within last 30 minutes)
            # This would typically be stored in session data
            # For now, always require 2FA for sensitive operations
            return True

        # For admin users without 2FA, consider requiring it for critical operations
        if user.role.value == "ADMIN" and sensitive_action in [
            "delete_user",
            "restart_application",
            "change_critical_settings",
        ]:
            logger.warning(
                f"Admin user {user.username} performing sensitive action without 2FA"
            )
            # Could return True to enforce 2FA for admins

        return False
