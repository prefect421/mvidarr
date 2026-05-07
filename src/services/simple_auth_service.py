"""
Simple single-user authentication service for MVidarr
Uses bcrypt for password hashing with lazy migration from SHA-256.
"""

import hashlib
from typing import Optional, Tuple

from flask import session as flask_session
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.simple_auth")


def _is_bcrypt_hash(hash_value: str) -> bool:
    """Check if a hash string is a bcrypt hash."""
    return hash_value.startswith(("$2b$", "$2a$", "$2y$"))


def _is_sha256_hash(hash_value: str) -> bool:
    """Check if a hash string is a SHA-256 hex digest."""
    return len(hash_value) == 64 and all(c in "0123456789abcdef" for c in hash_value)


class SimpleAuthService:
    """Simple single-user authentication service"""

    @staticmethod
    def set_credentials(username: str, password: str) -> Tuple[bool, str]:
        """
        Set username and password for single-user authentication.

        Args:
            username: Username to set
            password: Password to set (will be hashed with bcrypt)

        Returns:
            Tuple of (success, message)
        """
        try:
            if not username or not password:
                return False, "Username and password are required"

            if len(username) < 3:
                return False, "Username must be at least 3 characters long"

            if len(password) < 8:
                return False, "Password must be at least 8 characters long"

            # Hash password using bcrypt
            import bcrypt

            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

            # Store in settings
            SettingsService.set("simple_auth_username", username)
            SettingsService.set("simple_auth_password", password_hash)

            logger.info(f"Credentials updated for user: {username}")
            return True, "Credentials updated successfully"

        except Exception as e:
            logger.error(f"Error setting credentials: {e}")
            return False, "Failed to update credentials"

    @staticmethod
    def authenticate(username: str, password: str) -> Tuple[bool, str]:
        """
        Authenticate user with username and password.
        Supports lazy migration from SHA-256 to bcrypt.

        Args:
            username: Username to authenticate
            password: Password to authenticate

        Returns:
            Tuple of (success, message)
        """
        try:
            if not username or not password:
                return False, "Username and password are required"

            stored_username = SettingsService.get("simple_auth_username")
            stored_password_hash = SettingsService.get("simple_auth_password")

            if not stored_username or not stored_password_hash:
                logger.warning("No credentials configured in database")
                return False, "No credentials configured"

            # Check username
            if username != stored_username:
                return False, "Invalid username or password"

            # Verify password based on hash format
            import bcrypt

            if _is_bcrypt_hash(stored_password_hash):
                # bcrypt hash - verify directly
                if bcrypt.checkpw(password.encode(), stored_password_hash.encode()):
                    logger.info(f"User authenticated: {username}")
                    return True, "Authentication successful"
                else:
                    return False, "Invalid username or password"

            elif _is_sha256_hash(stored_password_hash):
                # Legacy SHA-256 hash - verify then migrate to bcrypt
                password_sha256 = hashlib.sha256(password.encode()).hexdigest()
                if password_sha256 == stored_password_hash:
                    # Password matches - migrate to bcrypt
                    new_hash = bcrypt.hashpw(
                        password.encode(), bcrypt.gensalt()
                    ).decode()
                    SettingsService.set("simple_auth_password", new_hash)
                    logger.info(
                        f"User authenticated and password migrated to bcrypt: {username}"
                    )
                    return True, "Authentication successful"
                else:
                    return False, "Invalid username or password"

            else:
                logger.error("Unknown password hash format in database")
                return False, "Invalid username or password"

        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return False, "Authentication failed"

    @staticmethod
    def login_user(username: str) -> bool:
        """
        Set user as logged in using Flask session.

        Args:
            username: Username to log in

        Returns:
            True if successful
        """
        try:
            flask_session["authenticated"] = True
            flask_session["username"] = username
            flask_session.permanent = True
            logger.info(f"User logged in: {username}")
            return True
        except Exception as e:
            logger.error(f"Error logging in user: {e}")
            return False

    @staticmethod
    def logout_user() -> bool:
        """
        Log out current user by clearing Flask session.

        Returns:
            True if successful
        """
        try:
            username = flask_session.get("username", "unknown")
            flask_session.clear()
            logger.info(f"User logged out: {username}")
            return True
        except Exception as e:
            logger.error(f"Error logging out user: {e}")
            return False

    @staticmethod
    def is_authenticated() -> bool:
        """Check if current user is authenticated."""
        return flask_session.get("authenticated", False)

    @staticmethod
    def get_current_username() -> Optional[str]:
        """Get current logged in username."""
        if SimpleAuthService.is_authenticated():
            return flask_session.get("username")
        return None

    @staticmethod
    def get_credentials() -> Tuple[Optional[str], bool]:
        """
        Get current stored username and whether credentials are configured.

        Returns:
            Tuple of (username, has_credentials)
        """
        username = SettingsService.get("simple_auth_username")
        password_hash = SettingsService.get("simple_auth_password")
        has_credentials = bool(username and password_hash)
        return username, has_credentials

    @staticmethod
    def _is_default_password() -> bool:
        """Check if current password is still the default 'mvidarr'."""
        try:
            stored_password_hash = SettingsService.get("simple_auth_password")
            if not stored_password_hash:
                return True

            import bcrypt

            if _is_bcrypt_hash(stored_password_hash):
                return bcrypt.checkpw(b"mvidarr", stored_password_hash.encode())
            elif _is_sha256_hash(stored_password_hash):
                default_hash = hashlib.sha256(b"mvidarr").hexdigest()
                return default_hash == stored_password_hash

            return True

        except Exception:
            return True

    @staticmethod
    def initialize_default_credentials() -> Tuple[bool, str, str, str]:
        """
        Initialize default credentials if none exist.

        Returns:
            Tuple of (created, username, password, message)
        """
        try:
            username, has_credentials = SimpleAuthService.get_credentials()

            if has_credentials:
                return False, username, "", "Credentials already configured"

            default_username = "admin"
            default_password = "mvidarr"

            # Use bcrypt for default credentials too
            import bcrypt

            password_hash = bcrypt.hashpw(
                default_password.encode(), bcrypt.gensalt()
            ).decode()
            SettingsService.set("simple_auth_username", default_username)
            SettingsService.set("simple_auth_password", password_hash)

            logger.info("Default credentials initialized with bcrypt")
            return (
                True,
                default_username,
                default_password,
                "Default credentials created",
            )

        except Exception as e:
            logger.error(f"Error initializing default credentials: {e}")
            return False, "", "", "Failed to initialize credentials"

    @staticmethod
    def ensure_default_credentials() -> bool:
        """
        Ensure default credentials exist in database if missing.
        Does not overwrite existing credentials.

        Returns:
            True if credentials exist or were created successfully
        """
        try:
            username, has_credentials = SimpleAuthService.get_credentials()

            if has_credentials:
                logger.debug("Authentication credentials already exist")
                return True

            logger.info("No authentication credentials found, creating defaults...")

            (
                created,
                username,
                password,
                message,
            ) = SimpleAuthService.initialize_default_credentials()

            if created:
                logger.info(f"Default credentials created: {username}")
                return True
            else:
                logger.error(f"Failed to create default credentials: {message}")
                return False

        except Exception as e:
            logger.error(f"Error ensuring default credentials: {e}")
            return False
