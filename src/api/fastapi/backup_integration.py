"""
Backup & Integration API Endpoints - Phase 3 Week 29
Consumer-focused API for cloud backup and YouTube integration
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.integrations.youtube_importer import ImportType, get_youtube_importer
from src.services.local_network_share import get_local_network_share
from src.services.personal_backup import (
    BackupType,
    CloudProvider,
    VideoQuality,
    get_personal_backup_service,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.backup_integration")

# Create router
backup_router = APIRouter(prefix="/backup", tags=["backup", "integration"])


# Pydantic models for request/response
class CloudProviderConfigRequest(BaseModel):
    provider: str = Field(
        ..., description="Cloud provider (google_drive, dropbox, onedrive)"
    )
    credentials: Dict[str, str] = Field(..., description="Provider credentials")


class BackupJobRequest(BaseModel):
    provider: str = Field(..., description="Cloud provider")
    backup_type: str = Field(..., description="Type of backup")
    source_paths: List[str] = Field(..., description="Source file/folder paths")
    destination_path: str = Field("", description="Destination path in cloud")


class YouTubeImportRequest(BaseModel):
    source_url: str = Field(..., description="YouTube URL (video, playlist, channel)")
    destination_directory: str = Field("", description="Local destination directory")
    quality: str = Field("high", description="Video quality preference")
    filter_music_only: bool = Field(True, description="Only import music videos")


class NetworkShareRequest(BaseModel):
    name: str = Field(..., description="Share name")
    share_type: str = Field(..., description="Type of share")
    local_path: str = Field(..., description="Local path to share")
    access_level: str = Field("streaming_only", description="Access level")
    password_protected: bool = Field(False, description="Require password")
    password: Optional[str] = Field(None, description="Share password")


class IntegrationResponse(BaseModel):
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    processing_time_ms: Optional[float] = Field(None, description="Processing time")


# Cloud Backup Endpoints


@backup_router.post("/cloud/configure", response_model=IntegrationResponse)
async def configure_cloud_provider(request: CloudProviderConfigRequest):
    """Configure cloud provider credentials"""
    try:
        start_time = time.time()

        # Validate provider
        try:
            provider = CloudProvider(request.provider)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {request.provider}"
            )

        backup_service = await get_personal_backup_service()

        result = await backup_service.configure_cloud_provider(
            provider, request.credentials
        )

        processing_time = (time.time() - start_time) * 1000

        return IntegrationResponse(
            success=result["success"],
            message=f"{'Successfully configured' if result['success'] else 'Failed to configure'} {provider.value}",
            data=result,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure cloud provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.post("/cloud/backup", response_model=IntegrationResponse)
async def create_backup_job(
    request: BackupJobRequest, background_tasks: BackgroundTasks
):
    """Create and start a cloud backup job"""
    try:
        start_time = time.time()

        # Validate enums
        try:
            provider = CloudProvider(request.provider)
            backup_type = BackupType(request.backup_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")

        backup_service = await get_personal_backup_service()

        # Create backup job
        job = await backup_service.create_backup_job(
            provider=provider,
            backup_type=backup_type,
            source_paths=request.source_paths,
            destination_path=request.destination_path,
        )

        # Start backup in background
        background_tasks.add_task(backup_service.start_backup_job, job.job_id)

        processing_time = (time.time() - start_time) * 1000

        return IntegrationResponse(
            success=True,
            message=f"Backup job created: {job.job_id}",
            data={
                "job_id": job.job_id,
                "provider": provider.value,
                "backup_type": backup_type.value,
                "total_files": job.total_files,
                "total_size_mb": job.total_bytes / (1024 * 1024),
                "status": "started",
            },
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create backup job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/cloud/status/{job_id}", response_model=IntegrationResponse)
async def get_backup_job_status(job_id: str):
    """Get status of a backup job"""
    try:
        backup_service = await get_personal_backup_service()

        status = await backup_service.get_backup_status(job_id)

        if not status:
            raise HTTPException(
                status_code=404, detail=f"Backup job {job_id} not found"
            )

        return IntegrationResponse(
            success=True, message="Backup job status retrieved", data=status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/cloud/jobs", response_model=IntegrationResponse)
async def list_backup_jobs(limit: int = Query(20, ge=1, le=100)):
    """List recent backup jobs"""
    try:
        backup_service = await get_personal_backup_service()

        jobs = await backup_service.list_backup_jobs(limit=limit)

        return IntegrationResponse(
            success=True,
            message=f"Retrieved {len(jobs)} backup jobs",
            data={"jobs": jobs, "total_count": len(jobs)},
        )

    except Exception as e:
        logger.error(f"Failed to list backup jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.delete("/cloud/jobs/{job_id}", response_model=IntegrationResponse)
async def cancel_backup_job(job_id: str):
    """Cancel a running backup job"""
    try:
        backup_service = await get_personal_backup_service()

        result = await backup_service.cancel_backup_job(job_id)

        return IntegrationResponse(
            success=result["success"],
            message=f"Backup job {job_id} {'cancelled' if result['success'] else 'could not be cancelled'}",
            data=result,
        )

    except Exception as e:
        logger.error(f"Failed to cancel backup job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# YouTube Import Endpoints


@backup_router.post("/youtube/import", response_model=IntegrationResponse)
async def create_youtube_import_job(
    request: YouTubeImportRequest, background_tasks: BackgroundTasks
):
    """Create and start a YouTube import job"""
    try:
        start_time = time.time()

        # Validate quality
        try:
            quality = VideoQuality(request.quality)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid quality: {request.quality}"
            )

        youtube_importer = await get_youtube_importer()

        # Create import job
        job = await youtube_importer.create_import_job(
            source_url=request.source_url,
            destination_directory=request.destination_directory,
            quality=quality,
            filter_music_only=request.filter_music_only,
        )

        # Start import in background
        background_tasks.add_task(youtube_importer.start_import_job, job.job_id)

        processing_time = (time.time() - start_time) * 1000

        return IntegrationResponse(
            success=True,
            message=f"YouTube import job created: {job.job_id}",
            data={
                "job_id": job.job_id,
                "import_type": job.import_type.value,
                "source_url": job.source_url,
                "quality": quality.value,
                "filter_music_only": job.filter_music_only,
                "status": "started",
            },
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create YouTube import job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/youtube/status/{job_id}", response_model=IntegrationResponse)
async def get_youtube_import_status(job_id: str):
    """Get status of a YouTube import job"""
    try:
        youtube_importer = await get_youtube_importer()

        status = await youtube_importer.get_import_status(job_id)

        if not status:
            raise HTTPException(
                status_code=404, detail=f"YouTube import job {job_id} not found"
            )

        return IntegrationResponse(
            success=True, message="YouTube import job status retrieved", data=status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get YouTube import status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/youtube/jobs", response_model=IntegrationResponse)
async def list_youtube_import_jobs(limit: int = Query(20, ge=1, le=100)):
    """List recent YouTube import jobs"""
    try:
        youtube_importer = await get_youtube_importer()

        jobs = await youtube_importer.list_import_jobs(limit=limit)

        return IntegrationResponse(
            success=True,
            message=f"Retrieved {len(jobs)} YouTube import jobs",
            data={"jobs": jobs, "total_count": len(jobs)},
        )

    except Exception as e:
        logger.error(f"Failed to list YouTube import jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.delete("/youtube/jobs/{job_id}", response_model=IntegrationResponse)
async def cancel_youtube_import_job(job_id: str):
    """Cancel a running YouTube import job"""
    try:
        youtube_importer = await get_youtube_importer()

        result = await youtube_importer.cancel_import_job(job_id)

        return IntegrationResponse(
            success=result["success"],
            message=f"YouTube import job {job_id} {'cancelled' if result['success'] else 'could not be cancelled'}",
            data=result,
        )

    except Exception as e:
        logger.error(f"Failed to cancel YouTube import job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Network Sharing Endpoints


@backup_router.post("/network/shares", response_model=IntegrationResponse)
async def create_network_share(request: NetworkShareRequest):
    """Create a new network share"""
    try:
        start_time = time.time()

        # Validate enums
        from src.services.local_network_share import AccessLevel, ShareType

        try:
            share_type = ShareType(request.share_type)
            access_level = AccessLevel(request.access_level)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")

        network_share = await get_local_network_share()

        # Prepare options
        options = {
            "password_protected": request.password_protected,
            "password": request.password,
        }

        # Create share
        share = await network_share.create_share(
            name=request.name,
            share_type=share_type,
            local_path=request.local_path,
            access_level=access_level,
            options=options,
        )

        processing_time = (time.time() - start_time) * 1000

        return IntegrationResponse(
            success=True,
            message=f"Network share '{request.name}' created successfully",
            data=share.to_dict(),
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create network share: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/network/shares", response_model=IntegrationResponse)
async def list_network_shares():
    """List all network shares"""
    try:
        network_share = await get_local_network_share()

        shares = await network_share.list_shares()

        return IntegrationResponse(
            success=True,
            message=f"Retrieved {len(shares)} network shares",
            data={"shares": shares, "total_count": len(shares)},
        )

    except Exception as e:
        logger.error(f"Failed to list network shares: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.put("/network/shares/{share_id}", response_model=IntegrationResponse)
async def update_network_share(share_id: str, updates: Dict[str, Any]):
    """Update an existing network share"""
    try:
        network_share = await get_local_network_share()

        success = await network_share.update_share(share_id, updates)

        if success:
            return IntegrationResponse(
                success=True,
                message=f"Network share {share_id} updated successfully",
                data={"share_id": share_id, "updates": updates},
            )
        else:
            return IntegrationResponse(
                success=False,
                message=f"Failed to update network share {share_id}",
                data={"share_id": share_id},
            )

    except Exception as e:
        logger.error(f"Failed to update network share: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.delete("/network/shares/{share_id}", response_model=IntegrationResponse)
async def delete_network_share(share_id: str):
    """Delete a network share"""
    try:
        network_share = await get_local_network_share()

        success = await network_share.delete_share(share_id)

        if success:
            return IntegrationResponse(
                success=True,
                message=f"Network share {share_id} deleted successfully",
                data={"share_id": share_id},
            )
        else:
            return IntegrationResponse(
                success=False,
                message=f"Failed to delete network share {share_id}",
                data={"share_id": share_id},
            )

    except Exception as e:
        logger.error(f"Failed to delete network share: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/network/devices", response_model=IntegrationResponse)
async def get_network_devices():
    """Get connected network devices"""
    try:
        network_share = await get_local_network_share()

        devices = await network_share.get_connected_devices()

        return IntegrationResponse(
            success=True,
            message=f"Retrieved {len(devices)} network devices",
            data={"devices": devices, "total_count": len(devices)},
        )

    except Exception as e:
        logger.error(f"Failed to get network devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/network/status", response_model=IntegrationResponse)
async def get_network_sharing_status():
    """Get network sharing service status"""
    try:
        network_share = await get_local_network_share()

        status = await network_share.get_network_status()

        return IntegrationResponse(
            success=True, message="Network sharing status retrieved", data=status
        )

    except Exception as e:
        logger.error(f"Failed to get network sharing status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/network/qr/{share_id}")
async def get_share_qr_code(share_id: str):
    """Get QR code for easy mobile access to network share"""
    try:
        network_share = await get_local_network_share()

        qr_code_data = await network_share.generate_access_qr_code(share_id)

        if qr_code_data:
            return JSONResponse(
                {
                    "success": True,
                    "share_id": share_id,
                    "qr_code": qr_code_data,
                    "format": "base64_png",
                }
            )
        else:
            raise HTTPException(status_code=404, detail=f"Share {share_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Integration Status and Health


@backup_router.get("/health", response_model=IntegrationResponse)
async def get_backup_integration_health():
    """Get health status of backup and integration services"""
    try:
        health_status = {
            "services": {},
            "overall_status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }

        # Check backup service
        try:
            backup_service = await get_personal_backup_service()
            health_status["services"]["personal_backup"] = "healthy"
        except Exception as e:
            health_status["services"]["personal_backup"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        # Check YouTube importer
        try:
            youtube_importer = await get_youtube_importer()
            health_status["services"]["youtube_importer"] = "healthy"
        except Exception as e:
            health_status["services"]["youtube_importer"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        # Check network sharing
        try:
            network_share = await get_local_network_share()
            health_status["services"]["network_sharing"] = "healthy"
        except Exception as e:
            health_status["services"]["network_sharing"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        return IntegrationResponse(
            success=True,
            message=f"Backup and integration services status: {health_status['overall_status']}",
            data=health_status,
        )

    except Exception as e:
        logger.error(f"Failed to get service health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backup_router.get("/capabilities")
async def get_integration_capabilities():
    """Get supported integration capabilities"""
    return JSONResponse(
        {
            "cloud_providers": [
                {
                    "name": "Google Drive",
                    "id": "google_drive",
                    "oauth_required": True,
                    "max_file_size_gb": 5,
                    "supported": True,
                },
                {
                    "name": "Dropbox",
                    "id": "dropbox",
                    "oauth_required": True,
                    "max_file_size_gb": 2,
                    "supported": True,
                },
                {
                    "name": "OneDrive",
                    "id": "onedrive",
                    "oauth_required": True,
                    "max_file_size_gb": 15,
                    "supported": True,
                },
            ],
            "backup_types": [
                {"name": "Music Videos", "id": "music_videos"},
                {"name": "Thumbnails", "id": "thumbnails"},
                {"name": "Database", "id": "database"},
                {"name": "Configuration", "id": "configuration"},
                {"name": "Full Backup", "id": "full_backup"},
            ],
            "youtube_import": {
                "supported_urls": [
                    "Single videos (youtube.com/watch?v=...)",
                    "Playlists (youtube.com/playlist?list=...)",
                    "Channels (youtube.com/channel/... or youtube.com/c/...)",
                    "Search queries",
                ],
                "quality_options": ["low", "medium", "high", "best", "audio_only"],
                "max_playlist_size": 500,
                "music_filtering": True,
            },
            "network_sharing": {
                "mdns_discovery": True,
                "qr_code_access": True,
                "mobile_optimized": True,
                "access_levels": ["read_only", "streaming_only", "download_allowed"],
                "share_types": [
                    "music_videos",
                    "collections",
                    "playlists",
                    "recent_imports",
                    "custom_folder",
                ],
            },
        }
    )


# Utility Endpoints


@backup_router.post("/quick-backup")
async def create_quick_backup(
    provider: str = Query(..., description="Cloud provider"),
    backup_type: str = Query("music_videos", description="What to backup"),
    background_tasks: BackgroundTasks = None,
):
    """Quick backup with default settings for consumer convenience"""
    try:
        # Validate inputs
        try:
            cloud_provider = CloudProvider(provider)
            backup_type_enum = BackupType(backup_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")

        backup_service = await get_personal_backup_service()

        # Default source paths based on backup type
        default_paths = {
            BackupType.MUSIC_VIDEOS: ["/data/musicvideos"],
            BackupType.THUMBNAILS: ["/data/thumbnails"],
            BackupType.DATABASE: ["/data/database"],
            BackupType.CONFIGURATION: ["/app/config"],
            BackupType.FULL_BACKUP: ["/data"],
        }

        source_paths = default_paths.get(backup_type_enum, ["/data/musicvideos"])

        # Create and start backup job
        job = await backup_service.create_backup_job(
            provider=cloud_provider,
            backup_type=backup_type_enum,
            source_paths=source_paths,
            destination_path=f"MVidarr Quick Backup/{backup_type}",
        )

        # Start backup in background
        background_tasks.add_task(backup_service.start_backup_job, job.job_id)

        return JSONResponse(
            {
                "success": True,
                "message": f"Quick backup started to {provider}",
                "job_id": job.job_id,
                "backup_type": backup_type,
                "estimated_files": job.total_files,
                "estimated_size_mb": job.total_bytes / (1024 * 1024),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create quick backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
