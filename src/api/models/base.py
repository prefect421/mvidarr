"""
Base Pydantic Models and Mixins for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Provides foundational classes and mixins for consistent model behavior across all endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Generic type for bulk operations
T = TypeVar("T")


class SortOrder(str, Enum):
    """Valid sort order options"""

    ASC = "asc"
    DESC = "desc"


class TaskStatus(str, Enum):
    """Valid task status values"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Valid task priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class BaseRequest(BaseModel):
    """Base class for all request models with common configuration"""

    model_config = ConfigDict(
        # Forbid extra fields to catch typos and enforce strict validation
        extra="forbid",
        # Use enum values instead of names in JSON
        use_enum_values=True,
        # Validate assignment when setting attributes
        validate_assignment=True,
        # Allow population by field name or alias
        populate_by_name=True,
    )


class BaseResponse(BaseModel):
    """Base class for all response models with common fields and configuration"""

    success: bool = Field(
        default=True, description="Whether the operation was successful"
    )
    message: Optional[str] = Field(
        default=None, description="Optional message about the operation"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )

    model_config = ConfigDict(
        # Allow population from ORM objects
        from_attributes=True,
        # Use enum values in JSON output
        use_enum_values=True,
    )


class ErrorResponse(BaseResponse):
    """Standard error response format"""

    success: bool = Field(default=False, description="Always false for error responses")
    error_code: Optional[str] = Field(
        default=None, description="Machine-readable error code"
    )
    error_details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional error information"
    )

    def __init__(
        self,
        message: str,
        error_code: str = None,
        error_details: Dict[str, Any] = None,
        **kwargs,
    ):
        super().__init__(
            success=False,
            message=message,
            error_code=error_code,
            error_details=error_details,
            **kwargs,
        )


class PaginationRequest(BaseRequest):
    """Mixin for request models that need pagination"""

    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of items to return (1-500)",
    )
    offset: int = Field(
        default=0, ge=0, description="Number of items to skip for pagination"
    )
    sort_by: str = Field(
        default="created_at",
        min_length=1,
        max_length=50,
        description="Field name to sort by",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.DESC,
        description="Sort order: 'asc' for ascending, 'desc' for descending",
    )

    @field_validator("sort_by")
    @classmethod
    def validate_sort_field(cls, v):
        """Ensure sort field contains only allowed characters"""
        if not v.replace("_", "").replace(".", "").isalnum():
            raise ValueError(
                "Sort field must contain only alphanumeric characters, underscores, and dots"
            )
        return v


class PaginationResponse(BaseResponse):
    """Response wrapper that includes pagination metadata"""

    pagination: Dict[str, Any] = Field(
        description="Pagination metadata including total count and navigation info"
    )

    @classmethod
    def create(
        cls,
        data: List[Any],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create a paginated response with metadata"""
        has_more = offset + limit < total_count

        return cls(
            data=data,
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(data),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class BulkOperationRequest(BaseRequest, Generic[T]):
    """Base class for bulk operations on collections of items"""

    ids: List[int] = Field(
        ...,
        min_items=1,
        max_items=1000,
        description="List of item IDs to operate on (1-1000 items)",
    )

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, v):
        """Ensure all IDs are positive integers and unique"""
        if not all(isinstance(id_, int) and id_ > 0 for id_ in v):
            raise ValueError("All IDs must be positive integers")

        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for id_ in v:
            if id_ not in seen:
                seen.add(id_)
                unique_ids.append(id_)

        return unique_ids


class BulkOperationResponse(BaseResponse):
    """Standard response format for bulk operations"""

    total_requested: int = Field(
        description="Total number of items requested for operation"
    )
    successful: int = Field(description="Number of items successfully processed")
    failed: int = Field(default=0, description="Number of items that failed processing")
    errors: List[str] = Field(
        default_factory=list, description="List of error messages for failed items"
    )
    processed_ids: List[int] = Field(
        default_factory=list, description="IDs of successfully processed items"
    )
    failed_ids: List[int] = Field(
        default_factory=list, description="IDs of items that failed processing"
    )

    @field_validator("errors", "processed_ids", "failed_ids", mode="before")
    @classmethod
    def ensure_list(cls, v):
        """Ensure fields are always lists"""
        return v if isinstance(v, list) else []


class TaskSubmissionResponse(BaseResponse):
    """Response format for submitting background tasks"""

    task_id: str = Field(description="Unique identifier for the background task")
    task_type: str = Field(description="Type of task that was submitted")
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL, description="Task priority level"
    )
    estimated_duration: Optional[int] = Field(
        default=None, description="Estimated completion time in seconds"
    )
    status_url: str = Field(description="URL to check task status")

    @field_validator("status_url")
    @classmethod
    def validate_status_url(cls, v, info):
        """Ensure status URL includes task ID"""
        if info.data and "task_id" in info.data and info.data["task_id"] not in v:
            return f"/api/tasks/{info.data['task_id']}/status"
        return v


class TaskStatusResponse(BaseResponse):
    """Response format for task status checks"""

    task_id: str = Field(description="Unique identifier for the task")
    status: TaskStatus = Field(description="Current task status")
    progress: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Task completion percentage (0-100)"
    )
    started_at: Optional[datetime] = Field(
        default=None, description="When the task started"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When the task completed (if finished)"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if task failed"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Task result data (if completed)"
    )
    estimated_remaining: Optional[int] = Field(
        default=None, description="Estimated remaining seconds"
    )

    @field_validator("completed_at")
    @classmethod
    def validate_completion_time(cls, v, info):
        """Ensure completed_at is only set for completed/failed tasks"""
        if v is not None:
            status = info.data.get("status") if info.data else None
            if status not in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ]:
                raise ValueError("completed_at can only be set for finished tasks")
        return v


class IdListRequest(BaseRequest):
    """Simple request model for operations requiring a list of IDs"""

    ids: List[int] = Field(
        ..., min_items=1, max_items=1000, description="List of item IDs (1-1000 items)"
    )

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, v):
        """Ensure all IDs are positive and unique"""
        if not all(isinstance(id_, int) and id_ > 0 for id_ in v):
            raise ValueError("All IDs must be positive integers")

        # Remove duplicates
        return list(dict.fromkeys(v))  # Preserves order while removing duplicates


class StatusUpdateRequest(BaseRequest):
    """Generic model for updating entity status"""

    status: str = Field(
        ..., min_length=1, max_length=50, description="New status value"
    )

    @field_validator("status")
    @classmethod
    def validate_status_format(cls, v):
        """Ensure status follows standard naming conventions"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Status must contain only alphanumeric characters, underscores, and hyphens"
            )
        return v.lower()


class FilePathRequest(BaseRequest):
    """Request model for operations involving file paths"""

    file_path: str = Field(
        ..., min_length=1, max_length=500, description="File system path"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        """Basic file path validation"""
        import os

        # Check for potentially dangerous path patterns
        if ".." in v or v.startswith("/etc") or v.startswith("/root"):
            raise ValueError("Invalid or potentially dangerous file path")

        # Normalize path
        return os.path.normpath(v)


# Re-export common types for convenience
__all__ = [
    "BaseRequest",
    "BaseResponse",
    "ErrorResponse",
    "PaginationRequest",
    "PaginationResponse",
    "BulkOperationRequest",
    "BulkOperationResponse",
    "TaskSubmissionResponse",
    "TaskStatusResponse",
    "IdListRequest",
    "StatusUpdateRequest",
    "FilePathRequest",
    "SortOrder",
    "TaskStatus",
    "TaskPriority",
]
