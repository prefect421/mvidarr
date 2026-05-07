"""
System Health API endpoints for MVidarr.

Provides health monitoring endpoints for home self-hosters.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from src.api.fastapi.template_system import template_system
from src.services.health_monitoring import (
    get_celery_status,
    get_cpu_usage,
    get_database_status,
    get_disk_usage,
    get_memory_usage,
    get_overall_health,
    get_recent_logs,
    get_redis_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system-health", tags=["System Health"])


@router.get("/")
async def get_health_summary() -> Dict:
    """
    Get overall system health summary.

    Returns all component statuses and overall health rating.
    """
    try:
        return get_overall_health()
    except Exception as e:
        logger.error(f"Error getting health summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/disk")
async def get_disk_health(paths: Optional[str] = None) -> Dict:
    """
    Get disk usage for specified paths.

    Args:
        paths: Comma-separated list of paths to check (optional)

    Returns:
        Disk usage information for each path
    """
    try:
        path_list = paths.split(",") if paths else None
        return {"disk_usage": get_disk_usage(path_list)}
    except Exception as e:
        logger.error(f"Error getting disk health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/memory")
async def get_memory_health() -> Dict:
    """Get current memory usage."""
    try:
        return {"memory": get_memory_usage()}
    except Exception as e:
        logger.error(f"Error getting memory health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cpu")
async def get_cpu_health() -> Dict:
    """Get current CPU usage."""
    try:
        return {"cpu": get_cpu_usage(interval=0.1)}
    except Exception as e:
        logger.error(f"Error getting CPU health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/database")
async def get_db_health() -> Dict:
    """Check database connection status."""
    try:
        return {"database": get_database_status()}
    except Exception as e:
        logger.error(f"Error getting database health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/celery")
async def get_celery_health() -> Dict:
    """Check Celery worker status."""
    try:
        return {"celery": get_celery_status()}
    except Exception as e:
        logger.error(f"Error getting Celery health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/redis")
async def get_redis_health() -> Dict:
    """Check Redis connection status."""
    try:
        return {"redis": get_redis_status()}
    except Exception as e:
        logger.error(f"Error getting Redis health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs")
async def get_logs(lines: int = 100, log_file: Optional[str] = None) -> Dict:
    """
    Get recent log entries.

    Args:
        lines: Number of recent lines to return (default: 100, max: 1000)
        log_file: Path to specific log file (optional)

    Returns:
        Recent log lines
    """
    try:
        # Limit max lines to prevent abuse
        lines = min(lines, 1000)

        log_lines = get_recent_logs(log_file=log_file, lines=lines)

        return {
            "lines_returned": len(log_lines),
            "log_file": log_file or "/app/data/logs/mvidarr.log",
            "logs": log_lines,
        }
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Create a separate router for the web page (without /api prefix)
page_router = APIRouter(tags=["System Health Pages"])


@page_router.get("/system-health", response_class=HTMLResponse)
async def system_health_page(request: Request):
    """Render the system health dashboard page."""
    context = {"page_title": "System Health"}
    return await template_system.render_response("system_health.html", request, context)
