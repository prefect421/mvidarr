"""
Playlist-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all playlist-related API operations.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, validator

from .base import BaseRequest, BaseResponse, PaginationRequest
from .common import MetadataMixin, TimestampMixin


class PlaylistType(str, Enum):
    """Playlist type options"""

    STATIC = "static"
    DYNAMIC = "dynamic"
    SMART = "smart"


class PlaylistPrivacy(str, Enum):
    """Playlist privacy levels"""

    PUBLIC = "public"
    PRIVATE = "private"
    SHARED = "shared"


class PlaylistSortOrder(str, Enum):
    """Playlist sort order options"""

    MANUAL = "manual"
    DATE_ADDED = "date_added"
    TITLE = "title"
    ARTIST = "artist"
    DURATION = "duration"
    RANDOM = "random"


class PlaylistEntryResponse(BaseResponse, TimestampMixin):
    """Individual playlist entry information"""

    id: int = Field(description="Entry ID")
    playlist_id: int = Field(description="Parent playlist ID")
    video_id: int = Field(description="Video ID")
    video_title: str = Field(description="Video title")
    artist_name: Optional[str] = Field(None, description="Artist name")
    position: int = Field(ge=0, description="Position in playlist")
    added_by_user_id: Optional[int] = Field(
        None, description="User who added the video"
    )
    duration: Optional[int] = Field(None, ge=0, description="Video duration in seconds")
    thumbnail_url: Optional[str] = Field(None, description="Video thumbnail URL")


class PlaylistResponse(BaseResponse, TimestampMixin, MetadataMixin):
    """Complete playlist information response"""

    id: int = Field(description="Unique playlist identifier")
    name: str = Field(description="Playlist name")
    description: Optional[str] = Field(None, description="Playlist description")
    playlist_type: PlaylistType = Field(description="Type of playlist")
    privacy: PlaylistPrivacy = Field(description="Privacy level")
    sort_order: PlaylistSortOrder = Field(description="How entries are sorted")

    # Ownership and access
    created_by_user_id: int = Field(description="Creator user ID")
    created_by_username: Optional[str] = Field(None, description="Creator username")
    is_system_playlist: bool = Field(
        default=False, description="Whether this is a system playlist"
    )

    # Statistics
    video_count: int = Field(
        default=0, ge=0, description="Number of videos in playlist"
    )
    total_duration: int = Field(
        default=0, ge=0, description="Total duration in seconds"
    )
    view_count: int = Field(default=0, ge=0, description="Number of times viewed")

    # Dynamic playlist filters (for smart playlists)
    filters: Optional[Dict[str, Any]] = Field(
        None, description="Filter criteria for dynamic playlists"
    )
    auto_update: bool = Field(
        default=False, description="Whether playlist updates automatically"
    )
    max_videos: Optional[int] = Field(
        None, ge=1, description="Maximum videos for dynamic playlists"
    )

    # Display
    thumbnail_url: Optional[str] = Field(None, description="Playlist cover image URL")
    color_scheme: Optional[str] = Field(None, description="UI color scheme")

    @validator("filters")
    def validate_filters(cls, v, values):
        """Validate dynamic playlist filters"""
        if v and values.get("playlist_type") == PlaylistType.STATIC:
            raise ValueError("Static playlists cannot have filters")
        return v


class PlaylistCreateRequest(BaseRequest):
    """Request to create a new playlist"""

    name: str = Field(..., min_length=1, max_length=200, description="Playlist name")
    description: Optional[str] = Field(
        None, max_length=1000, description="Playlist description"
    )
    playlist_type: PlaylistType = Field(
        default=PlaylistType.STATIC, description="Type of playlist to create"
    )
    privacy: PlaylistPrivacy = Field(
        default=PlaylistPrivacy.PRIVATE, description="Playlist privacy level"
    )
    sort_order: PlaylistSortOrder = Field(
        default=PlaylistSortOrder.MANUAL, description="Initial sort order"
    )

    # For dynamic playlists
    filters: Optional[Dict[str, Any]] = Field(
        None, description="Filter criteria for dynamic playlists"
    )
    auto_update: bool = Field(default=False, description="Enable automatic updates")
    max_videos: Optional[int] = Field(
        None, ge=1, le=10000, description="Maximum videos (1-10000)"
    )

    @validator("name")
    def validate_name(cls, v):
        """Clean playlist name"""
        return v.strip()

    @validator("filters")
    def validate_dynamic_filters(cls, v, values):
        """Ensure filters are only set for dynamic playlists"""
        playlist_type = values.get("playlist_type")
        if v and playlist_type == PlaylistType.STATIC:
            raise ValueError("Static playlists cannot have filters")
        if not v and playlist_type in [PlaylistType.DYNAMIC, PlaylistType.SMART]:
            raise ValueError("Dynamic and smart playlists require filters")
        return v


class PlaylistUpdateRequest(BaseRequest):
    """Request to update playlist information"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    privacy: Optional[PlaylistPrivacy] = None
    sort_order: Optional[PlaylistSortOrder] = None
    filters: Optional[Dict[str, Any]] = None
    auto_update: Optional[bool] = None
    max_videos: Optional[int] = Field(None, ge=1, le=10000)
    color_scheme: Optional[str] = Field(None, max_length=20)

    @validator("name")
    def validate_name(cls, v):
        """Clean name if provided"""
        return v.strip() if v else None


