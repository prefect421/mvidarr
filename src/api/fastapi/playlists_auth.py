"""
FastAPI Playlists Authentication Module
Authentication and permission checking utilities for playlist operations
"""

from typing import Dict

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Playlist, User, UserRole
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.playlists_auth")


# ========================================================================================
# USER INFO AND AUTHENTICATION SYSTEM
# ========================================================================================


class UserInfo:
    """Session-independent user info object"""

    def __init__(self, id: int, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role

    def can_access_admin(self):
        return self.role in [UserRole.ADMIN.value, UserRole.MANAGER.value]

    def can_modify(self):
        return self.role in [
            UserRole.ADMIN.value,
            UserRole.MANAGER.value,
            UserRole.USER.value,
        ]


async def get_current_user_from_session(request: Request) -> UserInfo:
    """Get current user from session for simple auth system"""
    from src.api.fastapi.auth_dependencies import get_current_user_legacy

    user_data = await get_current_user_legacy()
    username = user_data.get("username", "admin")

    # Look up the actual user ID from the database based on username
    with get_db() as db_session:
        user = db_session.query(User).filter(User.username == username).first()
        if user:
            user_id = user.id
            role = user.role.value
        else:
            # Fallback: find any admin user
            admin_user = (
                db_session.query(User).filter(User.role == UserRole.ADMIN).first()
            )
            if admin_user:
                user_id = admin_user.id
                role = UserRole.ADMIN.value
            else:
                raise HTTPException(
                    status_code=500,
                    detail="No admin user found in database. Please run database initialization.",
                )

    return UserInfo(
        id=user_id,
        username=username,
        role=role,
    )


# ========================================================================================
# PERMISSION CHECKING UTILITIES
# ========================================================================================


def can_access_playlist(playlist: Playlist, user: UserInfo) -> bool:
    """Check if user can access playlist"""
    if not user:
        return False

    # Owner can always access
    if playlist.user_id == 1:  # placeholder user id
        return True

    # Public playlists are accessible to all
    if playlist.is_public:
        return True

    # Note: Featured playlists would require admin check here if auth was implemented
    # Currently all featured playlists are publicly accessible

    return False


def can_modify_playlist(playlist: Playlist, user: UserInfo) -> bool:
    """Check if user can modify playlist

    Note: Simplified authentication - currently allows modification for placeholder user
    TODO: Implement proper user authentication when auth system is ready
    """
    if not user:
        return False

    # Owner can always modify
    if playlist.user_id == 1:  # placeholder user id
        return True

    # Note: Admin check would go here when auth system is implemented

    return False
