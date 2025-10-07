"""
FastAPI Enhanced Scheduler Router
Migrated from Flask src/api/enhanced_scheduler.py - Enhanced Docker-Native Scheduler API
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import (
    require_admin,
    require_authentication_legacy,
)
from src.database.connection import get_db_session
from src.services.enhanced_scheduler_service import enhanced_scheduler_service
from src.utils.logger import get_logger

logger = logging.getLogger("mvidarr.fastapi.enhanced_scheduler")

router = APIRouter(
    prefix="/api/enhanced-scheduler",
    tags=["enhanced-scheduler"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class SchedulerStatusResponse(BaseModel):
    """Scheduler status response"""

    running: bool
    thread_alive: bool
    jobs_count: int
    last_health_check: Optional[str] = None
    last_run_times: Optional[Dict[str, Any]] = None
    scheduled_jobs: Optional[List[Dict[str, Any]]] = None
    environment_config: Optional[Dict[str, Any]] = None


class SchedulerTriggerResponse(BaseModel):
    """Scheduler trigger response"""

    success: bool
    message: str
    task_id: Optional[str] = None
    triggered_at: Optional[str] = None


class SchedulerHealthResponse(BaseModel):
    """Scheduler health response"""

    status: str
    timestamp: Optional[str] = None
    details: Dict[str, Any]


class SchedulerConfigResponse(BaseModel):
    """Scheduler configuration response"""

    environment_config: Dict[str, Any]
    scheduler_info: Dict[str, Any]


class SchedulerLogsResponse(BaseModel):
    """Scheduler logs response"""

    message: str
    note: Optional[str] = None
    parameters: Dict[str, Any]


# ========================================================================================
# ENHANCED SCHEDULER CONTROL ENDPOINTS
# ========================================================================================


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_enhanced_scheduler_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get comprehensive enhanced scheduler status"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting enhanced scheduler status for user {current_user.get('username')}"
        )

        status = enhanced_scheduler_service.get_status()

        return SchedulerStatusResponse(**status)

    except Exception as e:
        logger.error(f"Error getting enhanced scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_enhanced_scheduler(
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Start the enhanced scheduler service"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Starting enhanced scheduler for admin user {current_user.get('username')}"
        )

        enhanced_scheduler_service.start()

        return {"success": True, "message": "Enhanced scheduler started successfully"}

    except Exception as e:
        logger.error(f"Error starting enhanced scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_enhanced_scheduler(
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Stop the enhanced scheduler service"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Stopping enhanced scheduler for admin user {current_user.get('username')}"
        )

        enhanced_scheduler_service.stop()

        return {"success": True, "message": "Enhanced scheduler stopped successfully"}

    except Exception as e:
        logger.error(f"Error stopping enhanced scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_enhanced_scheduler(
    current_user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
):
    """Reload enhanced scheduler configuration"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Reloading enhanced scheduler for admin user {current_user.get('username')}"
        )

        enhanced_scheduler_service.reload_schedule()

        return {"success": True, "message": "Enhanced scheduler reloaded successfully"}

    except Exception as e:
        logger.error(f"Error reloading enhanced scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# MANUAL TASK TRIGGER ENDPOINTS
# ========================================================================================


@router.post("/trigger/download", response_model=SchedulerTriggerResponse)
async def trigger_enhanced_download(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Manually trigger a download task"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Triggering enhanced download task for user {current_user.get('username')}"
        )

        result = enhanced_scheduler_service.trigger_download_now()

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to trigger download"),
            )

        return SchedulerTriggerResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering enhanced download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/discovery", response_model=SchedulerTriggerResponse)
async def trigger_enhanced_discovery(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Manually trigger a discovery task"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Triggering enhanced discovery task for user {current_user.get('username')}"
        )

        result = enhanced_scheduler_service.trigger_discovery_now()

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to trigger discovery"),
            )

        return SchedulerTriggerResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering enhanced discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# SCHEDULER MONITORING ENDPOINTS
# ========================================================================================


@router.get("/health", response_model=SchedulerHealthResponse)
async def get_enhanced_scheduler_health():
    """Health check endpoint (no auth required for monitoring)"""
    try:
        status = enhanced_scheduler_service.get_status()

        # Determine health based on scheduler status
        is_healthy = (
            status["running"] and status["thread_alive"] and status["jobs_count"] > 0
        )

        health_status = "healthy" if is_healthy else "unhealthy"
        http_code = 200 if is_healthy else 503

        health_response = SchedulerHealthResponse(
            status=health_status,
            timestamp=status.get("last_health_check"),
            details={
                "scheduler_running": status["running"],
                "thread_alive": status["thread_alive"],
                "jobs_count": status["jobs_count"],
                "last_download": status.get("last_run_times", {}).get("download"),
                "last_discovery": status.get("last_run_times", {}).get("discovery"),
            },
        )

        if not is_healthy:
            raise HTTPException(status_code=503, detail=health_response.dict())

        return health_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced scheduler health check: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "error": str(e), "timestamp": None},
        )


@router.get("/config", response_model=SchedulerConfigResponse)
async def get_enhanced_scheduler_config(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get enhanced scheduler environment configuration"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting enhanced scheduler config for user {current_user.get('username')}"
        )

        status = enhanced_scheduler_service.get_status()

        return SchedulerConfigResponse(
            environment_config=status.get("environment_config", {}),
            scheduler_info={
                "jobs_count": status["jobs_count"],
                "scheduled_jobs": status.get("scheduled_jobs", []),
            },
        )

    except Exception as e:
        logger.error(f"Error getting enhanced scheduler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=SchedulerLogsResponse)
async def get_enhanced_scheduler_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    level: str = Query(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get recent scheduler log entries"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting enhanced scheduler logs (limit={limit}, level={level}) for user {current_user.get('username')}"
        )

        # In a real implementation, this would read from log files
        # For now, return placeholder data
        logs_response = SchedulerLogsResponse(
            message="Log retrieval not implemented",
            note="Check Docker logs with: docker logs <container_id>",
            parameters={"limit": limit, "level": level.upper(), "user_id": user_id},
        )

        return logs_response

    except Exception as e:
        logger.error(f"Error getting enhanced scheduler logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
