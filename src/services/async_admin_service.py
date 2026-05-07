"""
Async Admin Service for FastAPI Migration
Non-blocking administrative operations using async subprocess patterns
"""

import os
import signal
import threading
import time
from pathlib import Path
from typing import Any, Dict

from src.services.async_base_service import AsyncBaseService
from src.utils.async_subprocess import (
    async_subprocess_manager,
    check_service_status,
    run_system_command,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.async_admin")


class AsyncAdminService(AsyncBaseService):
    """Async administrative service for system management operations"""

    def __init__(self):
        super().__init__("mvidarr.services.async_admin")

    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status with async operations"""
        try:
            status_info = {
                "service_name": "mvidarr",
                "restart_available": False,
                "service_managed_by_systemd": False,
                "service_details": None,
                "error": None,
            }

            # Check if running under systemd (non-blocking)
            try:
                systemd_active = await check_service_status("mvidarr")

                if systemd_active:
                    status_info["service_managed_by_systemd"] = True
                    status_info["restart_available"] = True

                    # Get detailed service status
                    try:
                        result = await run_system_command(
                            ["systemctl", "status", "mvidarr", "--no-pager"],
                            timeout=5.0,
                            capture_output=True,
                            text=True,
                        )

                        if result.returncode == 0:
                            status_info["service_details"] = result.stdout

                    except Exception as e:
                        logger.warning(f"Could not get systemd service details: {e}")

            except Exception as e:
                logger.debug(f"Systemd check failed (normal in dev environment): {e}")

            # Check for manage_service.sh script as alternative
            if not status_info["restart_available"]:
                script_path = (
                    Path(__file__).parent.parent.parent
                    / "scripts"
                    / "manage_service.sh"
                )
                if script_path.exists() and os.access(script_path, os.X_OK):
                    status_info["restart_available"] = True
                    status_info["service_details"] = (
                        "Restart available via manage_service.sh"
                    )

            return status_info

        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                "service_name": "mvidarr",
                "restart_available": False,
                "error": str(e),
            }

    async def restart_service(self) -> Dict[str, Any]:
        """Restart the service using async subprocess operations"""
        try:
            logger.info("Attempting to restart MVidarr service...")

            # Try systemctl first (production environment)
            try:
                systemd_active = await check_service_status("mvidarr")

                if systemd_active:
                    logger.info("Restarting via systemctl (async)...")
                    result = await run_system_command(
                        ["sudo", "systemctl", "restart", "mvidarr"], timeout=10.0
                    )

                    if result.returncode == 0:
                        return {
                            "success": True,
                            "method": "systemctl",
                            "message": "Service restart initiated via systemctl",
                        }
                    else:
                        logger.error(f"Systemctl restart failed: {result.stderr}")

            except Exception as e:
                logger.debug(f"Systemctl restart failed: {e}")

            # Try manage_service.sh script
            script_path = (
                Path(__file__).parent.parent.parent / "scripts" / "manage_service.sh"
            )
            if script_path.exists() and os.access(script_path, os.X_OK):
                logger.info("Restarting via manage_service.sh (async)...")
                try:
                    result = await run_system_command(
                        [str(script_path), "restart"], timeout=10.0
                    )

                    if result.returncode == 0:
                        return {
                            "success": True,
                            "method": "manage_service.sh",
                            "message": "Service restart initiated via script",
                        }
                    else:
                        logger.error(f"Script restart failed: {result.stderr}")

                except Exception as e:
                    logger.error(f"Script restart error: {e}")

            # Fallback: Signal the current process (development environment)
            logger.warning("Using fallback restart method (process signal)")

            def delayed_restart():
                """Delayed restart to allow response to be sent"""
                time.sleep(2)  # Give time for response to be sent
                logger.info("Initiating process restart...")
                os.kill(os.getpid(), signal.SIGUSR1)

            # Start restart in background thread
            restart_thread = threading.Thread(target=delayed_restart, daemon=True)
            restart_thread.start()

            return {
                "success": True,
                "method": "signal",
                "message": "Service restart initiated via process signal",
            }

        except Exception as e:
            logger.error(f"Service restart failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to restart service",
            }

    async def get_service_health(self) -> Dict[str, Any]:
        """Get service health information with async checks"""
        try:
            health_info = {"status": "healthy", "checks": {}, "timestamp": None}

            # Database connectivity check
            try:
                from sqlalchemy import text
                from src.database.async_connection import async_db_manager

                async with async_db_manager.session_scope() as session:
                    await session.execute(text("SELECT 1"))

                health_info["checks"]["database"] = {
                    "status": "healthy",
                    "message": "Database connection successful",
                }

            except Exception as e:
                health_info["checks"]["database"] = {
                    "status": "unhealthy",
                    "message": f"Database connection failed: {e}",
                }
                health_info["status"] = "unhealthy"

            # System service status check
            try:
                systemd_active = await check_service_status("mvidarr")
                health_info["checks"]["systemd"] = {
                    "status": "healthy" if systemd_active else "inactive",
                    "message": (
                        "Service is managed by systemd"
                        if systemd_active
                        else "Not running under systemd"
                    ),
                }

            except Exception as e:
                health_info["checks"]["systemd"] = {
                    "status": "unknown",
                    "message": f"Could not check systemd status: {e}",
                }

            # Add timestamp
            from datetime import datetime

            health_info["timestamp"] = datetime.utcnow().isoformat()

            return health_info

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_process_info(self) -> Dict[str, Any]:
        """Get process information using async system commands"""
        try:
            process_info = {"pid": os.getpid(), "ppid": os.getppid(), "processes": []}

            # Get process information using ps command
            try:
                result = await run_system_command(
                    ["ps", "aux", "--pid", str(os.getpid())],
                    timeout=3.0,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    if len(lines) > 1:  # Skip header
                        process_info["process_details"] = lines[1]

            except Exception as e:
                logger.debug(f"Could not get process info: {e}")

            return process_info

        except Exception as e:
            logger.error(f"Error getting process info: {e}")
            return {"error": str(e)}

    async def get_system_resources(self) -> Dict[str, Any]:
        """Get system resource information using async commands"""
        try:
            resources = {}

            # Get memory usage
            try:
                result = await run_system_command(
                    ["free", "-h"], timeout=3.0, capture_output=True, text=True
                )

                if result.returncode == 0:
                    resources["memory"] = result.stdout

            except Exception as e:
                logger.debug(f"Could not get memory info: {e}")

            # Get disk usage for current directory
            try:
                result = await run_system_command(
                    ["df", "-h", "."], timeout=3.0, capture_output=True, text=True
                )

                if result.returncode == 0:
                    resources["disk"] = result.stdout

            except Exception as e:
                logger.debug(f"Could not get disk info: {e}")

            return resources

        except Exception as e:
            logger.error(f"Error getting system resources: {e}")
            return {"error": str(e)}

    async def cleanup(self):
        """Cleanup resources"""
        await async_subprocess_manager.cleanup()
        await super().cleanup()


# Global async admin service instance
async_admin_service = AsyncAdminService()
