"""
Media Processing Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for media processing operations including video conversion,
metadata extraction, and bulk media operations.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from .base import (
    BaseRequest,
    BaseResponse,
    BulkOperationRequest,
    BulkOperationResponse,
    FilePathRequest,
    TaskPriority,
    TaskSubmissionResponse,
)
from .common import PriorityRequest


class VideoFormat(str, Enum):
    """Supported video formats"""

    MP4 = "mp4"
    WEBM = "webm"
    MKV = "mkv"
    AVI = "avi"
    MOV = "mov"
    FLV = "flv"
    WMV = "wmv"
    M4V = "m4v"


class VideoCodec(str, Enum):
    """Supported video codecs"""

    H264 = "h264"
    H265 = "h265"
    VP8 = "vp8"
    VP9 = "vp9"
    AV1 = "av1"
    MPEG4 = "mpeg4"
    XVID = "xvid"


class AudioCodec(str, Enum):
    """Supported audio codecs"""

    AAC = "aac"
    MP3 = "mp3"
    OGG = "ogg"
    FLAC = "flac"
    AC3 = "ac3"
    OPUS = "opus"


class VideoQuality(str, Enum):
    """Video quality presets"""

    LOW = "low"  # 480p
    MEDIUM = "medium"  # 720p
    HIGH = "high"  # 1080p
    ULTRA = "ultra"  # 4K
    CUSTOM = "custom"


class ProcessingStatus(str, Enum):
    """Media processing status"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoMetadataExtractionRequest(BaseRequest, FilePathRequest):
    """Request to extract metadata from a video file"""

    extract_thumbnails: bool = Field(
        default=True, description="Extract thumbnail images from video"
    )
    thumbnail_count: int = Field(
        default=3, ge=1, le=10, description="Number of thumbnails to extract (1-10)"
    )
    thumbnail_size: str = Field(
        default="medium",
        pattern="^(small|medium|large|original)$",
        description="Thumbnail size: small, medium, large, or original",
    )
    extract_chapters: bool = Field(
        default=False, description="Extract chapter information if available"
    )
    deep_analysis: bool = Field(
        default=False, description="Perform detailed codec and quality analysis"
    )


class VideoMetadataResponse(BaseResponse):
    """Response containing extracted video metadata"""

    # Basic file information
    filename: str = Field(description="Original filename")
    file_size: int = Field(ge=0, description="File size in bytes")
    format: str = Field(description="Container format")
    duration: float = Field(ge=0, description="Duration in seconds")

    # Video stream information
    video_codec: Optional[str] = Field(None, description="Video codec")
    video_bitrate: Optional[int] = Field(
        None, ge=0, description="Video bitrate in kbps"
    )
    resolution: Optional[str] = Field(
        None, description="Video resolution (WIDTHxHEIGHT)"
    )
    frame_rate: Optional[float] = Field(None, ge=0, description="Frame rate (fps)")
    aspect_ratio: Optional[str] = Field(None, description="Aspect ratio")

    # Audio stream information
    audio_codec: Optional[str] = Field(None, description="Audio codec")
    audio_bitrate: Optional[int] = Field(
        None, ge=0, description="Audio bitrate in kbps"
    )
    sample_rate: Optional[int] = Field(
        None, ge=0, description="Audio sample rate in Hz"
    )
    channels: Optional[int] = Field(None, ge=1, description="Audio channel count")

    # Quality assessment
    video_quality_score: Optional[float] = Field(
        None, ge=0, le=10, description="Video quality score (0-10)"
    )
    audio_quality_score: Optional[float] = Field(
        None, ge=0, le=10, description="Audio quality score (0-10)"
    )
    overall_quality: Optional[str] = Field(
        None, description="Overall quality assessment"
    )

    # Extracted thumbnails
    thumbnails: List[str] = Field(
        default_factory=list, description="Paths to extracted thumbnails"
    )

    # Additional metadata
    title: Optional[str] = Field(None, description="Title metadata")
    artist: Optional[str] = Field(None, description="Artist metadata")
    album: Optional[str] = Field(None, description="Album metadata")
    year: Optional[int] = Field(None, description="Year metadata")
    genre: Optional[str] = Field(None, description="Genre metadata")

    # Technical details (for deep analysis)
    color_space: Optional[str] = Field(None, description="Color space information")
    pixel_format: Optional[str] = Field(None, description="Pixel format")
    chapters: Optional[List[Dict[str, Any]]] = Field(
        None, description="Chapter information"
    )

    @validator("resolution")
    def validate_resolution_format(cls, v):
        """Validate resolution format"""
        if v and "x" in v:
            try:
                width, height = v.split("x")
                width, height = int(width), int(height)
                if width > 0 and height > 0:
                    return v
            except (ValueError, TypeError):
                pass
            raise ValueError('Resolution must be in format "WIDTHxHEIGHT"')
        return v


