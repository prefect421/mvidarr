"""
AI Services Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Centralized models for AI-powered features including content analysis,
auto-tagging, and smart recommendations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from .base import (
    BaseRequest,
    BaseResponse,
    BulkOperationRequest,
    BulkOperationResponse,
    TaskPriority,
    TaskSubmissionResponse,
)
from .common import PriorityRequest


class AnalysisType(str, Enum):
    """Types of content analysis"""

    VISUAL = "visual"
    AUDIO = "audio"
    METADATA = "metadata"
    COMPREHENSIVE = "comprehensive"


class ConfidenceLevel(str, Enum):
    """Confidence levels for AI predictions"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class TaggingMode(str, Enum):
    """Auto-tagging operation modes"""

    CONSERVATIVE = "conservative"  # Only high-confidence tags
    BALANCED = "balanced"  # Mixed confidence levels
    AGGRESSIVE = "aggressive"  # Include lower confidence tags


class RecommendationType(str, Enum):
    """Types of recommendations"""

    SIMILAR_VIDEOS = "similar_videos"
    RELATED_ARTISTS = "related_artists"
    GENRE_SUGGESTIONS = "genre_suggestions"
    PLAYLIST_ADDITIONS = "playlist_additions"
    QUALITY_IMPROVEMENTS = "quality_improvements"


class ContentAnalysisRequest(BaseRequest, PriorityRequest):
    """Request for AI-powered content analysis"""

    video_id: int = Field(..., ge=1, description="Video ID to analyze")
    analysis_types: List[AnalysisType] = Field(
        default=[AnalysisType.COMPREHENSIVE],
        min_items=1,
        max_items=4,
        description="Types of analysis to perform",
    )

    # Visual analysis options
    extract_scenes: bool = Field(
        default=True, description="Extract and analyze distinct scenes"
    )
    detect_objects: bool = Field(
        default=True, description="Detect objects and people in video"
    )
    analyze_colors: bool = Field(
        default=True, description="Analyze color palette and schemes"
    )
    detect_text: bool = Field(
        default=False, description="Detect and extract text overlays"
    )

    # Audio analysis options
    analyze_music: bool = Field(
        default=True, description="Analyze musical content and characteristics"
    )
    detect_speech: bool = Field(
        default=False, description="Detect and analyze speech content"
    )
    extract_lyrics: bool = Field(default=False, description="Attempt to extract lyrics")

    # Analysis depth
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.1,
        le=1.0,
        description="Minimum confidence threshold for results (0.1-1.0)",
    )
    max_processing_time: Optional[int] = Field(
        None,
        ge=60,
        le=3600,
        description="Maximum processing time in seconds (1min-1hr)",
    )

    @validator("analysis_types")
    def validate_analysis_types(cls, v):
        """Remove duplicates from analysis types"""
        return list(dict.fromkeys(v))


class ContentAnalysisResponse(BaseResponse, TaskSubmissionResponse):
    """Response containing content analysis results"""

    video_id: int = Field(description="Analyzed video ID")
    analysis_types: List[AnalysisType] = Field(
        description="Types of analysis performed"
    )

    # Visual analysis results
    scenes: Optional[List[Dict[str, Any]]] = Field(
        None, description="Detected scenes with timestamps and descriptions"
    )
    objects_detected: Optional[List[Dict[str, Any]]] = Field(
        None, description="Objects and people detected in video"
    )
    dominant_colors: Optional[List[str]] = Field(
        None, description="Dominant colors in hex format"
    )
    color_palette: Optional[Dict[str, Any]] = Field(
        None, description="Detailed color analysis"
    )
    text_content: Optional[List[Dict[str, Any]]] = Field(
        None, description="Text overlays detected in video"
    )

    # Audio analysis results
    music_analysis: Optional[Dict[str, Any]] = Field(
        None, description="Musical content analysis (tempo, key, mood, etc.)"
    )
    speech_content: Optional[List[Dict[str, Any]]] = Field(
        None, description="Speech segments and transcription"
    )
    extracted_lyrics: Optional[str] = Field(
        None, description="Extracted or detected lyrics"
    )

    # Metadata analysis
    metadata_insights: Optional[Dict[str, Any]] = Field(
        None, description="Insights derived from existing metadata"
    )

    # Overall insights
    content_summary: str = Field(description="AI-generated content summary")
    mood_analysis: Optional[Dict[str, float]] = Field(
        None, description="Detected moods with confidence scores"
    )
    genre_predictions: Optional[List[Dict[str, Any]]] = Field(
        None, description="Genre predictions with confidence scores"
    )
    quality_assessment: Optional[Dict[str, Any]] = Field(
        None, description="Technical and artistic quality assessment"
    )

    # Processing metadata
    processing_time: float = Field(
        ge=0, description="Analysis processing time in seconds"
    )
    model_versions: Dict[str, str] = Field(description="AI model versions used")
    confidence_scores: Dict[str, float] = Field(
        description="Overall confidence by analysis type"
    )


