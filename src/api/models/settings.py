"""
Settings-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all application settings and configuration operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from .base import BaseRequest, BaseResponse, TimestampMixin


class SettingType(str, Enum):
    """Setting value types"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"
    PASSWORD = "password"
    EMAIL = "email"
    URL = "url"
    PATH = "path"


class SettingCategory(str, Enum):
    """Setting categories for organization"""

    GENERAL = "general"
    AUTHENTICATION = "authentication"
    DATABASE = "database"
    MEDIA = "media"
    DOWNLOADS = "downloads"
    NOTIFICATIONS = "notifications"
    SECURITY = "security"
    PERFORMANCE = "performance"
    INTEGRATIONS = "integrations"
    UI = "ui"
    ADVANCED = "advanced"


class SchedulerStatus(str, Enum):
    """Scheduler status values"""

    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"


class SettingResponse(BaseResponse, TimestampMixin):
    """Individual setting information"""

    key: str = Field(description="Setting key identifier")
    value: Optional[Union[str, int, float, bool, list, dict]] = Field(
        None, description="Setting value"
    )
    default_value: Optional[Union[str, int, float, bool, list, dict]] = Field(
        None, description="Default value for this setting"
    )
    setting_type: SettingType = Field(description="Data type of the setting")
    category: SettingCategory = Field(description="Setting category")

    # Metadata
    name: str = Field(description="Human-readable setting name")
    description: Optional[str] = Field(None, description="Setting description")
    is_required: bool = Field(default=False, description="Whether setting is required")
    is_sensitive: bool = Field(
        default=False, description="Whether setting contains sensitive data"
    )
    is_readonly: bool = Field(default=False, description="Whether setting is read-only")

    # Validation constraints
    min_value: Optional[Union[int, float]] = Field(
        None, description="Minimum allowed value"
    )
    max_value: Optional[Union[int, float]] = Field(
        None, description="Maximum allowed value"
    )
    allowed_values: Optional[List[Union[str, int, float]]] = Field(
        None, description="List of allowed values"
    )
    validation_pattern: Optional[str] = Field(
        None, description="Regex pattern for validation"
    )

    # Display hints
    display_order: int = Field(default=0, description="Display order within category")
    help_text: Optional[str] = Field(None, description="Additional help text")
    placeholder: Optional[str] = Field(None, description="Placeholder text for UI")

    # Audit info
    last_modified_by: Optional[int] = Field(
        None, description="User ID who last modified"
    )
    last_modified_by_username: Optional[str] = Field(
        None, description="Username who last modified"
    )

    @validator("value")
    def validate_value_type(cls, v, values):
        """Validate value matches declared type"""
        if v is None:
            return v

        setting_type = values.get("setting_type")
        if not setting_type:
            return v

        if setting_type == SettingType.STRING and not isinstance(v, str):
            raise ValueError(f"Value must be string, got {type(v).__name__}")
        elif setting_type == SettingType.INTEGER and not isinstance(v, int):
            raise ValueError(f"Value must be integer, got {type(v).__name__}")
        elif setting_type == SettingType.FLOAT and not isinstance(v, (int, float)):
            raise ValueError(f"Value must be numeric, got {type(v).__name__}")
        elif setting_type == SettingType.BOOLEAN and not isinstance(v, bool):
            raise ValueError(f"Value must be boolean, got {type(v).__name__}")
        elif setting_type == SettingType.LIST and not isinstance(v, list):
            raise ValueError(f"Value must be list, got {type(v).__name__}")
        elif setting_type == SettingType.JSON and not isinstance(v, (dict, list)):
            raise ValueError(f"Value must be dict or list, got {type(v).__name__}")

        return v


class SettingUpdateRequest(BaseRequest):
    """Request to update a single setting"""

    value: Union[str, int, float, bool, list, dict] = Field(
        ..., description="New value for the setting"
    )
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for the change"
    )


class BulkSettingsUpdateRequest(BaseRequest):
    """Request to update multiple settings at once"""

    settings: Dict[str, Union[str, int, float, bool, list, dict]] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Settings to update (key: value pairs)",
    )
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for the changes"
    )

    @validator("settings")
    def validate_settings_keys(cls, v):
        """Ensure setting keys are valid"""
        for key in v.keys():
            if not key or not isinstance(key, str):
                raise ValueError("Setting keys must be non-empty strings")
            if len(key) > 100:
                raise ValueError("Setting keys cannot exceed 100 characters")
        return v


class AllSettingsResponse(BaseResponse):
    """Response containing all system settings organized by category"""

    settings_by_category: Dict[str, List[SettingResponse]] = Field(
        description="Settings organized by category"
    )
    total_settings: int = Field(ge=0, description="Total number of settings")
    categories: List[str] = Field(description="Available categories")
    last_modified: Optional[datetime] = Field(
        None, description="When settings were last modified"
    )


class BulkUpdateResponse(BaseResponse):
    """Response for bulk settings update operation"""

    updated_count: int = Field(
        ge=0, description="Number of settings successfully updated"
    )
    failed_count: int = Field(
        ge=0, description="Number of settings that failed to update"
    )
    errors: List[Dict[str, str]] = Field(
        default_factory=list, description="Errors for failed updates"
    )
    updated_settings: List[str] = Field(
        default_factory=list, description="Keys of successfully updated settings"
    )
    failed_settings: List[str] = Field(
        default_factory=list, description="Keys of settings that failed to update"
    )


