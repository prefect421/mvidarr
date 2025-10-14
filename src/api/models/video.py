"""
Video-Related Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for all video-related API operations.
"""

from typing import List, Optional

from pydantic import Field, HttpUrl, field_validator, validator

from .base import BaseRequest, BaseResponse, BulkOperationRequest, PaginationRequest
from .common import (
    GenresMixin,
    MetadataMixin,
    PriorityRequest,
    TimestampMixin,
    UrlValidationMixin,
)


class VideoResponse(BaseResponse, TimestampMixin, MetadataMixin, GenresMixin):
    """Complete video information response"""

    id: int = Field(description="Unique video identifier")
    title: str = Field(description="Video title")
    artist_id: Optional[int] = Field(None, description="Associated artist ID")
    artist_name: Optional[str] = Field(None, description="Associated artist name")
    url: Optional[HttpUrl] = Field(None, description="Video source URL")
    youtube_url: Optional[HttpUrl] = Field(
        None, description="YouTube URL if applicable"
    )
    status: str = Field(description="Current video status")
    file_path: Optional[str] = Field(None, description="Local file path if downloaded")
    file_size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    duration: Optional[int] = Field(None, ge=0, description="Duration in seconds")
    resolution: Optional[str] = Field(
        None, description="Video resolution (e.g., '1920x1080')"
    )
    fps: Optional[float] = Field(None, ge=0, description="Frames per second")
    codec: Optional[str] = Field(None, description="Video codec")
    bitrate: Optional[int] = Field(None, ge=0, description="Bitrate in kbps")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail image URL")
    download_count: int = Field(
        default=0, ge=0, description="Number of times downloaded"
    )
    view_count: int = Field(default=0, ge=0, description="Number of times viewed")

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v):
        """Validate video resolution format"""
        if v and "x" in v:
            try:
                width, height = v.split("x")
                width, height = int(width), int(height)
                if width > 0 and height > 0:
                    return v
            except (ValueError, TypeError):
                pass
            raise ValueError(
                'Resolution must be in format "WIDTHxHEIGHT" (e.g., "1920x1080")'
            )
        return v

    @field_validator("codec")
    @classmethod
    def validate_codec(cls, v):
        """Validate codec format"""
        if v:
            valid_codecs = {
                "h264",
                "h.264",
                "avc",
                "h265",
                "h.265",
                "hevc",
                "vp8",
                "vp9",
                "av1",
                "mpeg4",
                "mpeg-4",
                "xvid",
            }
            if v.lower() not in valid_codecs:
                # Don't raise error, just log warning for now
                pass
        return v


class VideoCreateRequest(BaseRequest, GenresMixin, UrlValidationMixin):
    """Request to create a new video"""

    title: str = Field(..., min_length=1, max_length=500, description="Video title")
    artist_id: Optional[int] = Field(None, ge=1, description="Associated artist ID")
    url: Optional[HttpUrl] = Field(None, description="Video source URL")
    youtube_url: Optional[HttpUrl] = Field(None, description="YouTube URL")
    status: str = Field(
        default="WANTED",
        pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED)$",
        description="Initial video status",
    )
    priority: int = Field(
        default=1, ge=1, le=10, description="Download priority (1-10)"
    )

    @validator("title")
    def validate_title(cls, v):
        """Clean and validate title"""
        return v.strip()


class VideoUpdateRequest(BaseRequest, GenresMixin, UrlValidationMixin):
    """Request to update video information"""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    artist_id: Optional[int] = Field(None, ge=1)
    url: Optional[HttpUrl] = None
    youtube_url: Optional[HttpUrl] = None
    status: Optional[str] = Field(
        None, pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED)$"
    )

    @validator("title")
    def validate_title(cls, v):
        """Clean title if provided"""
        return v.strip() if v else None


class VideoSearchRequest(BaseRequest, PaginationRequest):
    """Request to search videos with filters"""

    query: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Search in title and artist name",
    )
    artist_id: Optional[int] = Field(None, ge=1, description="Filter by artist ID")
    status: Optional[str] = Field(
        None,
        pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED)$",
        description="Filter by status",
    )
    year: Optional[int] = Field(
        None, ge=1900, le=2100, description="Filter by creation year"
    )
    genre: Optional[str] = Field(
        None, min_length=1, max_length=50, description="Filter by genre"
    )
    has_file: Optional[bool] = Field(
        None, description="Filter by whether video has downloaded file"
    )
    resolution: Optional[str] = Field(
        None,
        pattern="^\\d+x\\d+$",
        description="Filter by resolution (e.g., '1920x1080')",
    )
    duration_min: Optional[int] = Field(
        None, ge=0, description="Minimum duration in seconds"
    )
    duration_max: Optional[int] = Field(
        None, ge=0, description="Maximum duration in seconds"
    )

    @validator("duration_max")
    def validate_duration_range(cls, v, values):
        """Ensure duration_max > duration_min"""
        if v and "duration_min" in values and values["duration_min"]:
            if v <= values["duration_min"]:
                raise ValueError("duration_max must be greater than duration_min")
        return v


