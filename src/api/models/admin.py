"""
Admin-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all administration and system management operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import EmailStr, Field, validator

from .auth import UserRole
from .base import BaseRequest, BaseResponse, PaginationRequest, TimestampMixin


class SystemStatus(str, Enum):
    """System status values"""

    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class LogLevel(str, Enum):
    """Log level options"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditAction(str, Enum):
    """Audit log action types"""

    LOGIN = "login"
    LOGOUT = "logout"
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    EXPORT = "export"
    IMPORT = "import"
    SETTINGS_CHANGE = "settings_change"
    PERMISSION_CHANGE = "permission_change"


class UserResponse(BaseResponse, TimestampMixin):
    """Complete user information response"""

    id: int = Field(description="Unique user identifier")
    username: str = Field(description="Username")
    email: Optional[EmailStr] = Field(None, description="Email address")
    role: UserRole = Field(description="User role")
    is_active: bool = Field(description="Whether user account is active")
    is_verified: bool = Field(default=False, description="Whether email is verified")
    is_2fa_enabled: bool = Field(default=False, description="Whether 2FA is enabled")

    # Statistics
    login_count: int = Field(default=0, ge=0, description="Total login count")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    last_ip: Optional[str] = Field(None, description="Last known IP address")

    # Permissions and restrictions
    permissions: List[str] = Field(
        default_factory=list, description="Specific permissions"
    )
    restrictions: List[str] = Field(
        default_factory=list, description="Account restrictions"
    )

    # Activity stats
    videos_downloaded: int = Field(
        default=0, ge=0, description="Videos downloaded by user"
    )
    videos_uploaded: int = Field(default=0, ge=0, description="Videos uploaded by user")
    playlists_created: int = Field(
        default=0, ge=0, description="Playlists created by user"
    )


class UserCreateRequest(BaseRequest):
    """Request to create a new user"""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, underscore, hyphen only)",
    )
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(
        ..., min_length=8, max_length=100, description="Initial password"
    )
    role: UserRole = Field(default=UserRole.USER, description="User role")
    is_active: bool = Field(
        default=True, description="Whether account should be active"
    )
    send_welcome_email: bool = Field(
        default=True, description="Send welcome email to user"
    )

    @validator("username")
    def validate_username_format(cls, v):
        """Validate username format"""
        v = v.lower().strip()
        if not v:
            raise ValueError("Username cannot be empty")
        return v

    @validator("email")
    def validate_email_format(cls, v):
        """Normalize email"""
        return v.lower().strip()


class UserUpdateRequest(BaseRequest):
    """Request to update user information"""

    username: Optional[str] = Field(
        None, min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$"
    )
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    permissions: Optional[List[str]] = None
    restrictions: Optional[List[str]] = None

    @validator("username")
    def validate_username(cls, v):
        """Clean username if provided"""
        return v.lower().strip() if v else None

    @validator("email")
    def validate_email(cls, v):
        """Clean email if provided"""
        return v.lower().strip() if v else None


class UserRoleUpdateRequest(BaseRequest):
    """Request to update user role"""

    role: UserRole = Field(..., description="New role for user")
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for role change"
    )


class SystemStatusResponse(BaseResponse):
    """Response containing system status information"""

    status: SystemStatus = Field(description="Overall system status")
    uptime: float = Field(ge=0, description="System uptime in seconds")
    version: str = Field(description="Application version")

    # Resource usage
    cpu_usage: float = Field(ge=0, le=100, description="CPU usage percentage")
    memory_usage: float = Field(ge=0, le=100, description="Memory usage percentage")
    disk_usage: float = Field(ge=0, le=100, description="Disk usage percentage")

    # Service status
    database_status: str = Field(description="Database connection status")
    redis_status: Optional[str] = Field(None, description="Redis connection status")
    celery_status: Optional[str] = Field(None, description="Celery worker status")

    # Statistics
    active_users: int = Field(ge=0, description="Currently active users")
    total_videos: int = Field(ge=0, description="Total videos in system")
    total_artists: int = Field(ge=0, description="Total artists in system")
    total_playlists: int = Field(ge=0, description="Total playlists in system")

    # Background tasks
    pending_tasks: int = Field(ge=0, description="Pending background tasks")
    running_tasks: int = Field(ge=0, description="Currently running tasks")
    failed_tasks_24h: int = Field(ge=0, description="Failed tasks in last 24 hours")


class DashboardResponse(BaseResponse):
    """Response for admin dashboard data"""

    system_status: SystemStatus = Field(description="Current system status")

    # Quick stats
    stats: Dict[str, int] = Field(description="Key system statistics")

    # Recent activity
    recent_users: List[Dict[str, Any]] = Field(description="Recently registered users")
    recent_videos: List[Dict[str, Any]] = Field(description="Recently added videos")
    recent_downloads: List[Dict[str, Any]] = Field(
        description="Recent download activity"
    )

    # Charts data
    user_growth: List[Dict[str, Any]] = Field(description="User growth over time")
    video_activity: List[Dict[str, Any]] = Field(description="Video activity timeline")
    system_performance: List[Dict[str, Any]] = Field(
        description="System performance metrics"
    )

    # Alerts
    alerts: List[Dict[str, Any]] = Field(description="System alerts and warnings")

    @validator("stats")
    def validate_stats_format(cls, v):
        """Ensure stats contain expected keys"""
        required_keys = [
            "total_users",
            "total_videos",
            "total_artists",
            "active_sessions",
        ]
        for key in required_keys:
            if key not in v:
                v[key] = 0
        return v


