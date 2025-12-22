"""
Scheduler V2 API Router
Version: v0.10.1
Phase 4: API Layer

REST API endpoints for Scheduler V2 control and monitoring.

Endpoints:
- GET /api/v2/scheduler/status - Get scheduler status
- POST /api/v2/scheduler/start - Start scheduler
- POST /api/v2/scheduler/stop - Stop scheduler
- POST /api/v2/scheduler/trigger/discovery - Trigger discovery
- POST /api/v2/scheduler/trigger/downloads - Trigger downloads
- GET /api/v2/scheduler/jobs - Get job history
- GET /api/v2/scheduler/jobs/{job_id} - Get job details
- POST /api/v2/scheduler/jobs/{job_id}/retry - Retry failed job
- DELETE /api/v2/scheduler/jobs/{job_id} - Cancel job
- GET /api/v2/scheduler/health - Health check
- POST /api/v2/scheduler/settings/reload - Reload settings
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.database.connection import get_db
from src.database.models import ScheduledJob
from src.services.scheduler_service_v2 import scheduler_v2
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.scheduler_v2")

router = APIRouter(prefix="/api/v2/scheduler", tags=["Scheduler V2"])


# Pydantic Models for Request/Response


class SchedulerStatusResponse(BaseModel):
    """Scheduler status response"""

    status: str = Field(..., description="Scheduler status: running, stopped, error")
    enabled: bool = Field(..., description="Whether scheduler is enabled")
    celery_connected: bool = Field(..., description="Celery connection status")
    schedules: Dict[str, Any] = Field(..., description="Current schedules")
    statistics: Dict[str, Any] = Field(..., description="Job statistics (24h)")
    worker_count: int = Field(..., description="Number of Celery workers")
    health_check_enabled: bool = Field(..., description="Health check status")


class TriggerDiscoveryRequest(BaseModel):
    """Trigger discovery request"""

    artist_id: Optional[int] = Field(
        None, description="Optional artist ID for specific discovery"
    )
    triggered_by: str = Field(default="api", description="Trigger source")


class TriggerResponse(BaseModel):
    """Task trigger response"""

    status: str = Field(..., description="Trigger status")
    task_id: str = Field(..., description="Celery task ID")
    message: str = Field(..., description="Status message")
    artist_id: Optional[int] = Field(None, description="Artist ID if applicable")


class JobHistoryResponse(BaseModel):
    """Job history response"""

    jobs: List[Dict[str, Any]] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total count")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(default=0, description="Offset applied")


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(..., description="Health status: healthy, degraded, unhealthy")
    enabled: bool = Field(..., description="Scheduler enabled")
    running: bool = Field(..., description="Scheduler running")
    celery_connected: bool = Field(..., description="Celery connected")
    timestamp: str = Field(..., description="Check timestamp")


# API Endpoints


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status() -> Dict[str, Any]:
    """
    Get current scheduler status

    Returns scheduler state, statistics, and configuration.
    """
    try:
        status = scheduler_v2.get_status()
        return status

    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_scheduler() -> Dict[str, Any]:
    """
    Start the Scheduler V2 service

    Initializes scheduler with current database settings.
    """
    try:
        result = scheduler_v2.start()

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_scheduler() -> Dict[str, Any]:
    """
    Stop the Scheduler V2 service

    Gracefully stops the scheduler.
    """
    try:
        result = scheduler_v2.stop()

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/discovery", response_model=TriggerResponse)
async def trigger_discovery(request: TriggerDiscoveryRequest = None) -> Dict[str, Any]:
    """
    Manually trigger video discovery

    Triggers discovery for all artists or a specific artist.

    Args:
        request: Optional request with artist_id for specific discovery
    """
    try:
        artist_id = request.artist_id if request else None

        result = scheduler_v2.trigger_discovery_now(artist_id=artist_id)

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/downloads", response_model=TriggerResponse)
async def trigger_downloads() -> Dict[str, Any]:
    """
    Manually trigger video downloads

    Triggers scheduled downloads of wanted videos.
    """
    try:
        result = scheduler_v2.trigger_downloads_now()

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=JobHistoryResponse)
async def get_job_history(
    limit: int = Query(50, ge=1, le=500, description="Max jobs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    job_type: Optional[str] = Query(
        None, description="Filter by job type (discovery, download)"
    ),
) -> Dict[str, Any]:
    """
    Get scheduled job history

    Returns recent scheduled jobs with optional filtering.
    """
    try:
        jobs = scheduler_v2.get_scheduled_jobs_history(limit=limit, job_type=job_type)

        # Apply offset (simple implementation)
        total = len(jobs)
        jobs = jobs[offset : offset + limit] if offset < total else []

        return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}

    except Exception as e:
        logger.error(f"Failed to get job history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")
async def get_job_details(job_id: str) -> Dict[str, Any]:
    """
    Get specific job details by Celery task ID

    Returns detailed information about a scheduled job.
    """
    try:
        # Get Celery task status
        task_status = scheduler_v2.get_job_status(job_id)

        # Get ScheduledJob record if exists
        with get_db() as db:
            scheduled_job = (
                db.query(ScheduledJob).filter_by(celery_task_id=job_id).first()
            )

            if scheduled_job:
                return {
                    "celery_status": task_status,
                    "scheduled_job": scheduled_job.to_dict(),
                }
            else:
                return {"celery_status": task_status, "scheduled_job": None}

    except Exception as e:
        logger.error(f"Failed to get job details for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> Dict[str, Any]:
    """
    Retry a failed job

    Re-triggers a failed job by its task ID.
    """
    try:
        with get_db() as db:
            scheduled_job = (
                db.query(ScheduledJob).filter_by(celery_task_id=job_id).first()
            )

            if not scheduled_job:
                raise HTTPException(status_code=404, detail="Job not found")

            if scheduled_job.status not in ["failed", "retrying"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Job status is {scheduled_job.status}, cannot retry",
                )

            # Trigger appropriate task based on job type
            if scheduled_job.job_type == "discovery":
                if scheduled_job.artist_id:
                    result = scheduler_v2.trigger_discovery_now(
                        artist_id=scheduled_job.artist_id
                    )
                else:
                    result = scheduler_v2.trigger_discovery_now()
            elif scheduled_job.job_type == "download":
                result = scheduler_v2.trigger_downloads_now()
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown job type: {scheduled_job.job_type}",
                )

            return {
                "status": "retried",
                "original_job_id": job_id,
                "new_task_id": result.get("task_id"),
                "message": f"Job {job_id} retried successfully",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    """
    Cancel a pending or running job

    Attempts to cancel a Celery task.
    """
    try:
        from src.jobs.celery_app import celery_app

        # Revoke the task
        celery_app.control.revoke(job_id, terminate=True)

        # Update ScheduledJob record
        with get_db() as db:
            scheduled_job = (
                db.query(ScheduledJob).filter_by(celery_task_id=job_id).first()
            )

            if scheduled_job and scheduled_job.status in ["pending", "running"]:
                scheduled_job.status = "cancelled"
                scheduled_job.completed_at = datetime.utcnow()
                db.commit()

        return {
            "status": "cancelled",
            "task_id": job_id,
            "message": f"Job {job_id} cancelled successfully",
        }

    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def get_scheduler_health() -> Dict[str, Any]:
    """
    Get scheduler health status

    Returns health check information.
    """
    try:
        health = scheduler_v2.get_health()
        return health

    except Exception as e:
        logger.error(f"Failed to get scheduler health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/reload")
async def reload_settings() -> Dict[str, Any]:
    """
    Reload scheduler settings from database

    Updates Celery Beat schedule from current database settings.
    """
    try:
        result = scheduler_v2.update_schedule_from_settings()

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reload settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import datetime for cancel_job
from datetime import datetime