class VideoConversionRequest(BaseRequest, FilePathRequest, PriorityRequest):
    """Request to convert a video file"""

    output_format: VideoFormat = Field(..., description="Target video format")
    output_path: Optional[str] = Field(
        None, description="Output file path (auto-generated if not provided)"
    )

    # Video settings
    video_codec: Optional[VideoCodec] = Field(None, description="Video codec to use")
    video_quality: VideoQuality = Field(
        default=VideoQuality.MEDIUM, description="Video quality preset"
    )
    custom_resolution: Optional[str] = Field(
        None, pattern="^\\d+x\\d+$", description="Custom resolution (e.g., '1920x1080')"
    )
    video_bitrate: Optional[int] = Field(
        None, ge=100, le=50000, description="Video bitrate in kbps (100-50000)"
    )
    frame_rate: Optional[float] = Field(
        None, ge=1.0, le=120.0, description="Target frame rate (1-120 fps)"
    )

    # Audio settings
    audio_codec: Optional[AudioCodec] = Field(None, description="Audio codec to use")
    audio_bitrate: Optional[int] = Field(
        None, ge=32, le=512, description="Audio bitrate in kbps (32-512)"
    )
    audio_sample_rate: Optional[int] = Field(
        None, description="Audio sample rate in Hz"
    )
    audio_channels: Optional[int] = Field(
        None, ge=1, le=8, description="Number of audio channels (1-8)"
    )

    # Processing options
    two_pass_encoding: bool = Field(
        default=False, description="Use two-pass encoding for better quality"
    )
    hardware_acceleration: bool = Field(
        default=True, description="Use hardware acceleration if available"
    )
    preserve_metadata: bool = Field(
        default=True, description="Preserve original metadata in converted file"
    )

    # Time range (for partial conversion)
    start_time: Optional[float] = Field(
        None, ge=0, description="Start time in seconds for partial conversion"
    )
    end_time: Optional[float] = Field(
        None, ge=0, description="End time in seconds for partial conversion"
    )

    @validator("end_time")
    def validate_time_range(cls, v, values):
        """Ensure end_time > start_time"""
        if v and "start_time" in values and values["start_time"]:
            if v <= values["start_time"]:
                raise ValueError("end_time must be greater than start_time")
        return v

    @validator("custom_resolution")
    def validate_custom_resolution(cls, v, values):
        """Ensure custom resolution is only used with CUSTOM quality"""
        if v and values.get("video_quality") != VideoQuality.CUSTOM:
            raise ValueError(
                "custom_resolution can only be used with CUSTOM video quality"
            )
        return v


class VideoConversionResponse(BaseResponse, TaskSubmissionResponse):
    """Response for video conversion request"""

    input_file: str = Field(description="Path to input file")
    output_file: str = Field(description="Path to output file")
    conversion_settings: Dict[str, Any] = Field(
        description="Applied conversion settings"
    )
    estimated_size: Optional[int] = Field(
        None, description="Estimated output file size in bytes"
    )
    estimated_duration: Optional[int] = Field(
        None, description="Estimated processing time in seconds"
    )


class VideoValidationRequest(BaseRequest, FilePathRequest):
    """Request to validate a video file"""

    check_integrity: bool = Field(
        default=True, description="Check file integrity and corruption"
    )
    check_playability: bool = Field(
        default=True, description="Test if file is playable"
    )
    check_metadata: bool = Field(
        default=True, description="Validate metadata consistency"
    )
    strict_validation: bool = Field(
        default=False, description="Perform strict validation (may be slower)"
    )


