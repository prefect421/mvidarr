"""
FastAPI Videos CRUD API Module

This module contains the core CRUD (Create, Read, Update, Delete) operations for videos.
These endpoints handle basic video management operations:
- List videos with pagination, filtering, and sorting
- Get single video details
- Update video metadata
- Delete videos
- Update video status

Extracted from videos.py as part of the API modularization effort.
Uses Pydantic models from videos_models.py for request/response validation.

Authentication: All endpoints require session-based authentication via get_current_user dependency.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)
from src.api.fastapi.videos_models import (
    VideoResponse,
    VideoStatusUpdateRequest,
    VideoUpdateRequest,
)
from src.database.connection import get_db_session
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

# Router with NO prefix - prefix will be added by parent router
router = APIRouter(
    tags=["videos-crud"],
    responses={
        404: {"description": "Video not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.videos_crud")


# ========================================================================================
# AUTHENTICATION DEPENDENCIES
# ========================================================================================


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


def _safe_parse_genres(genres: Union[str, List[str], None]) -> List[str]:
    """Safely parse genres field that may be JSON string or list"""
    if isinstance(genres, list):
        return genres
    if not genres:
        return []
    if isinstance(genres, str):
        try:
            genres = genres.strip()
            if not genres:
                return []
            return json.loads(genres)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse genres JSON: {genres}, error: {e}")
            return []
    return []


# ========================================================================================
# CRUD ENDPOINTS
# ========================================================================================


@router.get("/", response_model=Dict)
async def list_videos(
    limit: int = Query(50, le=500, ge=1),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[str] = Query(None),
    artist_id: Optional[int] = Query(None),
    session: Session = Depends(get_db_session),
):
    """
    List all videos with pagination and sorting.

    Query Parameters:
    - limit: Maximum number of videos to return (1-500, default: 50)
    - offset: Number of videos to skip (default: 0)
    - sort_by: Field to sort by (default: created_at)
    - sort_order: Sort order - asc or desc (default: desc)
    - status: Filter by video status (optional)
    - artist_id: Filter by artist ID (optional)

    Returns:
    - videos: List of video objects with metadata
    - pagination: Pagination information (total, limit, offset, has_more)
    """
    try:
        # Build base query with eager loading
        query = session.query(Video).options(joinedload(Video.artist))

        # Apply filters
        if status:
            query = query.filter(Video.status == status)
        if artist_id:
            query = query.filter(Video.artist_id == artist_id)

        # Apply sorting
        sort_column = getattr(Video, sort_by, Video.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Get total count
        total_count = query.count()

        # Apply pagination
        videos = query.offset(offset).limit(limit).all()

        # Convert to response format
        video_responses = []
        for video in videos:
            video_dict = {
                "id": video.id,
                "title": video.title,
                "artist_id": video.artist_id,
                "artist_name": video.artist.name if video.artist else None,
                "url": video.url,
                "youtube_url": video.youtube_url,
                "video_url": video.url
                or video.youtube_url,  # For JavaScript compatibility
                "status": video.status,
                "file_path": getattr(video, "file_path", video.local_path),
                "local_path": video.local_path,  # For JavaScript compatibility
                "file_size": getattr(video, "file_size", None),
                "duration": video.duration,
                "resolution": getattr(video, "resolution", None),
                "fps": getattr(video, "fps", None),
                "codec": getattr(video, "codec", None),
                "bitrate": getattr(video, "bitrate", None),
                "created_at": (
                    video.created_at.isoformat() if video.created_at else None
                ),
                "updated_at": (
                    video.updated_at.isoformat() if video.updated_at else None
                ),
                "genres": _safe_parse_genres(getattr(video, "genres", [])),
                "thumbnail_url": (
                    f"/api/videos/{video.id}/thumbnail" if video.id else None
                ),
            }
            video_responses.append(video_dict)

        return {
            "videos": video_responses,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int = FastAPIPath(..., ge=1), session: Session = Depends(get_db_session)
):
    """
    Get single video details by ID.

    Path Parameters:
    - video_id: Unique identifier for the video

    Returns:
    - VideoResponse: Complete video metadata including artist, file info, and genres

    Raises:
    - 404: Video not found
    - 500: Internal server error
    """
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        return VideoResponse(
            id=video.id,
            title=video.title,
            artist_id=video.artist_id,
            artist_name=video.artist.name if video.artist else None,
            url=video.url,
            youtube_url=video.youtube_url,
            video_url=video.url
            or video.youtube_url,  # For compatibility, fallback to YouTube URL
            status=video.status,
            file_path=getattr(video, "file_path", video.local_path),
            local_path=video.local_path,
            file_size=getattr(video, "file_size", None),
            duration=video.duration,
            resolution=getattr(video, "resolution", None),
            fps=getattr(video, "fps", None),
            codec=getattr(video, "codec", None),
            bitrate=getattr(video, "bitrate", None),
            created_at=video.created_at,
            updated_at=video.updated_at,
            genres=_safe_parse_genres(getattr(video, "genres", [])),
            thumbnail_url=f"/api/videos/{video.id}/thumbnail",
            quality=getattr(video, "quality", None),
            video_metadata=getattr(video, "video_metadata", None),
            lyrics=getattr(video, "lyrics", None),
            year=getattr(video, "year", None),
            release_date=getattr(video, "release_date", None),
            album=getattr(video, "album", None),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: int = FastAPIPath(..., ge=1),
    update_data: VideoUpdateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """
    Update video information.

    Path Parameters:
    - video_id: Unique identifier for the video

    Request Body:
    - VideoUpdateRequest: Fields to update (all optional)
      - title: Video title
      - artist_id: Artist ID
      - artist_name: Artist name (alternative to artist_id, will find or create artist)
      - url: Video URL
      - youtube_url: YouTube URL
      - status: Video status
      - genres: List of genre strings
      - year: Release year
      - release_date: Release date (YYYY-MM-DD format)
      - album: Album name

    Note: Thumbnail fields are NOT updated through this endpoint.
    Use PUT /api/videos/{video_id}/thumbnail for thumbnail updates.

    Returns:
    - VideoResponse: Updated video metadata

    Raises:
    - 404: Video not found
    - 500: Internal server error
    """
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Update fields if provided
        update_fields = update_data.dict(exclude_unset=True)

        # Handle artist_name - find or create artist and set artist_id
        if "artist_name" in update_fields:
            artist_name = update_fields.pop("artist_name")
            if artist_name:
                # Find or create artist
                artist = (
                    session.query(Artist).filter(Artist.name == artist_name).first()
                )
                if not artist:
                    artist = Artist(name=artist_name)
                    session.add(artist)
                    session.flush()  # Get the artist ID
                video.artist_id = artist.id
                logger.info(
                    f"Updated video {video_id} artist to: {artist_name} (ID: {artist.id})"
                )

        # Fields that should NOT be updated through this endpoint
        # (they have dedicated endpoints)
        protected_fields = {
            "thumbnail_url",
            "thumbnail_path",
            "thumbnail_source",
            "thumbnail_metadata",
            "thumbnail_uploaded_at",
        }

        for field, value in update_fields.items():
            # Skip thumbnail fields - they should only be updated through thumbnail endpoints
            if field in protected_fields:
                logger.warning(
                    f"Skipping thumbnail field '{field}' in video update - use thumbnail endpoints instead"
                )
                continue

            if field == "genres" and value:
                # Convert genres list to JSON string for database storage
                value = json.dumps(value)
            setattr(video, field, value)

        video.updated_at = datetime.utcnow()
        session.commit()

        # Reload with artist relationship
        session.refresh(video)
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        logger.info(f"Updated video {video_id}")

        return VideoResponse(
            id=video.id,
            title=video.title,
            artist_id=video.artist_id,
            artist_name=video.artist.name if video.artist else None,
            url=video.url,
            youtube_url=video.youtube_url,
            video_url=video.url
            or video.youtube_url,  # For compatibility, fallback to YouTube URL
            status=video.status,
            file_path=getattr(video, "file_path", video.local_path),
            local_path=video.local_path,
            file_size=getattr(video, "file_size", None),
            duration=video.duration,
            resolution=getattr(video, "resolution", None),
            fps=getattr(video, "fps", None),
            codec=getattr(video, "codec", None),
            bitrate=getattr(video, "bitrate", None),
            created_at=video.created_at,
            updated_at=video.updated_at,
            genres=_safe_parse_genres(getattr(video, "genres", [])),
            thumbnail_url=f"/api/videos/{video.id}/thumbnail",
            quality=getattr(video, "quality", None),
            video_metadata=getattr(video, "video_metadata", None),
            lyrics=getattr(video, "lyrics", None),
            year=getattr(video, "year", None),
            release_date=getattr(video, "release_date", None),
            album=getattr(video, "album", None),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{video_id}")
async def delete_video(
    video_id: int = FastAPIPath(..., ge=1), session: Session = Depends(get_db_session)
):
    """
    Delete single video.

    This endpoint deletes a video from the database and optionally removes
    associated files from disk. Also removes video from any playlists.

    Path Parameters:
    - video_id: Unique identifier for the video

    Returns:
    - message: Success message

    Raises:
    - 404: Video not found
    - 500: Internal server error

    Side Effects:
    - Deletes video file from disk if it exists
    - Removes video from all playlists
    - Deletes video record from database
    """
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Delete associated files if they exist
        if (
            getattr(video, "file_path", video.local_path)
            and Path(getattr(video, "file_path", video.local_path)).exists()
        ):
            try:
                Path(getattr(video, "file_path", video.local_path)).unlink()
                logger.info(
                    f"Deleted video file: {getattr(video, 'file_path', video.local_path)}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete video file {getattr(video, 'file_path', video.local_path)}: {e}"
                )

        # Delete foreign key references first to avoid constraint errors

        # Remove from any playlists
        from src.database.models import PlaylistEntry

        playlist_entries = (
            session.query(PlaylistEntry)
            .filter(PlaylistEntry.video_id == video_id)
            .all()
        )
        for entry in playlist_entries:
            session.delete(entry)

        # Delete from database
        session.delete(video)
        session.commit()

        logger.info(f"Deleted video {video_id}")

        return {"message": f"Video {video_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{video_id}/status")
async def update_video_status(
    video_id: int = FastAPIPath(..., ge=1),
    status_data: VideoStatusUpdateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """
    Update video status.

    Path Parameters:
    - video_id: Unique identifier for the video

    Request Body:
    - VideoStatusUpdateRequest:
      - status: New status value (WANTED, DOWNLOADING, DOWNLOADED, IGNORED, FAILED, MONITORED)

    Returns:
    - message: Success message with new status

    Raises:
    - 404: Video not found
    - 422: Invalid status value
    - 500: Internal server error
    """
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Convert status to uppercase to match enum values
        normalized_status = status_data.status.upper()
        video.status = getattr(VideoStatus, normalized_status)
        video.updated_at = datetime.utcnow()
        session.commit()

        logger.info(f"Updated video {video_id} status to {status_data.status}")

        return {"message": f"Video status updated to {status_data.status}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating video status {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
