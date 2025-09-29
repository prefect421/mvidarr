"""
FastAPI User Management Router
Migrated from Flask src/api/users.py - Essential user management features
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    responses={
        404: {"description": "User not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# AUTHENTICATION - PROPER IMPLEMENTATION
# ========================================================================================

from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[str] = None
    password: str = Field(..., min_length=6)
    is_admin: bool = False


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")


# ========================================================================================
# USER MANAGEMENT ENDPOINTS
# ========================================================================================


@router.get("", response_model=List[UserResponse])
async def get_users(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get all users (admin only)"""
    try:
        # Check if current user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        users = session.query(User).all()
        return users

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Dict[str, Any])
async def create_user(
    user_data: CreateUserRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Create a new user (admin only)"""
    try:
        # Check if current user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        # Check if username already exists
        existing_user = (
            session.query(User).filter(User.username == user_data.username).first()
        )

        if existing_user:
            raise HTTPException(
                status_code=400,
                detail=f"Username '{user_data.username}' already exists",
            )

        # Create new user
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            is_admin=user_data.is_admin,
            is_active=True,
            created_at=datetime.utcnow(),
        )

        # In a real implementation, you'd hash the password
        # new_user.set_password(user_data.password)

        session.add(new_user)
        session.commit()
        session.refresh(new_user)

        logger.info(f"Created new user: {user_data.username}")

        return {
            "success": True,
            "message": f"User '{user_data.username}' created successfully",
            "user_id": new_user.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get a specific user by ID"""
    try:
        # Users can only view their own profile, admins can view any
        current_user_id = current_user.get("user_id")
        is_admin = current_user.get("role") == "admin"

        if not is_admin and current_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        user = session.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: int = FastAPIPath(..., ge=1),
    role_data: UpdateRoleRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update user role (admin only)"""
    try:
        # Check if current user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        user = session.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update role
        user.is_admin = role_data.role == "admin"
        session.commit()

        logger.info(f"Updated user {user_id} role to {role_data.role}")

        return {
            "success": True,
            "message": f"User role updated to {role_data.role}",
            "user_id": user_id,
            "new_role": role_data.role,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Deactivate a user (admin only)"""
    try:
        # Check if current user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        user = session.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Don't allow deactivating self
        if current_user.get("user_id") == user_id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

        user.is_active = False
        session.commit()

        logger.info(f"Deactivated user {user_id}")

        return {
            "success": True,
            "message": f"User {user.username} deactivated",
            "user_id": user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Activate a user (admin only)"""
    try:
        # Check if current user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        user = session.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = True
        session.commit()

        logger.info(f"Activated user {user_id}")

        return {
            "success": True,
            "message": f"User {user.username} activated",
            "user_id": user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
