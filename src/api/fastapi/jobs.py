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

    # Check Redis progress cache first (written by update_progress, survives broken result backend)
    redis_progress = _get_redis_progress(job_id)

    try:
        from src.jobs.celery_app import celery_app

        # Get task result from Celery
        result = celery_app.AsyncResult(job_id)

        try:
            state = result.state
            logger.info(f"Checking job status for {job_id}, state: {state}")
            status = result.status  # PENDING, PROGRESS, SUCCESS, FAILURE
        except ValueError as state_error:
            # Result expired or doesn't exist in backend
            logger.info(
                f"Job {job_id} result expired or not found in backend: {state_error}"
            )
            # If we have Redis-cached progress, surface it instead of "expired"
            if redis_progress:
                return _build_redis_progress_response(job_id, redis_progress)
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
        is_successful = False

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
                try:
                    error_info = result.result
                    error_msg = str(error_info) if error_info else "Unknown error"
                except Exception:
                    error_msg = "Task failed with unknown error"

                task_result = {"success": False, "error": error_msg}
        else:
            # Task is still running — check PROGRESS state
            if status == "PROGRESS":
                try:
                    progress_info = result.info or {}
                except Exception:
                    progress_info = {}

            # If Celery backend returns PENDING but we have Redis progress,
            # use the cached progress (handles broken result backend)
            if status == "PENDING" and redis_progress:
                return _build_redis_progress_response(job_id, redis_progress)

        return {
            "job_id": job_id,
            "status": status.lower(),
            "progress": progress_info or redis_progress,
            "result": task_result,
            "ready": is_ready,
            "successful": is_successful if is_ready else None,
            "failed": not is_successful if is_ready else None,
        }

    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {type(e).__name__}: {e}")
        # Surface Redis progress even when Celery is totally unavailable
        if redis_progress:
            return _build_redis_progress_response(job_id, redis_progress)
        return {
            "job_id": job_id,
            "status": "error",
            "progress": None,
            "result": {"success": False, "error": "Internal server error"},
            "ready": True,
            "successful": False,
            "failed": True,
        }


def _get_redis_progress(job_id: str) -> dict:
    """Try to read cached progress from Redis (written by update_progress)"""
    try:
        from src.jobs.redis_manager import redis_manager

        if not redis_manager.ensure_connection():
            return None
        raw = redis_manager.redis_client.get(f"job_progress:{job_id}")
        if raw:
            import json

            return json.loads(raw)
    except Exception:
        pass
    return None


def _build_redis_progress_response(job_id: str, redis_progress: dict) -> dict:
    """Build a status response from Redis-cached progress data"""
    pct = redis_progress.get("progress", 0)
    cached_status = redis_progress.get("status", "PROGRESS").lower()
    is_done = pct >= 100 or cached_status == "success"
    return {
        "job_id": job_id,
        "status": "success" if is_done else "progress",
        "progress": redis_progress,
        "result": {"success": True} if is_done else None,
        "ready": is_done,
        "successful": True if is_done else None,
        "failed": False,
    }


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """Deprecated: Job cancellation now handled by Celery"""
    return RedirectResponse(
        url=f"/api/metadata-enrichment/job/{job_id}/cancel", status_code=301
    )
