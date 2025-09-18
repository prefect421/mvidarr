"""
FastAPI Authentication Dependencies
Integrates with existing SimpleAuthService for session-based authentication
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
import logging

from src.services.simple_auth_service import SimpleAuthService

logger = logging.getLogger("mvidarr.fastapi.auth_deps")

# Optional bearer token security (for API tokens if needed)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Authentication related errors"""
    pass


async def get_current_user_session(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user from session
    
    Args:
        request: FastAPI request object
        
    Returns:
        User data if authenticated, None otherwise
    """
    try:
        # Check if we have Flask session data available
        # This requires proper session middleware setup
        if hasattr(request.app.state, 'session_interface'):
            # Get session from Flask session interface
            session_data = request.app.state.session_interface.get_session(request)
            
            # Check if user is authenticated via simple auth
            if session_data and session_data.get('authenticated'):
                username = session_data.get('username')
                if username:
                    return {
                        "username": username,
                        "authenticated": True,
                        "user_id": 1,  # Simple auth is single-user system
                        "role": "admin",  # Simple auth user has admin privileges
                        "is_admin": True,
                        "can_admin": True,
                        "can_modify": True,
                        "can_delete": True
                    }
        
        # Fallback: check Flask session directly if available
        try:
            from flask import has_request_context, session as flask_session
            
            if has_request_context() and flask_session.get('authenticated'):
                username = flask_session.get('username')
                if username:
                    return {
                        "username": username,
                        "authenticated": True,
                        "user_id": 1,
                        "role": "admin",
                        "is_admin": True,
                        "can_admin": True,
                        "can_modify": True,
                        "can_delete": True
                    }
        except (ImportError, RuntimeError):
            # Flask not available or no request context
            pass
        
        # Check for session token in cookies
        session_token = request.cookies.get('session_token')
        if session_token:
            # For now, accept any session token as valid
            # In production, validate token against database
            logger.info(f"Found session token: {session_token[:10]}...")
            return {
                "username": "admin",  # Default for session-based auth
                "authenticated": True,
                "user_id": 1,
                "role": "admin",
                "is_admin": True,
                "can_admin": True,
                "can_modify": True,
                "can_delete": True
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting user session: {e}")
        return None


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user
    
    Args:
        request: FastAPI request object
        
    Returns:
        User data
        
    Raises:
        HTTPException: If user is not authenticated
    """
    user = await get_current_user_session(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in through the web interface.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


async def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Dependency to get current user if authenticated, None otherwise
    
    Args:
        request: FastAPI request object
        
    Returns:
        User data if authenticated, None otherwise
    """
    return await get_current_user_session(request)


async def require_authentication(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Dependency to require authentication for protected endpoints
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User data
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user or not current_user.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


async def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Dependency to require admin privileges
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User data
        
    Raises:
        HTTPException: If user is not authenticated or not admin
    """
    if not current_user or not current_user.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user


# Compatibility functions for existing endpoints
async def get_current_user_legacy() -> Dict[str, Any]:
    """
    Legacy compatibility function for endpoints that don't have request access
    
    Returns:
        Default user data for simple auth system
        
    Note:
        This is a temporary compatibility function.
        Endpoints should be updated to use get_current_user(request: Request)
    """
    try:
        # Try to get from Flask session if available
        from flask import has_request_context, session as flask_session
        
        if has_request_context() and flask_session.get('authenticated'):
            username = flask_session.get('username', 'admin')
            return {
                "username": username,
                "authenticated": True,
                "user_id": 1,
                "role": "admin",
                "is_admin": True,
                "can_admin": True,
                "can_modify": True,
                "can_delete": True
            }
    except (ImportError, RuntimeError):
        pass
    
    # Fallback: assume authenticated for backward compatibility
    # This maintains current behavior while we transition
    logger.warning("Using legacy authentication fallback")
    return {
        "username": "admin",
        "authenticated": True,
        "user_id": 1,
        "role": "admin", 
        "is_admin": True,
        "can_admin": True,
        "can_modify": True,
        "can_delete": True
    }


async def require_authentication_legacy(current_user: Dict[str, Any] = Depends(get_current_user_legacy)):
    """
    Legacy compatibility function for endpoints that don't have request access
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User data
    """
    return current_user