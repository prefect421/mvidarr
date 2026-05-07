"""
Collection Management FastAPI Endpoints - Phase 3 Week 28
Consumer-focused music video collection management API
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.services.collection_organizer import (
    OrganizationRule,
    OrganizationStrategy,
    get_collection_organizer,
)
from src.services.duplicate_manager import DuplicateConfidence, get_duplicate_manager
from src.services.music_video_detector import get_music_video_detector
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.collection_management")

# Create router
collection_router = APIRouter(prefix="/collection", tags=["collection", "music-videos"])


# Pydantic models for request/response
class MusicVideoDetectionRequest(BaseModel):
    video_path: str = Field(..., description="Path to video file")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class BatchDetectionRequest(BaseModel):
    video_paths: List[str] = Field(..., description="List of video file paths")
    include_non_music: bool = Field(
        False, description="Include non-music videos in results"
    )


class OrganizationRequest(BaseModel):
    source_directory: str = Field(..., description="Source directory to organize")
    target_directory: str = Field(
        ..., description="Target directory for organized files"
    )
    strategy: str = Field("artist_title", description="Organization strategy")
    clean_filenames: bool = Field(True, description="Clean and sanitize filenames")
    preserve_quality_info: bool = Field(
        True, description="Preserve quality indicators in filenames"
    )
    group_versions: bool = Field(True, description="Group different versions together")
    handle_duplicates: bool = Field(
        True, description="Handle duplicate detection during organization"
    )
    create_artist_folders: bool = Field(
        True, description="Create artist-specific folders"
    )
    dry_run: bool = Field(True, description="Preview changes without executing")


class DuplicateScanRequest(BaseModel):
    directory: str = Field(..., description="Directory to scan for duplicates")
    scan_subdirs: bool = Field(True, description="Scan subdirectories")
    min_confidence: str = Field(
        "medium", description="Minimum confidence level for duplicates"
    )


class DuplicateRemovalRequest(BaseModel):
    group_ids: List[str] = Field(..., description="Duplicate group IDs to process")
    keep_strategy: str = Field(
        "highest_quality", description="Strategy for which files to keep"
    )
    dry_run: bool = Field(True, description="Preview changes without executing")


class CollectionResponse(BaseModel):
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    processing_time_ms: Optional[float] = Field(
        None, description="Processing time in milliseconds"
    )


# Music Video Detection Endpoints


@collection_router.post("/detect/single", response_model=CollectionResponse)
async def detect_single_music_video(request: MusicVideoDetectionRequest):
    """Detect if a single video is a music video"""
    try:
        start_time = time.time()

        if not os.path.exists(request.video_path):
            raise HTTPException(
                status_code=404, detail=f"Video file not found: {request.video_path}"
            )

        detector = await get_music_video_detector()

        result = await detector.detect_music_video(request.video_path, request.metadata)

        processing_time = (time.time() - start_time) * 1000

        return CollectionResponse(
            success=True,
            message="Music video detection completed",
            data=result.to_dict(),
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to detect music video: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@collection_router.post("/detect/batch", response_model=CollectionResponse)
async def detect_batch_music_videos(
    request: BatchDetectionRequest, background_tasks: BackgroundTasks
):
    """Batch detect music videos from list of paths"""
    try:
        start_time = time.time()

        # Validate paths
        valid_paths = []
        invalid_paths = []

        for path in request.video_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                invalid_paths.append(path)

        if not valid_paths:
            raise HTTPException(status_code=400, detail="No valid video paths provided")

        detector = await get_music_video_detector()

        results = await detector.batch_detect_music_videos(valid_paths)

        # Filter results if requested
        if not request.include_non_music:
            results = [r for r in results if r.is_music_video]

        processing_time = (time.time() - start_time) * 1000

        response_data = {
            "total_files": len(request.video_paths),
            "valid_files": len(valid_paths),
            "invalid_files": len(invalid_paths),
            "music_videos_found": len([r for r in results if r.is_music_video]),
            "detection_results": [r.to_dict() for r in results],
            "invalid_paths": invalid_paths,
        }

        return CollectionResponse(
            success=True,
            message=f"Batch detection completed: {len(results)} results",
            data=response_data,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch detect music videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@collection_router.get(
    "/detect/directory/{directory_path:path}", response_model=CollectionResponse
)
async def detect_directory_music_videos(
    directory_path: str,
    scan_subdirs: bool = Query(True, description="Scan subdirectories"),
    min_confidence: str = Query("medium", description="Minimum confidence level"),
):
    """Detect music videos in a directory"""
    try:
        start_time = time.time()

        if not os.path.exists(directory_path):
            raise HTTPException(
                status_code=404, detail=f"Directory not found: {directory_path}"
            )

        if not os.path.isdir(directory_path):
            raise HTTPException(
                status_code=400, detail=f"Path is not a directory: {directory_path}"
            )

        detector = await get_music_video_detector()

        # Find video files
        video_extensions = {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        video_files = []

        from pathlib import Path

        directory = Path(directory_path)
        pattern = "**/*" if scan_subdirs else "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                video_files.append(str(file_path))

        if not video_files:
            return CollectionResponse(
                success=True,
                message="No video files found in directory",
                data={
                    "directory": directory_path,
                    "video_files_found": 0,
                    "music_videos": [],
                },
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Detect music videos
        results = await detector.batch_detect_music_videos(video_files)

        # Filter by confidence level
        confidence_map = {
            "very_low": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "very_high": 4,
        }

        min_level = confidence_map.get(min_confidence, 2)
        confidence_levels = ["very_low", "low", "medium", "high", "very_high"]

        filtered_results = []
        for result in results:
            if result.is_music_video:
                result_level = confidence_map.get(result.confidence.value, 0)
                if result_level >= min_level:
                    filtered_results.append(result)

        processing_time = (time.time() - start_time) * 1000

        response_data = {
            "directory": directory_path,
            "scan_subdirs": scan_subdirs,
            "min_confidence": min_confidence,
            "total_video_files": len(video_files),
            "music_videos_found": len(filtered_results),
            "detection_results": [r.to_dict() for r in filtered_results],
        }

        return CollectionResponse(
            success=True,
            message=f"Directory scan completed: {len(filtered_results)} music videos found",
            data=response_data,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to detect directory music videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Collection Organization Endpoints


@collection_router.post("/organize/plan", response_model=CollectionResponse)
async def create_organization_plan(request: OrganizationRequest):
    """Create a plan for organizing music video collection"""
    try:
        start_time = time.time()

        if not os.path.exists(request.source_directory):
            raise HTTPException(
                status_code=404,
                detail=f"Source directory not found: {request.source_directory}",
            )

        organizer = await get_collection_organizer()

        # Create organization rules
        rules = OrganizationRule()

        # Map strategy string to enum
        strategy_map = {
            "artist_title": OrganizationStrategy.ARTIST_TITLE,
            "artist_album_title": OrganizationStrategy.ARTIST_ALBUM_TITLE,
            "genre_artist": OrganizationStrategy.GENRE_ARTIST,
            "year_artist": OrganizationStrategy.YEAR_ARTIST,
            "flat_artist_title": OrganizationStrategy.FLAT_ARTIST_TITLE,
            "custom": OrganizationStrategy.CUSTOM,
        }

        rules.strategy = strategy_map.get(
            request.strategy, OrganizationStrategy.ARTIST_TITLE
        )
        rules.clean_filenames = request.clean_filenames
        rules.preserve_quality_info = request.preserve_quality_info
        rules.group_versions = request.group_versions
        rules.handle_duplicates = request.handle_duplicates
        rules.create_artist_folders = request.create_artist_folders

        # Create organization plan
        plan = await organizer.create_organization_plan(
            request.source_directory, request.target_directory, rules, scan_subdirs=True
        )

        processing_time = (time.time() - start_time) * 1000

        return CollectionResponse(
            success=True,
            message=f"Organization plan created: {plan.music_videos_found} music videos, {len(plan.organization_actions)} actions",
            data=plan.to_dict(),
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create organization plan: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@collection_router.post("/organize/execute", response_model=CollectionResponse)
async def execute_organization(
    request: OrganizationRequest, background_tasks: BackgroundTasks
):
    """Execute collection organization"""
    try:
        start_time = time.time()

        organizer = await get_collection_organizer()

        # Create organization rules (same as plan endpoint)
        rules = OrganizationRule()

        strategy_map = {
            "artist_title": OrganizationStrategy.ARTIST_TITLE,
            "artist_album_title": OrganizationStrategy.ARTIST_ALBUM_TITLE,
            "genre_artist": OrganizationStrategy.GENRE_ARTIST,
            "year_artist": OrganizationStrategy.YEAR_ARTIST,
            "flat_artist_title": OrganizationStrategy.FLAT_ARTIST_TITLE,
            "custom": OrganizationStrategy.CUSTOM,
        }

        rules.strategy = strategy_map.get(
            request.strategy, OrganizationStrategy.ARTIST_TITLE
        )
        rules.clean_filenames = request.clean_filenames
        rules.preserve_quality_info = request.preserve_quality_info
        rules.group_versions = request.group_versions
        rules.handle_duplicates = request.handle_duplicates
        rules.create_artist_folders = request.create_artist_folders

        # Execute organization
        if request.dry_run:
            # For dry run, create plan only
            plan = await organizer.create_organization_plan(
                request.source_directory, request.target_directory, rules
            )

            processing_time = (time.time() - start_time) * 1000

            return CollectionResponse(
                success=True,
                message=f"DRY RUN: {plan.music_videos_found} music videos would be organized",
                data={"dry_run": True, "plan": plan.to_dict()},
                processing_time_ms=processing_time,
            )
        else:
            # Execute actual organization
            result = await organizer.organize_collection(
                request.source_directory, request.target_directory, rules, dry_run=False
            )

            processing_time = (time.time() - start_time) * 1000

            return CollectionResponse(
                success=result.success,
                message=f"Organization completed: {result.files_processed} files processed, {result.files_moved} moved",
                data=result.to_dict(),
                processing_time_ms=processing_time,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute organization: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Duplicate Detection Endpoints


@collection_router.post("/duplicates/scan", response_model=CollectionResponse)
async def scan_for_duplicates(request: DuplicateScanRequest):
    """Scan directory for duplicate music videos"""
    try:
        start_time = time.time()

        if not os.path.exists(request.directory):
            raise HTTPException(
                status_code=404, detail=f"Directory not found: {request.directory}"
            )

        duplicate_manager = await get_duplicate_manager()

        # Map confidence string to enum
        confidence_map = {
            "very_low": DuplicateConfidence.VERY_LOW,
            "low": DuplicateConfidence.LOW,
            "medium": DuplicateConfidence.MEDIUM,
            "high": DuplicateConfidence.HIGH,
            "very_high": DuplicateConfidence.VERY_HIGH,
        }

        min_confidence = confidence_map.get(
            request.min_confidence, DuplicateConfidence.MEDIUM
        )

        # Perform duplicate scan
        scan_result = await duplicate_manager.scan_for_duplicates(
            request.directory, request.scan_subdirs, min_confidence
        )

        processing_time = (time.time() - start_time) * 1000

        return CollectionResponse(
            success=True,
            message=f"Duplicate scan completed: {scan_result.duplicate_groups_found} groups found",
            data=scan_result.to_dict(),
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to scan for duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@collection_router.post("/duplicates/remove", response_model=CollectionResponse)
async def remove_duplicates(
    request: DuplicateRemovalRequest, background_tasks: BackgroundTasks
):
    """Remove duplicate files based on strategy"""
    try:
        start_time = time.time()

        duplicate_manager = await get_duplicate_manager()

        # This would require storing scan results somewhere accessible
        # For now, return error indicating need to scan first
        raise HTTPException(
            status_code=400,
            detail="Duplicate removal requires scan results. Use /duplicates/scan endpoint first.",
        )

        # Implementation would:
        # 1. Retrieve duplicate groups by IDs from cache/database
        # 2. Call duplicate_manager.remove_duplicates()
        # 3. Return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Collection Statistics and Information


@collection_router.get(
    "/stats/{directory_path:path}", response_model=CollectionResponse
)
async def get_collection_statistics(directory_path: str):
    """Get statistics about music video collection"""
    try:
        start_time = time.time()

        if not os.path.exists(directory_path):
            raise HTTPException(
                status_code=404, detail=f"Directory not found: {directory_path}"
            )

        # Gather collection statistics
        import collections
        from pathlib import Path

        directory = Path(directory_path)
        stats = {
            "directory": directory_path,
            "total_files": 0,
            "video_files": 0,
            "total_size_bytes": 0,
            "file_extensions": collections.defaultdict(int),
            "artist_folders": 0,
            "estimated_music_videos": 0,
            "organization_score": 0.0,
        }

        video_extensions = {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        music_keywords = ["music", "artist", "video", "mv"]

        # Scan directory
        for item in directory.rglob("*"):
            if item.is_file():
                stats["total_files"] += 1
                stats["file_extensions"][item.suffix.lower()] += 1

                try:
                    stats["total_size_bytes"] += item.stat().st_size
                except:
                    pass

                if item.suffix.lower() in video_extensions:
                    stats["video_files"] += 1

                    # Estimate music videos based on path/filename
                    path_str = str(item).lower()
                    if any(keyword in path_str for keyword in music_keywords):
                        stats["estimated_music_videos"] += 1

            elif item.is_dir():
                # Count potential artist folders
                if item.parent == directory and not item.name.startswith("."):
                    stats["artist_folders"] += 1

        # Calculate organization score (0-100)
        if stats["video_files"] > 0:
            organized_ratio = stats["estimated_music_videos"] / stats["video_files"]
            folder_organization = min(
                stats["artist_folders"] / max(stats["video_files"] // 10, 1), 1.0
            )
            stats["organization_score"] = (
                organized_ratio * 0.7 + folder_organization * 0.3
            ) * 100

        # Convert size to human readable
        size_mb = stats["total_size_bytes"] / (1024 * 1024)
        stats["total_size_mb"] = round(size_mb, 1)

        processing_time = (time.time() - start_time) * 1000

        return CollectionResponse(
            success=True,
            message="Collection statistics retrieved",
            data=stats,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@collection_router.get("/health", response_model=CollectionResponse)
async def get_collection_service_health():
    """Get health status of collection management services"""
    try:
        health_status = {
            "services": {},
            "overall_status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            detector = await get_music_video_detector()
            health_status["services"]["music_video_detector"] = "healthy"
        except Exception as e:
            health_status["services"]["music_video_detector"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        try:
            organizer = await get_collection_organizer()
            health_status["services"]["collection_organizer"] = "healthy"
        except Exception as e:
            health_status["services"]["collection_organizer"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        try:
            duplicate_manager = await get_duplicate_manager()
            health_status["services"]["duplicate_manager"] = "healthy"
        except Exception as e:
            health_status["services"]["duplicate_manager"] = f"error: {str(e)}"
            health_status["overall_status"] = "degraded"

        return CollectionResponse(
            success=True,
            message=f"Collection services status: {health_status['overall_status']}",
            data=health_status,
        )

    except Exception as e:
        logger.error(f"Failed to get service health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Utility Endpoints


@collection_router.get("/supported-formats")
async def get_supported_formats():
    """Get supported video formats for music video detection"""
    return JSONResponse(
        {
            "video_extensions": [
                ".mp4",
                ".avi",
                ".mkv",
                ".mov",
                ".wmv",
                ".flv",
                ".webm",
                ".m4v",
            ],
            "preferred_formats": [".mp4", ".mkv", ".webm"],
            "organization_strategies": [
                "artist_title",
                "artist_album_title",
                "genre_artist",
                "year_artist",
                "flat_artist_title",
                "custom",
            ],
            "confidence_levels": ["very_low", "low", "medium", "high", "very_high"],
            "duplicate_strategies": [
                "highest_quality",
                "largest_file",
                "smallest_file",
                "first_alphabetical",
            ],
        }
    )


@collection_router.post("/preview/organization")
async def preview_organization_path(
    artist: str = Query(..., description="Artist name"),
    title: str = Query(..., description="Song title"),
    strategy: str = Query("artist_title", description="Organization strategy"),
):
    """Preview how a file would be organized"""
    try:
        # Simple path generation preview
        strategy_map = {
            "artist_title": f"{artist}/{artist} - {title}",
            "flat_artist_title": f"{artist} - {title}",
            "genre_artist": f"Genre/{artist}/{title}",
            "year_artist": f"2024/{artist}/{title}",
        }

        example_path = strategy_map.get(strategy, f"{artist}/{artist} - {title}")

        return JSONResponse(
            {
                "artist": artist,
                "title": title,
                "strategy": strategy,
                "preview_path": example_path + ".mp4",
                "folder_structure": example_path.split("/")[:-1],
                "filename": example_path.split("/")[-1] + ".mp4",
            }
        )

    except Exception as e:
        logger.error(f"Failed to preview organization: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
