"""
Health Check Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for system health monitoring and status reporting.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, validator

from .base import BaseResponse


class HealthStatus(str, Enum):
    """Health status levels"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ServiceType(str, Enum):
    """Types of services being monitored"""

    DATABASE = "database"
    REDIS = "redis"
    CELERY = "celery"
    FILESYSTEM = "filesystem"
    EXTERNAL_API = "external_api"
    BACKGROUND_JOBS = "background_jobs"
    SEARCH_INDEX = "search_index"
    MESSAGE_QUEUE = "message_queue"


class HealthResponse(BaseResponse):
    """Basic health check response"""

    status: HealthStatus = Field(description="Overall health status")
    version: str = Field(description="Application version")
    uptime: float = Field(ge=0, description="Application uptime in seconds")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Health check timestamp"
    )

    # Quick status indicators
    database_connected: bool = Field(description="Database connection status")
    redis_connected: bool = Field(default=True, description="Redis connection status")
    jobs_running: bool = Field(description="Background jobs system status")

    # Basic metrics
    active_connections: int = Field(ge=0, description="Active database connections")
    pending_jobs: int = Field(ge=0, description="Pending background jobs")
    memory_usage_mb: float = Field(ge=0, description="Memory usage in MB")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "status": "healthy",
                "version": "0.9.8",
                "uptime": 86400.5,
                "database_connected": True,
                "redis_connected": True,
                "jobs_running": True,
                "active_connections": 5,
                "pending_jobs": 3,
                "memory_usage_mb": 256.7,
            }
        }


class ServiceHealthResponse(BaseResponse):
    """Detailed health information for a specific service"""

    service_name: str = Field(description="Name of the service")
    service_type: ServiceType = Field(description="Type of service")
    status: HealthStatus = Field(description="Service health status")

    # Connection details
    is_connected: bool = Field(description="Whether service is accessible")
    response_time: float = Field(ge=0, description="Response time in milliseconds")
    last_check: datetime = Field(description="Last health check timestamp")

    # Service-specific metrics
    version: Optional[str] = Field(None, description="Service version")
    host: Optional[str] = Field(None, description="Service host (masked if sensitive)")
    port: Optional[int] = Field(None, description="Service port")

    # Performance metrics
    cpu_usage: Optional[float] = Field(
        None, ge=0, le=100, description="CPU usage percentage"
    )
    memory_usage: Optional[float] = Field(
        None, ge=0, le=100, description="Memory usage percentage"
    )
    disk_usage: Optional[float] = Field(
        None, ge=0, le=100, description="Disk usage percentage"
    )

    # Service-specific data
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Service-specific health details"
    )

    # Error information
    error_message: Optional[str] = Field(None, description="Error message if unhealthy")
    error_details: Optional[Dict[str, Any]] = Field(
        None, description="Detailed error information"
    )

    @validator("response_time")
    def validate_response_time(cls, v, values):
        """Set high response time for disconnected services"""
        if not values.get("is_connected", True) and v == 0:
            return 999999.0  # High value to indicate timeout
        return v


class DatabaseHealthResponse(ServiceHealthResponse):
    """Database-specific health response"""

    service_type: ServiceType = Field(
        default=ServiceType.DATABASE, description="Always 'database'"
    )

    # Database-specific metrics
    connection_pool_size: int = Field(ge=0, description="Connection pool size")
    active_connections: int = Field(ge=0, description="Active connections")
    idle_connections: int = Field(ge=0, description="Idle connections")

    # Query performance
    avg_query_time: float = Field(
        ge=0, description="Average query time in milliseconds"
    )
    slow_queries_count: int = Field(ge=0, description="Slow queries in last hour")

    # Database info
    database_name: str = Field(description="Database name")
    charset: Optional[str] = Field(None, description="Database character set")
    timezone: Optional[str] = Field(None, description="Database timezone")

    # Storage
    database_size_mb: Optional[float] = Field(
        None, ge=0, description="Database size in MB"
    )
    available_space_mb: Optional[float] = Field(
        None, ge=0, description="Available storage in MB"
    )


class DetailedHealthResponse(BaseResponse):
    """Comprehensive health check response with all system components"""

    overall_status: HealthStatus = Field(description="Overall system health")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Health check timestamp"
    )

    # System information
    version: str = Field(description="Application version")
    environment: str = Field(description="Environment (dev, prod, etc.)")
    uptime: float = Field(ge=0, description="System uptime in seconds")
    hostname: str = Field(description="Server hostname")

    # Individual service health
    services: List[ServiceHealthResponse] = Field(
        description="Health status of individual services"
    )

    # System-wide metrics
    system_metrics: Dict[str, float] = Field(
        description="System resource usage metrics"
    )

    # Performance indicators
    performance_metrics: Dict[str, float] = Field(
        description="Application performance metrics"
    )

    # Recent issues
    recent_errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="Recent errors and warnings"
    )

    # Configuration validation
    config_issues: List[str] = Field(
        default_factory=list, description="Configuration validation issues"
    )

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="System optimization recommendations"
    )

    @validator("services")
    def validate_services_not_empty(cls, v):
        """Ensure at least basic services are checked"""
        if not v:
            raise ValueError("Services list cannot be empty")
        return v


