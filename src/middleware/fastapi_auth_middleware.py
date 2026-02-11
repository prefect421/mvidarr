"""
FastAPI Authentication Middleware and Dependencies
Re-exports from auth_dependencies for backward compatibility.
"""

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_admin,
    require_authentication,
)

__all__ = ["get_current_user", "require_authentication", "require_admin"]
