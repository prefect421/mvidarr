"""
FastAPI Video Indexing Router
Migrated from Flask src/api/video_indexing.py - Video indexing endpoints
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.services.imvdb_service import imvdb_service
from src.services.job_queue import (
    BackgroundJob,
    JobPriority,
    JobType,
    get_job_queue,
)
from src.services.thumbnail_service import thumbnail_service
from src.services.video_indexing_service import video_indexing_service

logger = logging.getLogger("mvidarr.fastapi.video_indexing")

router = APIRouter(
    prefix="/api/video-indexing",
    tags=["video-indexing"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class IndexAllRequest(BaseModel):
    """Index all videos request"""

    fetch_metadata: bool = Field(default=True, description="Whether to fetch metadata")
    max_files: Optional[int] = Field(None, ge=1, description="Maximum files to process")


class IndexSingleRequest(BaseModel):
    """Index single video request"""

    file_path: str = Field(..., min_length=1, description="Path to video file")
    fetch_metadata: bool = Field(default=True, description="Whether to fetch metadata")


class JobResponse(BaseModel):
    """Background job response"""

    success: bool
    job_id: str
    message: str


class IndexingStats(BaseModel):
    """Indexing statistics response"""

    total_videos: int
    indexed_videos: int
    unindexed_videos: int
    thumbnail_stats: Optional[Dict[str, Any]] = None


class VideoFilesScan(BaseModel):
    """Video files scan response"""

    files: List[str]
    count: int
    directory: str


class MetadataSearchRequest(BaseModel):
    """Metadata search request"""

    artist: str = Field(..., min_length=1, description="Artist name")
    title: Optional[str] = Field(None, description="Video title (optional)")


class MetadataSearchResponse(BaseModel):
    """Metadata search response"""

    success: bool
    metadata: Optional[Dict[str, Any]] = None
    videos: Optional[List[Dict[str, Any]]] = None
    count: Optional[int] = None
    message: Optional[str] = None


class ThumbnailDownloadRequest(BaseModel):
    """Thumbnail download request"""

    url: str = Field(..., min_length=1, description="Thumbnail URL")
    artist: str = Field(default="unknown", description="Artist name")
    title: str = Field(default="unknown", description="Video title")


class ThumbnailDownloadResponse(BaseModel):
    """Thumbnail download response"""

    success: bool
    thumbnail_path: Optional[str] = None
    message: str
    error: Optional[str] = None


class IndexingPreviewRequest(BaseModel):
    """Indexing preview request"""

    file_path: str = Field(..., min_length=1, description="Path to video file")


class IndexingPreview(BaseModel):
    """Indexing preview response"""

    file_path: str
    file_metadata: Dict[str, Any]
    can_index: bool
    imvdb_preview: Optional[Dict[str, Any]] = None


class ConnectionTestResponse(BaseModel):
    """Connection test response"""

    status: str
    message: Optional[str] = None
    error: Optional[str] = None


# ========================================================================================
# VIDEO INDEXING BACKGROUND JOBS
# ========================================================================================


@router.post("/index-all", response_model=JobResponse)
async def index_all_videos(
    index_request: IndexAllRequest = IndexAllRequest(),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Index all videos in the music videos directory (background job)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Starting video indexing process (fetch_metadata={index_request.fetch_metadata}, max_files={index_request.max_files}) for user {current_user.get('username')}"
        )

        # Create background job for video indexing
        job = BackgroundJob(
            type=JobType.VIDEO_INDEX_ALL,
            priority=JobPriority.NORMAL,
            payload={
                "fetch_metadata": index_request.fetch_metadata,
                "max_files": index_request.max_files,
            },
            created_by=user_id,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(f"Enqueued video indexing job {job_id}")

        return JobResponse(
            success=True,
            job_id=job_id,
            message=f"Video indexing job queued (fetch_metadata={index_request.fetch_metadata}, max_files={index_request.max_files or 'all'})",
        )

    except Exception as e:
        logger.error(f"Failed to queue video indexing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index-single", response_model=JobResponse)
async def index_single_video(
    index_request: IndexSingleRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Index a specific video file (background job)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Queueing single video indexing for '{index_request.file_path}' for user {current_user.get('username')}"
        )

        # Create background job for single video indexing
        job = BackgroundJob(
            type=JobType.VIDEO_INDEX_SINGLE,
            priority=JobPriority.HIGH,  # Single video indexing is higher priority
            payload={
                "file_path": index_request.file_path,
                "fetch_metadata": index_request.fetch_metadata,
            },
            created_by=user_id,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(
            f"Enqueued single video indexing job {job_id} for {index_request.file_path}"
        )

        return JobResponse(
            success=True,
            job_id=job_id,
            message=f"Single video indexing job queued for {index_request.file_path}",
        )

    except Exception as e:
        logger.error(f"Failed to queue single video indexing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# VIDEO INDEXING INFORMATION ENDPOINTS
# ========================================================================================


@router.get("/stats", response_model=IndexingStats)
async def get_indexing_stats(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get video indexing statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting indexing statistics for user {current_user.get('username')}"
        )

        stats = video_indexing_service.get_indexing_stats()

        # Add thumbnail stats
        thumbnail_stats = thumbnail_service.get_storage_stats()

        # Calculate indexed/unindexed from the actual stats keys
        total_videos = stats.get("total_videos", 0)
        downloaded_videos = stats.get("downloaded_videos", 0)
        unindexed_videos = total_videos - downloaded_videos

        return IndexingStats(
            total_videos=total_videos,
            indexed_videos=downloaded_videos,
            unindexed_videos=unindexed_videos,
            thumbnail_stats=thumbnail_stats,
        )

    except Exception as e:
        logger.error(f"Failed to get indexing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-files", response_model=VideoFilesScan)
async def scan_video_files(
    directory: Optional[str] = Query(None, description="Directory to scan (optional)"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Scan directory for video files without indexing"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Scanning video files (directory={directory}) for user {current_user.get('username')}"
        )

        scan_dir = Path(directory) if directory else None

        video_files = video_indexing_service.scan_video_files(scan_dir)

        # Convert Path objects to strings
        file_list = [str(f) for f in video_files]

        return VideoFilesScan(
            files=file_list,
            count=len(file_list),
            directory=str(scan_dir) if scan_dir else "default",
        )

    except Exception as e:
        logger.error(f"Failed to scan video files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview", response_model=IndexingPreview)
async def preview_indexing(
    preview_request: IndexingPreviewRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Preview what would be indexed without actually indexing"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Previewing indexing for '{preview_request.file_path}' for user {current_user.get('username')}"
        )

        file_metadata = video_indexing_service.extract_file_metadata(
            Path(preview_request.file_path)
        )

        preview = IndexingPreview(
            file_path=preview_request.file_path,
            file_metadata=file_metadata,
            can_index=bool(file_metadata.get("extracted_artist")),
        )

        # Try to get IMVDb preview if we have artist and title
        if file_metadata.get("extracted_artist") and file_metadata.get(
            "extracted_title"
        ):
            try:
                imvdb_metadata = video_indexing_service.fetch_imvdb_metadata(
                    file_metadata["extracted_artist"], file_metadata["extracted_title"]
                )
                preview.imvdb_preview = imvdb_metadata
            except Exception as e:
                logger.warning(f"Failed to get IMVDb preview: {e}")

        return preview

    except Exception as e:
        logger.error(f"Failed to preview indexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# METADATA AND THUMBNAIL ENDPOINTS
# ========================================================================================


@router.post("/metadata/search", response_model=MetadataSearchResponse)
async def search_metadata(
    search_request: MetadataSearchRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Search IMVDb for metadata"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Searching metadata for artist '{search_request.artist}' (title='{search_request.title}') for user {current_user.get('username')}"
        )

        if search_request.title:
            # Search for specific video
            metadata = imvdb_service.find_best_video_match(
                search_request.artist, search_request.title
            )
            if metadata:
                return MetadataSearchResponse(
                    success=True, metadata=imvdb_service.extract_metadata(metadata)
                )
            else:
                return MetadataSearchResponse(
                    success=False, message="No matching video found"
                )
        else:
            # Search for videos by artist
            videos = imvdb_service.search_videos(search_request.artist)
            metadata_list = [imvdb_service.extract_metadata(video) for video in videos]

            return MetadataSearchResponse(
                success=True, videos=metadata_list, count=len(metadata_list)
            )

    except Exception as e:
        logger.error(f"Failed to search metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thumbnails/download", response_model=ThumbnailDownloadResponse)
async def download_thumbnail(
    download_request: ThumbnailDownloadRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Download thumbnail for a video"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Downloading thumbnail from '{download_request.url}' for user {current_user.get('username')}"
        )

        thumbnail_path = thumbnail_service.download_video_thumbnail(
            download_request.artist, download_request.title, download_request.url
        )

        if thumbnail_path:
            return ThumbnailDownloadResponse(
                success=True,
                thumbnail_path=thumbnail_path,
                message="Thumbnail downloaded successfully",
            )
        else:
            return ThumbnailDownloadResponse(
                success=False,
                message="Failed to download thumbnail",
                error="Download operation failed",
            )

    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thumbnails/stats")
async def get_thumbnail_stats(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get thumbnail storage statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting thumbnail statistics for user {current_user.get('username')}"
        )

        stats = thumbnail_service.get_storage_stats()

        return stats

    except Exception as e:
        logger.error(f"Failed to get thumbnail stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# INTEGRATION TESTING ENDPOINTS
# ========================================================================================


@router.get("/imvdb/test", response_model=ConnectionTestResponse)
async def test_imvdb_connection(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Test IMVDb API connection"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Testing IMVDb connection for user {current_user.get('username')}")

        result = imvdb_service.test_connection()

        if result["status"] != "success":
            raise HTTPException(status_code=503, detail=result)

        return ConnectionTestResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IMVDb connection test failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "error", "error": str(e)}
        )