class SchedulerStatusResponse(BaseResponse):
    """Response containing scheduler status and job information"""

    status: SchedulerStatus = Field(description="Current scheduler status")
    uptime: Optional[float] = Field(
        None, ge=0, description="Scheduler uptime in seconds"
    )

    # Job statistics
    active_jobs: int = Field(ge=0, description="Currently running jobs")
    scheduled_jobs: int = Field(ge=0, description="Scheduled jobs waiting to run")
    completed_jobs_24h: int = Field(ge=0, description="Jobs completed in last 24 hours")
    failed_jobs_24h: int = Field(ge=0, description="Jobs failed in last 24 hours")

    # Job details
    job_types: Dict[str, int] = Field(
        default_factory=dict, description="Count of jobs by type"
    )
    next_jobs: List[Dict[str, Any]] = Field(
        default_factory=list, description="Next scheduled jobs"
    )
    recent_failures: List[Dict[str, Any]] = Field(
        default_factory=list, description="Recent job failures"
    )


class DatabaseConfigResponse(BaseResponse):
    """Response containing database configuration information"""

    # Connection info (sensitive data masked)
    database_type: str = Field(description="Database type (MySQL, PostgreSQL, etc.)")
    host: str = Field(description="Database host (masked if sensitive)")
    port: int = Field(description="Database port")
    database_name: str = Field(description="Database name")

    # Connection pool status
    pool_size: int = Field(ge=0, description="Connection pool size")
    active_connections: int = Field(ge=0, description="Active database connections")
    idle_connections: int = Field(ge=0, description="Idle database connections")

    # Performance metrics
    avg_query_time: float = Field(
        ge=0, description="Average query time in milliseconds"
    )
    slow_queries_24h: int = Field(ge=0, description="Slow queries in last 24 hours")

    # Database info
    version: Optional[str] = Field(None, description="Database server version")
    charset: Optional[str] = Field(None, description="Database character set")
    timezone: Optional[str] = Field(None, description="Database timezone")

    # Health check
    is_connected: bool = Field(description="Whether database is accessible")
    last_check: datetime = Field(description="Last health check timestamp")


class SettingSearchRequest(BaseRequest):
    """Request to search settings"""

    query: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Search in setting names and descriptions",
    )
    category: Optional[SettingCategory] = Field(None, description="Filter by category")
    setting_type: Optional[SettingType] = Field(
        None, description="Filter by setting type"
    )
    modified_only: bool = Field(
        default=False, description="Only show modified settings (non-default values)"
    )
    sensitive_only: bool = Field(
        default=False, description="Only show sensitive settings"
    )


class SettingValidationRequest(BaseRequest):
    """Request to validate a setting value without saving"""

    key: str = Field(..., min_length=1, max_length=100, description="Setting key")
    value: Union[str, int, float, bool, list, dict] = Field(
        ..., description="Value to validate"
    )


class SettingResetRequest(BaseRequest):
    """Request to reset settings to default values"""

    keys: List[str] = Field(
        ..., min_items=1, max_items=50, description="Setting keys to reset"
    )
    confirm_reset: bool = Field(
        ..., description="Confirmation that user wants to reset settings"
    )
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for resetting settings"
    )

    @validator("keys")
    def validate_setting_keys(cls, v):
        """Ensure keys are valid"""
        for key in v:
            if not key or len(key.strip()) == 0:
                raise ValueError("Setting keys cannot be empty")
        return [key.strip() for key in v]


class SettingExportRequest(BaseRequest):
    """Request to export settings"""

    categories: Optional[List[SettingCategory]] = Field(
        None, description="Categories to export (all if not specified)"
    )
    include_sensitive: bool = Field(
        default=False, description="Include sensitive settings in export"
    )
    include_defaults: bool = Field(
        default=False, description="Include settings with default values"
    )
    format: str = Field(
        default="json",
        pattern="^(json|yaml|env)$",
        description="Export format: json, yaml, or env",
    )


class SettingImportRequest(BaseRequest):
    """Request to import settings"""

    settings_data: str = Field(..., min_length=1, description="Settings data to import")
    format: str = Field(
        default="json",
        pattern="^(json|yaml|env)$",
        description="Data format: json, yaml, or env",
    )
    overwrite_existing: bool = Field(
        default=False, description="Overwrite existing settings"
    )
    dry_run: bool = Field(
        default=False, description="Validate import without making changes"
    )


# Export all settings-related models
__all__ = [
    "SettingType",
    "SettingCategory",
    "SchedulerStatus",
    "SettingResponse",
    "SettingUpdateRequest",
    "BulkSettingsUpdateRequest",
    "AllSettingsResponse",
    "BulkUpdateResponse",
    "SchedulerStatusResponse",
    "DatabaseConfigResponse",
    "SettingSearchRequest",
    "SettingValidationRequest",
    "SettingResetRequest",
    "SettingExportRequest",
    "SettingImportRequest",
]
