"""
MVidarr Bulk Operations API - Phase 2 Week 22
FastAPI endpoints for bulk media operations with progress tracking and error recovery
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, validator

from src.jobs.bulk_media_tasks import (
    BulkMediaProcessor,
    BulkOperationStatus,
    bulk_cleanup_media,
    bulk_enrich_metadata,
)
from src.services.media_collection_manager import (
    CollectionProcessingConfig,
    CollectionType,
    MediaCollectionManager,
    ProcessingPriority,
    process_directory_as_collection,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.bulk_operations")

router = APIRouter(
    prefix="/api/bulk-operations",
    tags=["bulk-operations"],
    responses={404: {"description": "Not found"}},
)

# Global instances for operation tracking
active_processors: Dict[str, BulkMediaProcessor] = {}
active_managers: Dict[str, MediaCollectionManager] = {}
websocket_connections: Dict[str, WebSocket] = {}


# Request/Response Models
class BulkMetadataEnrichmentRequest(BaseModel):
    """Request model for bulk metadata enrichment"""

    media_paths: List[str] = Field(
        ..., min_items=1, max_items=10000, description="List of media paths to process"
    )
    operation_name: Optional[str] = Field(
        None, description="Optional name for the operation"
    )
    priority: str = Field(
        "normal", description="Processing priority: low, normal, high, urgent"
    )
    enable_progress_updates: bool = Field(
        True, description="Enable real-time progress updates"
    )

    @validator("priority")
    def validate_priority(cls, v):
        valid_priorities = ["low", "normal", "high", "urgent"]
        if v.lower() not in valid_priorities:
            raise ValueError(f"Priority must be one of: {valid_priorities}")
        return v.lower()


class CollectionImportRequest(BaseModel):
    """Request model for collection import"""

    source_directory: str = Field(..., description="Source directory path")
    collection_name: str = Field(
        ..., min_length=1, max_length=255, description="Name for the collection"
    )
    collection_type: str = Field("mixed_collection", description="Type of collection")
    file_patterns: Optional[List[str]] = Field(
        None, description="File patterns to match (e.g., ['*.jpg', '*.mp4'])"
    )
    recursive: bool = Field(True, description="Include subdirectories")
    validate_files: bool = Field(True, description="Validate files during import")

    @validator("collection_type")
    def validate_collection_type(cls, v):
        valid_types = [
            "image_collection",
            "video_collection",
            "mixed_collection",
            "artist_collection",
            "playlist_collection",
        ]
        if v.lower() not in valid_types:
            raise ValueError(f"Collection type must be one of: {valid_types}")
        return v.lower()


class CollectionCleanupRequest(BaseModel):
    """Request model for collection cleanup"""

    collection_id: str = Field(..., description="Collection ID to clean up")
    target_directory: str = Field(..., description="Target directory for cleanup")
    cleanup_rules: Dict[str, Any] = Field(
        ..., description="Cleanup rules configuration"
    )
    dry_run: bool = Field(False, description="Perform dry run without actual cleanup")


class CollectionProcessingConfigRequest(BaseModel):
    """Request model for collection processing configuration"""

    max_concurrent_operations: int = Field(
        10, ge=1, le=100, description="Maximum concurrent operations"
    )
    batch_size: int = Field(
        100, ge=10, le=1000, description="Batch size for processing"
    )
    memory_limit_mb: int = Field(
        2048, ge=512, le=8192, description="Memory limit in MB"
    )
    processing_priority: str = Field("normal", description="Processing priority")
    enable_caching: bool = Field(True, description="Enable result caching")
    cache_ttl_seconds: int = Field(
        3600, ge=60, le=86400, description="Cache TTL in seconds"
    )


class OperationResponse(BaseModel):
    """Response model for operation status"""

    operation_id: str
    status: str
    message: str
    details: Dict[str, Any]


class ProgressResponse(BaseModel):
    """Response model for operation progress"""

    operation_id: str
    operation_type: str
    status: str
    progress_percentage: float
    processed_items: int
    successful_items: int
    failed_items: int
    total_items: int
    current_item: Optional[str]
    processing_time: float
    items_per_second: float
    error_count: int


# WebSocket endpoint for real-time progress updates
@router.websocket("/progress/{operation_id}")
async def websocket_progress_updates(websocket: WebSocket, operation_id: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()
    websocket_connections[operation_id] = websocket

    try:
        logger.info(f"📡 WebSocket connected for operation {operation_id}")

        # Keep connection alive and send updates
        while True:
            # Check if operation exists and send progress
            processor = active_processors.get(operation_id)
            if processor:
                progress = processor.get_operation_status(operation_id)
                if progress:
                    await websocket.send_json(progress.to_dict())

                    # Close connection if operation is complete
                    if progress.status in [
                        BulkOperationStatus.COMPLETED,
                        BulkOperationStatus.FAILED,
                        BulkOperationStatus.CANCELLED,
                    ]:
                        break

            await asyncio.sleep(1)  # Update interval

    except WebSocketDisconnect:
        logger.info(f"📡 WebSocket disconnected for operation {operation_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for operation {operation_id}: {e}")
    finally:
        websocket_connections.pop(operation_id, None)


# Bulk Operations Endpoints
@router.post("/metadata/enrich", response_model=OperationResponse)
async def enrich_metadata_bulk(
    request: BulkMetadataEnrichmentRequest, background_tasks: BackgroundTasks
):
    """
    Enrich metadata for large collections of media files

    This endpoint processes thousands of media files concurrently, extracting comprehensive
    metadata including EXIF data, quality metrics, and content analysis.
    """
    try:
        operation_id = str(uuid.uuid4())

        # Validate paths
        valid_paths = []
        for path_str in request.media_paths:
            path = Path(path_str)
            if path.exists():
                valid_paths.append(path_str)
            else:
                logger.warning(f"⚠️ Path not found: {path_str}")

        if not valid_paths:
            raise HTTPException(status_code=400, detail="No valid media paths provided")

        logger.info(f"🔍 Starting bulk metadata enrichment: {len(valid_paths)} files")

        # Create processor and start operation
        processor = BulkMediaProcessor()
        active_processors[operation_id] = processor

        # Progress callback for WebSocket updates
        async def progress_callback(progress_data):
            websocket = websocket_connections.get(operation_id)
            if websocket:
                try:
                    await websocket.send_json(progress_data)
                except Exception as e:
                    logger.error(f"❌ Failed to send WebSocket update: {e}")

        # Start background task
        background_tasks.add_task(
            bulk_enrich_metadata,
            media_paths=valid_paths,
            operation_id=operation_id,
            progress_callback=(
                progress_callback if request.enable_progress_updates else None
            ),
        )

        return OperationResponse(
            operation_id=operation_id,
            status="started",
            message=f"Bulk metadata enrichment started for {len(valid_paths)} files",
            details={
                "total_files": len(valid_paths),
                "operation_name": request.operation_name,
                "priority": request.priority,
                "progress_updates_enabled": request.enable_progress_updates,
                "websocket_url": f"/api/bulk-operations/progress/{operation_id}",
            },
        )

    except Exception as e:
        logger.error(f"❌ Bulk metadata enrichment failed to start: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/collections/import", response_model=OperationResponse)
async def import_collection(
    request: CollectionImportRequest, background_tasks: BackgroundTasks
):
    """
    Import large media collections from directories

    This endpoint scans directories for media files and creates organized collections
    with comprehensive metadata and validation.
    """
    try:
        # Validate source directory
        source_path = Path(request.source_directory)
        if not source_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Source directory not found: {request.source_directory}",
            )

        if not source_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a directory: {request.source_directory}",
            )

        operation_id = str(uuid.uuid4())

        logger.info(f"📥 Starting collection import from {request.source_directory}")

        # Progress callback for WebSocket updates
        async def progress_callback(progress_data):
            websocket = websocket_connections.get(operation_id)
            if websocket:
                try:
                    await websocket.send_json(progress_data)
                except Exception as e:
                    logger.error(f"❌ Failed to send WebSocket update: {e}")

        # Start background import task
        background_tasks.add_task(
            process_directory_as_collection,
            source_directory=request.source_directory,
            collection_name=request.collection_name,
            collection_type=CollectionType(request.collection_type.upper()),
            file_patterns=request.file_patterns,
            config=None,  # Use default config
            progress_callback=progress_callback,
        )

        return OperationResponse(
            operation_id=operation_id,
            status="started",
            message=f"Collection import started from {request.source_directory}",
            details={
                "source_directory": request.source_directory,
                "collection_name": request.collection_name,
                "collection_type": request.collection_type,
                "file_patterns": request.file_patterns,
                "recursive": request.recursive,
                "validate_files": request.validate_files,
                "websocket_url": f"/api/bulk-operations/progress/{operation_id}",
            },
        )

    except Exception as e:
        logger.error(f"❌ Collection import failed to start: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/collections/cleanup", response_model=OperationResponse)
async def cleanup_collection(
    request: CollectionCleanupRequest, background_tasks: BackgroundTasks
):
    """
    Perform cleanup operations on media collections

    This endpoint handles bulk cleanup operations including duplicate removal,
    empty file cleanup, and storage optimization.
    """
    try:
        # Validate target directory
        target_path = Path(request.target_directory)
        if not target_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Target directory not found: {request.target_directory}",
            )

        operation_id = str(uuid.uuid4())

        logger.info(f"🧹 Starting collection cleanup: {request.collection_id}")

        # Progress callback for WebSocket updates
        async def progress_callback(progress_data):
            websocket = websocket_connections.get(operation_id)
            if websocket:
                try:
                    await websocket.send_json(progress_data)
                except Exception as e:
                    logger.error(f"❌ Failed to send WebSocket update: {e}")

        # Start background cleanup task
        background_tasks.add_task(
            bulk_cleanup_media,
            target_directory=request.target_directory,
            operation_id=operation_id,
            cleanup_rules=request.cleanup_rules,
            progress_callback=progress_callback,
        )

        return OperationResponse(
            operation_id=operation_id,
            status="started",
            message=f"Collection cleanup started for {request.collection_id}",
            details={
                "collection_id": request.collection_id,
                "target_directory": request.target_directory,
                "cleanup_rules": request.cleanup_rules,
                "dry_run": request.dry_run,
                "websocket_url": f"/api/bulk-operations/progress/{operation_id}",
            },
        )

    except Exception as e:
        logger.error(f"❌ Collection cleanup failed to start: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Status and Management Endpoints
@router.get("/operations/{operation_id}/status", response_model=ProgressResponse)
async def get_operation_status(operation_id: str):
    """Get current status of a bulk operation"""
    try:
        processor = active_processors.get(operation_id)
        if not processor:
            raise HTTPException(
                status_code=404, detail=f"Operation {operation_id} not found"
            )

        progress = processor.get_operation_status(operation_id)
        if not progress:
            raise HTTPException(
                status_code=404,
                detail=f"No progress data found for operation {operation_id}",
            )

        return ProgressResponse(
            operation_id=progress.operation_id,
            operation_type=progress.operation_type.value,
            status=progress.status.value,
            progress_percentage=progress.progress_percentage,
            processed_items=progress.processed_items,
            successful_items=progress.successful_items,
            failed_items=progress.failed_items,
            total_items=progress.total_items,
            current_item=progress.current_item,
            processing_time=progress.processing_time,
            items_per_second=progress.items_per_second,
            error_count=len(progress.error_details),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get operation status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/operations/{operation_id}/cancel", response_model=OperationResponse)
async def cancel_operation(operation_id: str):
    """Cancel a running bulk operation"""
    try:
        processor = active_processors.get(operation_id)
        if not processor:
            raise HTTPException(
                status_code=404, detail=f"Operation {operation_id} not found"
            )

        success = processor.cancel_operation(operation_id)

        if success:
            return OperationResponse(
                operation_id=operation_id,
                status="cancelled",
                message="Operation cancelled successfully",
                details={"cancelled_at": time.time()},
            )
        else:
            raise HTTPException(
                status_code=400, detail="Operation could not be cancelled"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to cancel operation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/operations/active", response_model=List[Dict[str, Any]])
async def get_active_operations():
    """Get list of all active bulk operations"""
    try:
        active_ops = []

        for operation_id, processor in active_processors.items():
            ops = processor.get_active_operations()
            active_ops.extend(ops)

        return active_ops

    except Exception as e:
        logger.error(f"❌ Failed to get active operations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Collection Management Endpoints
@router.post("/collections/create", response_model=Dict[str, Any])
async def create_collection(
    collection_name: str = Body(..., description="Collection name"),
    collection_type: str = Body("mixed_collection", description="Collection type"),
    description: str = Body("", description="Collection description"),
    tags: List[str] = Body([], description="Collection tags"),
    config: Optional[CollectionProcessingConfigRequest] = Body(
        None, description="Processing configuration"
    ),
):
    """Create a new media collection"""
    try:
        collection_id = str(uuid.uuid4())

        # Create processing config
        processing_config = None
        if config:
            processing_config = CollectionProcessingConfig(
                max_concurrent_operations=config.max_concurrent_operations,
                batch_size=config.batch_size,
                memory_limit_mb=config.memory_limit_mb,
                processing_priority=ProcessingPriority(
                    config.processing_priority.upper()
                ),
                enable_caching=config.enable_caching,
                cache_ttl_seconds=config.cache_ttl_seconds,
            )

        # Create collection manager
        manager = MediaCollectionManager(processing_config)
        active_managers[collection_id] = manager

        # Create collection
        metadata = await manager.create_collection(
            collection_id=collection_id,
            name=collection_name,
            collection_type=CollectionType(collection_type.upper()),
            description=description,
            tags=tags,
        )

        return {
            "collection_id": collection_id,
            "metadata": metadata.to_dict(),
            "status": "created",
            "message": f"Collection '{collection_name}' created successfully",
        }

    except Exception as e:
        logger.error(f"❌ Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/collections/{collection_id}/statistics", response_model=Dict[str, Any])
async def get_collection_statistics(collection_id: str):
    """Get comprehensive statistics for a collection"""
    try:
        manager = active_managers.get(collection_id)
        if not manager:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        stats = await manager.get_collection_statistics(collection_id)
        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get collection statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/system/statistics", response_model=Dict[str, Any])
async def get_system_statistics():
    """Get overall system statistics for bulk operations"""
    try:
        total_active_operations = sum(
            len(processor.get_active_operations())
            for processor in active_processors.values()
        )

        stats = {
            "active_processors": len(active_processors),
            "active_managers": len(active_managers),
            "total_active_operations": total_active_operations,
            "websocket_connections": len(websocket_connections),
            "system_timestamp": time.time(),
        }

        # Add individual processor stats
        if active_processors:
            sample_processor = next(iter(active_processors.values()))
            if hasattr(sample_processor, "processing_stats"):
                stats["processing_stats"] = sample_processor.processing_stats

        return stats

    except Exception as e:
        logger.error(f"❌ Failed to get system statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/operations/{operation_id}/cleanup")
async def cleanup_operation(operation_id: str):
    """Clean up completed operation resources"""
    try:
        # Remove from active processors
        if operation_id in active_processors:
            del active_processors[operation_id]

        # Close WebSocket connections
        if operation_id in websocket_connections:
            websocket = websocket_connections[operation_id]
            try:
                await websocket.close()
            except:
                pass
            del websocket_connections[operation_id]

        return {"status": "cleaned_up", "operation_id": operation_id}

    except Exception as e:
        logger.error(f"❌ Failed to cleanup operation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
