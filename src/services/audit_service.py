"""
Audit and security event logging service for MVidarr
Provides comprehensive logging of authentication, authorization, and security events.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from flask import request
from flask import session as flask_session

from src.database.models import User
from src.utils.logger import get_logger

logger = get_logger("mvidarr.audit")


class AuditEventType:
    """Audit event type constants"""

    # Authentication Events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    TWO_FACTOR_REQUIRED = "two_factor_required"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"

    # OAuth Events
    OAUTH_LOGIN_INITIATED = "oauth_login_initiated"
    OAUTH_LOGIN_SUCCESS = "oauth_login_success"
    OAUTH_LOGIN_FAILED = "oauth_login_failed"
    OAUTH_USER_CREATED = "oauth_user_created"
    OAUTH_USER_LINKED = "oauth_user_linked"
    OAUTH_ROLE_UPDATED = "oauth_role_updated"

    # User Management Events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"
    USER_ROLE_CHANGED = "user_role_changed"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    EMAIL_VERIFIED = "email_verified"

    # Authorization Events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_ESCALATION = "permission_escalation"
    ADMIN_ACTION = "admin_action"

    # Security Events
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    CSRF_ATTEMPT = "csrf_attempt"
    SESSION_HIJACK_ATTEMPT = "session_hijack_attempt"

    # Content Events
    CONTENT_CREATED = "content_created"
    CONTENT_UPDATED = "content_updated"
    CONTENT_DELETED = "content_deleted"
    BULK_OPERATION = "bulk_operation"

    # System Events
    SYSTEM_RESTART = "system_restart"
    CONFIGURATION_CHANGED = "configuration_changed"
    MAINTENANCE_MODE = "maintenance_mode"


class AuditService:
    """Central audit and security event logging service"""

    @staticmethod
    def log_event(
        event_type: str,
        message: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        severity: str = "INFO",
    ):
        """
        Log an audit event with comprehensive details

        Args:
            event_type: Type of event (use AuditEventType constants)
            message: Human-readable event description
            user_id: User ID (if applicable)
            username: Username (if applicable)
            ip_address: Client IP address
            user_agent: Client user agent
            additional_data: Additional event-specific data
            severity: Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        try:
            # Get request context if available
            if not ip_address and request:
                ip_address = request.environ.get(
                    "HTTP_X_FORWARDED_FOR", request.remote_addr
                )

            if not user_agent and request:
                user_agent = request.headers.get("User-Agent")

            # Build event data
            event_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": event_type,
                "message": message,
                "user_id": user_id,
                "username": username,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "session_token": (
                    flask_session.get("session_token") if flask_session else None
                ),
                "request_method": request.method if request else None,
                "request_path": request.path if request else None,
                "request_endpoint": request.endpoint if request else None,
            }

            # Add additional data if provided
            if additional_data:
                event_data["additional_data"] = additional_data

            # Create log message
            log_message = f"[{event_type}] {message}"
            if username:
                log_message += f" | User: {username}"
            if user_id:
                log_message += f" | UserID: {user_id}"
            if ip_address:
                log_message += f" | IP: {ip_address}"

            # Log event with appropriate severity
            if severity == "DEBUG":
                logger.debug(
                    f"{log_message} | Data: {json.dumps(event_data, default=str)}"
                )
            elif severity == "WARNING":
                logger.warning(
                    f"{log_message} | Data: {json.dumps(event_data, default=str)}"
                )
            elif severity == "ERROR":
                logger.error(
                    f"{log_message} | Data: {json.dumps(event_data, default=str)}"
                )
            elif severity == "CRITICAL":
                logger.critical(
                    f"{log_message} | Data: {json.dumps(event_data, default=str)}"
                )
            else:
                logger.info(
                    f"{log_message} | Data: {json.dumps(event_data, default=str)}"
                )

        except Exception as e:
            # Fallback logging if audit logging fails
            logger.error(f"Failed to log audit event: {e}")

    @staticmethod
    def log_authentication_event(
        event_type: str,
        message: str,
        user: Optional[User] = None,
        success: bool = True,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log authentication-related events

        Args:
            event_type: Authentication event type
            message: Event description
            user: User object (if applicable)
            success: Whether the authentication was successful
            additional_data: Additional event data
        """
        severity = "INFO" if success else "WARNING"

        AuditService.log_event(
            event_type=event_type,
            message=message,
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data=additional_data,
            severity=severity,
        )

    @staticmethod
    def log_oauth_event(
        event_type: str,
        message: str,
        provider: str,
        user: Optional[User] = None,
        success: bool = True,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log OAuth-related events

        Args:
            event_type: OAuth event type
            message: Event description
            provider: OAuth provider name
            user: User object (if applicable)
            success: Whether the OAuth flow was successful
            additional_data: Additional event data
        """
        severity = "INFO" if success else "WARNING"

        oauth_data = {"provider": provider}
        if additional_data:
            oauth_data.update(additional_data)

        AuditService.log_event(
            event_type=event_type,
            message=f"[OAuth-{provider}] {message}",
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data=oauth_data,
            severity=severity,
        )

    @staticmethod
    def log_authorization_event(
        event_type: str,
        message: str,
        user: Optional[User] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        granted: bool = True,
    ):
        """
        Log authorization-related events

        Args:
            event_type: Authorization event type
            message: Event description
            user: User object
            resource: Resource being accessed
            action: Action being performed
            granted: Whether access was granted
        """
        severity = "INFO" if granted else "WARNING"

        auth_data = {}
        if resource:
            auth_data["resource"] = resource
        if action:
            auth_data["action"] = action
        auth_data["access_granted"] = granted

        AuditService.log_event(
            event_type=event_type,
            message=message,
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data=auth_data,
            severity=severity,
        )

    @staticmethod
    def log_security_event(
        event_type: str,
        message: str,
        severity: str = "WARNING",
        user: Optional[User] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log security-related events

        Args:
            event_type: Security event type
            message: Event description
            severity: Event severity (WARNING, ERROR, CRITICAL)
            user: User object (if applicable)
            additional_data: Additional event data
        """
        AuditService.log_event(
            event_type=event_type,
            message=f"[SECURITY] {message}",
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data=additional_data,
            severity=severity,
        )

    @staticmethod
    def log_user_action(
        action: str,
        resource: str,
        user: Optional[User] = None,
        resource_id: Optional[int] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log user actions on content/resources

        Args:
            action: Action performed (create, update, delete, view, etc.)
            resource: Resource type (artist, video, settings, etc.)
            user: User performing the action
            resource_id: ID of the resource (if applicable)
            additional_data: Additional action data
        """
        action_data = {
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
        }

        if additional_data:
            action_data.update(additional_data)

        AuditService.log_event(
            event_type="user_action",
            message=f"User {action} {resource}"
            + (f" (ID: {resource_id})" if resource_id else ""),
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data=action_data,
            severity="INFO",
        )

    @staticmethod
    def log_admin_action(
        action: str,
        target_user: Optional[User] = None,
        admin_user: Optional[User] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log administrative actions

        Args:
            action: Administrative action performed
            target_user: User being managed
            admin_user: Admin performing the action
            additional_data: Additional action data
        """
        admin_data = {"admin_action": action}
        if target_user:
            admin_data["target_user_id"] = target_user.id
            admin_data["target_username"] = target_user.username

        if additional_data:
            admin_data.update(additional_data)

        message = f"Admin action: {action}"
        if target_user and admin_user:
            message += (
                f" | Admin: {admin_user.username} | Target: {target_user.username}"
            )

        AuditService.log_event(
            event_type=AuditEventType.ADMIN_ACTION,
            message=message,
            user_id=admin_user.id if admin_user else None,
            username=admin_user.username if admin_user else None,
            additional_data=admin_data,
            severity="INFO",
        )


# Convenience functions for common audit events
def log_login_success(user: User):
    """Log successful login"""
    AuditService.log_authentication_event(
        AuditEventType.LOGIN_SUCCESS,
        f"User successfully logged in",
        user=user,
        success=True,
    )


def log_login_failed(username: str, reason: str = "Invalid credentials"):
    """Log failed login attempt"""
    AuditService.log_authentication_event(
        AuditEventType.LOGIN_FAILED,
        f"Failed login attempt: {reason}",
        success=False,
        additional_data={"attempted_username": username, "failure_reason": reason},
    )


def log_logout(user: User):
    """Log user logout"""
    AuditService.log_authentication_event(
        AuditEventType.LOGOUT, f"User logged out", user=user, success=True
    )


def log_oauth_login_success(user: User, provider: str):
    """Log successful OAuth login"""
    AuditService.log_oauth_event(
        AuditEventType.OAUTH_LOGIN_SUCCESS,
        f"User successfully logged in via OAuth",
        provider=provider,
        user=user,
        success=True,
    )


def log_oauth_login_failed(provider: str, reason: str):
    """Log failed OAuth login"""
    AuditService.log_oauth_event(
        AuditEventType.OAUTH_LOGIN_FAILED,
        f"OAuth login failed: {reason}",
        provider=provider,
        success=False,
        additional_data={"failure_reason": reason},
    )


def log_access_denied(user: Optional[User], resource: str, required_role: str):
    """Log access denied event"""
    AuditService.log_authorization_event(
        AuditEventType.ACCESS_DENIED,
        f"Access denied to {resource} - requires {required_role}",
        user=user,
        resource=resource,
        action="access",
        granted=False,
    )


def log_security_violation(event_type: str, message: str, severity: str = "WARNING"):
    """Log security violation"""
    AuditService.log_security_event(event_type, message, severity=severity)
