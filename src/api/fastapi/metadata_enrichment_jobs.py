"""
FastAPI Metadata Enrichment - Jobs Module
Job management endpoints (job status, cancel, celery health, celery inspect)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.metadata_enrichment.jobs")

# Create router for job management endpoints
router = APIRouter()


@router.get("/job/{job_id}/status")
async def get_job_status(
    job_id: str, current_user: dict = Depends(require_authentication)
):
    """Get status of a Celery metadata enrichment job"""
    # Handle expired/invalid job IDs
    if not job_id or job_id == "undefined":
        return {
            "job_id": job_id,
            "status": "invalid",
            "progress": None,
            "result": {"success": False, "error": "Invalid job ID"},
            "ready": True,
            "successful": False,
            "failed": True,
        }

    try:
        from src.jobs.celery_app import celery_app

        # Get task result
        result = celery_app.AsyncResult(job_id)

        try:
            # Try to get state first, this will fail if result is expired/corrupted
            state = result.state
            logger.info(f"Checking job status for {job_id}, state: {state}")
            status = result.status  # PENDING, PROGRESS, SUCCESS, FAILURE
        except ValueError as state_error:
            # Result expired or doesn't exist in backend
            logger.info(
                f"Job {job_id} result expired or not found in backend: {state_error}"
            )
            return {
                "job_id": job_id,
                "status": "expired",
                "progress": None,
                "result": {
                    "success": False,
                    "error": "Job result expired or not found",
                },
                "ready": True,
                "successful": False,
                "failed": True,
            }
        except Exception as status_error:
            logger.error(f"Error getting result status: {status_error}")
            status = "UNKNOWN"

        task_result = None
        progress_info = None

        try:
            is_ready = result.ready()
        except Exception:
            is_ready = False

        if is_ready:
            try:
                is_successful = result.successful()
            except Exception:
                is_successful = False

            if is_successful:
                try:
                    task_result = result.get()
                except Exception as get_error:
                    task_result = {
                        "success": False,
                        "error": f"Error getting result: {get_error}",
                    }
            else:
                # Task failed - get error info safely
                try:
                    error_info = result.result
                    error_msg = str(error_info) if error_info else "Unknown error"
                except Exception:
                    error_msg = "Task failed with unknown error"

                task_result = {
                    "success": False,
                    "error": error_msg,
                }
        else:
            # Task is still running - check for progress updates
            if status == "PROGRESS":
                try:
                    progress_info = result.info or {}
                except Exception:
                    progress_info = {}

        return {
            "job_id": job_id,
            "status": status.lower(),  # Convert to lowercase for consistency
            "progress": progress_info,
            "result": task_result,
            "ready": is_ready,
            "successful": is_successful if is_ready else None,
            "failed": not is_successful if is_ready else None,
        }

    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {type(e).__name__}: {e}")
        return {
            "job_id": job_id,
            "status": "error",
            "progress": None,
            "result": {"success": False, "error": "Internal server error"},
            "ready": True,
            "successful": False,
            "failed": True,
        }


@router.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: dict = Depends(require_authentication)):
    """Cancel a running Celery metadata enrichment job"""
    try:
        from src.jobs.celery_app import job_manager

        # Cancel the task
        success = job_manager.cancel_job(job_id)

        if success:
            return {
                "job_id": job_id,
                "message": "Job cancelled successfully",
                "cancelled": True,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to cancel job - it may have already completed",
            )

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.get("/celery/health")
async def get_celery_health(current_user: dict = Depends(require_authentication)):
    """Get Celery workers health status"""
    try:
        from src.jobs.celery_app import check_celery_health, job_manager

        health = check_celery_health()
        active_jobs = job_manager.get_active_jobs()
        queue_stats = {}

        # Get queue lengths for different queues
        for queue_name in [
            "metadata",
            "video_downloads",
            "image_processing",
            "default",
        ]:
            queue_length = job_manager.get_queue_length(queue_name)
            if queue_length >= 0:  # -1 indicates error
                queue_stats[queue_name] = queue_length

        return {
            **health,
            "active_jobs": active_jobs,
            "queue_stats": queue_stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting Celery health: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get Celery health: {str(e)}"
        )


@router.get("/celery/inspect")
async def get_celery_inspect(current_user: dict = Depends(require_authentication)):
    """Get all Celery job information for the jobs dashboard"""
    try:
        from src.jobs.celery_app import celery_app

        inspect = celery_app.control.inspect()

        # Get active, scheduled, and reserved tasks
        active = inspect.active() or {}
        scheduled = inspect.scheduled() or {}
        reserved = inspect.reserved() or {}

        # Collect all jobs from all workers
        jobs = []

        # Process active tasks
        for worker, tasks in active.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "processing",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        # Process scheduled tasks
        for worker, tasks in scheduled.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "queued",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        # Process reserved tasks
        for worker, tasks in reserved.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "queued",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        return {
            "jobs": jobs,
            "total": len(jobs),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error inspecting Celery jobs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to inspect Celery jobs: {str(e)}"
        )
