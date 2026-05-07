"""
Scheduled Jobs API Router
Version: v0.10.1
Phase 4: API Layer

REST API endpoints for scheduled job management and history.

Endpoints:
- GET /api/v2/jobs/scheduled - Get all scheduled jobs
- GET /api/v2/jobs/scheduled/{id} - Get job by ID
- POST /api/v2/jobs/scheduled/{id}/retry - Retry job
- POST /api/v2/jobs/scheduled/{id}/cancel - Cancel job
- GET /api/v2/jobs/history - Get job history with filters
- GET /api/v2/jobs/statistics - Get job statistics
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from src.database.connection import get_db
from src.database.models import Artist, ScheduledJob
from src.services.scheduler_service_v2 import scheduler_v2
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.scheduled_jobs")

router = APIRouter(prefix="/api/v2/jobs", tags=["Scheduled Jobs"])


# Pydantic Models


class ScheduledJobResponse(BaseModel):
    """Scheduled job response"""

    id: int
    job_type: str
    artist_id: Optional[int]
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    celery_task_id: Optional[str]
    retry_count: int
    max_retries: int
    error_message: Optional[str]
    result_summary: Optional[Dict[str, Any]]
    execution_time_seconds: Optional[int]
    triggered_by: str
    created_at: str
    updated_at: str


class JobStatisticsResponse(BaseModel):
    """Job statistics response"""

    total_jobs: int = Field(..., description="Total jobs")
    completed_jobs: int = Field(..., description="Completed jobs")
    failed_jobs: int = Field(..., description="Failed jobs")
    running_jobs: int = Field(..., description="Running jobs")
    pending_jobs: int = Field(..., description="Pending jobs")
    success_rate: float = Field(..., description="Success rate percentage")
    avg_execution_time: Optional[float] = Field(
        None, description="Average execution time"
    )
    by_job_type: Dict[str, int] = Field(..., description="Counts by job type")
    by_status: Dict[str, int] = Field(..., description="Counts by status")


# API Endpoints


@router.get("/scheduled")
async def get_all_scheduled_jobs(
    limit: int = Query(100, ge=1, le=500, description="Max jobs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status: Optional[str] = Query(None, description="Filter by status"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    artist_id: Optional[int] = Query(None, description="Filter by artist ID"),
) -> Dict[str, Any]:
    """
    Get all scheduled jobs with filtering and pagination

    Returns list of scheduled jobs matching the criteria.
    """
    try:
        with get_db() as db:
            # Build query
            query = db.query(ScheduledJob).order_by(ScheduledJob.created_at.desc())

            # Apply filters
            if status:
                query = query.filter(ScheduledJob.status == status)

            if job_type:
                query = query.filter(ScheduledJob.job_type == job_type)

            if artist_id:
                query = query.filter(ScheduledJob.artist_id == artist_id)

            # Get total count before pagination
            total = query.count()

            # Apply pagination
            jobs = query.offset(offset).limit(limit).all()

            # Convert to dict
            jobs_list = [job.to_dict() for job in jobs]

            return {"jobs": jobs_list, "total": total, "limit": limit, "offset": offset}

    except Exception as e:
        logger.error(f"Failed to get scheduled jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scheduled/{job_id}")
async def get_scheduled_job(job_id: int) -> Dict[str, Any]:
    """
    Get specific scheduled job by database ID

    Returns detailed job information including artist details.
    """
    try:
        with get_db() as db:
            job = db.query(ScheduledJob).filter_by(id=job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            job_dict = job.to_dict()

            # Add artist information if applicable
            if job.artist_id:
                artist = db.query(Artist).filter_by(id=job.artist_id).first()
                if artist:
                    job_dict["artist"] = {
                        "id": artist.id,
                        "name": artist.name,
                        "monitored": artist.monitored,
                    }

            # Add Celery task status if task is still running
            if job.celery_task_id and job.status in ["pending", "running", "retrying"]:
                celery_status = scheduler_v2.get_job_status(job.celery_task_id)
                job_dict["celery_status"] = celery_status

            return job_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scheduled/{job_id}/retry")
async def retry_scheduled_job(job_id: int) -> Dict[str, Any]:
    """
    Retry a failed scheduled job

    Creates a new task based on the failed job's parameters.
    """
    try:
        with get_db() as db:
            job = db.query(ScheduledJob).filter_by(id=job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            if job.status not in ["failed", "retrying"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Job status is {job.status}, can only retry failed jobs",
                )

            # Trigger new task based on job type
            if job.job_type == "discovery":
                if job.artist_id:
                    result = scheduler_v2.trigger_discovery_now(artist_id=job.artist_id)
                else:
                    result = scheduler_v2.trigger_discovery_now()
            elif job.job_type == "download":
                result = scheduler_v2.trigger_downloads_now()
            else:
                raise HTTPException(
                    status_code=400, detail=f"Cannot retry job type: {job.job_type}"
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scheduled/{job_id}/cancel")
async def cancel_scheduled_job(job_id: int) -> Dict[str, Any]:
    """
    Cancel a pending or running scheduled job

    Revokes the Celery task and updates job status.
    """
    try:
        with get_db() as db:
            job = db.query(ScheduledJob).filter_by(id=job_id).first()

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            if job.status not in ["pending", "running"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Job status is {job.status}, can only cancel pending/running jobs",
                )

            # Revoke Celery task
            if job.celery_task_id:
                from src.jobs.celery_app import celery_app

                celery_app.control.revoke(job.celery_task_id, terminate=True)

            # Update job status
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()
            db.commit()

            return {
                "status": "cancelled",
                "job_id": job_id,
                "message": f"Job {job_id} cancelled successfully",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history")
async def get_job_history(
    hours: int = Query(24, ge=1, le=720, description="Hours of history to retrieve"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    artist_id: Optional[int] = Query(None, description="Filter by artist ID"),
) -> Dict[str, Any]:
    """
    Get job history for specified time period

    Returns jobs from the last N hours with optional filtering.
    """
    try:
        with get_db() as db:
            # Calculate time threshold
            since = datetime.utcnow() - timedelta(hours=hours)

            # Build query
            query = (
                db.query(ScheduledJob)
                .filter(ScheduledJob.created_at >= since)
                .order_by(ScheduledJob.created_at.desc())
            )

            # Apply filters
            if job_type:
                query = query.filter(ScheduledJob.job_type == job_type)

            if status:
                query = query.filter(ScheduledJob.status == status)

            if artist_id:
                query = query.filter(ScheduledJob.artist_id == artist_id)

            jobs = query.all()

            # Convert to dict
            jobs_list = [job.to_dict() for job in jobs]

            return {
                "jobs": jobs_list,
                "total": len(jobs_list),
                "hours": hours,
                "since": since.isoformat(),
            }

    except Exception as e:
        logger.error(f"Failed to get job history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics", response_model=JobStatisticsResponse)
async def get_job_statistics(
    hours: int = Query(24, ge=1, le=720, description="Hours to calculate stats for")
) -> Dict[str, Any]:
    """
    Get job statistics for specified time period

    Returns aggregated statistics about scheduled jobs.
    """
    try:
        with get_db() as db:
            # Calculate time threshold
            since = datetime.utcnow() - timedelta(hours=hours)

            # Get all jobs in time period
            jobs = db.query(ScheduledJob).filter(ScheduledJob.created_at >= since).all()

            if not jobs:
                return {
                    "total_jobs": 0,
                    "completed_jobs": 0,
                    "failed_jobs": 0,
                    "running_jobs": 0,
                    "pending_jobs": 0,
                    "success_rate": 0.0,
                    "avg_execution_time": None,
                    "by_job_type": {},
                    "by_status": {},
                }

            # Calculate statistics
            total_jobs = len(jobs)
            completed_jobs = len([j for j in jobs if j.status == "completed"])
            failed_jobs = len([j for j in jobs if j.status == "failed"])
            running_jobs = len([j for j in jobs if j.status == "running"])
            pending_jobs = len([j for j in jobs if j.status == "pending"])

            success_rate = (
                (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
            )

            # Calculate average execution time
            execution_times = [
                j.execution_time_seconds
                for j in jobs
                if j.execution_time_seconds is not None
            ]
            avg_execution_time = (
                sum(execution_times) / len(execution_times) if execution_times else None
            )

            # Count by job type
            by_job_type = {}
            for job in jobs:
                by_job_type[job.job_type] = by_job_type.get(job.job_type, 0) + 1

            # Count by status
            by_status = {}
            for job in jobs:
                by_status[job.status] = by_status.get(job.status, 0) + 1

            return {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "running_jobs": running_jobs,
                "pending_jobs": pending_jobs,
                "success_rate": round(success_rate, 2),
                "avg_execution_time": (
                    round(avg_execution_time, 2) if avg_execution_time else None
                ),
                "by_job_type": by_job_type,
                "by_status": by_status,
            }

    except Exception as e:
        logger.error(f"Failed to get job statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/history/cleanup")
async def cleanup_old_jobs(
    days: int = Query(30, ge=1, le=365, description="Delete jobs older than N days")
) -> Dict[str, Any]:
    """
    Clean up old job history

    Deletes ScheduledJob records older than specified days.
    """
    try:
        with get_db() as db:
            # Calculate cutoff date
            cutoff = datetime.utcnow() - timedelta(days=days)

            # Delete old jobs
            deleted = (
                db.query(ScheduledJob).filter(ScheduledJob.created_at < cutoff).delete()
            )

            db.commit()

            return {
                "status": "success",
                "deleted": deleted,
                "cutoff_date": cutoff.isoformat(),
                "message": f"Deleted {deleted} jobs older than {days} days",
            }

    except Exception as e:
        logger.error(f"Failed to cleanup old jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
