"""
Pydantic Models for FastAPI Videos API

This module contains all Pydantic model definitions used for request/response
validation in the FastAPI videos endpoints. These models ensure type safety,
validation, and automatic API documentation.

Models are organized by functionality:
- Response Models: VideoResponse
- Request Models: VideoUpdateRequest, VideoSearchRequest, VideoListRequest
- Bulk Operation Models: BulkVideoRequest and its subclasses
- Specialized Models: ThumbnailSearchRequest, VideoStatusUpdateRequest
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.database.models import VideoStatus

# ========================================================================================
# RESPONSE MODELS
# ========================================================================================


class VideoResponse(BaseModel):
    """
    Standard video response model for API endpoints.

    Includes all video metadata, relationships, and file information.
    Used by GET endpoints to return video data to clients.
    """

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
    quality: Optional[str] = None
    video_metadata: Optional[Dict[str, Any]] = None
    lyrics: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    genres: Optional[List[str]] = []
    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


# ========================================================================================
# SINGLE VIDEO REQUEST MODELS
# ========================================================================================


class VideoUpdateRequest(BaseModel):
    """
    Request model for updating video metadata.

    All fields are optional - only provided fields will be updated.
    Supports updating by artist_name as an alternative to artist_id.
    """

    title: Optional[str] = None
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None  # Allow updating by artist name
    url: Optional[str] = None
    youtube_url: Optional[str] = None
    status: Optional[str] = None
    genres: Optional[List[str]] = None


class VideoSearchRequest(BaseModel):
    """
    Request model for searching videos.

    Simple search query that searches across video titles and artist names.
    """

    query: Optional[str] = None


class VideoListRequest(BaseModel):
    """
    Request model for paginated video listing.

    Supports pagination, sorting, and ordering of results.
    """

    limit: int = Field(default=50, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc")


class VideoStatusUpdateRequest(BaseModel):
    """
    Request model for updating video status.

    Enforces valid status values through regex pattern validation.
    Supports both uppercase and lowercase status names.
    """

    status: str = Field(
        ...,
        pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED|wanted|downloading|downloaded|ignored|failed|monitored)$",
    )


# ========================================================================================
# THUMBNAIL MODELS
# ========================================================================================


class ThumbnailSearchRequest(BaseModel):
    """
    Request model for searching thumbnails from external sources.

    Supports multiple sources (YouTube, IMVDb, Google) with automatic source detection.
    """

    query: Optional[str] = None
    source: str = Field(default="auto", pattern="^(auto|youtube|imvdb|google)$")


# ========================================================================================
# BULK OPERATION MODELS
# ========================================================================================


class BulkVideoRequest(BaseModel):
    """
    Base model for bulk video operations.

    All bulk operation models inherit from this base class.
    Requires at least one video ID to be provided.
    """

    video_ids: List[int] = Field(..., min_items=1)


class BulkDeleteRequest(BulkVideoRequest):
    """
    Request model for bulk video deletion.

    Inherits video_ids from BulkVideoRequest.
    """

    pass


class BulkDownloadRequest(BulkVideoRequest):
    """
    Request model for bulk video downloads.

    Inherits video_ids from BulkVideoRequest.
    """

    pass


class BulkStatusUpdateRequest(BulkVideoRequest):
    """
    Request model for bulk status updates.

    Updates the status of multiple videos to the same new status.
    """

    status: VideoStatus


class BulkEditRequest(BulkVideoRequest):
    """
    Request model for bulk video editing.

    Allows updating multiple fields across multiple videos simultaneously.
    All fields are optional - only provided fields will be updated.
    """

    title: Optional[str] = None
    artist_id: Optional[int] = None
    url: Optional[str] = None
    youtube_url: Optional[str] = None
    status: Optional[str] = None
    genres: Optional[List[str]] = None


class BulkOrganizeRequest(BulkVideoRequest):
    """
    Request model for bulk video file organization.

    Organizes video files into a directory structure, optionally creating
    artist folders and updating database paths.
    """

    target_directory: Optional[str] = None
    create_artist_folders: bool = True
    update_database_paths: bool = True


class BulkRefreshMetadataRequest(BulkVideoRequest):
    """
    Request model for bulk metadata refresh.

    Refreshes metadata from multiple sources (IMVDb, YouTube, MusicBrainz).
    Supports forced refresh to bypass caching.
    """

    refresh_imvdb: bool = True
    refresh_youtube: bool = True
    refresh_musicbrainz: bool = False
    force_refresh: bool = False
