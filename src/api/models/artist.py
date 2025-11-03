"""
Artist-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all artist-related API operations.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field, HttpUrl, validator

from .base import BaseRequest, BaseResponse, BulkOperationRequest, PaginationRequest
from .common import (
    MetadataMixin,
    ThumbnailSearchRequest,
    TimestampMixin,
    UrlValidationMixin,
)


class ArtistResponse(BaseResponse, TimestampMixin, MetadataMixin):
    """Complete artist information response"""

    id: int = Field(description="Unique artist identifier")
    name: str = Field(description="Artist name")
    bio: Optional[str] = Field(None, description="Artist biography")
    website: Optional[HttpUrl] = Field(None, description="Artist website URL")
    imvdb_url: Optional[HttpUrl] = Field(None, description="IMVDb profile URL")
    spotify_url: Optional[HttpUrl] = Field(None, description="Spotify profile URL")
    apple_music_url: Optional[HttpUrl] = Field(
        None, description="Apple Music profile URL"
    )
    youtube_channel: Optional[HttpUrl] = Field(None, description="YouTube channel URL")
    twitter_handle: Optional[str] = Field(
        None, description="Twitter handle (without @)"
    )
    instagram_handle: Optional[str] = Field(
        None, description="Instagram handle (without @)"
    )
    facebook_url: Optional[HttpUrl] = Field(None, description="Facebook page URL")

    # Statistics
    video_count: int = Field(
        default=0, ge=0, description="Number of videos by this artist"
    )
    total_duration: int = Field(
        default=0, ge=0, description="Total duration of all videos in seconds"
    )
    downloaded_count: int = Field(
        default=0, ge=0, description="Number of downloaded videos"
    )

    # Computed fields
    thumbnail_url: Optional[str] = Field(
        None, description="Artist thumbnail/avatar URL"
    )
    is_verified: bool = Field(default=False, description="Whether artist is verified")
    popularity_score: float = Field(
        default=0.0, ge=0.0, le=10.0, description="Popularity score (0-10)"
    )

    @validator("twitter_handle", "instagram_handle")
    def validate_social_handle(cls, v):
        """Validate social media handles"""
        if v:
            # Remove @ if present and validate format
            handle = v.lstrip("@").strip()
            if not handle.replace("_", "").replace(".", "").isalnum():
                raise ValueError("Social media handle contains invalid characters")
            if len(handle) > 50:
                raise ValueError("Social media handle too long")
            return handle
        return v


class ArtistCreateRequest(BaseRequest, UrlValidationMixin):
    """Request to create a new artist"""

    name: str = Field(..., min_length=1, max_length=200, description="Artist name")
    bio: Optional[str] = Field(None, max_length=2000, description="Artist biography")
    website: Optional[HttpUrl] = Field(None, description="Artist website URL")
    imvdb_url: Optional[HttpUrl] = Field(None, description="IMVDb profile URL")
    spotify_url: Optional[HttpUrl] = Field(None, description="Spotify profile URL")
    apple_music_url: Optional[HttpUrl] = Field(
        None, description="Apple Music profile URL"
    )
    youtube_channel: Optional[HttpUrl] = Field(None, description="YouTube channel URL")
    twitter_handle: Optional[str] = Field(
        None, max_length=50, description="Twitter handle"
    )
    instagram_handle: Optional[str] = Field(
        None, max_length=50, description="Instagram handle"
    )
    facebook_url: Optional[HttpUrl] = Field(None, description="Facebook page URL")

    @validator("name")
    def validate_name(cls, v):
        """Clean and validate artist name"""
        name = v.strip()
        if not name:
            raise ValueError("Artist name cannot be empty")
        return name

    @validator("bio")
    def validate_bio(cls, v):
        """Clean biography"""
        return v.strip() if v else None


class ArtistUpdateRequest(BaseRequest, UrlValidationMixin):
    """Request to update artist information"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    bio: Optional[str] = Field(None, max_length=2000)
    website: Optional[HttpUrl] = None
    imvdb_url: Optional[HttpUrl] = None
    spotify_url: Optional[HttpUrl] = None
    apple_music_url: Optional[HttpUrl] = None
    youtube_channel: Optional[HttpUrl] = None
    twitter_handle: Optional[str] = Field(None, max_length=50)
    instagram_handle: Optional[str] = Field(None, max_length=50)
    facebook_url: Optional[HttpUrl] = None
    is_verified: Optional[bool] = None

    @validator("name")
    def validate_name(cls, v):
        """Clean name if provided"""
        return v.strip() if v else None


