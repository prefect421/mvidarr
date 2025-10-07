"""
FastAPI Job System Integration
Provides status and health check functions for FastAPI applications
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .background_workers import BackgroundWorkerManager, get_worker_manager
from .job_queue import JobQueue, get_job_queue

logger = logging.getLogger(__name__)

# Global references for FastAPI context
_job_queue: Optional[JobQueue] = None
_worker_manager: Optional[BackgroundWorkerManager] = None
_job_system_enabled = False
_job_system_started = False


async def initialize_fastapi_job_system(worker_count: int = 2) -> bool:
    """Initialize job system for FastAPI application"""
    global _job_queue, _worker_manager, _job_system_enabled, _job_system_started

    try:
        logger.info("Initializing FastAPI job system...")

        # Get job queue instance
        _job_queue = await get_job_queue()
        logger.info("✅ Job queue initialized")

        # Get worker manager
        _worker_manager = await get_worker_manager()
        logger.info("✅ Worker manager initialized")

        # Mark as enabled and started
        _job_system_enabled = True
        _job_system_started = True

        logger.info(
            f"✅ FastAPI job system initialized successfully with {worker_count} workers"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to initialize FastAPI job system: {e}")
        _job_system_enabled = False
        _job_system_started = False
        return False


def is_fastapi_job_system_enabled() -> bool:
    """Check if FastAPI job system is enabled"""
    return _job_system_enabled


def is_fastapi_job_system_started() -> bool:
    """Check if FastAPI job system is started"""
    return _job_system_started


def get_fastapi_job_system_status() -> Dict[str, Any]:
    """Get current job system status for FastAPI"""
    global _job_queue, _worker_manager

    status = {
        "enabled": _job_system_enabled,
        "started": _job_system_started,
        "worker_count": 0,
        "queue_stats": None,
        "worker_stats": None,
    }

    if _job_system_started:
        try:
            if _job_queue:
                queue_stats = _job_queue.get_queue_stats()
                status["queue_stats"] = queue_stats
                status["queue_size"] = queue_stats.get("total_jobs", 0)
                status["active_jobs"] = queue_stats.get("running_jobs", 0)
                status["completed_jobs"] = queue_stats.get("completed_jobs", 0)
                status["failed_jobs"] = queue_stats.get("failed_jobs", 0)

            if _worker_manager:
                worker_stats = _worker_manager.get_stats()
                status["worker_stats"] = worker_stats
                status["worker_count"] = worker_stats.get("active_workers", 0)

        except Exception as e:
            logger.error(f"Error getting FastAPI job system status: {e}")
            status["error"] = str(e)

    return status


async def get_fastapi_job_system_health() -> Dict[str, Any]:
    """Get job system health check for FastAPI"""
    global _job_queue, _worker_manager

    if not _job_system_started:
        return {"status": "stopped", "message": "Job system is not running"}

    try:
        health_data = {
            "status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "components": {},
        }

        # Check job queue health
        if _job_queue:
            queue_stats = _job_queue.get_queue_stats()
            health_data["components"]["job_queue"] = {
                "status": "healthy",
                "stats": queue_stats,
            }

        # Check worker manager health
        if _worker_manager:
            worker_health = await _worker_manager.health_check()
            health_data["components"]["worker_manager"] = worker_health

            # Update overall status based on worker health
            if worker_health["status"] != "healthy":
                health_data["status"] = "degraded"
                health_data["issues"] = worker_health.get("issues", [])

        return health_data

    except Exception as e:
        logger.error(f"FastAPI health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time(),
        }


async def get_fastapi_job_queue() -> Optional[JobQueue]:
    """Get the job queue instance for FastAPI"""
    global _job_queue
    return _job_queue


async def shutdown_fastapi_job_system():
    """Shutdown FastAPI job system"""
    global _job_queue, _worker_manager, _job_system_enabled, _job_system_started

    try:
        logger.info("Shutting down FastAPI job system...")

        # Stop background workers
        from .background_workers import stop_background_workers

        await stop_background_workers()

        # Cleanup job queue
        from .job_queue import cleanup_job_queue

        await cleanup_job_queue()

        _job_system_enabled = False
        _job_system_started = False
        _job_queue = None
        _worker_manager = None

        logger.info("FastAPI job system shutdown completed")

    except Exception as e:
        logger.error(f"Error during FastAPI job system shutdown: {e}")
