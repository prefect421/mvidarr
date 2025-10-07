"""
FastAPI Authentication Dependencies
Provides dependency injection for JWT authentication in FastAPI routes
"""

from typing import Any, Dict, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from src.auth.jwt_handler import jwt_handler
from src.services.async_base_service import AsyncBaseService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth.dependencies")

# HTTPBearer scheme for Authorization header
bearer_scheme = HTTPBearer(auto_error=False)


class AuthDependencies(AsyncBaseService):
    """Authentication dependencies for FastAPI"""

    def __init__(self):
        super().__init__("mvidarr.auth.dependencies")


# Global instance
auth_deps = AuthDependencies()


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    access_token_cookie: Optional[str] = Cookie(None),
) -> Optional[Dict[str, Any]]:
    """
    Get current user from JWT token (optional - returns None if not authenticated)
    Checks both Authorization header and cookies
    """
    token = None

    # Try Authorization header first
    if credentials:
        token = credentials.credentials
    # Fallback to cookie
    elif access_token_cookie:
        token = access_token_cookie

    if not token:
        return None

    try:
        # Check if token is blacklisted
        if await jwt_handler.is_token_blacklisted(token):
            logger.debug("Token is blacklisted")
            return None

        # Verify token
        payload = await jwt_handler.verify_access_token(token)
        if not payload:
            logger.debug("Invalid or expired access token")
            return None

        return {
            "username": payload.get("username"),
            "user_id": payload.get("user_id"),
            "sub": payload.get("sub"),
            "token_payload": payload,
        }

    except Exception as e:
        logger.error(f"Error in get_current_user_optional: {e}")
        return None


async def get_current_user(
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
) -> Dict[str, Any]:
    """
    Get current user from JWT token (required - raises 401 if not authenticated)
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_username(user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Get current user's username"""
    return user["username"]


async def get_current_user_id(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Optional[int]:
    """Get current user's ID"""
    return user.get("user_id")


async def require_admin(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require admin privileges (for single-user system, any authenticated user is admin)
    In a multi-user system, you would check user roles here
    """
    # For single-user system, any authenticated user has admin privileges
    return user


class OptionalAuth:
    """Dependency that provides optional authentication"""

    def __init__(self, required: bool = False):
        self.required = required

    async def __call__(
        self, user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
    ) -> Optional[Dict[str, Any]]:
        if self.required and not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


class RoleRequired:
    """Dependency that requires specific role (extensible for future multi-user support)"""

    def __init__(self, roles: list = None):
        self.roles = roles or ["user"]  # Default role for single-user system

    async def __call__(
        self, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        # For single-user system, any authenticated user has all roles
        # In future multi-user implementation, check user.get("roles", [])
        return user


async def verify_refresh_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Verify refresh token and return payload"""
    try:
        if await jwt_handler.is_token_blacklisted(refresh_token):
            logger.debug("Refresh token is blacklisted")
            return None

        payload = await jwt_handler.verify_refresh_token(refresh_token)
        return payload

    except Exception as e:
        logger.error(f"Error verifying refresh token: {e}")
        return None


async def check_auth_enabled() -> bool:
    """Check if authentication is enabled in settings"""
    try:
        # Query settings to check if authentication is required
        query = "SELECT setting_value FROM settings WHERE setting_key = 'require_authentication'"
        result = await auth_deps.execute_query(query)

        if result and result[0]["setting_value"]:
            # Convert to boolean
            value = result[0]["setting_value"].lower()
            return value in ("true", "1", "yes", "on", "enabled")

        return False

    except Exception as e:
        logger.error(f"Error checking auth enabled status: {e}")
        # Default to disabled if we can't check
        return False


class ConditionalAuth:
    """Dependency that only requires auth if it's enabled in settings"""

    async def __call__(
        self,
        request: Request,
        user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
    ) -> Optional[Dict[str, Any]]:

        auth_enabled = await check_auth_enabled()

        if auth_enabled and not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user


# Convenience instances
optional_auth = OptionalAuth(required=False)
required_auth = OptionalAuth(required=True)
conditional_auth = ConditionalAuth()
admin_required = require_admin


# Rate limiting dependency (for login endpoints)
class RateLimitAuth:
    """Rate limiting for authentication endpoints"""

    def __init__(self, max_attempts: int = 5, window_minutes: int = 15):
        self.max_attempts = max_attempts
        self.window_minutes = window_minutes
        self._attempts = {}  # In production, use Redis or database

    async def __call__(self, request: Request) -> bool:
        """Check if request is within rate limit"""
        client_ip = request.client.host if request.client else "unknown"
        current_time = int(time.time())
        window_start = current_time - (self.window_minutes * 60)

        # Clean old attempts
        if client_ip in self._attempts:
            self._attempts[client_ip] = [
                attempt_time
                for attempt_time in self._attempts[client_ip]
                if attempt_time > window_start
            ]

        # Check current attempts
        attempts_count = len(self._attempts.get(client_ip, []))

        if attempts_count >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Try again in {self.window_minutes} minutes.",
            )

        # Record this attempt
        if client_ip not in self._attempts:
            self._attempts[client_ip] = []
        self._attempts[client_ip].append(current_time)

        return True


# Rate limiter instance
login_rate_limiter = RateLimitAuth()


# Test function for auth dependencies
async def test_auth_dependencies():
    """Test authentication dependencies"""
    try:
        from src.database.async_connection import initialize_async_database

        print("🔄 Initializing async database...")
        await initialize_async_database()

        print("🔄 Testing auth dependencies...")

        # Test auth enabled check
        auth_enabled = await check_auth_enabled()
        print(f"Auth enabled: {auth_enabled}")

        # Test token verification (will fail without valid token, which is expected)
        test_payload = await verify_refresh_token("invalid_token")
        print(f"Invalid token verification (should be None): {test_payload}")

        print("✅ Auth dependencies basic functionality working!")
        return True

    except Exception as e:
        print(f"❌ Auth dependencies test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    """Run tests if executed directly"""
    import asyncio
    import os
    import sys
    import time

    # Add project root to path
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    async def main():
        print("🧪 Testing Auth Dependencies")
        print("=" * 40)

        success = await test_auth_dependencies()

        print("=" * 40)
        if success:
            print("🎉 Auth Dependencies tests passed!")
        else:
            print("💥 Auth Dependencies tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
