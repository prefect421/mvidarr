"""
FastAPI Job Management API Endpoints
Phase 2: Media Processing Optimization - Celery Job Management
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth.dependencies import get_current_user_optional
from src.jobs.base_task import (
    cancel_task,
    get_task_progress,
    get_task_result,
    get_task_status,
)
from src.jobs.celery_app import check_celery_health, job_manager
from src.jobs.redis_manager import check_redis_health, redis_manager

# DISABLED: Broken video_download_tasks module
# from src.jobs.video_download_tasks import (
#     submit_playlist_download,
#     submit_video_download,
#     submit_video_info_extraction,
# )
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.job_management")


# Pydantic response models
class JobSubmissionRequest(BaseModel):
    job_type: str = Field(
        ..., description="Type of job (video_download, playlist_download, video_info)"
    )
    url: str = Field(..., description="URL to process")
    options: Dict[str, Any] = Field(
        default_factory=dict, description="Job-specific options"
    )
    priority: str = Field(default="normal", description="Job priority")


class JobSubmissionResponse(BaseModel):
    success: bool
    task_id: str
    job_type: str
    url: str
    message: str
    submitted_at: str


class JobStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    error: Optional[str] = None


class JobProgressResponse(BaseModel):
    task_id: str
    percent: int
    message: str
    status: str
    updated_at: str
    details: Dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    redis_health: Dict[str, Any]
    celery_health: Dict[str, Any]
    system_status: str
    active_jobs: int
    queue_length: int


class JobListResponse(BaseModel):
    active_jobs: Dict[str, Any]
    queue_stats: Dict[str, Any]
    worker_stats: Dict[str, Any]


# Create router
job_router = APIRouter(prefix="/jobs", tags=["background-jobs"])


@job_router.post("/submit", response_model=JobSubmissionResponse)
async def submit_job(
    job_request: JobSubmissionRequest,
    user: Optional[dict] = Depends(get_current_user_optional),
):
    """Submit a background job for processing"""
    try:
        job_type = job_request.job_type.lower()
        url = job_request.url
        options = job_request.options or {}

        # Add user context to options if authenticated
        if user:
            options["submitted_by"] = user.get("username", "unknown")
            options["user_id"] = user.get("user_id")

        # Submit job based on type
        if job_type == "video_download":
            task_id = submit_video_download(url, options)
            message = f"Video download job submitted for: {url}"

        elif job_type == "playlist_download":
            task_id = submit_playlist_download(url, options)
            message = f"Playlist download job submitted for: {url}"

        elif job_type == "video_info":
            task_id = submit_video_info_extraction(url)
            message = f"Video info extraction job submitted for: {url}"

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported job type: {job_type}. Supported types: video_download, playlist_download, video_info",
            )

        logger.info(f"Job {task_id} submitted: {job_type} for {url}")

        return JobSubmissionResponse(
            success=True,
            task_id=task_id,
            job_type=job_type,
            url=url,
            message=message,
            submitted_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")


@job_router.get("/{task_id}/status", response_model=JobStatusResponse)
async def get_job_status(task_id: str):
    """Get status of a specific job"""
    try:
        # Get task status from Redis
        status = get_task_status(task_id)
        progress = get_task_progress(task_id)
        result = get_task_result(task_id)

        if not status and not progress:
            raise HTTPException(status_code=404, detail=f"Job {task_id} not found")

        return JobStatusResponse(
            task_id=task_id,
            status=status.get("status", "UNKNOWN") if status else "UNKNOWN",
            progress=progress,
            result=result.get("result") if result else None,
            error=status.get("details", {}).get("error") if status else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status for {task_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get job status: {str(e)}"
        )


@job_router.get("/{task_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(task_id: str):
    """Get progress of a specific job"""
    try:
        progress = get_task_progress(task_id)

        if not progress:
            raise HTTPException(
                status_code=404, detail=f"Job {task_id} progress not found"
            )

        return JobProgressResponse(
            task_id=task_id,
            percent=progress.get("percent", 0),
            message=progress.get("message", "No progress message"),
            status=progress.get("status", "UNKNOWN"),
            updated_at=progress.get("updated_at", ""),
            details={
                k: v
                for k, v in progress.items()
                if k not in ["percent", "message", "status", "updated_at"]
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job progress for {task_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get job progress: {str(e)}"
        )


@job_router.get("/{task_id}/result")
async def get_job_result(task_id: str):
    """Get result of a completed job"""
    try:
        result = get_task_result(task_id)

        if not result:
            # Check if job is still running
            status = get_task_status(task_id)
            if status:
                current_status = status.get("status", "UNKNOWN")
                if current_status in ["STARTED", "PROGRESS", "RETRY"]:
                    raise HTTPException(
                        status_code=202, detail=f"Job {task_id} is still running"
                    )
                elif current_status == "FAILURE":
                    raise HTTPException(status_code=400, detail=f"Job {task_id} failed")
                elif current_status == "CANCELLED":
                    raise HTTPException(
                        status_code=410, detail=f"Job {task_id} was cancelled"
                    )

            raise HTTPException(
                status_code=404, detail=f"Job {task_id} result not found"
            )

        return {
            "task_id": task_id,
            "result": result.get("result", {}),
            "completed_at": result.get("completed_at", ""),
            "success": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job result for {task_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get job result: {str(e)}"
        )


@job_router.post("/{task_id}/cancel")
async def cancel_job(task_id: str, reason: str = "User requested cancellation"):
    """Cancel a running job"""
    try:
        # Cancel the task in Celery
        success = job_manager.cancel_job(task_id)

        if success:
            # Also mark in Redis
            cancel_task(task_id, reason)

            logger.info(f"Job {task_id} cancelled: {reason}")
            return {
                "success": True,
                "task_id": task_id,
                "message": f"Job cancelled: {reason}",
                "cancelled_at": datetime.utcnow().isoformat(),
            }
        else:
            raise HTTPException(
                status_code=400, detail=f"Failed to cancel job {task_id}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@job_router.get("/list", response_model=JobListResponse)
async def list_jobs():
    """List active jobs and queue statistics"""
    try:
        # Get active jobs from Celery
        active_jobs = job_manager.get_active_jobs()

        # Get job statistics
        stats = job_manager.get_job_stats()

        # Get queue lengths
        queue_stats = {
            "video_downloads": job_manager.get_queue_length("video_downloads"),
            "metadata": job_manager.get_queue_length("metadata"),
            "image_processing": job_manager.get_queue_length("image_processing"),
            "default": job_manager.get_queue_length("default"),
        }

        return JobListResponse(
            active_jobs=active_jobs, queue_stats=queue_stats, worker_stats=stats
        )

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@job_router.get("/health", response_model=SystemHealthResponse)
async def get_system_health():
    """Get health status of the background job system"""
    try:
        # Check Redis health
        redis_health = check_redis_health()

        # Check Celery health
        celery_health = check_celery_health()

        # Get active job count
        active_jobs = job_manager.get_active_jobs()
        active_count = sum(len(worker_jobs) for worker_jobs in active_jobs.values())

        # Get total queue length
        total_queue = sum(
            [
                job_manager.get_queue_length("video_downloads"),
                job_manager.get_queue_length("metadata"),
                job_manager.get_queue_length("image_processing"),
                job_manager.get_queue_length("default"),
            ]
        )

        # Determine overall system status
        if (
            redis_health.get("status") == "healthy"
            and celery_health.get("status") == "healthy"
        ):
            system_status = "healthy"
        else:
            system_status = "unhealthy"

        return SystemHealthResponse(
            redis_health=redis_health,
            celery_health=celery_health,
            system_status=system_status,
            active_jobs=active_count,
            queue_length=total_queue,
        )

    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get system health: {str(e)}"
        )


@job_router.get("/stats")
async def get_job_stats():
    """Get detailed job processing statistics"""
    try:
        # Get Redis statistics
        redis_stats = redis_manager.get_redis_stats()

        # Get Celery statistics
        celery_stats = job_manager.get_job_stats()

        # Get queue information
        queue_info = {}
        for queue_name in [
            "video_downloads",
            "metadata",
            "image_processing",
            "default",
        ]:
            queue_info[queue_name] = {
                "length": job_manager.get_queue_length(queue_name),
                "queue_name": queue_name,
            }

        return {
            "redis_stats": redis_stats,
            "celery_stats": celery_stats,
            "queue_info": queue_info,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get job stats: {str(e)}"
        )


@job_router.post("/cleanup")
async def cleanup_expired_jobs():
    """Clean up expired job data"""
    try:
        cleaned_count = redis_manager.cleanup_expired_jobs()

        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"Cleaned up {cleaned_count} expired job entries",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error cleaning up jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup jobs: {str(e)}")


# WebSocket endpoint for real-time job progress (will be implemented in websocket module)
@job_router.get("/{task_id}/subscribe")
async def subscribe_to_job_progress(task_id: str):
    """Get WebSocket URL for subscribing to real-time job progress"""
    return {
        "websocket_url": f"/ws/jobs/{task_id}/progress",
        "task_id": task_id,
        "message": "Connect to WebSocket URL for real-time progress updates",
    }


# Convenience endpoints for common operations
@job_router.post("/download-video")
async def download_video_endpoint(
    url: str,
    format: str = "best[height<=720]",
    extract_info: bool = True,
    user: Optional[dict] = Depends(get_current_user_optional),
):
    """Convenience endpoint for video downloads"""
    options = {"format": format, "extract_info": extract_info}

    request = JobSubmissionRequest(job_type="video_download", url=url, options=options)

    return await submit_job(request, user)


@job_router.post("/download-playlist")
async def download_playlist_endpoint(
    url: str,
    max_videos: int = 50,
    format: str = "best[height<=720]",
    user: Optional[dict] = Depends(get_current_user_optional),
):
    """Convenience endpoint for playlist downloads"""
    options = {"max_videos": max_videos, "format": format}

    request = JobSubmissionRequest(
        job_type="playlist_download", url=url, options=options
    )

    return await submit_job(request, user)


@job_router.post("/extract-info")
async def extract_video_info_endpoint(
    url: str, user: Optional[dict] = Depends(get_current_user_optional)
):
    """Convenience endpoint for video info extraction"""
    request = JobSubmissionRequest(job_type="video_info", url=url)

    return await submit_job(request, user)