class VersionInfoResponse(BaseResponse):
    """Application version and build information"""

    version: str = Field(description="Application version")
    build_date: str = Field(description="Build timestamp")
    git_commit: str = Field(description="Git commit hash")
    git_branch: str = Field(description="Git branch")
    release_name: Optional[str] = Field(None, description="Release name")

    # Feature flags
    features: List[str] = Field(
        default_factory=list, description="Enabled features in this build"
    )

    # Environment info
    python_version: str = Field(description="Python runtime version")
    platform: str = Field(description="Operating system platform")
    architecture: str = Field(description="System architecture")

    # Dependencies
    key_dependencies: Dict[str, str] = Field(description="Versions of key dependencies")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "version": "0.9.8",
                "build_date": "2024-01-15T10:30:00Z",
                "git_commit": "a1b2c3d4e5",
                "git_branch": "dev",
                "release_name": "Phase 3 Week 32 Complete",
                "features": ["FastAPI", "Async Jobs", "OpenAPI Docs"],
                "python_version": "3.9.16",
                "platform": "Linux",
                "architecture": "x86_64",
                "key_dependencies": {
                    "fastapi": "0.104.1",
                    "sqlalchemy": "2.0.23",
                    "pydantic": "2.5.0",
                },
            }
        }


class SystemMetricsResponse(BaseResponse):
    """System resource usage metrics"""

    # CPU metrics
    cpu_usage_percent: float = Field(ge=0, le=100, description="CPU usage percentage")
    cpu_count: int = Field(ge=1, description="Number of CPU cores")
    load_average: Optional[List[float]] = Field(
        None, description="System load average (1, 5, 15 min)"
    )

    # Memory metrics
    memory_total_mb: float = Field(ge=0, description="Total system memory in MB")
    memory_used_mb: float = Field(ge=0, description="Used memory in MB")
    memory_available_mb: float = Field(ge=0, description="Available memory in MB")
    memory_usage_percent: float = Field(
        ge=0, le=100, description="Memory usage percentage"
    )

    # Disk metrics
    disk_total_gb: float = Field(ge=0, description="Total disk space in GB")
    disk_used_gb: float = Field(ge=0, description="Used disk space in GB")
    disk_available_gb: float = Field(ge=0, description="Available disk space in GB")
    disk_usage_percent: float = Field(ge=0, le=100, description="Disk usage percentage")

    # Network metrics (if available)
    network_sent_mb: Optional[float] = Field(
        None, ge=0, description="Network data sent in MB"
    )
    network_recv_mb: Optional[float] = Field(
        None, ge=0, description="Network data received in MB"
    )

    # Application-specific metrics
    active_sessions: int = Field(ge=0, description="Active user sessions")
    database_connections: int = Field(ge=0, description="Active database connections")
    background_jobs: int = Field(ge=0, description="Running background jobs")
    cache_hit_rate: Optional[float] = Field(
        None, ge=0, le=100, description="Cache hit rate percentage"
    )

    @validator("memory_used_mb")
    def validate_memory_consistency(cls, v, values):
        """Ensure memory metrics are consistent"""
        total = values.get("memory_total_mb", 0)
        if total > 0 and v > total:
            raise ValueError("Used memory cannot exceed total memory")
        return v

    @validator("disk_used_gb")
    def validate_disk_consistency(cls, v, values):
        """Ensure disk metrics are consistent"""
        total = values.get("disk_total_gb", 0)
        if total > 0 and v > total:
            raise ValueError("Used disk space cannot exceed total disk space")
        return v


class HealthSummaryResponse(BaseResponse):
    """Summary health information for dashboard display"""

    overall_status: HealthStatus = Field(description="Overall system status")
    services_healthy: int = Field(ge=0, description="Number of healthy services")
    services_warning: int = Field(ge=0, description="Number of services with warnings")
    services_critical: int = Field(ge=0, description="Number of critical services")

    # Quick indicators
    uptime_hours: float = Field(ge=0, description="System uptime in hours")
    memory_usage: float = Field(ge=0, le=100, description="Memory usage percentage")
    disk_usage: float = Field(ge=0, le=100, description="Disk usage percentage")

    # Activity summary
    requests_last_hour: int = Field(ge=0, description="API requests in last hour")
    jobs_completed_today: int = Field(
        ge=0, description="Background jobs completed today"
    )
    active_users: int = Field(ge=0, description="Currently active users")

    # Issues summary
    critical_issues: int = Field(ge=0, description="Number of critical issues")
    warnings: int = Field(ge=0, description="Number of warnings")

    # Last update
    last_updated: datetime = Field(description="When health data was last updated")


# Export all health-related models
__all__ = [
    "HealthStatus",
    "ServiceType",
    "HealthResponse",
    "ServiceHealthResponse",
    "DatabaseHealthResponse",
    "DetailedHealthResponse",
    "VersionInfoResponse",
    "SystemMetricsResponse",
    "HealthSummaryResponse",
]
