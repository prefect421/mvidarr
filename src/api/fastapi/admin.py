"""
FastAPI Admin API for MVidarr
Complete system administration, user management, and monitoring endpoints.
Migrated from Flask admin_interface.py and users.py for enhanced performance.
"""

import asyncio
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.database.models import SessionStatus, User, UserRole, UserSession
from src.services.audit_service import AuditEventType, AuditService
from src.services.auth_service import AuthService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.admin")

# Create FastAPI router
router = APIRouter(prefix="/api/admin", tags=["admin"])

# ====================================
# Authentication & User Info Classes
# ====================================


@dataclass
class UserInfo:
    """User information for authentication"""

    id: int
    username: str
    role: str
    is_active: bool

    def can_access_admin(self) -> bool:
        return self.role in [UserRole.ADMIN.value, UserRole.MANAGER.value]

    def can_manage_users(self) -> bool:
        return self.role in [UserRole.ADMIN.value, UserRole.MANAGER.value]


async def get_current_user() -> UserInfo:
    """Get current authenticated user"""
    from src.api.fastapi.auth_dependencies import get_current_user_legacy

    user_data = await get_current_user_legacy()
    return UserInfo(
        id=user_data.get("user_id", 1),
        username=user_data.get("username", "admin"),
        role=UserRole.ADMIN.value,  # Simple auth user has admin privileges
        is_active=True,
    )


