"""
FastAPI Health Check API Endpoints
Enhanced for self-hosted production monitoring
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.database.async_connection import async_db_manager
from src.utils.async_subprocess import get_git_branch, get_git_version
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.health")


# Pydantic response models
class HealthResponse(BaseModel):
    status: str
    service: str = "mvidarr"


class DetailedHealthResponse(BaseModel):
    status: str
    components: Dict[str, str]
    timestamp: str


class DatabaseHealthResponse(BaseModel):
    status: str
    message: str


class VersionInfoResponse(BaseModel):
    version: str
    git_commit: str
    git_branch: str


class ServiceHealthResponse(BaseModel):
    status: str
    service: str
    message: Optional[str] = None
    error: Optional[str] = None


class SystemMetricsResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    load_average: Optional[list] = None
    uptime_seconds: int


class ProductionHealthResponse(BaseModel):
    status: str
    timestamp: str
    application: Dict[str, Any]
    database: Dict[str, Any]
    system: SystemMetricsResponse
    services: Dict[str, Any]
    alerts: list


# Create router
health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/", response_model=HealthResponse)
async def health_check():
    """Simple async health check endpoint for Docker health checks"""
    try:
        # Quick async database connectivity check
        from sqlalchemy import text

        async with async_db_manager.session_scope() as session:
            await session.execute(text("SELECT 1"))

        return HealthResponse(status="healthy")

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "error": str(e)}
        )


@health_router.get("/status", response_model=DetailedHealthResponse)
async def get_health_status():
    """Get overall system health status with async checks"""
    try:
        status = {
            "status": "healthy",
            "components": {"database": "healthy", "api": "healthy"},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Check async database health
        try:
            async with async_db_manager.session_scope() as session:
                from sqlalchemy import text

                await session.execute(text("SELECT 1"))
                logger.debug("Database health check passed")
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            status["components"]["database"] = "unhealthy"
            status["status"] = "unhealthy"

        return DetailedHealthResponse(**status)

    except Exception as e:
        logger.error(f"Health status check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@health_router.get("/database", response_model=DatabaseHealthResponse)
async def check_database():
    """Check async database connectivity and health"""
    try:
        async with async_db_manager.session_scope() as session:
            from sqlalchemy import text

            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()

            if row and row.test == 1:
                return DatabaseHealthResponse(
                    status="healthy", message="Database is accessible and healthy"
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail={"status": "unhealthy", "message": "Database query failed"},
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "error": str(e)}
        )


@health_router.get("/imvdb", response_model=ServiceHealthResponse)
async def check_imvdb():
    """Check IMVDB API connectivity with async HTTP client"""
    try:
        from src.services.imvdb_service import imvdb_service

        # If the service has async methods, use them; otherwise wrap in async
        result = await asyncio.create_task(
            asyncio.to_thread(imvdb_service.test_connection)
        )

        if result["status"] == "success":
            return ServiceHealthResponse(
                status="healthy", service="imvdb", message=result.get("message")
            )
        else:
            raise HTTPException(status_code=503, detail=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IMVDB health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "service": "imvdb", "error": str(e)},
        )


@health_router.get("/metube", response_model=ServiceHealthResponse)
async def check_metube():
    """Check yt-dlp Web UI connectivity with async HTTP client"""
    try:
        from src.services.ytdlp_service import ytdlp_service

        # If the service has async methods, use them; otherwise wrap in async
        result = await asyncio.create_task(
            asyncio.to_thread(ytdlp_service.test_connection)
        )

        if result["status"] == "success":
            return ServiceHealthResponse(
                status="healthy", service="metube", message=result.get("message")
            )
        else:
            raise HTTPException(status_code=503, detail=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"yt-dlp Web UI health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "service": "metube", "error": str(e)},
        )


@health_router.get("/version", response_model=VersionInfoResponse)
async def get_version_info():
    """Get version information with async git commands (non-blocking)"""
    try:
        # Get version from src/__init__.py
        from src import __version__

        version_info = {
            "version": __version__,
            "git_commit": "unknown",
            "git_branch": "unknown",
        }

        # Use async subprocess utilities for git commands (non-blocking)
        try:
            git_commit = await get_git_version()
            if git_commit:
                version_info["git_commit"] = git_commit
        except Exception as e:
            logger.debug(f"Could not get git commit: {e}")

        try:
            git_branch = await get_git_branch()
            if git_branch:
                version_info["git_branch"] = git_branch
        except Exception as e:
            logger.debug(f"Could not get git branch: {e}")

        # Try to read version.json as fallback
        try:
            version_json_path = (
                Path(__file__).parent.parent.parent.parent / "version.json"
            )
            if version_json_path.exists():
                with open(version_json_path) as f:
                    version_data = json.load(f)
                    if version_info["git_commit"] == "unknown":
                        version_info["git_commit"] = version_data.get(
                            "git_commit", "unknown"
                        )
        except Exception as e:
            logger.debug(f"Could not read version.json: {e}")

        return VersionInfoResponse(**version_info)

    except Exception as e:
        logger.error(f"Version info retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/performance", response_model=Dict[str, Any])
async def get_performance_stats():
    """Get subprocess performance statistics for monitoring"""
    try:
        from src.utils.async_subprocess import async_subprocess_manager

        stats = async_subprocess_manager.get_performance_stats()

        return {
            "subprocess_performance": stats,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
        }

    except Exception as e:
        logger.error(f"Performance stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


# Add missing import
import asyncio


@health_router.get("/system", response_model=SystemMetricsResponse)
async def get_system_metrics():
    """Get system resource metrics for self-hosted monitoring"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_gb = memory.available / (1024**3)

        # Disk usage
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
        disk_free_gb = disk.free / (1024**3)

        # Load average (Unix only)
        load_average = None
        if hasattr(os, "getloadavg"):
            load_average = list(os.getloadavg())

        # System uptime
        uptime_seconds = int(time.time() - psutil.boot_time())

        return SystemMetricsResponse(
            cpu_percent=round(cpu_percent, 1),
            memory_percent=round(memory_percent, 1),
            memory_available_gb=round(memory_available_gb, 1),
            disk_percent=round(disk_percent, 1),
            disk_free_gb=round(disk_free_gb, 1),
            load_average=load_average,
            uptime_seconds=uptime_seconds,
        )

    except Exception as e:
        logger.error(f"System metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/production", response_model=ProductionHealthResponse)
