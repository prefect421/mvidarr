"""
FastAPI Settings Management API for MVidarr
Complete settings management, scheduler control, and application restart endpoints.
Migrated from Flask settings.py for enhanced performance and async support.
"""

import os
import signal
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.services.settings_service import SettingsService, settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.settings")

# Create FastAPI router
router = APIRouter(prefix="/api/settings", tags=["settings"])

# ====================================
# Authentication (Mock for now)
# ====================================


async def get_current_admin():
    """Mock admin authentication - replace with actual authentication"""
    return {"id": 1, "username": "admin", "role": "admin"}


# ====================================
# Pydantic Models
# ====================================


class SettingUpdateRequest(BaseModel):
    """Request model for updating a setting"""

    value: Any = Field(
        ..., description="Setting value (can be string, number, boolean)"
    )
    description: Optional[str] = Field(default="", description="Setting description")


class BulkSettingsUpdateRequest(BaseModel):
    """Request model for bulk settings update"""

    settings: Dict[str, Any] = Field(
        ..., description="Dictionary of setting key-value pairs"
    )


class SettingResponse(BaseModel):
    """Response model for a single setting"""

    key: str
    value: Any
    description: str
    updated_at: str


class AllSettingsResponse(BaseModel):
    """Response model for all settings"""

    settings: Dict[str, Dict[str, Any]]
    count: int


class BulkUpdateResponse(BaseModel):
    """Response model for bulk update"""

    updated_settings: List[Dict[str, str]]
    count: int


