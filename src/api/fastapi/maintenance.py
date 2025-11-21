"""
Maintenance API endpoints for MVidarr.

Provides simple cleanup and optimization tools for home self-hosters.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional
import logging

from src.services.maintenance_tasks import (
    cleanup_old_logs,
    optimize_database,
    cleanup_orphaned_thumbnails,
    cleanup_temp_files,
    cleanup_old_job_history,
    get_maintenance_summary,
)

logger = logging.getLogger(__name__)

# Setup templates
templates = Jinja2Templates(directory="frontend/templates")

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])


@router.get("/summary")
async def get_summary() -> Dict:
    """
    Get summary of what all maintenance tasks would find (dry run).

    Returns:
        Summary of potential cleanup actions
    """
    try:
        return get_maintenance_summary()
    except Exception as e:
        logger.error(f"Error getting maintenance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs/cleanup")
async def cleanup_logs(
    days_to_keep: int = 30,
    dry_run: bool = False,
    log_directory: Optional[str] = None
) -> Dict:
    """
    Clean up old log files.

    Args:
        days_to_keep: Keep logs from last N days (default: 30)
        dry_run: If true, only report what would be deleted (default: false)
        log_directory: Custom log directory path (optional)

    Returns:
        Cleanup results
    """
    try:
        kwargs = {"days_to_keep": days_to_keep, "dry_run": dry_run}
        if log_directory:
            kwargs["log_directory"] = log_directory

        result = cleanup_old_logs(**kwargs)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/optimize")
async def optimize_db() -> Dict:
    """
    Optimize all database tables.

    Returns:
        Optimization results
    """
    try:
        result = optimize_database()

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thumbnails/cleanup")
async def cleanup_thumbnails(
    dry_run: bool = False,
    thumbnails_path: Optional[str] = None
) -> Dict:
    """
    Clean up orphaned thumbnail files.

    Args:
        dry_run: If true, only report what would be deleted (default: false)
        thumbnails_path: Custom thumbnails directory path (optional)

    Returns:
        Cleanup results
    """
    try:
        kwargs = {"dry_run": dry_run}
        if thumbnails_path:
            kwargs["thumbnails_path"] = thumbnails_path

        result = cleanup_orphaned_thumbnails(**kwargs)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning thumbnails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/temp-files/cleanup")
async def cleanup_temp(
    dry_run: bool = False
) -> Dict:
    """
    Clean up temporary files and cache.

    Args:
        dry_run: If true, only report what would be deleted (default: false)

    Returns:
        Cleanup results
    """
    try:
        result = cleanup_temp_files(dry_run=dry_run)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/cleanup")
async def cleanup_jobs(
    days_to_keep: int = 30,
    dry_run: bool = False
) -> Dict:
    """
    Clean up old job history from Redis.

    Args:
        days_to_keep: Keep job history from last N days (default: 30)
        dry_run: If true, only report what would be deleted (default: false)

    Returns:
        Cleanup results
    """
    try:
        result = cleanup_old_job_history(days_to_keep=days_to_keep, dry_run=dry_run)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning job history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Create a separate router for the web page (without /api prefix)
page_router = APIRouter(tags=["Maintenance Pages"])


@page_router.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Render the maintenance tools page."""
    return templates.TemplateResponse("maintenance.html", {"request": request})
