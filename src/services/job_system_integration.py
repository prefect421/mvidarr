"""
Flask App Integration for Background Job System
Handles startup, shutdown, and lifecycle management of the job system within Flask.
"""

import asyncio
import atexit
import logging
from typing import Optional

from flask import Flask, current_app

from .background_workers import (
    get_worker_manager,
    start_background_workers,
    stop_background_workers,
)
from .job_queue import cleanup_job_queue, get_job_queue

logger = logging.getLogger(__name__)


class JobSystemManager:
    """
    Manages the lifecycle of the background job system within Flask application
    """

    def __init__(self, app: Optional[Flask] = None):
        self.app = app
        self.job_queue = None
        self.worker_manager = None
        self._loop = None
        self._started = False

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        """Initialize job system with Flask app"""
        self.app = app

        # Store reference in app extensions
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["job_system"] = self

        # Configure job system settings from app config
        self.configure_from_app_config()

        # Register startup and shutdown handlers
        self.register_handlers()

        logger.info("Job system manager initialized with Flask app")

    def configure_from_app_config(self):
        """Configure job system from Flask app config"""
        # Default configuration
        defaults = {
            "JOB_SYSTEM_ENABLED": True,
            "JOB_WORKER_COUNT": 3,
            "JOB_CLEANUP_DAYS": 7,
            "JOB_LOG_LEVEL": "INFO",
            "JOB_AUTO_CLEANUP": True,
            "JOB_PERSIST_TO_DB": True,
        }

        # Apply defaults
        for key, value in defaults.items():
            self.app.config.setdefault(key, value)

        # Configure logging
        log_level = getattr(
            logging, self.app.config["JOB_LOG_LEVEL"].upper(), logging.INFO
        )
        logging.getLogger("mvidarr.services.job_queue").setLevel(log_level)
        logging.getLogger("mvidarr.services.background_workers").setLevel(log_level)

        logger.info(
            f"Job system configured: workers={self.app.config['JOB_WORKER_COUNT']}, "
            f"cleanup_days={self.app.config['JOB_CLEANUP_DAYS']}"
        )

    def register_handlers(self):
        """Register Flask startup and shutdown handlers"""

        @self.app.before_first_request
        def startup_job_system():
            """Start job system on first request"""
            if self.app.config["JOB_SYSTEM_ENABLED"] and not self._started:
                try:
                    # Create event loop for background tasks if needed
                    try:
                        self._loop = asyncio.get_event_loop()
                    except RuntimeError:
                        self._loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(self._loop)

                    # Start job system in background
                    self._loop.create_task(self._start_job_system())
                    logger.info("Job system startup initiated")

                except Exception as e:
                    logger.error(f"Failed to start job system: {e}")

        # Register cleanup on app shutdown
        atexit.register(self._cleanup_on_exit)

        logger.debug("Job system handlers registered")

    async def _start_job_system(self):
        """Internal method to start job system components"""
        try:
            # Initialize job queue
            self.job_queue = await get_job_queue()

            # Initialize worker manager
            self.worker_manager = await get_worker_manager()

            # Start background workers
            worker_count = self.app.config.get("JOB_WORKER_COUNT", 3)
            await start_background_workers(worker_count)

            self._started = True
            logger.info(f"Job system started successfully with {worker_count} workers")

            # Schedule periodic cleanup if enabled
            if self.app.config.get("JOB_AUTO_CLEANUP", True):
                cleanup_days = self.app.config.get("JOB_CLEANUP_DAYS", 7)
                await self._schedule_periodic_cleanup(cleanup_days)

        except Exception as e:
            logger.error(f"Failed to start job system: {e}")
            self._started = False
            raise

    async def _schedule_periodic_cleanup(self, days_to_keep: int):
        """Schedule periodic cleanup of old jobs"""

        async def cleanup_task():
            while self._started:
                try:
                    # Wait 24 hours between cleanups
                    await asyncio.sleep(24 * 60 * 60)

                    if self.job_queue:
                        removed = await self.job_queue.cleanup_old_jobs(days_to_keep)
                        if removed > 0:
                            logger.info(f"Periodic cleanup removed {removed} old jobs")

                except Exception as e:
                    logger.error(f"Periodic cleanup error: {e}")

        # Start cleanup task
        if self._loop:
            self._loop.create_task(cleanup_task())
            logger.info(f"Periodic cleanup scheduled (keeping {days_to_keep} days)")

    def _cleanup_on_exit(self):
        """Cleanup method called on application exit"""
        if self._started and self._loop:
            try:
                # Create cleanup task
                cleanup_task = self._loop.create_task(self._shutdown_job_system())

                # Wait for cleanup to complete
                if not self._loop.is_closed():
                    self._loop.run_until_complete(cleanup_task)

                logger.info("Job system cleanup completed on exit")

            except Exception as e:
                logger.error(f"Error during job system cleanup: {e}")

    async def _shutdown_job_system(self):
        """Internal method to shutdown job system components"""
        try:
            logger.info("Shutting down job system...")

            # Stop background workers
            await stop_background_workers()

            # Cleanup job queue
            await cleanup_job_queue()

            self._started = False
            logger.info("Job system shutdown completed")

        except Exception as e:
            logger.error(f"Error during job system shutdown: {e}")

    def get_status(self) -> dict:
        """Get current status of job system"""
        status = {
            "enabled": self.app.config.get("JOB_SYSTEM_ENABLED", False),
            "started": self._started,
            "worker_count": self.app.config.get("JOB_WORKER_COUNT", 0),
            "queue_stats": None,
            "worker_stats": None,
        }

        if self._started:
            try:
                if self.job_queue:
                    status["queue_stats"] = self.job_queue.get_queue_stats()

                if self.worker_manager:
                    status["worker_stats"] = self.worker_manager.get_stats()

            except Exception as e:
                logger.error(f"Error getting job system status: {e}")
                status["error"] = str(e)

        return status

    async def health_check(self) -> dict:
        """Perform comprehensive health check"""
        if not self._started:
            return {"status": "stopped", "message": "Job system is not running"}

        try:
            health_data = {
                "status": "healthy",
                "timestamp": asyncio.get_event_loop().time(),
                "components": {},
            }

            # Check job queue health
            if self.job_queue:
                queue_stats = self.job_queue.get_queue_stats()
                health_data["components"]["job_queue"] = {
                    "status": "healthy",
                    "stats": queue_stats,
                }

            # Check worker manager health
            if self.worker_manager:
                worker_health = await self.worker_manager.health_check()
                health_data["components"]["worker_manager"] = worker_health

                # Update overall status based on worker health
                if worker_health["status"] != "healthy":
                    health_data["status"] = "degraded"
                    health_data["issues"] = worker_health.get("issues", [])

            return health_data

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time(),
            }


