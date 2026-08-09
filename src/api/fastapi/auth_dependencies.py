"""
FastAPI Authentication Dependencies
Integrates with SessionStore for real session-based authentication.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

logger = logging.getLogger("mvidarr.fastapi.auth_deps")

# Optional bearer token security (for API tokens if needed)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Authentication related errors"""

    pass


async def get_current_user_session(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user from their session_token cookie,
    validated against SessionStore.

    Returns:
        User data if authenticated, None otherwise
    """
    try:
        session_token = request.cookies.get("session_token")
        if session_token:
            from src.services.session_store import SessionStore

            user_data = SessionStore.validate_session(session_token)
            if user_data:
                return user_data

        return None

    except Exception as e:
        logger.error(f"Error getting user session: {e}")
        return None


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user.

    Raises:
        HTTPException: If user is not authenticated
    """
    user = await get_current_user_session(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in through the web interface.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Dependency to get current user if authenticated, None otherwise.
    """
    return await get_current_user_session(request)


async def require_authentication(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Dependency to require authentication for protected endpoints.

    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user or not current_user.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return current_user


async def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Dependency to require admin privileges.

    Raises:
        HTTPException: If user is not authenticated or not admin
    """
    if not current_user or not current_user.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )

    return current_user
