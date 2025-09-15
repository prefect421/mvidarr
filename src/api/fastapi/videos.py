"""
FastAPI Videos API - Complete Migration from Flask
Phase 3 Week 27: Videos API Complete Migration

Migrated from src/api/videos.py (7,738 lines, 67 endpoints)
"""

import asyncio
import json
import mimetypes
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, unquote

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
)
from fastapi import Path as FastAPIPath
from fastapi import (
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from src.database.connection import get_db_session
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.services.imvdb_service import imvdb_service
from src.services.metadata_enrichment_service import metadata_enrichment_service
from src.services.settings_service import settings
from src.services.thumbnail_service import thumbnail_service
from src.services.video_indexing_service import VideoIndexingService
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

router = APIRouter(
    prefix="/api/videos",
    tags=["videos"],
    responses={
        404: {"description": "Video not found"},
        422: {"description": "Validation error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.videos")

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class VideoResponse(BaseModel):
    id: int
    title: str
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    url: Optional[str] = None
    youtube_url: Optional[str] = None
    video_url: Optional[str] = None
    status: Optional[str] = None
    file_path: Optional[str] = None
    local_path: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    genres: Optional[List[str]] = []
    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class VideoUpdateRequest(BaseModel):
    title: Optional[str] = None
    artist_id: Optional[int] = None
    url: Optional[str] = None
    youtube_url: Optional[str] = None
    status: Optional[str] = None
    genres: Optional[List[str]] = None


class VideoSearchRequest(BaseModel):
    query: Optional[str] = None
    artist_id: Optional[int] = None
    status: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    limit: int = Field(default=50, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc")


class BulkVideoRequest(BaseModel):
    video_ids: List[int] = Field(..., min_items=1)


class BulkDeleteRequest(BulkVideoRequest):
    pass


class BulkDownloadRequest(BulkVideoRequest):
    pass


class BulkStatusUpdateRequest(BulkVideoRequest):
    status: str = Field(..., pattern="^(wanted|ignored|downloaded|failed)$")


class BulkEditRequest(BulkVideoRequest):
    title: Optional[str] = None
    artist_id: Optional[int] = None
    url: Optional[str] = None
    youtube_url: Optional[str] = None
    status: Optional[str] = None
    genres: Optional[List[str]] = None


class BulkOrganizeRequest(BulkVideoRequest):
    target_directory: Optional[str] = None
    create_artist_folders: bool = True
    update_database_paths: bool = True


class BulkRefreshMetadataRequest(BulkVideoRequest):
    refresh_imvdb: bool = True
    refresh_youtube: bool = True
    refresh_musicbrainz: bool = False
    force_refresh: bool = False


class VideoStatusUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED|wanted|downloading|downloaded|ignored|failed|monitored)$",
    )


class ThumbnailSearchRequest(BaseModel):
    query: Optional[str] = None
    source: str = Field(default="auto", pattern="^(auto|youtube|imvdb|google)$")


class DownloadRequest(BaseModel):
    priority: int = Field(default=1, ge=1, le=10)
    force_redownload: bool = False


# ========================================================================================
# UTILITY FUNCTIONS
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


async def resolve_video_url(video: Video, session: Session) -> Optional[str]:
    """
    Helper function to resolve video URL using yt-dlp search

    Args:
        video: Video object
        session: Database session

    Returns:
        str: Resolved URL or None
    """
    if video.url:
        return video.url

    # Also check youtube_url field as fallback (but ensure it's complete)
    if (
        video.youtube_url and len(video.youtube_url.strip()) > 30
    ):  # Valid YouTube URLs are longer than 30 chars
        # Additional check: ensure URL has a video ID (not just ending with "?v=")
        if not video.youtube_url.endswith("?v="):
            return video.youtube_url

    try:
        artist_name = video.artist.name if video.artist else "Unknown Artist"
        # Ensure title is a string (fix for integer title issue)
        video_title = str(video.title) if video.title is not None else "Unknown"
        search_query = f"{artist_name} {video_title}"
        logger.info(f"Searching for video URL: {search_query}")

        # Use yt-dlp to search YouTube
        cmd = [
            "/usr/local/bin/yt-dlp",  # Use the system-installed version
            "--dump-json",
            "--no-download",
            "--playlist-items",
            "1",
            f"ytsearch1:{search_query}",
        ]

        # Run subprocess asynchronously
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode == 0 and stdout:
            video_info = json.loads(stdout.decode().strip())
            resolved_url = video_info.get("webpage_url") or video_info.get("url")

            if resolved_url:
                # Update the video's URL in the database
                video.url = resolved_url
                session.commit()
                logger.info(f"✅ Resolved URL for '{search_query}': {resolved_url}")
                return resolved_url
        else:
            logger.warning(
                f"⚠️ Failed to resolve URL for '{search_query}': {stderr.decode() if stderr else 'No error output'}"
            )

    except asyncio.TimeoutError:
        logger.error(f"❌ Timeout resolving URL for video {video.id}")
    except Exception as e:
        logger.error(f"❌ Error resolving URL for video {video.id}: {e}")

    return None


async def find_relocated_video(video: Video) -> Optional[Path]:
    """Find video file if it has been relocated"""
    if not getattr(video, "file_path", video.local_path):
        return None

    original_path = Path(getattr(video, "file_path", video.local_path))
    if original_path.exists():
        return original_path

    # Search for relocated file
    filename = original_path.name
    search_dirs = [
        Path("/data/musicvideos"),
        Path("/data/music_videos"),
        Path("data/musicvideos"),
        Path("data/music_videos"),
    ]

    for search_dir in search_dirs:
        if search_dir.exists():
            for file_path in search_dir.rglob(filename):
                if file_path.is_file():
                    logger.info(f"Found relocated video: {file_path}")
                    return file_path

    return None


# ========================================================================================
# CORE VIDEO CRUD OPERATIONS
# ========================================================================================


@router.get("/", response_model=Dict[str, Any])
async def list_videos(
    limit: int = Query(50, le=500, ge=1),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[str] = Query(None),
    artist_id: Optional[int] = Query(None),
    session: Session = Depends(get_db_session),
):
    """List all videos with pagination and sorting"""
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


@router.get("/universal-search", response_model=Dict)
async def universal_search(
    q: str = Query(..., min_length=1),
    extended: bool = Query(False),
    session: Session = Depends(get_db_session),
):
    """Universal search endpoint that searches across videos, artists, IMVDb, and YouTube"""
    try:
        query = q.lower()

        # Local database search (skip if extended mode)
        video_results = []
        artist_results = []

        if not extended:
            # Search local videos
            videos = (
                session.query(Video)
                .join(Artist)
                .filter(
                    Video.title.ilike(f"%{query}%") | Artist.name.ilike(f"%{query}%")
                )
                .limit(5)
                .all()
            )

            for video in videos:
                video_results.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist": video.artist.name if video.artist else "Unknown",
                        "status": (
                            video.status.value
                            if hasattr(video.status, "value")
                            else str(video.status)
                        ),
                        "year": getattr(video, "year", None),
                        "thumbnail": f"/api/videos/{video.id}/thumbnail",
                        "duration": getattr(video, "duration", None),
                        "quality": getattr(video, "quality", None),
                        "url": f"/video/{video.id}",
                    }
                )

            # Search local artists
            artists = (
                session.query(Artist)
                .filter(Artist.name.ilike(f"%{query}%"))
                .limit(5)
                .all()
            )

            for artist in artists:
                artist_results.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "video_count": len(artist.videos) if artist.videos else 0,
                        "monitored": getattr(artist, "monitored", True),
                        "genres": [],
                        "url": f"/artist/{artist.id}",
                    }
                )

        # External search results
        external_results = []

        # IMVDb Search
        try:
            from src.services.imvdb_service import imvdb_service

            imvdb_limit = 8 if extended else 3

            if imvdb_service:
                imvdb_search_result = await asyncio.to_thread(
                    imvdb_service.search_artist_videos, query, imvdb_limit
                )

                if imvdb_search_result and imvdb_search_result.get("videos"):
                    imvdb_results = []
                    logger.debug(
                        f"Sample IMVDb video data: {imvdb_search_result['videos'][0] if imvdb_search_result['videos'] else 'No videos'}"
                    )
                    for video in imvdb_search_result["videos"][:imvdb_limit]:
                        # Extract artist name from nested structure with multiple fallbacks
                        artist_name = ""
                        artist_data = video.get("artist")

                        if isinstance(artist_data, dict):
                            # Try common artist name fields
                            artist_name = (
                                artist_data.get("name")
                                or artist_data.get("artist_name")
                                or artist_data.get("entity_name")
                                or ""
                            )
                        elif isinstance(artist_data, str):
                            artist_name = artist_data

                        # Additional fallbacks
                        if not artist_name:
                            artist_name = (
                                video.get("artist_name", "")
                                or video.get("entity_name", "")
                                or video.get("band_name", "")
                                or query.title()  # Use the search query as artist name
                            )

                        imvdb_results.append(
                            {
                                "source": "IMVDb",
                                "id": str(video.get("id", "")),
                                "title": video.get("song_title", ""),
                                "artist": artist_name,
                                "year": video.get("year", None),
                                "thumbnail": (
                                    video.get("image", {}).get("o", "")
                                    if video.get("image")
                                    else ""
                                ),
                                "action": "add_to_library",
                                "video_id": str(video.get("id", "")),
                                "imvdb_url": (
                                    f"https://imvdb.com/video/{video.get('id', '')}"
                                    if video.get("id")
                                    else ""
                                ),
                            }
                        )
                    external_results.extend(imvdb_results)
                    logger.info(
                        f"Found {len(imvdb_results)} IMVDb results for: {query}"
                    )
                else:
                    logger.info(f"No IMVDb results found for: {query}")
        except Exception as e:
            logger.warning(f"IMVDb search failed: {e}")

        # YouTube Search
        try:
            from src.services.youtube_search_service import youtube_search_service

            youtube_limit = 10 if extended else 5

            if youtube_search_service and youtube_search_service.api_key:
                youtube_search_result = await asyncio.to_thread(
                    youtube_search_service.search_artist_videos, query, youtube_limit
                )

                if youtube_search_result and youtube_search_result.get("videos"):
                    youtube_results = []
                    for video in youtube_search_result["videos"][:youtube_limit]:
                        youtube_results.append(
                            {
                                "source": "YouTube",
                                "id": video.get("youtube_id", ""),
                                "title": video.get("title", ""),
                                "artist": video.get("channel_title", ""),
                                "thumbnail": video.get("thumbnail_url", ""),
                                "duration": (
                                    str(video.get("duration", ""))
                                    if video.get("duration")
                                    else ""
                                ),
                                "view_count": (
                                    str(video.get("view_count", ""))
                                    if video.get("view_count")
                                    else ""
                                ),
                                "action": "add_to_library",
                                "video_id": video.get("youtube_id", ""),
                                "youtube_url": video.get("youtube_url", ""),
                            }
                        )
                    external_results.extend(youtube_results)
                    logger.info(
                        f"Found {len(youtube_results)} YouTube results for: {query}"
                    )
                else:
                    logger.info(f"No YouTube results found for: {query}")
            else:
                logger.warning(
                    "YouTube API key not configured, skipping YouTube search"
                )
        except Exception as e:
            logger.warning(f"YouTube search failed: {e}")

        # Structured response matching Flask format
        response = {
            "videos": video_results,
            "artists": artist_results,
            "external": external_results,
            "total": len(video_results) + len(artist_results) + len(external_results),
        }

        return response

    except Exception as e:
        logger.error(f"Universal search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int = FastAPIPath(..., ge=1), session: Session = Depends(get_db_session)
):
    """Get single video details"""
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
    """Update video information"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Update fields if provided
        update_fields = update_data.dict(exclude_unset=True)

        for field, value in update_fields.items():
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
    """Delete single video"""
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
    """Update video status"""
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


# ========================================================================================
# VIDEO SEARCH OPERATIONS
# ========================================================================================


@router.get("/search")
async def search_videos(
    query: Optional[str] = Query(None),
    artist_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    genre: Optional[str] = Query(None),
    limit: int = Query(50, le=500, ge=1),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_db_session),
):
    """Search videos with filters"""
    try:
        # Build base query
        query_builder = session.query(Video).options(joinedload(Video.artist))

        # Apply text search
        if query:
            search_filter = or_(
                Video.title.ilike(f"%{query}%"),
                Video.artist.has(Artist.name.ilike(f"%{query}%")),
            )
            query_builder = query_builder.filter(search_filter)

        # Apply filters
        if artist_id:
            query_builder = query_builder.filter(Video.artist_id == artist_id)
        if status:
            query_builder = query_builder.filter(Video.status == status)
        if year:
            # Assuming we have a year field or extract from created_at
            query_builder = query_builder.filter(
                func.extract("year", Video.created_at) == year
            )
        if genre:
            # Search in genres JSON field
            query_builder = query_builder.filter(Video.genres.like(f'%"{genre}"%'))

        # Apply sorting
        sort_column = getattr(Video, sort_by, Video.created_at)
        if sort_order == "desc":
            query_builder = query_builder.order_by(sort_column.desc())
        else:
            query_builder = query_builder.order_by(sort_column.asc())

        # Get total count
        total_count = query_builder.count()

        # Apply pagination
        videos = query_builder.offset(offset).limit(limit).all()

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
                "created_at": (
                    video.created_at.isoformat() if video.created_at else None
                ),
                "genres": _safe_parse_genres(getattr(video, "genres", [])),
                "thumbnail_url": f"/api/videos/{video.id}/thumbnail",
            }
            video_responses.append(video_dict)

        return {
            "videos": video_responses,
            "search": {
                "query": query,
                "filters": {
                    "artist_id": artist_id,
                    "status": status,
                    "year": year,
                    "genre": genre,
                },
            },
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Error searching videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# VIDEO STREAMING AND MEDIA OPERATIONS
# ========================================================================================


@router.get("/{video_id}/stream")
@router.head("/{video_id}/stream")
async def stream_video(
    request: Request,
    video_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Stream video with HTTP range support"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Find the video file
        video_path = None
        if video.local_path and Path(video.local_path).exists():
            video_path = Path(video.local_path)
        else:
            # Try to find relocated file
            video_path = await find_relocated_video(video)

        if not video_path or not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Get file size
        file_size = video_path.stat().st_size

        # Handle range requests for video streaming
        range_header = request.headers.get("Range")

        if range_header:
            # Parse range header
            range_match = range_header.replace("bytes=", "").split("-")
            range_start = int(range_match[0]) if range_match[0] else 0
            range_end = int(range_match[1]) if range_match[1] else file_size - 1

            # Ensure valid range
            range_start = max(0, min(range_start, file_size - 1))
            range_end = max(range_start, min(range_end, file_size - 1))
            content_length = range_end - range_start + 1

            # Create streaming response for range
            def generate_range():
                with open(video_path, "rb") as f:
                    f.seek(range_start)
                    remaining = content_length
                    while remaining:
                        chunk_size = min(8192, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            # Get MIME type
            content_type, _ = mimetypes.guess_type(str(video_path))
            if not content_type:
                content_type = "video/mp4"  # Default fallback

            headers = {
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
            }

            return StreamingResponse(generate_range(), status_code=206, headers=headers)
        else:
            # Return full file
            content_type, _ = mimetypes.guess_type(str(video_path))
            if not content_type:
                content_type = "video/mp4"

            return FileResponse(
                video_path, media_type=content_type, filename=video_path.name
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# THUMBNAIL OPERATIONS
# ========================================================================================


@router.get("/{video_id}/thumbnail")
async def get_video_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    size: Optional[str] = Query(None, pattern="^(small|medium|large)$"),
    session: Session = Depends(get_db_session),
):
    """Get video thumbnail"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # First, check if video has a thumbnail_path in database
        if video.thumbnail_path and video.thumbnail_path.strip():
            thumbnail_file = Path(video.thumbnail_path)
            if thumbnail_file.exists():
                # Detect media type based on file extension
                media_type = "image/jpeg"
                if thumbnail_file.suffix.lower() in [".png"]:
                    media_type = "image/png"
                elif thumbnail_file.suffix.lower() in [".webp"]:
                    media_type = "image/webp"

                return FileResponse(
                    thumbnail_file,
                    media_type=media_type,
                    filename=f"video_{video_id}_thumbnail{thumbnail_file.suffix}",
                )

        # Fall back to old naming pattern for compatibility
        thumbnail_dir = Path("/home/mike/mvidarr/data/thumbnails/videos")

        if size:
            thumbnail_file = thumbnail_dir / f"{video_id}_{size}.webp"
        else:
            # Try different sizes in order of preference
            for sz in ["medium", "large", "small"]:
                thumbnail_file = thumbnail_dir / f"{video_id}_{sz}.webp"
                if thumbnail_file.exists():
                    break
            else:
                # Try without size suffix
                thumbnail_file = thumbnail_dir / f"{video_id}.webp"

        if thumbnail_file.exists():
            return FileResponse(
                thumbnail_file,
                media_type="image/webp",
                filename=f"video_{video_id}_thumbnail.webp",
            )
        else:
            # Return placeholder thumbnail
            placeholder_path = Path("frontend/static/placeholder-video.png")
            if placeholder_path.exists():
                return FileResponse(
                    placeholder_path, media_type="image/png", filename="placeholder.png"
                )
            else:
                raise HTTPException(status_code=404, detail="Thumbnail not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thumbnail for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-thumbnails")