class TaggingRequest(BaseRequest, PriorityRequest):
    """Request for AI-powered auto-tagging"""

    video_id: int = Field(..., ge=1, description="Video ID to tag")
    tagging_mode: TaggingMode = Field(
        default=TaggingMode.BALANCED, description="Tagging operation mode"
    )

    # Tag sources
    use_visual_analysis: bool = Field(
        default=True, description="Generate tags from visual content"
    )
    use_audio_analysis: bool = Field(
        default=True, description="Generate tags from audio content"
    )
    use_metadata: bool = Field(
        default=True, description="Generate tags from existing metadata"
    )
    use_filename: bool = Field(default=True, description="Extract tags from filename")

    # Tag filtering
    max_tags: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of tags to generate (1-100)",
    )
    min_confidence: float = Field(
        default=0.6, ge=0.1, le=1.0, description="Minimum confidence for tag inclusion"
    )
    exclude_tags: Optional[List[str]] = Field(
        None, max_items=50, description="Tags to exclude from results"
    )
    preferred_categories: Optional[List[str]] = Field(
        None, max_items=20, description="Preferred tag categories to prioritize"
    )

    # Behavior options
    replace_existing: bool = Field(
        default=False, description="Replace existing tags instead of merging"
    )
    suggest_only: bool = Field(
        default=False, description="Only suggest tags without applying them"
    )

    @validator("exclude_tags", "preferred_categories")
    def validate_tag_lists(cls, v):
        """Clean and validate tag lists"""
        if v:
            cleaned = []
            for tag in v:
                tag = tag.strip().lower()
                if tag and len(tag) <= 50 and tag not in cleaned:
                    cleaned.append(tag)
            return cleaned[:50]  # Limit to 50 items
        return v


class TaggingResponse(BaseResponse, TaskSubmissionResponse):
    """Response containing auto-tagging results"""

    video_id: int = Field(description="Tagged video ID")
    tagging_mode: TaggingMode = Field(description="Tagging mode used")

    # Generated tags
    suggested_tags: List[Dict[str, Any]] = Field(
        description="AI-generated tags with confidence scores"
    )
    applied_tags: Optional[List[str]] = Field(
        None, description="Tags that were actually applied to the video"
    )
    existing_tags: Optional[List[str]] = Field(
        None, description="Tags that were already present"
    )

    # Tag sources breakdown
    tags_from_visual: List[str] = Field(
        default_factory=list, description="Tags from visual analysis"
    )
    tags_from_audio: List[str] = Field(
        default_factory=list, description="Tags from audio analysis"
    )
    tags_from_metadata: List[str] = Field(
        default_factory=list, description="Tags from metadata"
    )
    tags_from_filename: List[str] = Field(
        default_factory=list, description="Tags from filename"
    )

    # Quality metrics
    average_confidence: float = Field(
        ge=0, le=1, description="Average confidence of all tags"
    )
    tag_diversity_score: float = Field(
        ge=0, le=1, description="Diversity score of generated tags"
    )

    # Processing info
    processing_time: float = Field(
        ge=0, description="Tagging processing time in seconds"
    )
    model_version: str = Field(description="Tagging model version used")


class BatchAnalysisRequest(BaseRequest, PriorityRequest):
    """Request for batch analysis of multiple videos"""

    video_ids: List[int] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Video IDs to analyze (1-100 videos)",
    )
    analysis_types: List[AnalysisType] = Field(
        default=[AnalysisType.COMPREHENSIVE],
        min_items=1,
        description="Analysis types to perform on all videos",
    )

    # Batch processing options
    max_concurrent: int = Field(
        default=3, ge=1, le=10, description="Maximum concurrent analysis jobs (1-10)"
    )
    continue_on_error: bool = Field(
        default=True, description="Continue batch if individual analyses fail"
    )

    # Analysis options (applied to all videos)
    confidence_threshold: float = Field(
        default=0.7, ge=0.1, le=1.0, description="Confidence threshold for all analyses"
    )

    @validator("video_ids")
    def validate_unique_video_ids(cls, v):
        """Remove duplicates and ensure positive IDs"""
        unique_ids = []
        for vid in v:
            if isinstance(vid, int) and vid > 0 and vid not in unique_ids:
                unique_ids.append(vid)
        return unique_ids


