"""
FastAPI Advanced Jobs API Router
Enhanced background job management with scheduling, dependencies, and analytics
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.api.fastapi.auth_dependencies import require_authentication
from src.services.job_queue import (
    BackgroundJob,
    JobPriority,
    JobStatus,
    JobType,
    get_job_queue,
)
from src.utils.structured_logger import get_structured_logger

logger = get_structured_logger("mvidarr.api.advanced_jobs")

router = APIRouter(prefix="/api/advanced-jobs", tags=["Advanced Jobs"])


# Pydantic models for request/response validation
class JobRequest(BaseModel):
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="normal", description="low, normal, high, urgent")
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_strategy: str = Field(
        default="exponential", description="exponential, linear, fixed"
    )
    scheduled_for: Optional[datetime] = Field(
        default=None, description="When to execute the job"
    )
    delay_seconds: Optional[int] = Field(
        default=None, description="Delay execution by seconds"
    )
    depends_on: List[str] = Field(
        default_factory=list, description="Job IDs this job depends on"
    )
    blocking: bool = Field(
        default=False, description="Whether this job blocks dependent jobs if it fails"
    )
    tags: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    priority: str
    progress: int
    message: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    scheduled_for: Optional[datetime]
    depends_on: List[str]
    retry_count: int
    max_retries: int
    retry_strategy: str
    error_message: Optional[str]
    tags: Dict[str, Any]


class JobAnalyticsResponse(BaseModel):
    period_days: int
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    success_rate: float
    job_types: Dict[str, Dict[str, int]]
    average_processing_times: Dict[str, float]
    retry_statistics: Dict[str, int]
    current_queue_size: int
    scheduled_jobs: int
    waiting_jobs: int


class ScheduledJobRequest(BaseModel):
    job_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    scheduled_for: Optional[datetime] = None
    delay_seconds: Optional[int] = None
    priority: str = Field(default="normal")


class DependencyRequest(BaseModel):
    depends_on_job_id: str
    blocking: bool = Field(default=False)


# Job management endpoints
@router.post("/schedule", response_model=Dict[str, str])
async def schedule_job(
    job_request: JobRequest, current_user: dict = Depends(require_authentication)
):
    """Schedule a job for immediate or delayed execution"""
    try:
        job_queue = await get_job_queue()

        # Convert string priority to enum
        try:
            priority = JobPriority[job_request.priority.upper()]
        except KeyError:
            priority = JobPriority.NORMAL

        # Convert string job type to enum
        try:
            job_type = JobType(job_request.type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid job type: {job_request.type}"
            )

        # Create job
        job = BackgroundJob(
            type=job_type,
            payload=job_request.payload,
            priority=priority,
            max_retries=job_request.max_retries,
            retry_strategy=job_request.retry_strategy,
            scheduled_for=job_request.scheduled_for,
            depends_on=job_request.depends_on,
            blocking=job_request.blocking,
            created_by=str(current_user.get("user_id", "unknown")),
            tags=job_request.tags,
        )

        # Schedule job
        if job_request.delay_seconds:
            job_id = await job_queue.schedule_job(
                job, delay_seconds=job_request.delay_seconds
            )
        else:
            job_id = await job_queue.enqueue(job)

        logger.info(f"Scheduled job {job_id} of type {job_request.type}")

        return {
            "job_id": job_id,
            "status": "scheduled" if job.scheduled_for else "queued",
            "message": f"Job {job_id} has been scheduled successfully",
        }

    except Exception as e:
        logger.error(f"Error scheduling job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics", response_model=JobAnalyticsResponse)
async def get_job_analytics(
    days: int = Query(default=7, ge=1, le=30, description="Number of days to analyze"),
    current_user: dict = Depends(require_authentication),
):
    """Get detailed job analytics for the specified period"""
    try:
        job_queue = await get_job_queue()
        analytics = job_queue.get_job_analytics(days=days)

        logger.info(f"Retrieved job analytics for {days} days")
        return JobAnalyticsResponse(**analytics)

    except Exception as e:
        logger.error(f"Error getting job analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = Query(default=None, description="Filter by job status"),
    job_type: Optional[str] = Query(default=None, description="Filter by job type"),
    limit: int = Query(
        default=50, ge=1, le=200, description="Maximum number of jobs to return"
    ),
    current_user: dict = Depends(require_authentication),
):
    """List jobs with optional filtering"""
    try:
        job_queue = await get_job_queue()

        # Get user jobs
        user_id = str(current_user.get("user_id", "unknown"))
        jobs = job_queue.get_user_jobs(user_id, limit=limit)

        # Apply filters
        if status:
            try:
                status_enum = JobStatus(status.lower())
                jobs = [job for job in jobs if job.status == status_enum]
            except ValueError:
                pass  # Invalid status, ignore filter

        if job_type:
            jobs = [job for job in jobs if job.type.value == job_type.lower()]

        # Convert to response models
        job_responses = []
        for job in jobs:
            job_responses.append(
                JobResponse(
                    id=job.id,
                    type=job.type.value,
                    status=job.status.value,
                    priority=job.priority.name.lower(),
                    progress=job.progress,
                    message=job.message,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    scheduled_for=job.scheduled_for,
                    depends_on=job.depends_on,
                    retry_count=job.retry_count,
                    max_retries=job.max_retries,
                    retry_strategy=job.retry_strategy,
                    error_message=job.error_message,
                    tags=job.tags,
                )
            )

        logger.info(f"Retrieved {len(job_responses)} jobs for user {user_id}")
        return job_responses

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: dict = Depends(require_authentication)):
    """Get detailed information about a specific job"""
    try:
        job_queue = await get_job_queue()
        job = job_queue.get_job(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has permission to view this job
        user_id = str(current_user.get("user_id", "unknown"))
        if job.created_by != user_id and not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Permission denied")

        return JobResponse(
            id=job.id,
            type=job.type.value,
            status=job.status.value,
            priority=job.priority.name.lower(),
            progress=job.progress,
            message=job.message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            scheduled_for=job.scheduled_for,
            depends_on=job.depends_on,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            retry_strategy=job.retry_strategy,
            error_message=job.error_message,
            tags=job.tags,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{job_id}/dependencies", response_model=Dict[str, str])
async def add_job_dependency(
    job_id: str,
    dependency: DependencyRequest,
    current_user: dict = Depends(require_authentication),
):
    """Add a dependency to an existing job"""
    try:
        job_queue = await get_job_queue()
        job = job_queue.get_job(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has permission to modify this job
        user_id = str(current_user.get("user_id", "unknown"))
        if job.created_by != user_id and not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Permission denied")

        # Check if dependency job exists
        dep_job = job_queue.get_job(dependency.depends_on_job_id)
        if not dep_job:
            raise HTTPException(status_code=400, detail="Dependency job not found")

        await job_queue.add_job_dependency(
            job_id, dependency.depends_on_job_id, dependency.blocking
        )

        logger.info(f"Added dependency {dependency.depends_on_job_id} to job {job_id}")

        return {
            "job_id": job_id,
            "dependency_added": dependency.depends_on_job_id,
            "blocking": dependency.blocking,
            "message": "Dependency added successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding dependency to job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{job_id}", response_model=Dict[str, str])
async def cancel_job(job_id: str, current_user: dict = Depends(require_authentication)):
    """Cancel a queued job"""
    try:
        job_queue = await get_job_queue()
        job = job_queue.get_job(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has permission to cancel this job
        user_id = str(current_user.get("user_id", "unknown"))
        if job.created_by != user_id and not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Permission denied")

        if job.status not in [
            JobStatus.QUEUED,
            JobStatus.SCHEDULED,
            JobStatus.WAITING_DEPENDENCIES,
        ]:
            raise HTTPException(
                status_code=400, detail="Job cannot be cancelled in current status"
            )

        success = await job_queue.cancel_job(job_id)

        if success:
            logger.info(f"Cancelled job {job_id}")
            return {
                "job_id": job_id,
                "status": "cancelled",
                "message": "Job cancelled successfully",
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel job")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats/queue", response_model=Dict[str, Any])
async def get_queue_stats(current_user: dict = Depends(require_authentication)):
    """Get current queue statistics"""
    try:
        job_queue = await get_job_queue()
        stats = job_queue.get_queue_stats()

        logger.debug("Retrieved queue statistics")
        return stats

    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/maintenance/process-scheduled", response_model=Dict[str, Any])
async def process_scheduled_jobs(
    current_user: dict = Depends(require_authentication),
):
    """Manually trigger processing of scheduled jobs (admin only)"""
    try:
        if not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin access required")

        job_queue = await get_job_queue()
        await job_queue.process_scheduled_jobs()

        logger.info("Manually triggered scheduled job processing")
        return {"status": "success", "message": "Scheduled jobs processing triggered"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing scheduled jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/maintenance/process-waiting", response_model=Dict[str, Any])
async def process_waiting_jobs(
    current_user: dict = Depends(require_authentication),
):
    """Manually trigger processing of jobs waiting for dependencies (admin only)"""
    try:
        if not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin access required")

        job_queue = await get_job_queue()
        await job_queue.process_waiting_jobs()

        logger.info("Manually triggered waiting job processing")
        return {"status": "success", "message": "Waiting jobs processing triggered"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing waiting jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/maintenance/cleanup", response_model=Dict[str, Any])
async def cleanup_old_jobs(
    days: int = Query(default=7, ge=1, le=30, description="Days to keep jobs"),
    current_user: dict = Depends(require_authentication),
):
    """Clean up old completed/failed jobs (admin only)"""
    try:
        if not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin access required")

        job_queue = await get_job_queue()
        removed_count = await job_queue.cleanup_old_jobs(days_to_keep=days)

        logger.info(f"Cleaned up {removed_count} old jobs")
        return {
            "status": "success",
            "removed_count": removed_count,
            "message": f"Cleaned up {removed_count} jobs older than {days} days",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
