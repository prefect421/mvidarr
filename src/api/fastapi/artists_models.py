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

    updates: Dict[str, Any] = Field(..., min_items=1)


class ThumbnailSearchRequest(BaseModel):
    """Request model for searching artist thumbnails"""

    source: str = Field("auto", pattern="^(auto|wikipedia|youtube|imvdb)$")
    query: Optional[str] = None


class IMVDbImportRequest(BaseModel):
    """Request model for importing artists from IMVDb"""

    imvdb_id: int = Field(..., ge=1)
    auto_discover_videos: bool = True
