"""
Session Store for MVidarr
Manages session tokens with database backing and in-memory fallback.
"""

import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.session_store")

# In-memory session store (fallback when DB is unavailable)
_memory_sessions: Dict[str, Dict[str, Any]] = {}

SESSION_EXPIRY_HOURS = 24


class SessionStore:
    """Simple token-based session store backed by settings DB or in-memory fallback."""

    @staticmethod
    def create_session(username: str, ip: str = "unknown") -> str:
        """
        Create a new session token for the given user.

        Args:
            username: Authenticated username
            ip: Client IP address

        Returns:
            Session token string
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=SESSION_EXPIRY_HOURS)

        session_data = {
            "username": username,
            "ip": ip,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat(),
            "authenticated": True,
            "user_id": 1,  # Single-user system
            "role": "admin",
            "is_admin": True,
            "can_admin": True,
            "can_modify": True,
            "can_delete": True,
        }

        # Try DB-backed storage first
        try:
            import json

            from src.services.settings_service import SettingsService

            # Store session keyed by token
            SettingsService.set(
                f"session:{token}",
                json.dumps(session_data),
            )
            logger.debug(f"Session created in DB for user: {username}")
        except Exception as e:
            logger.warning(f"DB session store unavailable, using memory: {e}")

        # Always store in memory as well for fast lookups
        _memory_sessions[token] = session_data

        # Cleanup expired sessions periodically (every 10 creates)
        if len(_memory_sessions) % 10 == 0:
            SessionStore.cleanup_expired()

        return token

    @staticmethod
    def validate_session(token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a session token and return user data if valid.

        Args:
            token: Session token to validate

        Returns:
            User data dict if valid, None if invalid/expired
        """
        if not token:
            return None

        # Check memory first (fast path)
        session_data = _memory_sessions.get(token)

        if not session_data:
            # Try DB fallback
            try:
                import json

                from src.services.settings_service import SettingsService

                raw = SettingsService.get(f"session:{token}")
                if raw:
                    session_data = json.loads(raw)
                    # Cache in memory
                    _memory_sessions[token] = session_data
            except Exception as e:
                logger.debug(f"DB session lookup failed: {e}")
                return None

        if not session_data:
            return None

        # Check expiry
        try:
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.utcnow() > expires_at:
                # Session expired - clean up
                SessionStore.destroy_session(token)
                return None
        except (KeyError, ValueError):
            # Malformed session data
            SessionStore.destroy_session(token)
            return None

        return {
            "username": session_data.get("username", "admin"),
            "authenticated": True,
            "user_id": session_data.get("user_id", 1),
            "role": session_data.get("role", "admin"),
            "is_admin": session_data.get("is_admin", True),
            "can_admin": session_data.get("can_admin", True),
            "can_modify": session_data.get("can_modify", True),
            "can_delete": session_data.get("can_delete", True),
        }

    @staticmethod
    def destroy_session(token: str) -> None:
        """
        Destroy a session token.

        Args:
            token: Session token to destroy
        """
        # Remove from memory
        _memory_sessions.pop(token, None)

        # Remove from DB
        try:
            from src.services.settings_service import SettingsService

            SettingsService.delete(f"session:{token}")
        except Exception:
            pass

    @staticmethod
    def cleanup_expired() -> int:
        """
        Remove all expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        cleaned = 0
        now = datetime.utcnow()

        # Clean memory sessions
        expired_tokens = []
        for token, data in _memory_sessions.items():
            try:
                expires_at = datetime.fromisoformat(data["expires_at"])
                if now > expires_at:
                    expired_tokens.append(token)
            except (KeyError, ValueError):
                expired_tokens.append(token)

        for token in expired_tokens:
            _memory_sessions.pop(token, None)
            try:
                from src.services.settings_service import SettingsService

                SettingsService.delete(f"session:{token}")
            except Exception:
                pass
            cleaned += 1

        if cleaned > 0:
            logger.debug(f"Cleaned up {cleaned} expired sessions")

        return cleaned
