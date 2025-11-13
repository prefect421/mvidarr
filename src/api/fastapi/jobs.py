"""
FastAPI Jobs API Router - DEPRECATED
Background jobs are now handled by Celery + Redis system.
This module provides compatibility endpoints and redirects to the new system.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.jobs")

router = APIRouter(prefix="/api/jobs", tags=["Background Jobs (Deprecated)"])


@router.get("/health")
async def get_job_system_health():
    """Redirect to Celery health endpoint"""
    return RedirectResponse(
        url="/api/metadata-enrichment/celery/health", status_code=301
    )


@router.get("/status")
async def get_job_system_status():
    """Deprecated: Job system status now handled by Celery"""
    return {
        "status": "deprecated",
        "message": "Job system migrated to Celery + Redis. Use /api/metadata-enrichment/celery/health instead.",
        "migration_complete": True,
        "new_endpoints": {
            "health": "/api/metadata-enrichment/celery/health",
            "enrich_artist": "/api/metadata-enrichment/enrich/artist/{artist_id}",
            "enrich_video": "/api/metadata-enrichment/enrich/video/{video_id}",
            "job_status": "/api/metadata-enrichment/job/{job_id}/status",
        },
    }


@router.get("/")
async def list_jobs():
    """Deprecated: Job listing now handled by Celery"""
    return {
        "status": "deprecated",
        "message": "Job system migrated to Celery + Redis. Use the new metadata enrichment endpoints.",
        "active_jobs": "Use /api/metadata-enrichment/celery/health for active job information",
    }


@router.post("/")
async def create_job():
    """Deprecated: Job creation now handled by specific Celery endpoints"""
    raise HTTPException(
        status_code=410,
        detail={
            "error": "Job creation endpoint deprecated",
            "message": "Use specific endpoints like /api/metadata-enrichment/enrich/artist/{id}",
            "migration_date": "2025-09-15",
            "new_system": "Celery + Redis",
        },
    )


@router.get("/{job_id}")
async def get_job(job_id: str):
    """
    Get status of a Celery job (wizard-compatible, no auth required)

    This endpoint queries Celery directly and is compatible with the wizard
    which uses its own middleware for access control.
    """
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

        # Get task result from Celery
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


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """Deprecated: Job cancellation now handled by Celery"""
    return RedirectResponse(
        url=f"/api/metadata-enrichment/job/{job_id}/cancel", status_code=301
    )