async def require_admin_access(
    current_user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    """Require admin access for endpoint"""
    if not current_user.can_access_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


# ====================================
# Pydantic Models for Request/Response
# ====================================


class UserCreateRequest(BaseModel):
    """Request model for creating a new user"""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(..., min_length=8)
    role: str = Field(default="USER", pattern=r"^(USER|MANAGER|ADMIN)$")


class UserRoleUpdateRequest(BaseModel):
    """Request model for updating user role"""

    role: str = Field(..., pattern=r"^(USER|MANAGER|ADMIN)$")


class UserSessionInfo(BaseModel):
    """User session information"""

    id: int
    session_token: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_activity: datetime
    status: str
    is_current: bool = False

    class Config:
        from_attributes = True


class UserDetails(BaseModel):
    """Complete user details with sessions"""

    id: int
    username: str
    email: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    login_attempts: int
    account_locked_until: Optional[datetime]
    active_sessions: List[UserSessionInfo] = []
    preferences: Optional[Dict] = {}

    class Config:
        from_attributes = True


class SystemStatusResponse(BaseModel):
    """System status information"""

    pid: int
    service_type: str
    restart_available: bool
    uptime: Optional[str] = None
    service_details: Optional[str] = None


class UserStatsResponse(BaseModel):
    """User statistics for dashboard"""

    total: int
    active: int
    inactive: int
    by_role: Dict[str, int]


class DashboardResponse(BaseModel):
    """Admin dashboard response"""

    user_stats: UserStatsResponse
    recent_users: List[UserDetails]
    auth_status: Dict
    protection_status: Dict


class LogsResponse(BaseModel):
    """Recent logs response"""

    log_entries: List[str]
    log_file: str
    entry_count: int


# ====================================
# Admin Dashboard & System Status
# ====================================


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Admin dashboard with system overview"""
    try:
        # Get user statistics
        users = session.query(User).all()
        user_stats = UserStatsResponse(
            total=len(users),
            active=len([u for u in users if u.is_active]),
            inactive=len([u for u in users if not u.is_active]),
            by_role={},
        )

        # Count users by role
        for role in UserRole:
            user_stats.by_role[role.value] = len([u for u in users if u.role == role])

        # Get recent users (last 10)
        recent_users = (
            session.query(User).order_by(User.created_at.desc()).limit(10).all()
        )
        recent_users_data = [
            UserDetails(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role.value,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
                login_attempts=user.login_attempts,
                account_locked_until=user.account_locked_until,
                preferences=user.preferences or {},
            )
            for user in recent_users
        ]

        # Mock auth/protection status for now
        auth_status = {"enabled": True, "method": "session"}
        protection_status = {"csrf_enabled": True, "https_enforced": False}

        return DashboardResponse(
            user_stats=user_stats,
            recent_users=recent_users_data,
            auth_status=auth_status,
            protection_status=protection_status,
        )

    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard",
        )


@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(current_user: UserInfo = Depends(require_admin_access)):
    """Get system status information"""
    try:
        status_info = SystemStatusResponse(
            pid=os.getpid(), service_type="unknown", restart_available=False
        )

        # Check if running under systemd
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "mvidarr"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                status_info.service_type = "systemd"
                status_info.restart_available = True

                # Get service details
                status_result = subprocess.run(
                    ["systemctl", "status", "mvidarr", "--no-pager"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if status_result.returncode == 0:
                    status_info.service_details = status_result.stdout

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ):
            pass

        # Check for manage_service.sh script
        script_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            ),
            "scripts",
            "manage_service.sh",
        )
        if os.path.exists(script_path) and os.access(script_path, os.X_OK):
            if status_info.service_type == "unknown":
                status_info.service_type = "script"
            status_info.restart_available = True

        # If no service management found, still allow process restart
        if not status_info.restart_available:
            status_info.restart_available = True
            status_info.service_type = "process"

        return status_info

    except Exception as e:
        logger.error(f"System status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system status",
        )


@router.post("/system/restart")
async def restart_application(current_user: UserInfo = Depends(require_admin_access)):
    """Restart the MVidarr application (Admin only)"""
    try:
        # Log the restart action for audit trail
        logger.warning(
            f"Application restart initiated by admin user: {current_user.username}"
        )

        # Schedule restart in a separate thread to allow response to be sent
        def delayed_restart():
            try:
                # Wait 2 seconds to allow response to be sent
                time.sleep(2)

                # Get the current process ID
                current_pid = os.getpid()

                # First, stop Celery workers to ensure they pick up code changes
                logger.info("Stopping Celery workers before restart...")
                try:
                    # Find and terminate Celery worker processes
                    result = subprocess.run(
                        ["pgrep", "-f", "celery.*worker"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        worker_pids = result.stdout.strip().split('\n')
                        for pid in worker_pids:
                            if pid.strip():
                                try:
                                    subprocess.run(["kill", "-TERM", pid.strip()], timeout=5)
                                    logger.info(f"Terminated Celery worker PID: {pid.strip()}")
                                except Exception as e:
                                    logger.warning(f"Failed to terminate Celery worker {pid}: {e}")
                        
                        # Wait a moment for workers to shut down gracefully
                        time.sleep(2)
                        
                        logger.info("Celery workers stopped successfully")
                    else:
                        logger.info("No Celery workers found to stop")
                except Exception as e:
                    logger.warning(f"Failed to stop Celery workers: {e}")

                # Try to restart using systemctl if available (production environment)
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", "mvidarr"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        # Service is managed by systemd - try sudo restart
                        logger.info("Restarting via systemctl...")
                        try:
                            subprocess.run(
                                ["sudo", "systemctl", "restart", "mvidarr"],
                                timeout=10,
                                check=True,
                            )
                            return
                        except (
                            subprocess.CalledProcessError,
                            subprocess.TimeoutExpired,
                        ):
                            # Sudo failed, fall through to SIGTERM method
                            logger.warning(
                                "Systemctl restart failed, using process termination method"
                            )
                except (
                    subprocess.TimeoutExpired,
                    subprocess.CalledProcessError,
                    FileNotFoundError,
                ):
                    pass

                # Try using the manage_service.sh script if available
                script_path = os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    ),
                    "scripts",
                    "manage_service.sh",
                )
                if os.path.exists(script_path) and os.access(script_path, os.X_OK):
                    logger.info("Restarting via manage_service.sh...")
                    subprocess.run([script_path, "restart"], timeout=10)
                    return

                # Fallback: Signal the current process to restart
                logger.info("Performing graceful process restart...")
                os.kill(current_pid, signal.SIGTERM)

            except Exception as e:
                logger.error(f"Failed to restart application: {e}")

        # Start the restart process in background
        restart_thread = threading.Thread(target=delayed_restart, daemon=True)
        restart_thread.start()

        return {
            "success": True,
            "message": "Application restart initiated. The service will be back online shortly.",
            "estimated_downtime": "10-30 seconds",
        }

    except Exception as e:
        logger.error(f"Restart application error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate application restart",
        )


@router.get("/system/logs/recent", response_model=LogsResponse)
async def get_recent_logs(
    lines: int = 50, current_user: UserInfo = Depends(require_admin_access)
):
    """Get recent application logs (Admin only)"""
    try:
        log_entries = []
        log_file_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            ),
            "data",
            "logs",
            "mvidarr.log",
        )

        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r") as f:
                    file_lines = f.readlines()
                    recent_lines = (
                        file_lines[-lines:] if len(file_lines) > lines else file_lines
                    )

                    for line in recent_lines:
                        line = line.strip()
                        if line:
                            log_entries.append(line)

            except Exception as e:
                logger.error(f"Error reading log file: {e}")
                log_entries = [f"Error reading log file: {e}"]
        else:
            log_entries = ["Log file not found"]

        return LogsResponse(
            log_entries=log_entries,
            log_file=log_file_path,
            entry_count=len(log_entries),
        )

    except Exception as e:
        logger.error(f"Recent logs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve recent logs",
        )


# ====================================
# User Management
# ====================================


@router.get("/users", response_model=Dict)
async def list_all_users(
    include_inactive: bool = True,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """List all users (admin only)"""
    try:
        query = session.query(User)
        if not include_inactive:
            query = query.filter(User.is_active == True)

        users = query.all()

        users_data = []
        for user in users:
            users_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": (
                        user.created_at.isoformat() if user.created_at else None
                    ),
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                    "login_attempts": user.login_attempts,
                    "is_locked": bool(
                        user.account_locked_until
                        and user.account_locked_until > datetime.utcnow()
                    ),
                }
            )

        logger.info(f"Admin {current_user.username} listed {len(users)} users")

        return {"users": users_data, "total": len(users_data), "can_manage": True}

    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users",
        )


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    user_data: UserCreateRequest,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Create a new user (admin only)"""
    try:
        # Validate role
        try:
            role = UserRole[user_data.role.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {user_data.role}",
            )

        # Create user using AuthService
        success, message, user = AuthService.create_user(
            user_data.username, user_data.email, user_data.password, role
        )

        if success:
            logger.info(f"Admin {current_user.username} created user: {user.username}")

            return {
                "success": True,
                "message": message,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": (
                        user.created_at.isoformat() if user.created_at else None
                    ),
                },
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )


@router.get("/users/{user_id}", response_model=UserDetails)
async def get_user_details(
    user_id: int,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Get detailed user information"""
    try:
        user = session.query(User).filter_by(id=user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Get active sessions
        active_sessions = (
            session.query(UserSession)
            .filter_by(user_id=user_id, status=SessionStatus.ACTIVE)
            .order_by(UserSession.last_activity.desc())
            .all()
        )

        session_data = []
        for user_session in active_sessions:
            session_data.append(
                UserSessionInfo(
                    id=user_session.id,
                    session_token=(
                        user_session.session_token[:16] + "..."
                        if user_session.session_token
                        else ""
                    ),
                    ip_address=user_session.ip_address,
                    user_agent=user_session.user_agent,
                    created_at=user_session.created_at,
                    last_activity=user_session.last_activity,
                    status=user_session.status.value,
                )
            )

        return UserDetails(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
            login_attempts=user.login_attempts,
            account_locked_until=user.account_locked_until,
            active_sessions=session_data,
            preferences=user.preferences or {},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user details error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user details",
        )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role_data: UserRoleUpdateRequest,
    current_user: UserInfo = Depends(require_admin_access),
):
    """Update user role (admin only)"""
    try:
        # Validate role
        try:
            new_role = UserRole[role_data.role.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {role_data.role}",
            )

        # Update role using AuthService
        success, message = AuthService.update_user_role(
            user_id, new_role, current_user.id
        )

        if success:
            logger.info(
                f"Admin {current_user.username} updated user {user_id} role to {new_role.value}"
            )
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user role error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role",
        )


@router.post("/users/{user_id}/deactivate")
async def deactivate_user_account(
    user_id: int, current_user: UserInfo = Depends(require_admin_access)
):
    """Deactivate user account (admin only)"""
    try:
        # Prevent admin from deactivating themselves
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account",
            )

        success, message = AuthService.deactivate_user(user_id, current_user.id)

        if success:
            logger.info(f"Admin {current_user.username} deactivated user {user_id}")
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user",
        )


@router.post("/users/{user_id}/activate")
async def activate_user_account(
    user_id: int,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Activate user account (admin only)"""
    try:
        user = session.query(User).filter_by(id=user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="User is already active"
            )

        # Activate user
        user.is_active = True
        user.unlock_account()  # Also unlock if locked
        session.commit()

        logger.info(f"Admin {current_user.username} activated user {user.username}")

        return {"success": True, "message": "User activated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user",
        )


@router.post("/users/{user_id}/unlock")
async def unlock_user_account(
    user_id: int,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Unlock user account (admin only)"""
    try:
        user = session.query(User).filter_by(id=user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if not user.is_locked():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account is not locked",
            )

        # Unlock user
        user.unlock_account()
        session.commit()

        logger.info(f"Admin {current_user.username} unlocked user {user.username}")

        return {"success": True, "message": "User account unlocked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unlock user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlock user",
        )


@router.get("/users/{user_id}/sessions")
async def get_user_sessions(
    user_id: int,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Get user sessions (admin only)"""
    try:
        user = session.query(User).filter_by(id=user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Get active sessions
        sessions = (
            session.query(UserSession)
            .filter_by(user_id=user_id, status=SessionStatus.ACTIVE)
            .order_by(UserSession.last_activity.desc())
            .all()
        )

        sessions_data = []
        for user_session in sessions:
            sessions_data.append(
                {
                    "id": user_session.id,
                    "session_token": (
                        user_session.session_token[:16] + "..."
                        if user_session.session_token
                        else ""
                    ),
                    "ip_address": user_session.ip_address,
                    "user_agent": user_session.user_agent,
                    "created_at": user_session.created_at.isoformat(),
                    "last_activity": user_session.last_activity.isoformat(),
                    "status": user_session.status.value,
                    "is_current": False,  # Admin viewing can't determine current session
                }
            )

        return {"sessions": sessions_data, "total": len(sessions_data)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user sessions",
        )


@router.delete("/users/{user_id}/sessions/{session_id}")
async def revoke_user_session(
    user_id: int,
    session_id: int,
    current_user: UserInfo = Depends(require_admin_access),
    session: Session = Depends(get_db_session),
):
    """Revoke a specific user session (admin only)"""
    try:
        # Find the session
        user_session = (
            session.query(UserSession).filter_by(id=session_id, user_id=user_id).first()
        )

        if not user_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )

        # Revoke the session
        user_session.revoke()
        session.commit()

        logger.info(
            f"Admin {current_user.username} revoked session {session_id} for user {user_id}"
        )

        return {
            "success": True,
            "message": "Session revoked",
            "current_session_revoked": False,  # Admin can't revoke their own session this way
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Revoke user session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke session",
        )


@router.delete("/users/{user_id}/sessions")
async def revoke_all_user_sessions(
    user_id: int, current_user: UserInfo = Depends(require_admin_access)
):
    """Revoke all sessions for a user (admin only)"""
    try:
        # Revoke all sessions using AuthService
        success = AuthService.logout_all_sessions(user_id)

        if success:
            logger.info(
                f"Admin {current_user.username} revoked all sessions for user {user_id}"
            )

            return {
                "success": True,
                "message": "All sessions revoked",
                "redirect_to_login": user_id
                == current_user.id,  # Only if admin revoked their own
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke sessions",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Revoke all user sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke all sessions",
        )


# ====================================
# Audit Log Management
# ====================================


@router.get("/audit/logs")
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    current_user: UserInfo = Depends(require_admin_access),
):
    """Get audit logs (admin only)"""
    try:
        # For now, return a placeholder
        # In a full implementation, you'd query audit logs from database
        return {
            "logs": [
                {
                    "id": 1,
                    "timestamp": datetime.utcnow().isoformat(),
                    "event_type": "user_created",
                    "description": "Admin created new user",
                    "admin_user": current_user.username,
                    "target_user": "example_user",
                }
            ],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Audit logs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs",
        )


# ====================================
# Health & Monitoring Endpoints
# ====================================


@router.get("/health/detailed")
async def get_detailed_health(current_user: UserInfo = Depends(require_admin_access)):
    """Get detailed system health information"""
    try:
        health_info = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "connected",
                "auth": "operational",
                "jobs": "operational",
            },
            "system": {
                "pid": os.getpid(),
                "memory_usage": "unknown",  # Would need psutil for actual memory info
                "uptime": "unknown",
            },
        }

        return health_info

    except Exception as e:
        logger.error(f"Detailed health error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get health information",
        )
