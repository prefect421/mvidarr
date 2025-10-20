"""
FastAPI YouTube Playlist Management Router
Migrated from Flask src/api/youtube_playlists.py - YouTube playlist monitoring and management
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.services.youtube_playlist_service import youtube_playlist_service

logger = logging.getLogger("mvidarr.fastapi.youtube_playlists")

router = APIRouter(
    prefix="/api/youtube/playlists",
    tags=["youtube-playlists"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class PlaylistMonitorRequest(BaseModel):
    """Playlist monitor creation request"""

    playlist_url: str = Field(..., min_length=10, max_length=500)
    name: Optional[str] = Field(None, max_length=200)
    auto_download: bool = Field(default=True)
    quality: str = Field(
        default="720p", pattern="^(144p|240p|360p|480p|720p|1080p|best)$"
    )
    keywords: List[str] = Field(default_factory=list, max_items=20)


class PlaylistMonitorUpdate(BaseModel):
    """Playlist monitor update request"""

    name: Optional[str] = Field(None, max_length=200)
    auto_download: Optional[bool] = None
    quality: Optional[str] = Field(
        None, pattern="^(144p|240p|360p|480p|720p|1080p|best)$"
    )
    keywords: Optional[List[str]] = Field(None, max_items=20)


class PlaylistUrlRequest(BaseModel):
    """Playlist URL request for validation/info"""

    playlist_url: str = Field(..., min_length=10, max_length=500)


class PlaylistPreviewRequest(BaseModel):
    """Playlist preview request"""

    playlist_url: str = Field(..., min_length=10, max_length=500)
    max_results: int = Field(default=20, ge=1, le=50)


class PlaylistInfoResponse(BaseModel):
    """Playlist information response"""

    playlist_id: str = Field(..., alias="id")
    title: str
    description: Optional[str] = None
    channel_title: str
    item_count: int
    thumbnail_url: Optional[str] = None
    published_at: Optional[str] = None
    valid: bool = True

    class Config:
        populate_by_name = True  # Allow using both 'id' and 'playlist_id'


class PlaylistMonitorResponse(BaseModel):
    """Playlist monitor response"""

    id: int
    name: str
    playlist_id: str
    playlist_url: str
    auto_download: bool
    quality: str
    keywords: List[str]
    last_sync: Optional[str] = None
    video_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VideoDetails(BaseModel):
    """Video details in playlist"""

    video_id: str
    title: str
    description: Optional[str] = None
    channel_title: str
    published_at: Optional[str] = None
    duration: Optional[str] = None
    thumbnail_url: Optional[str] = None
    view_count: Optional[int] = None


class PlaylistPreviewResponse(BaseModel):
    """Playlist preview response"""

    playlist_info: PlaylistInfoResponse
    videos: List[VideoDetails]
    video_count: int
    total_videos: int


class YouTubeStatusResponse(BaseModel):
    """YouTube integration status"""

    configured: bool
    api_key: Optional[str] = None
    metube_url: Optional[str] = None


# ========================================================================================
# YOUTUBE PLAYLIST MONITORING ENDPOINTS
# ========================================================================================


@router.get("/", response_model=Dict[str, Any])
async def get_monitored_playlists(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get all monitored playlists"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting monitored playlists for user {current_user.get('username')}"
        )

        playlists = youtube_playlist_service.get_monitored_playlists()

        return {"playlists": playlists, "count": len(playlists)}

    except Exception as e:
        logger.error(f"Failed to get monitored playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_playlist_monitor(
    monitor_request: PlaylistMonitorRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Create a new playlist monitor"""
    try:
        user_id = current_user.get("user_id", 1)

        # Validate YouTube API key
        if not youtube_playlist_service.api_key:
            raise HTTPException(
                status_code=400,
                detail="YouTube API key not configured. Please set YOUTUBE_API_KEY environment variable.",
            )

        logger.info(
            f"Creating playlist monitor for URL '{monitor_request.playlist_url}' by user {current_user.get('username')}"
        )

        result = youtube_playlist_service.create_playlist_monitor(
            playlist_url=monitor_request.playlist_url,
            name=monitor_request.name,
            auto_download=monitor_request.auto_download,
            quality=monitor_request.quality,
            keywords=monitor_request.keywords,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to create playlist monitor"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create playlist monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/{monitor_id}")