class VideoDownloadRequest(BaseRequest, PriorityRequest):
    """Request to download a video"""

    force_redownload: bool = Field(
        default=False, description="Force redownload even if file exists"
    )
    quality: str = Field(
        default="best",
        pattern="^(worst|best|\\d+p?)$",
        description="Download quality preference",
    )
    format_preference: Optional[str] = Field(
        None, pattern="^(mp4|webm|mkv|avi)$", description="Preferred video format"
    )


class VideoStreamingResponse(BaseResponse):
    """Response for video streaming endpoints"""

    stream_url: str = Field(description="URL for video streaming")
    content_type: str = Field(description="MIME type of video content")
    content_length: Optional[int] = Field(None, description="Content length in bytes")
    supports_ranges: bool = Field(
        default=True, description="Whether HTTP range requests are supported"
    )
    duration: Optional[int] = Field(None, description="Video duration in seconds")


class VideoBulkDeleteRequest(BulkOperationRequest):
    """Request to bulk delete videos"""

    delete_files: bool = Field(
        default=True, description="Also delete associated video files from disk"
    )
    force: bool = Field(
        default=False,
        description="Force deletion even if video is referenced elsewhere",
    )


class VideoBulkDownloadRequest(BulkOperationRequest, PriorityRequest):
    """Request to bulk download videos"""

    quality: str = Field(
        default="best",
        pattern="^(worst|best|\\d+p?)$",
        description="Download quality for all videos",
    )
    skip_existing: bool = Field(
        default=True, description="Skip videos that are already downloaded"
    )


class VideoBulkStatusUpdateRequest(BulkOperationRequest):
    """Request to bulk update video statuses"""

    status: str = Field(
        ...,
        pattern="^(WANTED|DOWNLOADING|DOWNLOADED|IGNORED|FAILED|MONITORED)$",
        description="New status for all specified videos",
    )
    reason: Optional[str] = Field(
        None, max_length=200, description="Optional reason for status change"
    )


class VideoThumbnailRequest(BaseRequest):
    """Request to update video thumbnail"""

    thumbnail_url: Optional[HttpUrl] = Field(None, description="URL of new thumbnail")
    generate_from_video: bool = Field(
        default=False, description="Generate thumbnail from video file"
    )
    timestamp: Optional[int] = Field(
        None, ge=0, description="Timestamp in seconds for thumbnail extraction"
    )
    size: str = Field(
        default="medium",
        pattern="^(small|medium|large|original)$",
        description="Thumbnail size",
    )


class VideoMetadataResponse(BaseResponse):
    """Response containing extracted video metadata"""

    title: Optional[str] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    file_size: Optional[int] = None
    format: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_bitrate: Optional[int] = None
    thumbnail_extracted: bool = Field(default=False)

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "title": "Example Music Video",
                "duration": 240,
                "resolution": "1920x1080",
                "fps": 30.0,
                "codec": "h264",
                "bitrate": 5000,
                "file_size": 150000000,
                "format": "mp4",
                "audio_codec": "aac",
                "audio_bitrate": 128,
                "thumbnail_extracted": True,
            }
        }


class VideoListResponse(BaseResponse):
    """Response containing list of videos with pagination"""

    videos: List[VideoResponse] = Field(description="List of videos")
    pagination: dict = Field(description="Pagination information")

    @classmethod
    def create_paginated(
        cls,
        videos: List[VideoResponse],
        total_count: int,
        limit: int,
        offset: int,
        message: str = None,
    ):
        """Create a paginated video list response"""
        has_more = offset + limit < total_count

        return cls(
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


class VideoStatsResponse(BaseResponse):
    """Response containing video statistics"""

    total_videos: int = Field(ge=0)
    by_status: dict = Field(description="Video count by status")
    by_resolution: dict = Field(description="Video count by resolution")
    by_codec: dict = Field(description="Video count by codec")
    total_file_size: int = Field(
        ge=0, description="Total size of all video files in bytes"
    )
    total_duration: int = Field(
        ge=0, description="Total duration of all videos in seconds"
    )
    average_file_size: float = Field(ge=0, description="Average file size in bytes")
    average_duration: float = Field(ge=0, description="Average duration in seconds")


# Export all video-related models
__all__ = [
    "VideoResponse",
    "VideoCreateRequest",
    "VideoUpdateRequest",
    "VideoSearchRequest",
    "VideoDownloadRequest",
    "VideoStreamingResponse",
    "VideoBulkDeleteRequest",
    "VideoBulkDownloadRequest",
    "VideoBulkStatusUpdateRequest",
    "VideoThumbnailRequest",
    "VideoMetadataResponse",
    "VideoListResponse",
    "VideoStatsResponse",
]
