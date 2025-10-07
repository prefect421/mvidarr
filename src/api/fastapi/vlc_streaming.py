"""
FastAPI VLC Streaming Router - Migrated from Flask Blueprint
VLC Streaming API endpoints for MVidarr
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)
from src.database.connection import get_db
from src.database.models import Video
from src.services.vlc_streaming_service import vlc_streaming_service
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/vlc",
    tags=["vlc-streaming"],
    responses={
        404: {"description": "Video not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.vlc_streaming")


# ========================================================================================
# AUTHENTICATION
# ========================================================================================


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================


class StreamResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    stream_url: Optional[str] = None
    stream_id: Optional[str] = None


class StreamInfo(BaseModel):
    success: bool
    video_id: int
    stream_url: Optional[str] = None
    stream_id: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class ActiveStreamsResponse(BaseModel):
    streams: List[Dict[str, Any]]
    count: int


class CleanupResponse(BaseModel):
    message: str


# ========================================================================================
# ENDPOINTS
# ========================================================================================


@router.post("/stream/{video_id}", response_model=StreamResponse)
async def start_video_stream(
    video_id: int, current_user: dict = Depends(require_authentication)
):
    """Start a VLC stream for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
                )

            if not video.local_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No local file available for streaming",
                )

            # Construct absolute path
            if os.path.isabs(video.local_path):
                video_path = video.local_path
            else:
                video_path = os.path.join(os.getcwd(), video.local_path)

            if not os.path.exists(video_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video file not found on disk",
                )

            # Start the stream
            result = vlc_streaming_service.start_stream(video_id, video_path)

            if result["success"]:
                logger.info(f"Started VLC stream for video {video_id}: {video.title}")
                return StreamResponse(**result)
            else:
                logger.error(
                    f"Failed to start VLC stream for video {video_id}: {result.get('error')}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result.get("error", "Failed to start VLC stream"),
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting VLC stream for video {video_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/stream/{video_id}", response_model=StreamResponse)
async def stop_video_stream(
    video_id: int, current_user: dict = Depends(require_authentication)
):
    """Stop a VLC stream for a video"""
    try:
        result = vlc_streaming_service.stop_stream(video_id)

        if result["success"]:
            logger.info(f"Stopped VLC stream for video {video_id}")
            return StreamResponse(**result)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("error", "Stream not found"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping VLC stream for video {video_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/stream/{video_id}", response_model=StreamInfo)
async def get_stream_info(
    video_id: int, current_user: dict = Depends(require_authentication)
):
    """Get information about a video stream"""
    try:
        result = vlc_streaming_service.get_stream_info(video_id)

        if result["success"]:
            return StreamInfo(
                success=True,
                video_id=video_id,
                stream_url=result.get("stream_url"),
                stream_id=result.get("stream_id"),
                is_active=result.get("is_active", False),
                created_at=result.get("created_at"),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("error", "Stream not found"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VLC stream info for video {video_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/streams", response_model=ActiveStreamsResponse)
async def list_active_streams(current_user: dict = Depends(require_authentication)):
    """List all active VLC streams"""
    try:
        streams = vlc_streaming_service.list_active_streams()
        return ActiveStreamsResponse(streams=streams, count=len(streams))

    except Exception as e:
        logger.error(f"Error listing VLC streams: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_streams(current_user: dict = Depends(require_authentication)):
    """Clean up old/expired VLC streams"""
    try:
        vlc_streaming_service.cleanup_old_streams()
        return CleanupResponse(message="Cleanup completed")

    except Exception as e:
        logger.error(f"Error cleaning up VLC streams: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
