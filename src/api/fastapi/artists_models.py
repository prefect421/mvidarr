"""
FastAPI Artists API - Pydantic Models and Schemas
Split from artists.py for better code organization

This module contains all Pydantic models used for request/response validation
in the Artists API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ArtistResponse(BaseModel):
    """Response model for artist data"""

    id: int
    name: str
    sort_name: Optional[str] = None
    folder_path: Optional[str] = None
    imvdb_id: Optional[int] = None
    imvdb_slug: Optional[str] = None
    thumbnail_url: Optional[str] = None
    biography: Optional[str] = None
    formed_year: Optional[int] = None
    location: Optional[str] = None
    website: Optional[str] = None
    wikipedia_url: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    spotify_id: Optional[str] = None
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    imvdb_metadata: Optional[Dict[str, Any]] = (
        None  # Include metadata for song recommendations
    )
    # Category 1 fields - Issue #174: Fields in database but were missing from API
    keywords: Optional[List[str]] = None  # Video filtering keywords
    genres: Optional[List[str]] = None  # Artist genres
    labels: Optional[List[str]] = None  # Record labels
    members: Optional[str] = None  # Band members
    # Category 3 fields - Issue #174: Fields in frontend but were missing from API/database
    overview: Optional[str] = None  # Artist overview/summary
    disbanded_year: Optional[int] = None  # Year the band disbanded
    origin_country: Optional[str] = None  # Country of origin
    spotify_url: Optional[str] = None  # Spotify profile URL
    youtube_url: Optional[str] = None  # YouTube channel URL
    apple_music_url: Optional[str] = None  # Apple Music profile URL
    twitter_url: Optional[str] = None  # Twitter/X profile URL
    facebook_url: Optional[str] = None  # Facebook page URL
    instagram_url: Optional[str] = None  # Instagram profile URL
    quality_profile: Optional[str] = None  # Quality profile for downloads
    priority: Optional[int] = None  # Artist priority for downloads
    video_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArtistCreateRequest(BaseModel):
    """Request model for creating a new artist"""

    name: str = Field(..., min_length=1, max_length=255)
    imvdb_id: Optional[int] = None
    folder_path: Optional[str] = None
    monitored: bool = True
    auto_download: bool = False
    auto_discover: bool = True


class ArtistUpdateRequest(BaseModel):
    """Request model for updating an existing artist"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    sort_name: Optional[str] = None
    folder_path: Optional[str] = None
    imvdb_id: Optional[int] = None
    imvdb_slug: Optional[str] = None
    biography: Optional[str] = None
    formed_year: Optional[int] = Field(None, ge=1800, le=2100)
    location: Optional[str] = None
    website: Optional[str] = None
    wikipedia_url: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    spotify_id: Optional[str] = None
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    # Category 1 fields - Issue #174: Fields in database but were missing from API
    keywords: Optional[List[str]] = None  # Video filtering keywords
    genres: Optional[List[str]] = None  # Artist genres
    labels: Optional[List[str]] = None  # Record labels
    members: Optional[str] = None  # Band members
    # Category 3 fields - Issue #174: Fields in frontend but were missing from API/database
    overview: Optional[str] = None  # Artist overview/summary
    disbanded_year: Optional[int] = Field(
        None, ge=1800, le=2100
    )  # Year the band disbanded
    origin_country: Optional[str] = None  # Country of origin
    spotify_url: Optional[str] = None  # Spotify profile URL
    youtube_url: Optional[str] = None  # YouTube channel URL
    apple_music_url: Optional[str] = None  # Apple Music profile URL
    twitter_url: Optional[str] = None  # Twitter/X profile URL
    facebook_url: Optional[str] = None  # Facebook page URL
    instagram_url: Optional[str] = None  # Instagram profile URL
    quality_profile: Optional[str] = None  # Quality profile for downloads
    priority: Optional[int] = Field(None, ge=0)  # Artist priority for downloads


class ArtistSearchRequest(BaseModel):
    """Request model for searching/filtering artists"""

    query: Optional[str] = None
    sort_by: str = Field("name", pattern="^(name|video_count|created_at|updated_at)$")
    sort_order: str = Field("asc", pattern="^(asc|desc)$")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
    has_videos: Optional[bool] = None
    has_imvdb: Optional[bool] = None


class BulkArtistRequest(BaseModel):
    """Base request model for bulk artist operations"""

    artist_ids: List[int] = Field(..., min_items=1)


class BulkDeleteRequest(BulkArtistRequest):
    """Request model for bulk artist deletion"""

    delete_videos: bool = False


class BulkEditRequest(BulkArtistRequest):
    """Request model for bulk artist editing"""

    updates: Dict[str, Any] = Field(..., description="Fields to update")


class BulkMonitoringRequest(BulkArtistRequest):
    """Request model for bulk monitoring updates"""

    monitored: Optional[bool] = None
    monitor_new_items: Optional[str] = None


class RenameCommandRequest(BulkArtistRequest):
    """Request model for rename artist command"""

    pass


class RetagCommandRequest(BulkArtistRequest):
    """Request model for retag artist command"""

    pass


class MergeArtistsRequest(BaseModel):
    """Request model for merging multiple artists into one"""

    primary_artist_id: int = Field(..., description="ID of the artist to keep")
    secondary_artist_ids: List[int] = Field(
        ..., min_items=1, description="IDs of artists to merge into the primary"
    )


class ThumbnailSearchRequest(BaseModel):
    """Request model for searching artist thumbnails"""

    source: str = Field("auto", pattern="^(auto|wikipedia|youtube|imvdb)$")
    query: Optional[str] = None


class IMVDbImportRequest(BaseModel):
    """Request model for importing artists from IMVDb"""

    imvdb_id: int = Field(..., ge=1)
    auto_discover_videos: bool = True