async def get_production_health():
    """Comprehensive health check for self-hosted production monitoring"""
    try:
        overall_status = "healthy"
        alerts = []

        # Application health
        app_health = {
            "status": "healthy",
            "version": "unknown",
            "uptime": int(time.time() - psutil.Process().create_time()),
            "workers": os.getenv("WORKERS", "unknown"),
        }

        try:
            from src import __version__

            app_health["version"] = __version__
        except:
            pass

        # Database health
        db_health = {"status": "unhealthy", "error": "Not checked"}
        try:
            async with async_db_manager.session_scope() as session:
                from sqlalchemy import text

                result = await session.execute(
                    text("SELECT COUNT(*) FROM information_schema.tables")
                )
                table_count = result.scalar()
                db_health = {
                    "status": "healthy",
                    "table_count": table_count,
                    "connection": "active",
                }
        except Exception as e:
            db_health = {"status": "unhealthy", "error": str(e)}
            overall_status = "unhealthy"
            alerts.append(f"Database connection failed: {str(e)}")

        # System metrics
        system_metrics = await get_system_metrics()

        # Check for system alerts
        if system_metrics.cpu_percent > 90:
            alerts.append(f"High CPU usage: {system_metrics.cpu_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.memory_percent > 90:
            alerts.append(f"High memory usage: {system_metrics.memory_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.disk_percent > 90:
            alerts.append(
                f"Low disk space: {system_metrics.disk_free_gb:.1f}GB remaining"
            )
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        # Service health checks
        services = {}

        # Check Redis if available
        try:
            import redis

            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
                r.ping()
                services["redis"] = {"status": "healthy", "connection": "active"}
            else:
                services["redis"] = {"status": "not_configured"}
        except Exception as e:
            services["redis"] = {"status": "unhealthy", "error": str(e)}
            if "redis" in str(e).lower():
                alerts.append(f"Redis connection failed: {str(e)}")

        # Check background job system
        try:
            from src.jobs.celery_app import celery_app

            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            if stats:
                services["celery"] = {"status": "healthy", "workers": len(stats)}
            else:
                services["celery"] = {
                    "status": "unhealthy",
                    "error": "No workers available",
                }
        except Exception as e:
            services["celery"] = {"status": "not_configured"}

        return ProductionHealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            application=app_health,
            database=db_health,
            system=system_metrics,
            services=services,
            alerts=alerts,
        )

    except Exception as e:
        logger.error(f"Production health check failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/readiness")
async def readiness_check():
    """Kubernetes-style readiness check for load balancers"""
    try:
        # Check database connectivity
        async with async_db_manager.session_scope() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))

        return {"status": "ready", "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@health_router.get("/liveness")
async def liveness_check():
    """Kubernetes-style liveness check for container health"""
    try:
        # Basic application health
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_alive",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