async def get_playlist_monitor(
    monitor_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get a specific playlist monitor"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting playlist monitor {monitor_id} for user {current_user.get('username')}"
        )

        playlists = youtube_playlist_service.get_monitored_playlists()
        playlist = next((p for p in playlists if p["id"] == monitor_id), None)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist monitor not found")

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playlist monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/monitor/{monitor_id}")
async def update_playlist_monitor(
    monitor_id: int,
    update_request: PlaylistMonitorUpdate,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Update playlist monitor settings"""
    try:
        user_id = current_user.get("user_id", 1)

        # Filter out None values and convert to dict
        updates = {k: v for k, v in update_request.dict().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        logger.info(
            f"Updating playlist monitor {monitor_id} for user {current_user.get('username')}"
        )

        result = youtube_playlist_service.update_playlist_monitor(monitor_id, updates)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update playlist monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/monitor/{monitor_id}")
async def delete_playlist_monitor(
    monitor_id: int,
    delete_videos: bool = Query(default=False),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Delete playlist monitor"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Deleting playlist monitor {monitor_id} (delete_videos={delete_videos}) for user {current_user.get('username')}"
        )

        result = youtube_playlist_service.delete_playlist_monitor(
            monitor_id, delete_videos
        )

        return result

    except Exception as e:
        logger.error(f"Failed to delete playlist monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# PLAYLIST SYNCHRONIZATION ENDPOINTS
# ========================================================================================


@router.post("/monitor/{monitor_id}/sync")
async def sync_playlist(
    monitor_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Sync a specific playlist"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get playlist ID from monitor
        playlists = youtube_playlist_service.get_monitored_playlists()
        playlist = next((p for p in playlists if p["id"] == monitor_id), None)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist monitor not found")

        logger.info(
            f"Syncing playlist '{playlist['name']}' (ID: {monitor_id}) for user {current_user.get('username')}"
        )

        result = youtube_playlist_service.sync_playlist_videos(playlist["playlist_id"])

        return {
            "success": True,
            "message": f"Synced playlist '{playlist['name']}'",
            "results": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-all")
async def sync_all_playlists(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Sync all monitored playlists"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Syncing all playlists for user {current_user.get('username')}")

        result = youtube_playlist_service.sync_all_playlists()

        return {
            "success": True,
            "message": f"Synced {result['synced_playlists']} playlists with {result['total_new_videos']} new videos",
            "results": result,
        }

    except Exception as e:
        logger.error(f"Failed to sync all playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_playlists(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Sync all monitored playlists for settings page"""
    try:
        user_id = current_user.get("user_id", 1)

        # Check if API key is configured
        if not youtube_playlist_service.api_key:
            raise HTTPException(
                status_code=400,
                detail="YouTube API key not configured. Please set youtube_api_key in settings.",
            )

        logger.info(
            f"Syncing playlists from settings page for user {current_user.get('username')}"
        )

        # Sync all playlists
        result = youtube_playlist_service.sync_all_playlists()

        return {
            "success": True,
            "synced_count": result.get("synced_playlists", 0),
            "new_videos": result.get("total_new_videos", 0),
            "message": f"Synced {result.get('synced_playlists', 0)} playlists with {result.get('total_new_videos', 0)} new videos",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# PLAYLIST UTILITY ENDPOINTS
# ========================================================================================


@router.post("/extract-id")
async def extract_playlist_id(
    url_request: PlaylistUrlRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Extract playlist ID from YouTube URL"""
    try:
        user_id = current_user.get("user_id", 1)

        playlist_id = youtube_playlist_service.extract_playlist_id(
            url_request.playlist_url
        )

        if not playlist_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube playlist URL")

        return {"playlist_id": playlist_id, "valid": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract playlist ID: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/info", response_model=Dict[str, Any])
async def get_playlist_info(
    url_request: PlaylistUrlRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get playlist information without creating monitor"""
    try:
        user_id = current_user.get("user_id", 1)

        if not youtube_playlist_service.api_key:
            raise HTTPException(
                status_code=400, detail="YouTube API key not configured"
            )

        playlist_id = youtube_playlist_service.extract_playlist_id(
            url_request.playlist_url
        )

        if not playlist_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube playlist URL")

        logger.info(
            f"Getting playlist info for ID '{playlist_id}' for user {current_user.get('username')}"
        )

        playlist_info = youtube_playlist_service.get_playlist_info(playlist_id)

        if not playlist_info:
            raise HTTPException(
                status_code=404, detail="Playlist not found or is private"
            )

        return {"playlist_info": playlist_info, "valid": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playlist info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview", response_model=PlaylistPreviewResponse)
async def preview_playlist_videos(
    preview_request: PlaylistPreviewRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Preview videos in a playlist without creating monitor"""
    try:
        user_id = current_user.get("user_id", 1)

        if not youtube_playlist_service.api_key:
            raise HTTPException(
                status_code=400, detail="YouTube API key not configured"
            )

        playlist_id = youtube_playlist_service.extract_playlist_id(
            preview_request.playlist_url
        )

        if not playlist_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube playlist URL")

        logger.info(
            f"Previewing playlist '{playlist_id}' for user {current_user.get('username')}"
        )

        # Get playlist info
        playlist_info = youtube_playlist_service.get_playlist_info(playlist_id)

        if not playlist_info:
            raise HTTPException(
                status_code=404, detail="Playlist not found or is private"
            )

        # Get videos
        videos = youtube_playlist_service.get_playlist_videos(
            playlist_id, preview_request.max_results
        )

        # Get video details
        video_ids = [v["video_id"] for v in videos if v["video_id"]]
        video_details = youtube_playlist_service.get_video_details(video_ids)

        # Combine video data with details
        for video in videos:
            video_id = video["video_id"]
            if video_id in video_details:
                video.update(video_details[video_id])

        return PlaylistPreviewResponse(
            playlist_info=PlaylistInfoResponse(**playlist_info),
            videos=[VideoDetails(**video) for video in videos],
            video_count=len(videos),
            total_videos=playlist_info["item_count"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview playlist videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# YOUTUBE INTEGRATION STATUS AND TESTING
# ========================================================================================


@router.get("/status", response_model=YouTubeStatusResponse)
async def get_youtube_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get YouTube integration status"""
    try:
        user_id = current_user.get("user_id", 1)

        configured = youtube_playlist_service.api_key is not None

        return YouTubeStatusResponse(
            configured=configured,
            api_key=(
                youtube_playlist_service.api_key[:8] + "..." if configured else None
            ),
            metube_url=youtube_playlist_service.metube_url,
        )

    except Exception as e:
        logger.error(f"Failed to get YouTube status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_youtube_integration(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Test YouTube API connection"""
    try:
        user_id = current_user.get("user_id", 1)

        # Check if API key is configured
        if not youtube_playlist_service.api_key:
            raise HTTPException(
                status_code=400,
                detail="YouTube API key not configured. Please set youtube_api_key in settings.",
            )

        logger.info(
            f"Testing YouTube API connection for user {current_user.get('username')}"
        )

        # Test API connection with a simple request
        import requests

        url = f"{youtube_playlist_service.base_url}/search"
        params = {
            "part": "snippet",
            "q": "test",
            "type": "playlist",
            "maxResults": 1,
            "key": youtube_playlist_service.api_key,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        return {
            "status": "success",
            "message": "YouTube API connection successful",
            "api_quota_used": True,
            "response_items": len(data.get("items", [])),
        }

    except requests.RequestException as e:
        logger.error(f"YouTube API test failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"YouTube API connection failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"YouTube integration test failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"YouTube integration test failed: {str(e)}"
        )


# ========================================================================================
# ROUTE ALIASES FOR FRONTEND COMPATIBILITY
# ========================================================================================
# These aliases allow frontend to use /{id} pattern instead of /monitor/{id}
# IMPORTANT: These MUST be defined last, after all specific routes (/status, /preview, etc.)
# to avoid catching those paths as monitor IDs


@router.get("/{monitor_id}")
async def get_playlist_monitor_alias(
    monitor_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get a specific playlist monitor (alias route for frontend)"""
    return await get_playlist_monitor(monitor_id, current_user, session)


@router.put("/{monitor_id}")
async def update_playlist_monitor_alias(
    monitor_id: int,
    update_request: PlaylistMonitorUpdate,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Update playlist monitor settings (alias route for frontend)"""
    return await update_playlist_monitor(
        monitor_id, update_request, current_user, session
    )


@router.delete("/{monitor_id}")
async def delete_playlist_monitor_alias(
    monitor_id: int,
    delete_videos: bool = Query(default=False),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Delete playlist monitor (alias route for frontend)"""
    return await delete_playlist_monitor(
        monitor_id, delete_videos, current_user, session
    )


@router.post("/{monitor_id}/sync")
async def sync_playlist_alias(
    monitor_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Sync a specific playlist (alias route for frontend)"""
    return await sync_playlist(monitor_id, current_user, session)