class BatchAnalysisResponse(
    BaseResponse, BulkOperationResponse, TaskSubmissionResponse
):
    """Response for batch analysis operation"""

    video_ids: List[int] = Field(description="Video IDs in batch")
    analysis_types: List[AnalysisType] = Field(description="Analysis types performed")

    # Batch results
    completed_analyses: List[int] = Field(
        description="Successfully completed video IDs"
    )
    failed_analyses: List[int] = Field(description="Failed video IDs")
    pending_analyses: List[int] = Field(description="Still processing video IDs")

    # Summary statistics
    total_processing_time: float = Field(
        ge=0, description="Total processing time for batch"
    )
    average_processing_time: float = Field(ge=0, description="Average time per video")
    success_rate: float = Field(ge=0, le=100, description="Success rate percentage")


class RecommendationRequest(BaseRequest):
    """Request for AI-powered recommendations"""

    recommendation_type: RecommendationType = Field(
        ..., description="Type of recommendations to generate"
    )

    # Context for recommendations
    video_id: Optional[int] = Field(
        None, ge=1, description="Base video for similar recommendations"
    )
    artist_id: Optional[int] = Field(
        None, ge=1, description="Base artist for recommendations"
    )
    user_id: Optional[int] = Field(
        None, ge=1, description="User for personalized recommendations"
    )
    playlist_id: Optional[int] = Field(
        None, ge=1, description="Playlist for addition suggestions"
    )

    # Recommendation parameters
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of recommendations (1-100)",
    )
    min_similarity: float = Field(
        default=0.3, ge=0.1, le=1.0, description="Minimum similarity threshold"
    )

    # Filtering options
    exclude_ids: Optional[List[int]] = Field(
        None, max_items=1000, description="IDs to exclude from recommendations"
    )
    include_genres: Optional[List[str]] = Field(
        None, max_items=20, description="Genres to prioritize"
    )
    exclude_genres: Optional[List[str]] = Field(
        None, max_items=20, description="Genres to avoid"
    )

    # Recommendation behavior
    diversify_results: bool = Field(
        default=True, description="Ensure diverse recommendations"
    )
    include_new_content: bool = Field(
        default=True, description="Include recently added content"
    )

    @validator("exclude_ids")
    def validate_exclude_ids(cls, v):
        """Validate exclude IDs list"""
        if v:
            return [id for id in v if isinstance(id, int) and id > 0]
        return v


class RecommendationResponse(BaseResponse):
    """Response containing AI-generated recommendations"""

    recommendation_type: RecommendationType = Field(
        description="Type of recommendations"
    )
    context: Dict[str, Any] = Field(description="Context used for recommendations")

    # Recommendations
    recommendations: List[Dict[str, Any]] = Field(
        description="Recommended items with scores and reasons"
    )

    # Metadata
    total_candidates: int = Field(ge=0, description="Total items considered")
    algorithm_used: str = Field(description="Recommendation algorithm used")
    model_version: str = Field(description="Model version used")

    # Quality metrics
    average_confidence: float = Field(
        ge=0, le=1, description="Average recommendation confidence"
    )
    diversity_score: float = Field(
        ge=0, le=1, description="Diversity of recommendations"
    )

    # Processing info
    processing_time: float = Field(
        ge=0, description="Time taken to generate recommendations"
    )
    cache_hit: bool = Field(description="Whether results were served from cache")


class AIServiceStatsResponse(BaseResponse):
    """Response containing AI service statistics"""

    # Usage statistics
    total_analyses: int = Field(ge=0, description="Total analyses performed")
    analyses_today: int = Field(ge=0, description="Analyses performed today")
    active_jobs: int = Field(ge=0, description="Currently running AI jobs")

    by_type: Dict[str, int] = Field(description="Analysis count by type")
    by_status: Dict[str, int] = Field(description="Job count by status")

    # Performance metrics
    average_processing_time: float = Field(
        ge=0, description="Average processing time in seconds"
    )
    success_rate: float = Field(ge=0, le=100, description="Success rate percentage")
    cache_hit_rate: float = Field(ge=0, le=100, description="Cache hit rate percentage")

    # Quality metrics
    average_confidence: float = Field(
        ge=0, le=1, description="Average confidence score"
    )
    user_satisfaction: Optional[float] = Field(
        None, ge=0, le=5, description="User satisfaction rating"
    )

    # Resource usage
    total_processing_time: float = Field(
        ge=0, description="Total processing time in seconds"
    )
    model_versions: Dict[str, str] = Field(
        description="Currently active model versions"
    )

    # Recent activity
    recent_analyses: List[Dict[str, Any]] = Field(description="Recent analysis jobs")
    popular_features: List[str] = Field(description="Most used AI features")


# Export all AI service models
__all__ = [
    "AnalysisType",
    "ConfidenceLevel",
    "TaggingMode",
    "RecommendationType",
    "ContentAnalysisRequest",
    "ContentAnalysisResponse",
    "TaggingRequest",
    "TaggingResponse",
    "BatchAnalysisRequest",
    "BatchAnalysisResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    "AIServiceStatsResponse",
]