class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status"""

    running: bool
    schedule_info: Dict[str, Any]
    diagnostics: Dict[str, Any]


class DatabaseConfigResponse(BaseModel):
    """Response model for database configuration"""

    database_config: Dict[str, str]


# ====================================
# Settings CRUD Operations
# ====================================


@router.get("/", response_model=AllSettingsResponse)
async def get_all_settings():
    """Get all application settings"""
    try:
        settings_dict = settings.get_all()

        return AllSettingsResponse(settings=settings_dict, count=len(settings_dict))

    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/database-config", response_model=DatabaseConfigResponse)
async def get_database_config():
    """Get current database configuration (read-only)"""
    try:
        from src.config.config import Config

        # Load environment variables to get current database config
        Config.load_env()

        db_config = {
            "db_host": os.environ.get("DB_HOST", "localhost"),
            "db_port": os.environ.get("DB_PORT", "3306"),
            "db_name": os.environ.get("DB_NAME", "mvidarr"),
            "db_user": os.environ.get("DB_USER", "mvidarr"),
            "db_password": "***hidden***",  # Don't expose password
            "db_pool_size": os.environ.get("DB_POOL_SIZE", "10"),
            "db_pool_overflow": os.environ.get("DB_MAX_OVERFLOW", "20"),
            "db_pool_recycle": os.environ.get("DB_POOL_RECYCLE", "3600"),
            "db_pool_timeout": os.environ.get("DB_POOL_TIMEOUT", "30"),
        }

        return DatabaseConfigResponse(database_config=db_config)

    except Exception as e:
        logger.error(f"Failed to get database config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str):
    """Get a specific setting by key"""
    try:
        all_settings = settings.get_all()

        if key not in all_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found"
            )

        setting_data = all_settings[key]

        return SettingResponse(
            key=key,
            value=setting_data["value"],
            description=setting_data["description"],
            updated_at=setting_data["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get setting '{key}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/bulk", response_model=BulkUpdateResponse)
async def update_multiple_settings(
    bulk_update: BulkSettingsUpdateRequest, admin_user=Depends(get_current_admin)
):
    """Update multiple settings at once"""
    try:
        # Convert values to strings for the settings service
        settings_data = {key: str(value) for key, value in bulk_update.settings.items()}

        success = settings.set_multiple(settings_data)

        if success:
            updated_settings = []
            for key, value in settings_data.items():
                updated_settings.append({"key": key, "value": value})

            # Handle special setting updates for bulk changes
            await _handle_bulk_special_updates(bulk_update.settings)

            return BulkUpdateResponse(
                updated_settings=updated_settings, count=len(updated_settings)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update settings",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update multiple settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_update: SettingUpdateRequest,
    admin_user=Depends(get_current_admin),
):
    """Update a specific setting"""
    try:
        success = settings.set(key, setting_update.value, setting_update.description)

        if success:
            # Handle special setting updates
            await _handle_special_setting_update(key, setting_update.value)

            return SettingResponse(
                key=key,
                value=setting_update.value,
                description=setting_update.description,
                updated_at="now",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update setting",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update setting '{key}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{key}")
async def delete_setting(key: str, admin_user=Depends(get_current_admin)):
    """Delete a specific setting"""
    try:
        success = settings.delete(key)

        if success:
            return {"message": f"Setting '{key}' deleted"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete setting '{key}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ====================================
# Application Control
# ====================================


@router.post("/restart")
async def restart_application(admin_user=Depends(get_current_admin)):
    """Restart the application"""
    try:
        logger.info("Application restart requested via FastAPI interface")

        # Schedule restart in background to allow response to be sent
        async def restart_worker():
            try:
                # Give time for the response to be sent
                await asyncio.sleep(1)

                # Check if systemd service is available and prefer it
                try:
                    process = await asyncio.create_subprocess_exec(
                        "systemctl",
                        "is-active",
                        "mvidarr.service",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=5
                    )
                    result_returncode = process.returncode
                    result_stdout = stdout.decode().strip()

                    if result_returncode == 0 and result_stdout == "active":
                        logger.info("Using systemd service restart")

                        # Use management script which has sudo configured properly
                        script_path = os.path.join(
                            os.getcwd(), "scripts", "manage_service.sh"
                        )
                        if os.path.exists(script_path):
                            logger.info("Using management script for systemd restart")
                            process = await asyncio.create_subprocess_exec(
                                script_path,
                                "restart",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            await process.wait()
                            logger.info(
                                "Systemd service restart initiated successfully via management script"
                            )
                            return
                        else:
                            # Direct systemd call (may require sudo configuration)
                            process = await asyncio.create_subprocess_exec(
                                "systemctl",
                                "restart",
                                "mvidarr.service",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            await process.wait()
                            logger.info(
                                "Systemd service restart initiated successfully"
                            )
                            return

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Systemd restart failed: {e}")
                except Exception as e:
                    logger.warning(f"Systemd check failed: {e}")

                # Fallback to management script (async)
                script_path = os.path.join(os.getcwd(), "scripts", "manage_service.sh")
                if os.path.exists(script_path):
                    logger.info("Using management script to restart service")
                    process = await asyncio.create_subprocess_exec(
                        script_path,
                        "restart",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await process.wait()
                    return

                # Use the improved restart script (async)
                script_path = os.path.join(
                    os.getcwd(), "scripts", "improved_restart.py"
                )
                if os.path.exists(script_path):
                    logger.info("Using improved Python restart script")
                    # Run the restart script in background with detailed logging (async)
                    process = await asyncio.create_subprocess_exec(
                        "python3",
                        script_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    # Don't wait for completion, let it run in background
                    asyncio.create_task(process.wait())
                    return

                # Fallback to original restart script (async)
                script_path = os.path.join(os.getcwd(), "scripts", "restart_app.py")
                if os.path.exists(script_path):
                    logger.info("Using original Python restart script")
                    process = await asyncio.create_subprocess_exec(
                        "python3",
                        script_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    asyncio.create_task(process.wait())
                    return

                # Last resort: terminate current process
                logger.warning("No restart script found, using direct termination")
                os.kill(os.getpid(), signal.SIGTERM)

            except Exception as e:
                logger.error(f"Restart worker failed: {e}")
                # Last resort: terminate current process
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception as kill_error:
                    logger.error(f"Failed to terminate process: {kill_error}")

        # Start restart as async task
        asyncio.create_task(restart_worker())

        return {
            "message": "Application restart initiated. Please wait 10-15 seconds and refresh the page."
        }

    except Exception as e:
        logger.error(f"Failed to restart application: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/restart-systemd")
async def restart_systemd_service(admin_user=Depends(get_current_admin)):
    """Emergency systemd restart endpoint"""
    try:
        logger.info("Emergency systemd restart requested via FastAPI")

        async def systemd_restart_worker():
            try:
                await asyncio.sleep(1)

                # Use management script for systemd restart
                script_path = os.path.join(os.getcwd(), "scripts", "manage_service.sh")
                if os.path.exists(script_path):
                    logger.info("Using management script for emergency systemd restart")
                    process = await asyncio.create_subprocess_exec(
                        script_path,
                        "restart",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await process.wait()
                    logger.info("Emergency systemd restart completed successfully")
                else:
                    logger.error("Management script not found for emergency restart")

            except Exception as e:
                logger.error(f"Emergency restart failed: {e}")

        # Start restart as async task
        asyncio.create_task(systemd_restart_worker())

        return {
            "message": "Emergency systemd restart initiated. Service will restart shortly."
        }

    except Exception as e:
        logger.error(f"Emergency restart failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ====================================
# Scheduler Management
# ====================================


@router.get("/scheduler/status", response_model=Dict)
async def get_scheduler_status():
    """Get current scheduler status and configuration"""
    try:
        from src.services.scheduler_service import scheduler_service

        schedule_info = scheduler_service.get_schedule_info()

        # Add diagnostic information to help troubleshoot issues
        diagnostic_info = {
            "wanted_videos_count": 0,
            "settings_accessible": True,
            "issues_detected": [],
        }

        try:
            # Check if we can count wanted videos
            wanted_count = scheduler_service._get_wanted_video_count()
            diagnostic_info["wanted_videos_count"] = wanted_count

            if wanted_count == 0:
                diagnostic_info["issues_detected"].append("No videos marked as WANTED")
        except Exception as e:
            diagnostic_info["issues_detected"].append(
                f"Cannot access wanted videos: {str(e)}"
            )

        try:
            # Check if settings are accessible
            test_setting = SettingsService.get_bool(
                "auto_download_schedule_enabled", True
            )
        except Exception as e:
            diagnostic_info["settings_accessible"] = False
            diagnostic_info["issues_detected"].append(
                f"Cannot access settings: {str(e)}"
            )

        return {
            "scheduler": {
                "running": scheduler_service.running,
                "schedule_info": schedule_info,
                "diagnostics": diagnostic_info,
            }
        }

    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/scheduler/start")
async def start_scheduler():
    """Start the scheduler service"""
    try:
        from src.services.scheduler_service import scheduler_service

        if scheduler_service.running:
            return {"message": "Scheduler is already running"}

        scheduler_service.start()
        return {"message": "Scheduler started successfully"}

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the scheduler service"""
    try:
        from src.services.scheduler_service import scheduler_service

        if not scheduler_service.running:
            return {"message": "Scheduler is not running"}

        scheduler_service.stop()
        return {"message": "Scheduler stopped successfully"}

    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/scheduler/reload")