class ArtistSearchRequest(BaseRequest, PaginationRequest):
    """Request to search artists with filters"""

    query: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Search in artist name and bio"
    )
    has_videos: Optional[bool] = Field(
        None, description="Filter by whether artist has videos"
    )
    verified_only: bool = Field(
        default=False, description="Only return verified artists"
    )
    min_videos: Optional[int] = Field(
        None, ge=0, description="Minimum number of videos"
    )
    max_videos: Optional[int] = Field(
        None, ge=0, description="Maximum number of videos"
    )
    has_imvdb: Optional[bool] = Field(
        None, description="Filter by whether artist has IMVDb profile"
    )

    @validator("max_videos")
    def validate_video_range(cls, v, values):
        """Ensure max_videos > min_videos"""
        if v and "min_videos" in values and values["min_videos"]:
            if v <= values["min_videos"]:
                raise ValueError("max_videos must be greater than min_videos")
        return v


class ArtistBulkRequest(BulkOperationRequest):
    """Base request for bulk artist operations"""

    pass


class ArtistIMVDbImportRequest(BaseRequest):
    """Request to import artist information from IMVDb"""

    imvdb_url: HttpUrl = Field(..., description="IMVDb artist profile URL")
    update_existing: bool = Field(
        default=True, description="Update existing artist data if artist already exists"
    )
    import_videos: bool = Field(
        default=False, description="Also import videos from IMVDb"
    )

    @validator("imvdb_url")
    def validate_imvdb_url(cls, v):
        """Ensure URL is from IMVDb"""
        if "imvdb.com" not in str(v):
            raise ValueError("URL must be from imvdb.com")
        return v


class ArtistStatsResponse(BaseResponse):
    """Response containing artist statistics"""

    total_artists: int = Field(ge=0, description="Total number of artists")
    verified_artists: int = Field(ge=0, description="Number of verified artists")
    artists_with_videos: int = Field(ge=0, description="Artists that have videos")
    artists_with_imvdb: int = Field(ge=0, description="Artists with IMVDb profiles")
    top_artists: List[Dict[str, Any]] = Field(description="Top artists by video count")
    recent_additions: List[Dict[str, Any]] = Field(description="Recently added artists")

    @validator("top_artists", "recent_additions")
    def validate_artist_lists(cls, v):
        """Ensure artist list items have required fields"""
        for item in v:
            if not isinstance(item, dict) or "id" not in item or "name" not in item:
                raise ValueError("Artist list items must include id and name")
        return v


class ArtistVideoListResponse(BaseResponse):
    """Response containing videos by a specific artist"""

    artist_id: int = Field(description="Artist ID")
    artist_name: str = Field(description="Artist name")
    videos: List[Dict[str, Any]] = Field(description="List of videos by this artist")
    pagination: Dict[str, Any] = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        artist_id: int,
        artist_name: str,
        videos: List[Dict[str, Any]],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create paginated artist video list"""
        has_more = offset + limit < total_count

        return cls(
            artist_id=artist_id,
            artist_name=artist_name,
            videos=videos,
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(videos),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class ArtistMergeRequest(BaseRequest):
    """Request to merge two artists"""

    source_artist_id: int = Field(
        ..., ge=1, description="ID of artist to merge (will be deleted)"
    )
    target_artist_id: int = Field(
        ..., ge=1, description="ID of artist to merge into (will be kept)"
    )
    merge_videos: bool = Field(
        default=True, description="Transfer all videos to target artist"
    )
    merge_metadata: bool = Field(
        default=True, description="Merge social media links and other metadata"
    )

    @validator("target_artist_id")
    def validate_different_artists(cls, v, values):
        """Ensure source and target are different"""
        if "source_artist_id" in values and v == values["source_artist_id"]:
            raise ValueError("Source and target artist IDs must be different")
        return v


class ArtistListResponse(BaseResponse):
    """Response containing list of artists with pagination"""

    artists: List[ArtistResponse] = Field(description="List of artists")
    pagination: Dict[str, Any] = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        artists: List[ArtistResponse],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create paginated artist list response"""
        has_more = offset + limit < total_count

        return cls(
            artists=artists,
            message=message,
            pagination={
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(artists),
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
                "prev_offset": max(0, offset - limit) if offset > 0 else None,
            },
        )


class ArtistThumbnailSearchRequest(ThumbnailSearchRequest):
    """Artist-specific thumbnail search request"""

    artist_name: Optional[str] = Field(
        None, description="Artist name for thumbnail search"
    )


# Export all artist-related models
__all__ = [
    "ArtistResponse",
    "ArtistCreateRequest",
    "ArtistUpdateRequest",
    "ArtistSearchRequest",
    "ArtistBulkRequest",
    "ArtistIMVDbImportRequest",
    "ArtistStatsResponse",
    "ArtistVideoListResponse",
    "ArtistMergeRequest",
    "ArtistListResponse",
    "ArtistThumbnailSearchRequest",
]