class PlaylistAddVideoRequest(BaseRequest):
    """Request to add videos to a playlist"""

    video_ids: List[int] = Field(
        ..., min_items=1, max_items=100, description="Video IDs to add (1-100 videos)"
    )
    position: Optional[int] = Field(
        None, ge=0, description="Position to insert videos (default: end of playlist)"
    )

    @validator("video_ids")
    def validate_unique_videos(cls, v):
        """Ensure video IDs are unique"""
        return list(dict.fromkeys(v))  # Remove duplicates while preserving order


class PlaylistReorderRequest(BaseRequest):
    """Request to reorder videos in a playlist"""

    entry_id: int = Field(..., ge=1, description="Playlist entry ID to move")
    new_position: int = Field(..., ge=0, description="New position for the entry")


class PlaylistRemoveVideosRequest(BaseRequest):
    """Request to remove videos from a playlist"""

    entry_ids: List[int] = Field(
        ..., min_items=1, max_items=100, description="Playlist entry IDs to remove"
    )

    @validator("entry_ids")
    def validate_unique_entries(cls, v):
        """Ensure entry IDs are unique"""
        return list(dict.fromkeys(v))


class DynamicPlaylistRequest(BaseRequest):
    """Request to create or update dynamic playlist filters"""

    filters: Dict[str, Any] = Field(
        ..., description="Filter criteria for dynamic playlist"
    )
    max_videos: int = Field(
        default=100, ge=1, le=10000, description="Maximum number of videos in playlist"
    )
    sort_by: str = Field(default="created_at", description="Field to sort videos by")
    sort_order: str = Field(
        default="desc", pattern="^(asc|desc)$", description="Sort order"
    )
    auto_update_interval: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="Update interval in seconds (5min-24hr)",
    )

    @validator("filters")
    def validate_filter_structure(cls, v):
        """Validate filter structure"""
        allowed_filters = {
            "artist_ids",
            "genres",
            "status",
            "year_from",
            "year_to",
            "duration_min",
            "duration_max",
            "keywords",
            "tags",
        }

        for key in v.keys():
            if key not in allowed_filters:
                raise ValueError(f"Invalid filter: {key}")

        return v


class PlaylistFilterUpdateRequest(BaseRequest):
    """Request to update dynamic playlist filters"""

    filters: Dict[str, Any] = Field(..., description="New filter criteria")
    apply_immediately: bool = Field(
        default=True, description="Apply filters and update playlist immediately"
    )


class PlaylistSearchRequest(BaseRequest, PaginationRequest):
    """Request to search playlists"""

    query: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Search in playlist name and description",
    )
    playlist_type: Optional[PlaylistType] = Field(
        None, description="Filter by playlist type"
    )
    privacy: Optional[PlaylistPrivacy] = Field(
        None, description="Filter by privacy level"
    )
    created_by_user_id: Optional[int] = Field(
        None, ge=1, description="Filter by creator user ID"
    )
    min_videos: Optional[int] = Field(
        None, ge=0, description="Minimum number of videos"
    )
    max_videos: Optional[int] = Field(
        None, ge=0, description="Maximum number of videos"
    )

    @validator("max_videos")
    def validate_video_range(cls, v, values):
        """Ensure max > min"""
        if v and "min_videos" in values and values["min_videos"]:
            if v <= values["min_videos"]:
                raise ValueError("max_videos must be greater than min_videos")
        return v


class PlaylistListResponse(BaseResponse):
    """Response containing list of playlists"""

    playlists: List[PlaylistResponse] = Field(description="List of playlists")
    pagination: Dict[str, Any] = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        playlists: List[PlaylistResponse],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create paginated playlist response"""
        has_more = offset + limit < total_count

        return cls(
            playlists=playlists,
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(playlists),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class PlaylistEntriesResponse(BaseResponse):
    """Response containing playlist entries"""

    playlist_id: int = Field(description="Playlist ID")
    playlist_name: str = Field(description="Playlist name")
    entries: List[PlaylistEntryResponse] = Field(description="Playlist entries")
    pagination: Dict[str, Any] = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        playlist_id: int,
        playlist_name: str,
        entries: List[PlaylistEntryResponse],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create paginated playlist entries response"""
        has_more = offset + limit < total_count

        return cls(
            playlist_id=playlist_id,
            playlist_name=playlist_name,
            entries=entries,
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(entries),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class PlaylistStatsResponse(BaseResponse):
    """Response containing playlist statistics"""

    total_playlists: int = Field(ge=0)
    by_type: Dict[str, int] = Field(description="Playlist count by type")
    by_privacy: Dict[str, int] = Field(description="Playlist count by privacy level")
    most_popular: List[Dict[str, Any]] = Field(description="Most viewed playlists")
    recently_created: List[Dict[str, Any]] = Field(
        description="Recently created playlists"
    )
    total_entries: int = Field(
        ge=0, description="Total playlist entries across all playlists"
    )


# Export all playlist-related models
__all__ = [
    "PlaylistType",
    "PlaylistPrivacy",
    "PlaylistSortOrder",
    "PlaylistEntryResponse",
    "PlaylistResponse",
    "PlaylistCreateRequest",
    "PlaylistUpdateRequest",
    "PlaylistAddVideoRequest",
    "PlaylistReorderRequest",
    "PlaylistRemoveVideosRequest",
    "DynamicPlaylistRequest",
    "PlaylistFilterUpdateRequest",
    "PlaylistSearchRequest",
    "PlaylistListResponse",
    "PlaylistEntriesResponse",
    "PlaylistStatsResponse",
]
