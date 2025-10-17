"""
FastAPI Playlists Models Module
Pydantic models and utility functions for playlist operations
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.database.models import Playlist
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.playlists_models")


# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class PlaylistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    user_id: int
    username: Optional[str] = None
    is_public: bool = False
    is_featured: bool = False
    is_dynamic: bool = False
    video_count: int = 0
    total_duration: int = 0
    thumbnail_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    can_modify: bool = False

    class Config:
        from_attributes = True


class PlaylistCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_public: bool = False
    is_featured: bool = False


class PlaylistUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None


class PlaylistEntryResponse(BaseModel):
    id: int
    playlist_id: int
    video_id: int
    position: int
    added_at: Optional[str] = None
    video: Optional[Dict[str, Any]] = None


class AddVideoRequest(BaseModel):
    video_ids: List[int] = Field(..., min_items=1)
    position: Optional[int] = None


class ReorderVideoRequest(BaseModel):
    entry_id: int
    new_position: int = Field(..., ge=1)


class BulkDeleteRequest(BaseModel):
    playlist_ids: List[int] = Field(..., min_items=1)


class DynamicPlaylistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    filter_criteria: Dict[str, Any] = Field(..., min_items=1)
    is_public: bool = False
    auto_update: bool = True


class FilterUpdateRequest(BaseModel):
    filter_criteria: Dict[str, Any] = Field(..., min_items=1)


class DynamicPlaylistPreviewRequest(BaseModel):
    filter_criteria: Dict[str, Any] = Field(..., min_items=1)
    limit: int = Field(default=50, ge=1, le=100)


# ========================================================================================
# UTILITY FUNCTIONS
# ========================================================================================


def playlist_to_dict(
    playlist: Playlist, include_entries: bool = False, user=None
) -> Dict[str, Any]:
    """Convert playlist to dictionary representation"""
    # Check if playlist is dynamic by calling the method or checking the type
    try:
        is_dynamic = (
            playlist.is_dynamic()
            if callable(getattr(playlist, "is_dynamic", None))
            else False
        )
    except:
        is_dynamic = False

    # Determine if user can modify playlist
    # In single-user mode, authenticated users can modify all playlists
    can_modify = False
    if user:
        # User is authenticated - allow modification
        can_modify = True

    data = {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "user_id": playlist.user_id,
        "username": playlist.user.username if playlist.user else None,
        "is_public": playlist.is_public,
        "is_featured": playlist.is_featured,
        "is_dynamic": is_dynamic,
        "filter_criteria": (
            playlist.filter_criteria if hasattr(playlist, "filter_criteria") else None
        ),
        "video_count": getattr(playlist, "video_count", 0),
        "total_duration": getattr(playlist, "total_duration", 0),
        "thumbnail_url": (
            f"/api/playlists/{playlist.id}/thumbnail" if playlist.id else None
        ),
        "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
        "updated_at": playlist.updated_at.isoformat() if playlist.updated_at else None,
        "can_modify": can_modify,
    }

    if include_entries and hasattr(playlist, "entries"):
        data["entries"] = [
            {
                "id": entry.id,
                "video_id": entry.video_id,
                "position": entry.position,
                "added_at": entry.added_at.isoformat() if entry.added_at else None,
                "video": (
                    {
                        "id": entry.video.id,
                        "title": entry.video.title,
                        "artist_name": (
                            entry.video.artist.name if entry.video.artist else None
                        ),
                        "duration": entry.video.duration,
                        "thumbnail_url": f"/api/videos/{entry.video.id}/thumbnail",
                        "local_path": entry.video.local_path,
                        "status": (
                            entry.video.status.value
                            if hasattr(entry.video.status, "value")
                            else entry.video.status
                        ),
                        "quality": entry.video.quality,
                        "year": entry.video.year,
                        "release_date": (
                            entry.video.release_date.isoformat()
                            if entry.video.release_date
                            else None
                        ),
                        "youtube_id": entry.video.youtube_id,
                        "youtube_url": entry.video.youtube_url,
                    }
                    if entry.video
                    else None
                ),
            }
            for entry in playlist.entries
        ]

    return data