# Global instance for Flask integration
job_system_manager = JobSystemManager()


def init_job_system(app: Flask) -> JobSystemManager:
    """Initialize job system with Flask app"""
    job_system_manager.init_app(app)
    return job_system_manager


def get_job_system_status() -> dict:
    """Get current job system status (Flask context)"""
    try:
        # Use the new Flask job integrator
        from .flask_job_integration import get_flask_job_system_status

        return get_flask_job_system_status()
    except Exception as e:
        return {
            "enabled": False,
            "started": False,
            "error": f"Job system not available: {e}",
        }


async def get_job_system_health() -> dict:
    """Get job system health check (Flask context)"""
    try:
        # Use the new Flask job integrator
        from .flask_job_integration import get_flask_job_system_health

        return await get_flask_job_system_health()
    except Exception as e:
        return {
            "status": "not_initialized",
            "message": f"Job system not available: {e}",
        }


# Utility functions for external use


def is_job_system_enabled() -> bool:
    """Check if job system is enabled"""
    try:
        # Use the new Flask job integrator
        from .flask_job_integration import is_job_system_enabled as flask_is_enabled

        return flask_is_enabled()
    except Exception:
        return False


def get_job_system_config() -> dict:
    """Get job system configuration"""
    if hasattr(current_app, "config"):
        return {
            key: current_app.config.get(key)
            for key in current_app.config.keys()
            if key.startswith("JOB_")
        }
    return {}
