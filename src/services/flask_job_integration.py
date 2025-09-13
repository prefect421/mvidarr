"""
Flask Integration for Background Job System with WebSocket Support
Integrates the background job system with Flask application lifecycle including SocketIO.
"""

import asyncio
import atexit
import logging
from typing import Optional

from flask import Flask, current_app
from flask_socketio import SocketIO

from src.api.websocket_jobs import init_websocket_job_endpoints

from .background_workers import (
    get_worker_manager,
    start_background_workers,
    stop_background_workers,
)
from .job_queue import cleanup_job_queue, get_job_queue
from .websocket_job_events import init_job_event_broadcaster

logger = logging.getLogger(__name__)


class FlaskJobSystemIntegrator:
    """
    Integrates background job system with Flask app including WebSocket support
    """

    def __init__(
        self, app: Optional[Flask] = None, socketio: Optional[SocketIO] = None
    ):
        self.app = app
        self.socketio = socketio
        self.job_queue = None
        self.worker_manager = None
        self.job_broadcaster = None
        self._loop = None
        self._started = False

        if app is not None:
            self.init_app(app, socketio)

    def init_app(self, app: Flask, socketio: Optional[SocketIO] = None):
        """Initialize job system with Flask app and optional SocketIO"""
        self.app = app
        self.socketio = socketio

        # Store reference in app extensions
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["job_system"] = self

        # Configure job system settings from app config
        self.configure_from_app_config()

        # Initialize WebSocket support if available
        if socketio:
            self.init_websocket_support(socketio)

        # Register lifecycle handlers
        self.register_handlers()

        logger.info("Flask job system integrator initialized")

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
            "JOB_WEBSOCKET_ENABLED": bool(self.socketio),
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
            f"websockets={'enabled' if self.socketio else 'disabled'}"
        )

    def init_websocket_support(self, socketio: SocketIO):
        """Initialize WebSocket support for job progress updates"""
        try:
            # Initialize job event broadcaster
            self.job_broadcaster = init_job_event_broadcaster(socketio)

            # Initialize WebSocket endpoints
            init_websocket_job_endpoints(socketio)

            # Store reference for job queue to use
            self.app.extensions["job_broadcaster"] = self.job_broadcaster

            logger.info("WebSocket job progress support initialized")

        except Exception as e:
            logger.error(f"Failed to initialize WebSocket support: {e}")
            self.app.config["JOB_WEBSOCKET_ENABLED"] = False

    def register_handlers(self):
        """Register Flask application handlers"""

        # Use the newer Flask 2.x pattern instead of before_first_request
        @self.app.before_request
        def ensure_job_system_started():
            """Ensure job system is started on first request"""
            if self.app.config["JOB_SYSTEM_ENABLED"] and not self._started:
                try:
                    # Set started flag early to prevent multiple startup attempts
                    self._started = True

                    # Create or get event loop for job system startup
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_closed():
                            raise RuntimeError("Loop is closed")
                    except RuntimeError:
                        # No event loop exists, create one
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # Start job system components synchronously within the Flask context
                    try:
                        # Run the startup task synchronously to ensure it completes
                        loop.run_until_complete(self._start_job_system())
                        logger.info("Job system startup completed successfully")
                    except Exception as startup_error:
                        logger.error(f"Failed to start job system: {startup_error}")
                        # Reset flag on failure
                        self._started = False

                except Exception as e:
                    logger.error(f"Failed to start job system: {e}")
                    self._started = False

        # Register cleanup on app shutdown
        atexit.register(self._cleanup_on_exit)

        logger.debug("Flask job system handlers registered")

    async def _start_job_system(self):
        """Internal method to start job system components"""
        try:
            # Initialize job queue
            self.job_queue = await get_job_queue()
            self.app.extensions["job_queue"] = self.job_queue

            # Initialize worker manager
            worker_count = self.app.config.get("JOB_WORKER_COUNT", 3)
            self.worker_manager = await get_worker_manager()

            # Start background workers
            await start_background_workers(worker_count)

            logger.info(f"Job system started successfully with {worker_count} workers")

            # Schedule periodic cleanup if enabled
            if self.app.config.get("JOB_AUTO_CLEANUP", True):
                cleanup_days = self.app.config.get("JOB_CLEANUP_DAYS", 7)
                await self._schedule_periodic_cleanup(cleanup_days)

        except Exception as e:
            logger.error(f"Failed to start job system: {e}")
            self._started = False
            raise

    async def _start_job_system_deferred(self):
        """Deferred startup method that handles its own exceptions"""
        try:
            await self._start_job_system()
        except Exception as e:
            logger.error(f"Deferred job system startup failed: {e}")
            self._started = False

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
        asyncio.create_task(cleanup_task())
        logger.info(f"Periodic cleanup scheduled (keeping {days_to_keep} days)")

    def _cleanup_on_exit(self):
        """Cleanup method called on application exit"""
        if self._started:
            try:
                # Create new event loop for cleanup if needed
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Run cleanup
                loop.run_until_complete(self._shutdown_job_system())

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
            "websocket_enabled": self.app.config.get("JOB_WEBSOCKET_ENABLED", False),
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

            # Check WebSocket broadcaster health
            if self.job_broadcaster:
                broadcaster_stats = self.job_broadcaster.get_subscription_stats()
                health_data["components"]["websocket_broadcaster"] = {
                    "status": "healthy",
                    "stats": broadcaster_stats,
                }

            return health_data

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time(),
            }


# Global instance for Flask integration
flask_job_integrator = FlaskJobSystemIntegrator()


def init_job_system_with_flask(
    app: Flask, socketio: Optional[SocketIO] = None
) -> FlaskJobSystemIntegrator:
    """Initialize job system with Flask app and optional SocketIO support"""
    flask_job_integrator.init_app(app, socketio)
    return flask_job_integrator


def get_flask_job_system_status() -> dict:
    """Get current job system status (Flask context)"""
    if hasattr(current_app, "extensions") and "job_system" in current_app.extensions:
        return current_app.extensions["job_system"].get_status()
    return {"enabled": False, "started": False, "error": "Job system not initialized"}


async def get_flask_job_system_health() -> dict:
    """Get job system health check (Flask context)"""
    if hasattr(current_app, "extensions") and "job_system" in current_app.extensions:
        return await current_app.extensions["job_system"].health_check()
    return {"status": "not_initialized", "message": "Job system not initialized"}


# Utility functions for external use


def is_job_system_enabled() -> bool:
    """Check if job system is enabled and running"""
    if hasattr(current_app, "extensions") and "job_system" in current_app.extensions:
        return current_app.extensions["job_system"]._started
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
