"""
Job Management Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for background job management and task processing operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, validator

from .base import (
    BaseRequest,
    BaseResponse,
    PaginationRequest,
    TaskPriority,
    TaskStatus,
    TimestampMixin,
)


class JobType(str, Enum):
    """Available job types in the system"""

    VIDEO_DOWNLOAD = "video_download"
    VIDEO_CONVERSION = "video_conversion"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    METADATA_EXTRACTION = "metadata_extraction"
    BULK_IMPORT = "bulk_import"
    CLEANUP = "cleanup"
    BACKUP = "backup"
    IMVDB_SYNC = "imvdb_sync"
    PLAYLIST_UPDATE = "playlist_update"
    SYSTEM_MAINTENANCE = "system_maintenance"


class JobRequest(BaseRequest):
    """Request to submit a new background job"""

    job_type: JobType = Field(..., description="Type of job to execute")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Job-specific parameters"
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL, description="Job priority level"
    )
    scheduled_for: Optional[datetime] = Field(
        None, description="When to execute the job (immediate if not specified)"
    )
    retry_count: int = Field(
        default=3, ge=0, le=10, description="Number of retry attempts on failure (0-10)"
    )
    timeout: Optional[int] = Field(
        None, ge=30, le=7200, description="Job timeout in seconds (30s-2h)"
    )

    @validator("parameters")
    def validate_parameters_serializable(cls, v):
        """Ensure parameters are JSON serializable"""
        try:
            import json

            json.dumps(v)
            return v
        except (TypeError, ValueError):
            raise ValueError("Parameters must be JSON serializable")

    @validator("scheduled_for")
    def validate_future_schedule(cls, v):
        """Ensure scheduled time is in the future"""
        if v and v <= datetime.utcnow():
            raise ValueError("Scheduled time must be in the future")
        return v


class JobResponse(BaseResponse, TimestampMixin):
    """Complete job information response"""

    id: str = Field(description="Unique job identifier")
    job_type: JobType = Field(description="Type of job")
    status: TaskStatus = Field(description="Current job status")
    priority: TaskPriority = Field(description="Job priority")

    # Execution details
    submitted_by: Optional[int] = Field(
        None, description="User ID who submitted the job"
    )
    submitted_by_username: Optional[str] = Field(
        None, description="Username who submitted"
    )
    scheduled_for: Optional[datetime] = Field(
        None, description="Scheduled execution time"
    )
    started_at: Optional[datetime] = Field(None, description="When job started")
    completed_at: Optional[datetime] = Field(None, description="When job completed")

    # Progress tracking
    progress: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Completion percentage"
    )
    current_step: Optional[str] = Field(None, description="Current processing step")
    total_steps: Optional[int] = Field(None, ge=1, description="Total number of steps")

    # Results and errors
    result: Optional[Dict[str, Any]] = Field(None, description="Job result data")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Optional[Dict[str, Any]] = Field(
        None, description="Detailed error information"
    )

    # Retry information
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    next_retry_at: Optional[datetime] = Field(None, description="Next retry time")

    # Performance metrics
    duration: Optional[float] = Field(None, ge=0, description="Job duration in seconds")
    memory_usage: Optional[int] = Field(
        None, ge=0, description="Peak memory usage in bytes"
    )
    cpu_time: Optional[float] = Field(
        None, ge=0, description="CPU time used in seconds"
    )

    # Job parameters (may be filtered for security)
    parameters: Optional[Dict[str, Any]] = Field(None, description="Job parameters")

    @validator("completed_at")
    def validate_completion_logic(cls, v, values):
        """Validate completion timestamp logic"""
        if v:
            status = values.get("status")
            if status not in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ]:
                raise ValueError("completed_at should only be set for finished jobs")
        return v


class JobProgressResponse(BaseResponse):
    """Job progress update response"""

    job_id: str = Field(description="Job identifier")
    status: TaskStatus = Field(description="Current status")
    progress: float = Field(ge=0.0, le=100.0, description="Completion percentage")
    current_step: Optional[str] = Field(None, description="Current step description")
    step_number: Optional[int] = Field(None, ge=1, description="Current step number")
    total_steps: Optional[int] = Field(None, ge=1, description="Total steps")
    estimated_remaining: Optional[int] = Field(
        None, ge=0, description="Estimated remaining seconds"
    )
    throughput: Optional[Dict[str, float]] = Field(
        None, description="Processing throughput metrics"
    )


class JobListResponse(BaseResponse):
    """Response containing list of jobs with pagination"""

    jobs: List[JobResponse] = Field(description="List of jobs")
    pagination: Dict[str, Any] = Field(description="Pagination information")
    summary: Dict[str, int] = Field(description="Job count summary by status")

    @classmethod
    def create_paginated(
        cls,
        jobs: List[JobResponse],
        total_count: int,
        limit: int,
        offset: int,
        summary: Dict[str, int] = None,
        message: str = None,
    ):
        """Create paginated job list response"""
        has_more = offset + limit < total_count

        return cls(
            jobs=jobs,
            summary=summary or {},
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(jobs),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class JobSearchRequest(BaseRequest, PaginationRequest):
    """Request to search jobs with filters"""

    job_types: Optional[List[JobType]] = Field(
        None, max_items=10, description="Filter by job types"
    )
    statuses: Optional[List[TaskStatus]] = Field(
        None, max_items=10, description="Filter by job statuses"
    )
    priorities: Optional[List[TaskPriority]] = Field(
        None, max_items=4, description="Filter by priorities"
    )
    submitted_by: Optional[int] = Field(
        None, ge=1, description="Filter by user who submitted"
    )
    date_from: Optional[datetime] = Field(
        None, description="Filter jobs created after this date"
    )
    date_to: Optional[datetime] = Field(
        None, description="Filter jobs created before this date"
    )
    duration_min: Optional[float] = Field(
        None, ge=0, description="Minimum job duration in seconds"
    )
    duration_max: Optional[float] = Field(
        None, ge=0, description="Maximum job duration in seconds"
    )
    has_errors: Optional[bool] = Field(
        None, description="Filter jobs with/without errors"
    )

    @validator("date_to")
    def validate_date_range(cls, v, values):
        """Ensure date_to is after date_from"""
        if v and "date_from" in values and values["date_from"]:
            if v <= values["date_from"]:
                raise ValueError("date_to must be after date_from")
        return v

    @validator("duration_max")
    def validate_duration_range(cls, v, values):
        """Ensure max duration > min duration"""
        if v and "duration_min" in values and values["duration_min"]:
            if v <= values["duration_min"]:
                raise ValueError("duration_max must be greater than duration_min")
        return v


class JobStatusUpdateRequest(BaseRequest):
    """Request to update job status (admin only)"""

    status: TaskStatus = Field(..., description="New job status")
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for status change"
    )
    force: bool = Field(
        default=False, description="Force status change even if invalid transition"
    )


class JobCancellationRequest(BaseRequest):
    """Request to cancel a job"""

    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for cancellation"
    )
    force: bool = Field(
        default=False, description="Force cancellation even if job is running"
    )


class BulkJobActionRequest(BaseRequest):
    """Request for bulk job operations"""

    job_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Job IDs to operate on (1-100 jobs)",
    )
    action: str = Field(
        ...,
        pattern="^(cancel|retry|delete|archive)$",
        description="Action to perform: cancel, retry, delete, or archive",
    )
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for bulk action"
    )

    @validator("job_ids")
    def validate_unique_job_ids(cls, v):
        """Ensure job IDs are unique"""
        return list(dict.fromkeys(v))  # Remove duplicates while preserving order


class JobStatsResponse(BaseResponse):
    """Response containing job statistics"""

    total_jobs: int = Field(ge=0, description="Total jobs in system")
    by_status: Dict[str, int] = Field(description="Job count by status")
    by_type: Dict[str, int] = Field(description="Job count by type")
    by_priority: Dict[str, int] = Field(description="Job count by priority")

    # Performance metrics
    average_duration: float = Field(ge=0, description="Average job duration in seconds")
    success_rate: float = Field(ge=0, le=100, description="Success rate percentage")
    failure_rate: float = Field(ge=0, le=100, description="Failure rate percentage")

    # Timeline data
    jobs_per_hour: List[Dict[str, Any]] = Field(description="Jobs processed per hour")
    jobs_per_day: List[Dict[str, Any]] = Field(description="Jobs processed per day")

    # Resource usage
    total_cpu_time: float = Field(ge=0, description="Total CPU time used in seconds")
    total_memory_usage: int = Field(ge=0, description="Total memory usage in bytes")

    # Recent activity
    recent_completions: List[str] = Field(description="Recently completed job IDs")
    recent_failures: List[str] = Field(description="Recently failed job IDs")


class JobRetryRequest(BaseRequest):
    """Request to retry a failed job"""

    reset_retry_count: bool = Field(
        default=False, description="Reset the retry counter to 0"
    )
    new_priority: Optional[TaskPriority] = Field(
        None, description="New priority for retry"
    )
    delay_seconds: Optional[int] = Field(
        None, ge=0, le=86400, description="Delay before retry in seconds (max 24 hours)"
    )


class JobTemplateRequest(BaseRequest):
    """Request to create a job template for reuse"""

    name: str = Field(..., min_length=1, max_length=100, description="Template name")
    description: Optional[str] = Field(
        None, max_length=500, description="Template description"
    )
    job_type: JobType = Field(..., description="Job type for template")
    default_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default parameters for jobs created from template",
    )
    default_priority: TaskPriority = Field(
        default=TaskPriority.NORMAL, description="Default priority"
    )

    @validator("name")
    def validate_template_name(cls, v):
        """Clean and validate template name"""
        name = v.strip()
        if not name:
            raise ValueError("Template name cannot be empty")
        return name


# Export all job-related models
__all__ = [
    "JobType",
    "JobRequest",
    "JobResponse",
    "JobProgressResponse",
    "JobListResponse",
    "JobSearchRequest",
    "JobStatusUpdateRequest",
    "JobCancellationRequest",
    "BulkJobActionRequest",
    "JobStatsResponse",
    "JobRetryRequest",
    "JobTemplateRequest",
]