async def reload_scheduler():
    """Reload scheduler configuration from settings"""
    try:
        from src.services.scheduler_service import scheduler_service

        scheduler_service.reload_schedule()
        return {"message": "Scheduler configuration reloaded successfully"}

    except Exception as e:
        logger.error(f"Failed to reload scheduler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/scheduler/trigger")
async def trigger_scheduled_download():
    """Manually trigger a scheduled download"""
    try:
        from src.services.scheduler_service import scheduler_service

        # Get max videos setting
        max_videos = SettingsService.get_int("auto_download_max_videos", 50)

        # Import and run the download function
        from src.services.video_batch_service import download_all_wanted_videos_internal

        result = download_all_wanted_videos_internal(limit=max_videos)

        if result.get("success"):
            return {
                "message": "Manual download triggered successfully",
                "result": result,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Manual download failed",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger scheduled download: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ====================================
# Database Configuration
# ====================================


# ====================================
# Helper Functions
# ====================================


async def _handle_special_setting_update(key: str, value: Any):
    """Handle special logic for certain setting updates"""
    try:
        # Auto-reload Spotify service if Spotify settings are updated
        if key.startswith("spotify_"):
            try:
                from src.services.spotify_service import spotify_service

                logger.info(f"Reloading Spotify service after updating {key}")
                spotify_service.reload_settings()
                logger.info(
                    f"Spotify service successfully reloaded after updating {key}. New redirect URI: {spotify_service.redirect_uri}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to reload Spotify service after updating {key}: {e}"
                )
                # Continue with the response even if reload fails

        # Handle authentication setting change
        elif key == "require_authentication":
            logger.info(f"Authentication requirement changed to: {value}")
            logger.info(
                "Application restart required for authentication changes to take effect"
            )

    except Exception as e:
        logger.error(f"Error handling special setting update for {key}: {e}")


async def _handle_bulk_special_updates(settings_data: Dict[str, Any]):
    """Handle special logic for bulk setting updates"""
    try:
        # Auto-reload Spotify service if any Spotify settings were updated
        spotify_settings_updated = any(
            key.startswith("spotify_") for key in settings_data.keys()
        )
        if spotify_settings_updated:
            try:
                from src.services.spotify_service import spotify_service

                updated_spotify_keys = [
                    key for key in settings_data.keys() if key.startswith("spotify_")
                ]
                logger.info(
                    f"Reloading Spotify service after bulk update of: {updated_spotify_keys}"
                )
                spotify_service.reload_settings()
                logger.info(
                    f"Spotify service successfully reloaded after bulk update. New redirect URI: {spotify_service.redirect_uri}"
                )
            except Exception as e:
                logger.error(f"Failed to reload Spotify service after bulk update: {e}")
                # Continue with the response even if reload fails

    except Exception as e:
        logger.error(f"Error handling bulk special updates: {e}")