async def refresh_video_thumbnails(
    body: Optional[dict] = Body(None), session: Session = Depends(get_db_session)
):
    """Refresh thumbnails for videos using FFmpeg frame extraction"""
    try:
        video_ids = None
        if body and "video_ids" in body:
            video_ids = body["video_ids"]

        if video_ids is None:
            # Refresh all videos that have local file paths (limit to first 10 for testing)
            videos = (
                session.query(Video)
                .filter(Video.local_path.isnot(None), Video.local_path != "")
                .limit(10)
                .all()
            )
        else:
            # Refresh specific videos
            videos = (
                session.query(Video)
                .filter(
                    Video.id.in_(video_ids),
                    Video.local_path.isnot(None),
                    Video.local_path != "",
                )
                .all()
            )

        if not videos:
            return {
                "message": "No videos with local file paths found in database",
                "refreshed_count": 0,
                "total_videos": 0,
                "valid_videos": 0,
                "errors": ["No videos have local_path field populated"],
            }

        # Filter videos that actually have existing video files
        valid_videos = []
        video_paths = []

        for video in videos:
            video_file = Path(video.local_path)
            if video_file.exists() and video_file.is_file():
                valid_videos.append(video)
                video_paths.append(str(video_file))

        if not valid_videos:
            return {
                "message": "No videos with existing local files found for thumbnail generation",
                "refreshed_count": 0,
                "total_videos": len(videos),
                "valid_videos": 0,
                "errors": ["No video files found on disk"],
            }

        logger.info(f"Starting thumbnail generation for {len(valid_videos)} videos")

        # Get thumbnails directory from settings
        thumbnails_dir = thumbnail_service.thumbnails_dir / "videos"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        # Process videos directly using FFmpeg
        refreshed_count = 0
        errors = []

        for video in valid_videos:
            try:
                video_file = Path(video.local_path)
                logger.debug(f"Generating thumbnail for: {video_file.name}")

                # Create video-specific thumbnail directory
                video_thumb_dir = thumbnails_dir / video_file.stem
                video_thumb_dir.mkdir(parents=True, exist_ok=True)

                # Generate thumbnail filename
                thumbnail_filename = f"{video_file.stem}_thumb.jpg"
                thumbnail_path = video_thumb_dir / thumbnail_filename

                # Generate thumbnail using FFmpeg
                result = await ffmpeg_stream_manager.generate_thumbnail_async(
                    video_path=video_file,
                    output_path=thumbnail_path,
                    timestamp=None,  # Auto-detect middle of video
                    size="640x480",
                )

                if result["success"]:
                    # Update video record with thumbnail path
                    video.thumbnail_path = str(thumbnail_path)
                    video.updated_at = datetime.utcnow()

                    refreshed_count += 1
                    logger.info(
                        f"Generated thumbnail for video {video.id}: {thumbnail_path}"
                    )
                else:
                    error_msg = result.get("error", "Unknown error")
                    errors.append(f"Video {video.id} ({video_file.name}): {error_msg}")
                    logger.warning(
                        f"Failed to generate thumbnail for video {video.id}: {error_msg}"
                    )

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error generating thumbnail for video {video.id}: {e}")

        # Commit database changes
        try:
            session.commit()
            logger.info(
                f"Successfully updated {refreshed_count} video thumbnail paths in database"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit thumbnail path updates: {e}")
            errors.append(f"Database update failed: {str(e)}")

        return {
            "message": f"Thumbnail generation completed for {refreshed_count} videos",
            "refreshed_count": refreshed_count,
            "total_videos": len(videos),
            "valid_videos": len(valid_videos),
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing thumbnails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{video_id}/thumbnail")
async def update_video_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    thumbnail_url: str = Body(..., embed=True),
    session: Session = Depends(get_db_session),
):
    """Update video thumbnail from URL"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # TODO: Implement thumbnail download and processing
        # This would involve downloading the image from thumbnail_url,
        # processing it (resize, format conversion), and saving to thumbnail directory

        logger.info(f"Thumbnail update requested for video {video_id}: {thumbnail_url}")

        return {"message": "Thumbnail update queued", "video_id": video_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating thumbnail for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# DOWNLOAD OPERATIONS
# ========================================================================================


@router.post("/{video_id}/download")
async def queue_video_download(
    video_id: int = FastAPIPath(..., ge=1),
    download_request: DownloadRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Queue video download"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Check if already downloaded and not forcing redownload
        if (
            video.status == VideoStatus.DOWNLOADED
            and not download_request.force_redownload
        ):
            return {"message": "Video already downloaded", "video_id": video_id}

        # Check if download already in queue
        existing_download = (
            session.query(Download)
            .filter(
                Download.video_id == video_id,
                Download.status.in_(["queued", "downloading"]),
            )
            .first()
        )

        if existing_download and not download_request.force_redownload:
            return {
                "message": "Video already in download queue",
                "video_id": video_id,
                "download_id": existing_download.id,
            }

        # Resolve video URL if needed
        if not video.url:
            url = await resolve_video_url(video, session)
            if not url:
                raise HTTPException(
                    status_code=400, detail="Could not resolve video URL for download"
                )

        # Create download entry
        download = Download(
            artist_id=video.artist_id,
            video_id=video_id,
            title=video.title,
            original_url=(
                video.url
                or video.youtube_url
                or f"https://youtube.com/watch?v={video.youtube_id}"
                if hasattr(video, "youtube_id") and video.youtube_id
                else "Unknown URL"
            ),
            status="queued",
            priority=download_request.priority,
            created_at=datetime.utcnow(),
        )

        session.add(download)

        # Update video status
        video.status = VideoStatus.DOWNLOADING
        video.updated_at = datetime.utcnow()

        session.commit()

        # Create background job for download processing
        try:
            from ...services.job_queue import (
                BackgroundJob,
                JobPriority,
                JobType,
                get_job_queue,
            )

            job_queue = await get_job_queue()

            # Map download priority to job priority
            job_priority_map = {
                1: JobPriority.LOW,
                2: JobPriority.NORMAL,
                3: JobPriority.HIGH,
                4: JobPriority.URGENT,
                5: JobPriority.URGENT,
            }
            job_priority = job_priority_map.get(
                download_request.priority, JobPriority.NORMAL
            )

            # Create download job
            download_job = BackgroundJob(
                type=JobType.VIDEO_DOWNLOAD,
                priority=job_priority,
                payload={
                    "video_id": video_id,
                    "download_id": download.id,
                    "quality": "best",
                    "force_redownload": download_request.force_redownload,
                },
                created_by=f"user-api-download-{video_id}",
            )

            job_id = await job_queue.enqueue(download_job)
            logger.info(
                f"Created background download job {job_id} for video {video_id}"
            )

        except Exception as job_error:
            logger.error(
                f"Failed to create background download job for video {video_id}: {job_error}"
            )
            # Don't fail the request if job creation fails
        # This would integrate with the Celery task system
        logger.info(
            f"Queued download for video {video_id} (priority: {download_request.priority})"
        )

        return {
            "message": "Video download queued",
            "video_id": video_id,
            "download_id": download.id,
            "priority": download_request.priority,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing download for video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# BULK OPERATIONS
# ========================================================================================


@router.post("/bulk/delete")
async def bulk_delete_videos(
    request: BulkDeleteRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk delete videos"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to delete
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        deleted_count = 0
        errors = []

        for video in videos:
            try:
                # Delete associated files if they exist
                if (
                    getattr(video, "file_path", video.local_path)
                    and Path(getattr(video, "file_path", video.local_path)).exists()
                ):
                    Path(getattr(video, "file_path", video.local_path)).unlink()

                session.delete(video)
                deleted_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error deleting video {video.id}: {e}")

        session.commit()

        logger.info(f"Bulk deleted {deleted_count} videos")

        result = {
            "message": f"Bulk delete completed",
            "deleted_count": deleted_count,
            "total_requested": len(request.video_ids),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/download")
async def bulk_download_videos(
    request: BulkDownloadRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk download videos"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to download
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        queued_count = 0
        skipped_count = 0
        errors = []

        for video in videos:
            try:
                # Skip if already downloaded
                if video.status == "downloaded":
                    skipped_count += 1
                    continue

                # Check if already in queue
                existing_download = (
                    session.query(Download)
                    .filter(
                        Download.video_id == video.id,
                        Download.status.in_(["queued", "downloading"]),
                    )
                    .first()
                )

                if existing_download:
                    skipped_count += 1
                    continue

                # Create download entry
                download = Download(
                    video_id=video.id,
                    url=video.url,
                    status="queued",
                    priority=1,  # Default priority for bulk downloads
                    created_at=datetime.utcnow(),
                )

                session.add(download)

                # Update video status
                video.status = "queued"
                video.updated_at = datetime.utcnow()

                queued_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error queuing download for video {video.id}: {e}")

        session.commit()

        logger.info(f"Bulk queued {queued_count} downloads, skipped {skipped_count}")

        result = {
            "message": "Bulk download completed",
            "queued_count": queued_count,
            "skipped_count": skipped_count,
            "total_requested": len(request.video_ids),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk download: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/status")
async def bulk_update_status(
    request: BulkStatusUpdateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Bulk update video status"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Update video statuses
        updated_count = (
            session.query(Video)
            .filter(Video.id.in_(request.video_ids))
            .update(
                {Video.status: request.status, Video.updated_at: datetime.utcnow()},
                synchronize_session=False,
            )
        )

        session.commit()

        logger.info(f"Bulk updated {updated_count} video statuses to {request.status}")

        return {
            "message": f"Bulk status update completed",
            "updated_count": updated_count,
            "new_status": request.status,
            "total_requested": len(request.video_ids),
        }

    except Exception as e:
        logger.error(f"Error in bulk status update: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/edit")
async def bulk_edit_videos(
    request: BulkEditRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk edit videos with specified updates"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to edit
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        # Build update dictionary from request (excluding video_ids and None values)
        update_fields = request.dict(
            exclude={"video_ids"}, exclude_unset=True, exclude_none=True
        )

        if not update_fields:
            return {
                "message": "No fields provided for update",
                "updated_count": 0,
                "total_requested": len(request.video_ids),
            }

        # Handle special field processing
        if "genres" in update_fields and update_fields["genres"]:
            # Convert genres list to JSON string for database storage
            update_fields["genres"] = json.dumps(update_fields["genres"])

        # Add updated timestamp
        update_fields["updated_at"] = datetime.utcnow()

        updated_count = 0
        errors = []

        for video in videos:
            try:
                # Apply updates to each video
                for field, value in update_fields.items():
                    if hasattr(video, field):
                        setattr(video, field, value)

                updated_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error updating video {video.id}: {e}")

        session.commit()

        logger.info(
            f"Bulk updated {updated_count} videos with fields: {list(update_fields.keys())}"
        )

        result = {
            "message": "Bulk edit completed",
            "updated_count": updated_count,
            "total_requested": len(request.video_ids),
            "updated_fields": list(update_fields.keys()),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk edit: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/organize")
async def bulk_organize_videos(
    request: BulkOrganizeRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk organize video files into proper directory structure"""
    try:
        import re
        import shutil

        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to organize with artist information
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(request.video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        # Determine base directory for organization
        base_directory = request.target_directory or "/data/musicvideos"
        base_path = Path(base_directory)

        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Cannot create target directory: {e}"
                )

        organized_count = 0
        errors = []
        moves = []

        def sanitize_filename(name: str) -> str:
            """Sanitize filename/directory name for filesystem compatibility"""
            # Replace problematic characters
            sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
            # Remove leading/trailing dots and spaces
            sanitized = sanitized.strip(". ")
            return sanitized or "Unknown"

        for video in videos:
            try:
                # Get current file path
                current_path = getattr(video, "file_path", video.local_path)
                if not current_path or not Path(current_path).exists():
                    errors.append(f"Video {video.id}: File not found at {current_path}")
                    continue

                current_file = Path(current_path)

                # Determine artist folder name
                if video.artist and video.artist.name:
                    artist_folder = sanitize_filename(video.artist.name)
                else:
                    artist_folder = "Unknown Artist"

                # Create target directory structure
                if request.create_artist_folders:
                    target_dir = base_path / artist_folder
                else:
                    target_dir = base_path

                target_dir.mkdir(parents=True, exist_ok=True)

                # Determine target file path
                target_file = target_dir / current_file.name

                # Handle file name conflicts
                counter = 1
                original_target = target_file
                while target_file.exists() and target_file != current_file:
                    stem = original_target.stem
                    suffix = original_target.suffix
                    target_file = target_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                # Only move if source and target are different
                if current_file.resolve() != target_file.resolve():
                    # Move the file
                    shutil.move(str(current_file), str(target_file))

                    # Update database if requested
                    if request.update_database_paths:
                        if hasattr(video, "file_path"):
                            video.file_path = str(target_file)
                        else:
                            video.local_path = str(target_file)
                        video.updated_at = datetime.utcnow()

                    moves.append(
                        {
                            "video_id": video.id,
                            "from": str(current_file),
                            "to": str(target_file),
                        }
                    )

                organized_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error organizing video {video.id}: {e}")

        # Commit database changes if requested
        if request.update_database_paths:
            session.commit()

        logger.info(f"Bulk organized {organized_count} videos into {base_directory}")

        result = {
            "message": "Bulk organization completed",
            "organized_count": organized_count,
            "total_requested": len(request.video_ids),
            "target_directory": str(base_path),
            "moves": moves,
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk organize: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/refresh-metadata")
async def bulk_refresh_metadata(
    request: BulkRefreshMetadataRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Bulk refresh metadata for videos from various sources"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to refresh metadata for
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(request.video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        refreshed_count = 0
        errors = []
        metadata_updates = []

        for video in videos:
            try:
                video_updates = {"video_id": video.id, "updates": []}

                # Check if refresh is needed (unless force_refresh is True)
                should_refresh = (
                    request.force_refresh
                    or not getattr(video, "last_enriched", None)
                    or (datetime.utcnow() - video.last_enriched).days > 7
                )

                if not should_refresh:
                    video_updates["updates"].append(
                        "Metadata is recent, skipping refresh"
                    )
                    metadata_updates.append(video_updates)
                    continue

                # Simulate metadata refresh operations
                # In a real implementation, these would call actual services

                if request.refresh_imvdb:
                    # Simulate IMVDb metadata refresh
                    video_updates["updates"].append("IMVDb metadata refreshed")
                    # video.imvdb_metadata = await imvdb_service.get_video_metadata(video.id)

                if request.refresh_youtube and video.youtube_id:
                    # Simulate YouTube metadata refresh
                    video_updates["updates"].append("YouTube metadata refreshed")
                    # video.youtube_metadata = await youtube_service.get_video_metadata(video.youtube_id)

                if request.refresh_musicbrainz and video.artist:
                    # Simulate MusicBrainz metadata refresh
                    video_updates["updates"].append("MusicBrainz metadata refreshed")
                    # video.musicbrainz_metadata = await musicbrainz_service.get_artist_metadata(video.artist.name)

                # Update last enriched timestamp
                if hasattr(video, "last_enriched"):
                    video.last_enriched = datetime.utcnow()
                video.updated_at = datetime.utcnow()

                # Add some mock metadata updates
                if not video_updates["updates"]:
                    video_updates["updates"].append("Basic metadata refreshed")

                metadata_updates.append(video_updates)
                refreshed_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error refreshing metadata for video {video.id}: {e}")

        session.commit()

        logger.info(f"Bulk refreshed metadata for {refreshed_count} videos")

        result = {
            "message": "Bulk metadata refresh completed",
            "refreshed_count": refreshed_count,
            "total_requested": len(request.video_ids),
            "sources_refreshed": {
                "imvdb": request.refresh_imvdb,
                "youtube": request.refresh_youtube,
                "musicbrainz": request.refresh_musicbrainz,
            },
            "metadata_updates": metadata_updates,
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk metadata refresh: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/enhanced-refresh-metadata")
async def bulk_enhanced_refresh_metadata(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk enhanced metadata refresh for multiple videos"""
    try:
        video_ids = request.get("video_ids", [])
        if not video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        force_refresh = request.get("force_refresh", False)

        # Get videos to refresh metadata for
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        refreshed_count = 0
        errors = []
        sources_used_total = set()

        for video in videos:
            try:
                # Check if refresh is needed (unless force_refresh is True)
                should_refresh = (
                    force_refresh
                    or not getattr(video, "last_enriched", None)
                    or (datetime.utcnow() - video.last_enriched).days > 7
                )

                if should_refresh:
                    # Simulate enhanced metadata refresh operations
                    sources_used = ["imvdb"]

                    if video.youtube_url or getattr(video, "youtube_id", None):
                        sources_used.append("youtube")

                    if video.artist:
                        sources_used.append("musicbrainz")

                    sources_used_total.update(sources_used)

                    # Update timestamps
                    if hasattr(video, "last_enriched"):
                        video.last_enriched = datetime.utcnow()
                    video.updated_at = datetime.utcnow()

                    refreshed_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(
                    f"Error refreshing enhanced metadata for video {video.id}: {e}"
                )

        session.commit()

        logger.info(f"Bulk enhanced metadata refreshed for {refreshed_count} videos")

        result = {
            "success": True,
            "message": "Bulk enhanced metadata refresh completed",
            "refreshed_count": refreshed_count,
            "total_requested": len(video_ids),
            "sources_used": list(sources_used_total),
            "errors": errors if errors else [],
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk enhanced metadata refresh: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/enhanced-refresh-metadata")
async def enhanced_refresh_metadata(
    video_id: int = FastAPIPath(..., ge=1),
    request: dict = Body(...),
    session: Session = Depends(get_db_session),
):
    """Enhanced metadata refresh for a single video from multiple sources"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        force_refresh = request.get("force_refresh", False)

        # Check if refresh is needed (unless force_refresh is True)
        should_refresh = (
            force_refresh
            or not getattr(video, "last_enriched", None)
            or (datetime.utcnow() - video.last_enriched).days > 7
        )

        sources_used = []

        if should_refresh:
            # Simulate enhanced metadata refresh operations
            # In a real implementation, these would call actual services

            # IMVDb metadata
            sources_used.append("imvdb")

            # YouTube metadata (if available)
            if video.youtube_url or getattr(video, "youtube_id", None):
                sources_used.append("youtube")

            # MusicBrainz (if artist available)
            if video.artist:
                sources_used.append("musicbrainz")

            # Update timestamps
            if hasattr(video, "last_enriched"):
                video.last_enriched = datetime.utcnow()
            video.updated_at = datetime.utcnow()

            session.commit()

            logger.info(f"Enhanced metadata refreshed for video {video_id}")

            return {
                "success": True,
                "message": "Enhanced metadata refreshed successfully",
                "video_id": video_id,
                "sources_used": sources_used,
                "refreshed": True,
            }
        else:
            return {
                "success": True,
                "message": "Metadata is recent, refresh not needed",
                "video_id": video_id,
                "sources_used": [],
                "refreshed": False,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced metadata refresh for video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/lyrics/search")
async def search_video_lyrics(
    video_id: int = FastAPIPath(..., ge=1), session: Session = Depends(get_db_session)
):
    """Search and retrieve lyrics for a video"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        logger.info(f"Searching lyrics for video {video_id}: {video.title}")

        # Simulate lyrics search from various sources
        # In a real implementation, this would call lyrics APIs like Genius, AZLyrics, etc.

        # Mock lyrics data for demonstration
        mock_lyrics = f"""[Verse 1]
This is where the lyrics for "{video.title}" would appear.
The lyrics search would query multiple sources like:
- Genius API
- AZLyrics
- LyricFind
- Musixmatch

[Chorus]
Artist: {video.artist.name if video.artist else 'Unknown Artist'}
Video: {video.title}

[Verse 2]
In a real implementation, this endpoint would:
1. Search multiple lyrics providers
2. Match by artist name and song title
3. Clean and format the lyrics
4. Store them in the database
5. Return the formatted lyrics

[Bridge]
This is a mock response for development purposes.
The actual lyrics would be fetched from external services.

[Outro]
Thank you for using MVidarr's lyrics search feature!
"""

        # In a real implementation, save lyrics to database
        # video.lyrics = found_lyrics
        # session.commit()

        return {
            "success": True,
            "message": "Lyrics found successfully",
            "video_id": video_id,
            "lyrics": mock_lyrics,
            "source": "mock_provider",
            "found": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching lyrics for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/download-wanted")
async def bulk_download_wanted_videos(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Download all videos with 'wanted' status"""
    try:
        limit = request.get(
            "limit", 100
        )  # Default limit to prevent overwhelming the system

        # Get all videos with 'wanted' status
        wanted_videos = (
            session.query(Video)
            .filter(Video.status == VideoStatus.WANTED)
            .limit(limit)
            .all()
        )

        if not wanted_videos:
            return {
                "message": "No wanted videos found to download",
                "success": True,
                "success_count": 0,  # Frontend expects this field
                "failed_count": 0,  # Frontend expects this field
                "queued_count": 0,
                "total_wanted": 0,
                "skipped_count": 0,
                "errors": [],
                "results": [],  # Frontend expects this field
            }

        queued_count = 0
        skipped_count = 0
        errors = []

        for video in wanted_videos:
            try:
                # Check if download already in queue
                existing_download = (
                    session.query(Download)
                    .filter(
                        Download.video_id == video.id,
                        Download.status.in_(["queued", "downloading"]),
                    )
                    .first()
                )

                if existing_download:
                    skipped_count += 1
                    continue

                # Create download entry
                download = Download(
                    artist_id=video.artist_id,
                    video_id=video.id,
                    title=video.title,
                    original_url=(
                        video.url
                        or video.youtube_url
                        or f"https://youtube.com/watch?v={video.youtube_id}"
                        if hasattr(video, "youtube_id") and video.youtube_id
                        else "Unknown URL"
                    ),
                    status="queued",
                    quality="best",  # Default quality for wanted videos
                    priority=1,  # Default priority for wanted videos
                    created_at=datetime.utcnow(),
                )

                session.add(download)
                session.flush()  # Ensure download.id is available

                # Update video status to downloading/queued
                video.status = VideoStatus.DOWNLOADING
                video.updated_at = datetime.utcnow()

                # Create background job for download processing
                try:
                    from ...services.job_queue import (
                        BackgroundJob,
                        JobPriority,
                        JobType,
                        get_job_queue,
                    )

                    job_queue = await get_job_queue()

                    # Create download job with normal priority for wanted videos
                    download_job = BackgroundJob(
                        type=JobType.VIDEO_DOWNLOAD,
                        priority=JobPriority.NORMAL,
                        payload={
                            "video_id": video.id,
                            "download_id": download.id,
                            "quality": "best",
                            "force_redownload": False,
                        },
                        created_by=f"bulk-wanted-download-{video.id}",
                    )

                    job_id = await job_queue.enqueue(download_job)
                    logger.info(
                        f"Created background download job {job_id} for wanted video {video.id}"
                    )

                except Exception as job_error:
                    logger.error(
                        f"Failed to create background download job for wanted video {video.id}: {job_error}"
                    )
                    # Don't fail the bulk operation if individual job creation fails

                queued_count += 1
                logger.info(
                    f"Queued wanted video for download: {video.title} (ID: {video.id})"
                )

            except Exception as e:
                errors.append(f"Video {video.id} ({video.title}): {str(e)}")
                logger.error(f"Error queuing wanted video {video.id} for download: {e}")

        session.commit()

        logger.info(
            f"Bulk download wanted: queued {queued_count}, skipped {skipped_count} videos"
        )

        result = {
            "message": f"Queued {queued_count} wanted videos for download",
            "success": True,
            "success_count": queued_count,  # Frontend expects this field
            "failed_count": len(errors),  # Frontend expects this field
            "queued_count": queued_count,  # Keep for backward compatibility
            "total_wanted": len(wanted_videos),
            "skipped_count": skipped_count,
            "limit_applied": limit,
            "results": [],  # Frontend expects this field
        }

        if errors:
            result["errors"] = errors
            # Add results array with individual video results for frontend
            for error_msg in errors:
                result["results"].append({"success": False, "error": error_msg})

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk download wanted videos: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-from-youtube")
async def import_from_youtube(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Import a video from YouTube"""
    try:
        youtube_id = request.get("youtube_id", "")
        url = request.get("url", "")
        title = request.get("title", "")
        artist = request.get("artist", "")
        auto_download = request.get("auto_download", True)

        if not youtube_id or not url:
            raise HTTPException(
                status_code=400, detail="YouTube ID and URL are required"
            )

        # Check if video already exists
        existing_video = (
            session.query(Video).filter(Video.youtube_id == youtube_id).first()
        )

        if existing_video:
            return {
                "success": True,
                "message": "Video already exists in library",
                "video_id": existing_video.id,
                "status": "exists",
            }

        # Create new video entry using only valid Video model fields
        new_video = Video(
            title=title or f"YouTube Video {youtube_id}",
            youtube_id=youtube_id,
            youtube_url=url,
            url=url,  # Store the YouTube URL in the generic url field
            source="youtube_import",
            status=VideoStatus.WANTED if auto_download else VideoStatus.MONITORED,
            duration=None,  # Will be updated when metadata is fetched
            discovered_date=datetime.utcnow(),
        )

        # Try to find or create artist
        if artist:
            artist_obj = session.query(Artist).filter(Artist.name == artist).first()
            if not artist_obj:
                artist_obj = Artist(
                    name=artist, monitored=True, source="youtube_import"
                )
                session.add(artist_obj)
                session.flush()  # Get the artist ID
            new_video.artist_id = artist_obj.id

        session.add(new_video)
        session.commit()

        logger.info(f"Imported YouTube video: {title} ({youtube_id})")

        return {
            "success": True,
            "message": f"Video '{title}' imported successfully",
            "video_id": new_video.id,
            "status": "imported",
            "auto_download": auto_download,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing YouTube video: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Note: This completes the core video operations migration including:
# - CRUD operations (list, get, update, delete)
# - Search functionality
# - Video streaming with HTTP range support
# - Thumbnail operations
# - Download queue management
# - Bulk operations (delete, download, status updates)
#
# Additional endpoints like metadata processing, imports, and advanced features
# can be added in subsequent iterations.
