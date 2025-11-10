"""
FastAPI Backup Management Router
v1.0.0 Feature: Backup and restore API endpoints
Issue #93: https://github.com/prefect421/mvidarr/issues/93
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.services.backup_service import BackupService, BackupType

logger = logging.getLogger("mvidarr.fastapi.backups")

router = APIRouter(
    prefix="/api/backups",
    tags=["backups"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================


class CreateBackupRequest(BaseModel):
    """Create backup request"""

    backup_type: str = Field(
        ..., description="Type of backup: database, configuration, thumbnails, full"
    )


class BackupResponse(BaseModel):
    """Backup metadata response"""

    backup_id: str
    backup_type: str
    timestamp: str
    file_path: str
    file_size: int
    file_size_mb: float
    status: str
    error: Optional[str] = None


class BackupListResponse(BaseModel):
    """List of backups response"""

    success: bool
    backups: List[BackupResponse]
    total: int


class RestoreBackupRequest(BaseModel):
    """Restore backup request"""

    backup_id: str = Field(..., description="Backup ID to restore")


class OperationResponse(BaseModel):
    """Generic operation response"""

    success: bool
    message: str


# ========================================================================================
# BACKUP ENDPOINTS
# ========================================================================================


@router.post("/create", response_model=BackupResponse)
async def create_backup(
    request: CreateBackupRequest,
    current_user: dict = Depends(require_authentication_legacy),
):
    """
    Create a new backup.

    Creates a backup of the specified type:
    - database: MariaDB/MySQL database dump
    - configuration: Config files (.env, config.yml)
    - thumbnails: Thumbnail directory
    - full: All of the above

    Requires admin authentication.
    """
    try:
        # Validate backup type
        try:
            backup_type = BackupType[request.backup_type.upper()]
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid backup type: {request.backup_type}. Valid types: database, configuration, thumbnails, full",
            )

        # Create backup
        backup_service = BackupService()
        metadata = backup_service.create_backup(backup_type)

        if not metadata:
            raise HTTPException(status_code=500, detail="Backup creation failed")

        if metadata.status.value != "success":
            raise HTTPException(
                status_code=500, detail=f"Backup failed: {metadata.error}"
            )

        return BackupResponse(**metadata.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=BackupListResponse)
async def list_backups(
    backup_type: Optional[str] = None,
    current_user: dict = Depends(require_authentication_legacy),
):
    """
    List all available backups.

    Optionally filter by backup type.
    Returns list of backups sorted by timestamp (newest first).

    Requires admin authentication.
    """
    try:
        backup_service = BackupService()

        # Filter by type if specified
        type_filter = None
        if backup_type:
            try:
                type_filter = BackupType[backup_type.upper()]
            except KeyError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid backup type: {backup_type}"
                )

        backups = backup_service.list_backups(type_filter)

        # Convert to response models
        backup_responses = [BackupResponse(**b.to_dict()) for b in backups]

        # Sort by timestamp (newest first)
        backup_responses.sort(key=lambda b: b.timestamp, reverse=True)

        return BackupListResponse(
            success=True, backups=backup_responses, total=len(backup_responses)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore", response_model=OperationResponse)
async def restore_backup(
    request: RestoreBackupRequest,
    current_user: dict = Depends(require_authentication_legacy),
):
    """
    Restore from a backup.

    This will overwrite current data with the backup.
    Use with caution!

    Requires admin authentication.
    """
    try:
        backup_service = BackupService()
        success = backup_service.restore_backup(request.backup_id)

        if success:
            return OperationResponse(
                success=True,
                message=f"Successfully restored from backup: {request.backup_id}. You may need to restart MVidarr.",
            )
        else:
            raise HTTPException(status_code=500, detail="Restore operation failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}", response_model=OperationResponse)
async def delete_backup(
    backup_id: str,
    current_user: dict = Depends(require_authentication_legacy),
):
    """
    Delete a backup.

    Permanently deletes the backup file and removes it from the metadata.

    Requires admin authentication.
    """
    try:
        backup_service = BackupService()
        success = backup_service.delete_backup(backup_id)

        if success:
            return OperationResponse(
                success=True, message=f"Successfully deleted backup: {backup_id}"
            )
        else:
            raise HTTPException(
                status_code=404, detail=f"Backup not found: {backup_id}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info", response_model=dict)
async def get_backup_info(
    current_user: dict = Depends(require_authentication_legacy),
):
    """
    Get backup configuration and statistics.

    Returns backup directory, retention settings, and backup counts.

    Requires admin authentication.
    """
    try:
        backup_service = BackupService()

        # Get all backups
        all_backups = backup_service.list_backups()

        # Count by type
        type_counts = {}
        total_size = 0

        for backup in all_backups:
            backup_type = backup.backup_type.value
            type_counts[backup_type] = type_counts.get(backup_type, 0) + 1
            total_size += backup.file_size

        return {
            "success": True,
            "backup_dir": str(backup_service.backup_dir),
            "retention_days": backup_service.retention_days,
            "max_backups": backup_service.max_backups,
            "total_backups": len(all_backups),
            "backups_by_type": type_counts,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    except Exception as e:
        logger.error(f"Error getting backup info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