class AuditLogResponse(BaseResponse, TimestampMixin):
    """Response containing audit log entry"""

    id: int = Field(description="Log entry ID")
    user_id: Optional[int] = Field(None, description="User who performed action")
    username: Optional[str] = Field(None, description="Username")
    action: AuditAction = Field(description="Action performed")
    resource_type: Optional[str] = Field(None, description="Type of resource affected")
    resource_id: Optional[int] = Field(None, description="ID of affected resource")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")
    session_id: Optional[str] = Field(None, description="Session ID")

    @validator("details")
    def validate_details_serializable(cls, v):
        """Ensure details are JSON serializable"""
        if v:
            try:
                import json

                json.dumps(v)
                return v
            except (TypeError, ValueError):
                raise ValueError("Details must be JSON serializable")
        return v


class SystemHealthResponse(BaseResponse):
    """Detailed system health check response"""

    overall_status: SystemStatus = Field(description="Overall health status")

    # Component health
    components: Dict[str, Dict[str, Any]] = Field(
        description="Health status of individual components"
    )

    # Performance metrics
    response_times: Dict[str, float] = Field(
        description="Average response times by endpoint"
    )
    error_rates: Dict[str, float] = Field(description="Error rates by component")

    # Resource monitoring
    resources: Dict[str, Dict[str, Any]] = Field(description="System resource usage")

    # Dependencies
    external_services: Dict[str, str] = Field(
        description="Status of external service dependencies"
    )

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="System optimization recommendations"
    )


class LogsResponse(BaseResponse):
    """Response containing system logs"""

    logs: List[Dict[str, Any]] = Field(description="Log entries")
    total_count: int = Field(ge=0, description="Total number of log entries")
    filters_applied: Dict[str, Any] = Field(description="Applied filters")
    pagination: Dict[str, Any] = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        logs: List[Dict[str, Any]],
        total_count: int,
        limit: int,
        offset: int,
        filters: Dict[str, Any] = None,
        message: str = None,
    ):
        """Create paginated logs response"""
        has_more = offset + limit < total_count

        return cls(
            logs=logs,
            total_count=total_count,
            filters_applied=filters or {},
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(logs),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class LogSearchRequest(BaseRequest, PaginationRequest):
    """Request to search system logs"""

    level: Optional[LogLevel] = Field(None, description="Filter by log level")
    component: Optional[str] = Field(None, description="Filter by component name")
    message_contains: Optional[str] = Field(
        None, max_length=200, description="Search in log messages"
    )
    user_id: Optional[int] = Field(None, description="Filter by user ID")
    date_from: Optional[datetime] = Field(None, description="Start date for log search")
    date_to: Optional[datetime] = Field(None, description="End date for log search")

    @validator("date_to")
    def validate_date_range(cls, v, values):
        """Ensure date_to is after date_from"""
        if v and "date_from" in values and values["date_from"]:
            if v <= values["date_from"]:
                raise ValueError("date_to must be after date_from")
        return v


class UserStatsResponse(BaseResponse):
    """Response containing user statistics"""

    total_users: int = Field(ge=0, description="Total number of users")
    active_users: int = Field(ge=0, description="Active users in last 30 days")
    new_users_today: int = Field(ge=0, description="New users registered today")
    new_users_week: int = Field(ge=0, description="New users registered this week")

    by_role: Dict[str, int] = Field(description="User count by role")
    by_status: Dict[str, int] = Field(description="User count by status")

    login_activity: List[Dict[str, Any]] = Field(description="Login activity over time")
    most_active_users: List[Dict[str, Any]] = Field(description="Most active users")


class SystemMaintenanceRequest(BaseRequest):
    """Request to perform system maintenance"""

    maintenance_type: str = Field(
        ...,
        pattern="^(cleanup|optimize|backup|restart|update)$",
        description="Type of maintenance to perform",
    )
    scheduled_time: Optional[datetime] = Field(
        None, description="When to perform maintenance (immediate if not specified)"
    )
    notify_users: bool = Field(
        default=True, description="Notify users about maintenance"
    )
    max_downtime: Optional[int] = Field(
        None, ge=0, description="Maximum allowed downtime in seconds"
    )


# Export all admin-related models
__all__ = [
    "SystemStatus",
    "LogLevel",
    "AuditAction",
    "UserResponse",
    "UserCreateRequest",
    "UserUpdateRequest",
    "UserRoleUpdateRequest",
    "SystemStatusResponse",
    "DashboardResponse",
    "AuditLogResponse",
    "SystemHealthResponse",
    "LogsResponse",
    "LogSearchRequest",
    "UserStatsResponse",
    "SystemMaintenanceRequest",
]