class VideoValidationResponse(BaseResponse):
    """Response containing video validation results"""

    is_valid: bool = Field(description="Whether the video file is valid")
    is_playable: bool = Field(description="Whether the video can be played")
    has_video_stream: bool = Field(description="Whether file contains video stream")
    has_audio_stream: bool = Field(description="Whether file contains audio stream")

    # Issues found
    issues: List[str] = Field(
        default_factory=list, description="Validation issues found"
    )
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")

    # File information
    file_size: int = Field(ge=0, description="File size in bytes")
    duration: Optional[float] = Field(None, description="Video duration in seconds")
    format_info: Dict[str, Any] = Field(description="Format information")

    # Integrity check results
    checksum: Optional[str] = Field(None, description="File checksum (if computed)")
    corruption_detected: bool = Field(
        default=False, description="Whether corruption was detected"
    )

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations for fixing issues"
    )


class BulkMediaRequest(BulkOperationRequest):
    """Base request for bulk media operations"""

    file_paths: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of file paths to process (1-100 files)",
    )
    operation_type: str = Field(
        ...,
        pattern="^(metadata|convert|validate|optimize)$",
        description="Type of bulk operation: metadata, convert, validate, or optimize",
    )

    @validator("file_paths")
    def validate_file_paths(cls, v):
        """Validate file paths and remove duplicates"""
        cleaned_paths = []
        for path_str in v:
            path = Path(path_str)
            if path.is_absolute() and len(str(path)) < 500:
                cleaned_paths.append(str(path))
        return list(dict.fromkeys(cleaned_paths))  # Remove duplicates


class BulkMediaResponse(BulkOperationResponse):
    """Response for bulk media operations"""

    operation_type: str = Field(description="Type of operation performed")
    file_results: List[Dict[str, Any]] = Field(
        description="Results for each processed file"
    )
    summary: Dict[str, int] = Field(description="Operation summary statistics")


class ImageOptimizationRequest(BaseRequest, FilePathRequest, PriorityRequest):
    """Request to optimize image files"""

    target_format: str = Field(
        default="webp",
        pattern="^(webp|jpeg|png|avif)$",
        description="Target image format",
    )
    quality: int = Field(
        default=85, ge=10, le=100, description="Output quality (10-100)"
    )
    max_width: Optional[int] = Field(
        None, ge=100, le=4096, description="Maximum width in pixels"
    )
    max_height: Optional[int] = Field(
        None, ge=100, le=4096, description="Maximum height in pixels"
    )
    preserve_metadata: bool = Field(
        default=False, description="Preserve EXIF and other metadata"
    )
    progressive: bool = Field(
        default=True, description="Create progressive/interlaced images"
    )


class MediaProcessingStatsResponse(BaseResponse):
    """Response containing media processing statistics"""

    total_files_processed: int = Field(ge=0, description="Total files processed")
    processing_time_total: float = Field(
        ge=0, description="Total processing time in seconds"
    )
    average_processing_time: float = Field(
        ge=0, description="Average processing time per file"
    )

    by_operation: Dict[str, int] = Field(description="File count by operation type")
    by_status: Dict[str, int] = Field(description="File count by processing status")
    by_format: Dict[str, int] = Field(description="File count by format")

    # Performance metrics
    throughput_files_per_hour: float = Field(
        ge=0, description="Files processed per hour"
    )
    success_rate: float = Field(ge=0, le=100, description="Success rate percentage")

    # Storage impact
    total_size_before: int = Field(
        ge=0, description="Total size before processing in bytes"
    )
    total_size_after: int = Field(
        ge=0, description="Total size after processing in bytes"
    )
    space_saved: int = Field(description="Space saved in bytes (can be negative)")
    space_saved_percent: float = Field(description="Space saved as percentage")

    # Recent activity
    recent_files: List[Dict[str, Any]] = Field(description="Recently processed files")
    active_jobs: int = Field(ge=0, description="Currently active processing jobs")


# Export all media processing models
__all__ = [
    "VideoFormat",
    "VideoCodec",
    "AudioCodec",
    "VideoQuality",
    "ProcessingStatus",
    "VideoMetadataExtractionRequest",
    "VideoMetadataResponse",
    "VideoConversionRequest",
    "VideoConversionResponse",
    "VideoValidationRequest",
    "VideoValidationResponse",
    "BulkMediaRequest",
    "BulkMediaResponse",
    "ImageOptimizationRequest",
    "MediaProcessingStatsResponse",
]
