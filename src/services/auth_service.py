"""
Authentication and user management service for MVidarr
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Optional Flask support - only needed for Flask-based routes
try:
    from flask import session as flask_session
    FLASK_AVAILABLE = True
except ImportError:
    flask_session = None
    FLASK_AVAILABLE = False

from sqlalchemy.exc import IntegrityError

from src.database.connection import get_db
from src.database.models import SessionStatus, User, UserRole, UserSession
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth")


class AuthenticationError(Exception):
    """Authentication related errors"""

    pass


class AuthorizationError(Exception):
    """Authorization related errors"""

    pass


class AuthService:
    """Central authentication and authorization service"""

    PASSWORD_MIN_LENGTH = 8
    PASSWORD_COMPLEXITY_REGEX = (
        r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]"
    )

    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """
        Validate password complexity

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < AuthService.PASSWORD_MIN_LENGTH:
            return (
                False,
                f"Password must be at least {AuthService.PASSWORD_MIN_LENGTH} characters long",
            )

        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"

        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"

        if not re.search(r"\d", password):
            return False, "Password must contain at least one digit"

        if not re.search(r"[@$!%*?&]", password):
            return (
                False,
                "Password must contain at least one special character (@$!%*?&)",
            )

        return True, ""

    @staticmethod
    def validate_username(username: str) -> Tuple[bool, str]:
        """
        Validate username format

        Args:
            username: Username to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(username) < 3:
            return False, "Username must be at least 3 characters long"

        if len(username) > 30:
            return False, "Username must be no more than 30 characters long"

        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            return (
                False,
                "Username can only contain letters, numbers, underscores, and hyphens",
            )

        return True, ""

    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """
        Validate email format

        Args:
            email: Email to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not re.match(email_regex, email):
            return False, "Invalid email format"

        if len(email) > 120:
            return False, "Email address is too long"

        return True, ""

    @staticmethod
    def create_user(
        username: str, email: str, password: str, role: UserRole = UserRole.USER
    ) -> Tuple[bool, str, Optional[User]]:
        """
        Create a new user

        Args:
            username: Username for the new user
            email: Email address for the new user
            password: Password for the new user
            role: User role (default: USER)

        Returns:
            Tuple of (success, message, user_object)
        """
        try:
            # Validate input
            username_valid, username_error = AuthService.validate_username(username)
            if not username_valid:
                return False, username_error, None

            email_valid, email_error = AuthService.validate_email(email)
            if not email_valid:
                return False, email_error, None

            password_valid, password_error = AuthService.validate_password(password)
            if not password_valid:
                return False, password_error, None

            with get_db() as session:
                # Check for existing username
                existing_user = session.query(User).filter_by(username=username).first()
                if existing_user:
                    return False, "Username already exists", None

                # Check for existing email
                existing_email = session.query(User).filter_by(email=email).first()
                if existing_email:
                    return False, "Email address already registered", None

                # Create new user
                user = User(
                    username=username, email=email, password=password, role=role
                )
                session.add(user)
                session.commit()

                logger.info(f"User created: {username} with role {role.value}")
                return True, "User created successfully", user

        except IntegrityError as e:
            logger.error(f"Database integrity error creating user: {e}")
            return False, "User creation failed due to database constraint", None
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False, "User creation failed", None

    @staticmethod
    def authenticate_user(
        username: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None,
        two_factor_token: str = None,
    ) -> Tuple[bool, str, Optional[dict], Optional[dict], bool]:
        """
        Authenticate user credentials with optional 2FA

        Args:
            username: Username or email
            password: Password
            ip_address: Client IP address
            user_agent: Client user agent
            two_factor_token: Optional 2FA token

        Returns:
            Tuple of (success, message, user_data_dict, session_data_dict, requires_2fa)
        """
        try:
            with get_db() as session:
                # Find user by username or email
                user = (
                    session.query(User)
                    .filter((User.username == username) | (User.email == username))
                    .first()
                )

                if not user:
                    logger.warning(f"Login attempt for non-existent user: {username}")
                    return False, "Invalid username or password", None, None, False

                # Check if user is active
                if not user.is_active:
                    logger.warning(f"Login attempt for inactive user: {username}")
                    return False, "Account is inactive", None, None, False

                # Check if user is locked
                if user.is_locked():
                    logger.warning(f"Login attempt for locked user: {username}")
                    return (
                        False,
                        f"Account is locked until {user.locked_until}",
                        None,
                        None,
                        False,
                    )

                # Verify password
                if not user.check_password(password):
                    user.increment_failed_login()
                    session.commit()
                    logger.warning(
                        f"Failed login attempt for user: {username} from {ip_address}"
                    )
                    return False, "Invalid username or password", None, None, False

                # Check if 2FA is enabled
                if user.two_factor_enabled:
                    if not two_factor_token:
                        # Password correct but 2FA required - create user data dict
                        user_data = {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "role": user.role.value,
                            "last_login": user.last_login,
                        }
                        logger.info(f"2FA required for user: {username}")
                        return (
                            True,
                            "Two-factor authentication required",
                            user_data,
                            None,
                            True,
                        )

                    # Verify 2FA token
                    from src.services.two_factor_service import TwoFactorService

                    totp_valid, totp_message = TwoFactorService.verify_two_factor_login(
                        user.id, two_factor_token
                    )

                    if not totp_valid:
                        logger.warning(
                            f"Failed 2FA attempt for user: {username} from {ip_address}"
                        )
                        return False, totp_message, None, None, False

                # Successful authentication (with or without 2FA)
                user.reset_failed_login()
                user.last_login = datetime.utcnow()
                user.last_login_ip = ip_address

                # Create new session
                user_session = UserSession(
                    user_id=user.id, ip_address=ip_address, user_agent=user_agent
                )
                session.add(user_session)
                session.commit()

                # Create both user and session data dictionaries to avoid SQLAlchemy session binding issues
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "last_login": user.last_login,
                    "two_factor_enabled": user.two_factor_enabled,
                }

                session_data = {
                    "session_token": user_session.session_token,
                    "id": user_session.id,
                    "user_id": user_session.user_id,
                    "created_at": user_session.created_at,
                    "expires_at": user_session.expires_at,
                }

                logger.info(
                    f"User authenticated: {username} from {ip_address} (2FA: {user.two_factor_enabled})"
                )
                return True, "Authentication successful", user_data, session_data, False

        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return False, "Authentication failed", None, None, False

    @staticmethod
    def get_user_by_session_token(token: str) -> Optional[dict]:
        """
        Get user by session token

        Args:
            token: Session token

        Returns:
            User data dictionary if valid session, None otherwise
        """
        try:
            with get_db() as session:
                user_session = (
                    session.query(UserSession).filter_by(session_token=token).first()
                )

                if not user_session or not user_session.is_valid():
                    return None

                # Refresh session activity
                user_session.refresh()
                session.commit()

                # Get user data and return as dictionary to avoid session binding issues
                user = user_session.user
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "last_login": user.last_login,
                    "two_factor_enabled": user.two_factor_enabled,
                    "can_access_admin": user.role.value == "ADMIN",
                    "can_modify_content": user.role.value
                    in ["ADMIN", "MANAGER", "USER"],
                    "can_delete_content": user.role.value in ["ADMIN", "MANAGER"],
                }

                return user_data

        except Exception as e:
            logger.error(f"Error getting user by session token: {e}")
            return None

    @staticmethod
    def logout_user(token: str) -> bool:
        """
        Logout user by revoking session

        Args:
            token: Session token to revoke

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db() as session:
                user_session = (
                    session.query(UserSession).filter_by(session_token=token).first()
                )

                if user_session:
                    user_session.revoke()
                    session.commit()
                    logger.info(f"User session revoked: {user_session.user.username}")
                    return True

                return False

        except Exception as e:
            logger.error(f"Error logging out user: {e}")
            return False

    @staticmethod
    def logout_all_sessions(user_id: int) -> bool:
        """
        Logout user from all sessions

        Args:
            user_id: User ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db() as session:
                user_sessions = (
                    session.query(UserSession)
                    .filter_by(user_id=user_id, status=SessionStatus.ACTIVE)
                    .all()
                )

                for user_session in user_sessions:
                    user_session.revoke()

                session.commit()
                logger.info(f"All sessions revoked for user ID: {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error logging out all sessions: {e}")
            return False

    @staticmethod
    def cleanup_expired_sessions():
        """
        Clean up expired sessions from database
        """
        try:
            with get_db() as session:
                expired_sessions = (
                    session.query(UserSession)
                    .filter(UserSession.expires_at < datetime.utcnow())
                    .all()
                )

                for expired_session in expired_sessions:
                    expired_session.expire()

                session.commit()
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")

    @staticmethod
    def change_password(
        user_id: int, current_password: str, new_password: str
    ) -> Tuple[bool, str]:
        """
        Change user password

        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password

        Returns:
            Tuple of (success, message)
        """
        try:
            # Validate new password
            password_valid, password_error = AuthService.validate_password(new_password)
            if not password_valid:
                return False, password_error

            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()

                if not user:
                    return False, "User not found"

                # Verify current password
                if not user.check_password(current_password):
                    return False, "Current password is incorrect"

                # Set new password
                user.set_password(new_password)
                session.commit()

                # Logout all other sessions for security
                AuthService.logout_all_sessions(user_id)

                logger.info(f"Password changed for user: {user.username}")
                return True, "Password changed successfully"

        except Exception as e:
            logger.error(f"Error changing password: {e}")
            return False, "Password change failed"

    @staticmethod
    def get_users(include_inactive: bool = False) -> List[User]:
        """
        Get all users

        Args:
            include_inactive: Whether to include inactive users

        Returns:
            List of user objects
        """
        try:
            with get_db() as session:
                query = session.query(User)

                if not include_inactive:
                    query = query.filter_by(is_active=True)

                return query.all()

        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []

    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, any]:
        """
        Validate password strength and return detailed requirements

        Args:
            password: Password to validate

        Returns:
            Dictionary with validation results and requirements
        """
        requirements = {
            "min_length": len(password) >= AuthService.PASSWORD_MIN_LENGTH,
            "has_lowercase": bool(re.search(r"[a-z]", password)),
            "has_uppercase": bool(re.search(r"[A-Z]", password)),
            "has_digit": bool(re.search(r"\d", password)),
            "has_special": bool(re.search(r"[@$!%*?&]", password)),
        }

        all_valid = all(requirements.values())

        return {
            "valid": all_valid,
            "requirements": requirements,
            "strength_score": sum(requirements.values()) / len(requirements) * 100,
        }

    @staticmethod
    def create_user_session(
        user: User, ip_address: str = None, user_agent: str = None
    ) -> str:
        """
        Create a new user session and return session token

        Args:
            user: User object
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Session token string
        """
        try:
            with get_db() as session:
                user_session = UserSession(
                    user_id=user.id, ip_address=ip_address, user_agent=user_agent
                )
                session.add(user_session)
                session.commit()

                return user_session.session_token

        except Exception as e:
            logger.error(f"Error creating user session: {e}")
            return None

    @staticmethod
    def revoke_all_user_sessions_except_current(
        user_id: int, current_token: str
    ) -> bool:
        """
        Revoke all user sessions except the current one

        Args:
            user_id: User ID
            current_token: Current session token to preserve

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db() as session:
                user_sessions = (
                    session.query(UserSession)
                    .filter(
                        UserSession.user_id == user_id,
                        UserSession.status == SessionStatus.ACTIVE,
                        UserSession.session_token
                        != current_token.replace("Bearer ", ""),
                    )
                    .all()
                )

                for user_session in user_sessions:
                    user_session.revoke()

                session.commit()
                logger.info(
                    f"Revoked {len(user_sessions)} sessions for user ID: {user_id}"
                )
                return True

        except Exception as e:
            logger.error(f"Error revoking user sessions: {e}")
            return False

    @staticmethod
    def update_user_role(
        user_id: int, new_role: UserRole, admin_user_id: int
    ) -> Tuple[bool, str]:
        """
        Update user role (admin only)

        Args:
            user_id: User ID to update
            new_role: New role to assign
            admin_user_id: Admin user performing the update

        Returns:
            Tuple of (success, message)
        """
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found"

                admin_user = session.query(User).filter_by(id=admin_user_id).first()
                if not admin_user or admin_user.role != UserRole.ADMIN:
                    return False, "Unauthorized: Admin access required"

                old_role = user.role
                user.role = new_role
                user.updated_at = datetime.utcnow()
                session.commit()

                # Log role change
                from src.services.audit_service import AuditService

                AuditService.log_admin_action(
                    "update_user_role",
                    target_user=user,
                    admin_user=admin_user,
                    additional_data={
                        "old_role": old_role.value,
                        "new_role": new_role.value,
                    },
                )

                logger.info(
                    f"User role updated: {user.username} from {old_role.value} to {new_role.value}"
                )
                return True, f"User role updated to {new_role.value}"

        except Exception as e:
            logger.error(f"Error updating user role: {e}")
            return False, "Role update failed"

    @staticmethod
    def deactivate_user(user_id: int, admin_user_id: int) -> Tuple[bool, str]:
        """
        Deactivate user account (admin only)

        Args:
            user_id: User ID to deactivate
            admin_user_id: Admin user performing the action

        Returns:
            Tuple of (success, message)
        """
        try:
            with get_db() as session:
                user = session.query(User).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found"

                admin_user = session.query(User).filter_by(id=admin_user_id).first()
                if not admin_user or admin_user.role != UserRole.ADMIN:
                    return False, "Unauthorized: Admin access required"

                # Prevent self-deactivation
                if user_id == admin_user_id:
                    return False, "Cannot deactivate your own account"

                user.is_active = False
                user.updated_at = datetime.utcnow()
                session.commit()

                # Revoke all user sessions
                AuthService.logout_all_sessions(user_id)

                # Log deactivation
                from src.services.audit_service import AuditService

                AuditService.log_admin_action(
                    "deactivate_user", target_user=user, admin_user=admin_user
                )

                logger.info(f"User deactivated: {user.username}")
                return True, "User account deactivated"

        except Exception as e:
            logger.error(f"Error deactivating user: {e}")
            return False, "User deactivation failed"

    @staticmethod
    def get_current_user() -> Optional[dict]:
        """
        Get current authenticated user from Flask session

        Note: Only works when Flask is available. For FastAPI, use request-based auth.

        Returns:
            User data dict if authenticated, None otherwise
        """
        if not FLASK_AVAILABLE or flask_session is None:
            # Flask not available - return None (FastAPI should use request-based auth)
            return None

        session_token = flask_session.get("session_token")
        if session_token:
            return AuthService.get_user_by_session_token(session_token)
        return None

    @staticmethod
    def require_authentication():
        """
        Decorator helper to check if user is authenticated

        Returns:
            User data dict if authenticated, raises AuthenticationError otherwise
        """
        user_data = AuthService.get_current_user()
        if not user_data:
            raise AuthenticationError("Authentication required")
        return user_data

    @staticmethod
    def require_role(required_role: UserRole):
        """
        Decorator helper to check if user has required role

        Args:
            required_role: Minimum required role

        Returns:
            User data dict if authorized, raises AuthorizationError otherwise
        """
        user_data = AuthService.require_authentication()

        # Check role permissions manually since user_data is now a dict
        user_role = UserRole(user_data["role"])
        role_hierarchy = {
            UserRole.READONLY: 0,
            UserRole.USER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
        }

        if role_hierarchy.get(user_role, 0) < role_hierarchy.get(required_role, 3):
            raise AuthorizationError(f"Role {required_role.value} or higher required")
        return user_data

    @staticmethod
    def create_default_admin():
        """
        Create default admin user if no admin exists

        Returns:
            Tuple of (created, message)
        """
        try:
            with get_db() as session:
                # Check if any admin exists
                admin_count = session.query(User).filter_by(role=UserRole.ADMIN).count()

                if admin_count == 0:
                    # Create default admin
                    success, message, admin_user = AuthService.create_user(
                        username="admin",
                        email="admin@mvidarr.local",
                        password="MVidarr@dmin123",  # Strong default password
                        role=UserRole.ADMIN,
                    )

                    if success:
                        logger.info("Default admin user created")
                        return (
                            True,
                            "Default admin user created with username 'admin' and password 'MVidarr@dmin123'. Please change the password immediately.",
                        )
                    else:
                        return False, f"Failed to create default admin: {message}"

                return False, "Admin user already exists"

        except Exception as e:
            logger.error(f"Error creating default admin: {e}")
            return False, "Failed to create default admin"
