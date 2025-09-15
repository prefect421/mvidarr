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
    """Deprecated: Job status now handled by Celery"""
    return RedirectResponse(
        url=f"/api/metadata-enrichment/job/{job_id}/status", status_code=301
    )


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """Deprecated: Job cancellation now handled by Celery"""
    return RedirectResponse(
        url=f"/api/metadata-enrichment/job/{job_id}/cancel", status_code=301
    )
