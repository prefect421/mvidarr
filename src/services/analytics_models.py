"""
Content Analytics Models - Phase 3 Week 27
Data models for content analytics including enums and dataclasses
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ContentType(Enum):
    """Types of content to analyze"""

    MUSIC_VIDEO = "music_video"
    ARTIST = "artist"
    PLAYLIST = "playlist"
    ALBUM = "album"
    GENRE = "genre"


class MetricType(Enum):
    """Content performance metric types"""

    VIEWS = "views"
    DOWNLOADS = "downloads"
    PLAYS = "plays"
    SEARCHES = "searches"
    SHARES = "shares"
    LIKES = "likes"
    QUALITY_SCORE = "quality_score"
    ENGAGEMENT_TIME = "engagement_time"
    CONVERSION_RATE = "conversion_rate"


class TimeWindow(Enum):
    """Analysis time windows"""

    LAST_HOUR = "1h"
    LAST_DAY = "24h"
    LAST_WEEK = "7d"
    LAST_MONTH = "30d"
    ALL_TIME = "all_time"


@dataclass
class ContentMetric:
    """Individual content performance metric"""

    content_id: str
    content_type: ContentType
    metric_type: MetricType
    value: float
    timestamp: float
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.value,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }


@dataclass
class ContentPerformance:
    """Comprehensive content performance analysis"""

    content_id: str
    content_type: ContentType
    title: str
    artist: str
    analysis_period: str

    # Performance metrics
    total_views: int = 0
    total_downloads: int = 0
    total_plays: int = 0
    total_searches: int = 0
    unique_users: int = 0
    avg_engagement_time: float = 0.0
    quality_score: float = 0.0

    # Trend analysis
    daily_views: List[int] = field(default_factory=list)
    hourly_distribution: Dict[int, int] = field(default_factory=dict)
    geographic_distribution: Dict[str, int] = field(default_factory=dict)
    device_distribution: Dict[str, int] = field(default_factory=dict)

    # Rankings and scores
    popularity_rank: int = 0
    trending_score: float = 0.0
    discovery_score: float = 0.0  # How well content is discovered through search
    retention_score: float = 0.0  # User retention and return engagement

    # Insights
    peak_activity_hours: List[int] = field(default_factory=list)
    user_segments: Dict[str, int] = field(default_factory=dict)
    conversion_funnel: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.value,
            "title": self.title,
            "artist": self.artist,
            "analysis_period": self.analysis_period,
            "performance_metrics": {
                "total_views": self.total_views,
                "total_downloads": self.total_downloads,
                "total_plays": self.total_plays,
                "total_searches": self.total_searches,
                "unique_users": self.unique_users,
                "avg_engagement_time": self.avg_engagement_time,
                "quality_score": self.quality_score,
            },
            "trends": {
                "daily_views": self.daily_views,
                "hourly_distribution": self.hourly_distribution,
                "geographic_distribution": self.geographic_distribution,
                "device_distribution": self.device_distribution,
            },
            "scores": {
                "popularity_rank": self.popularity_rank,
                "trending_score": self.trending_score,
                "discovery_score": self.discovery_score,
                "retention_score": self.retention_score,
            },
            "insights": {
                "peak_activity_hours": self.peak_activity_hours,
                "user_segments": self.user_segments,
                "conversion_funnel": self.conversion_funnel,
                "recommendations": self.recommendations,
            },
            "created_at": self.created_at,
        }


@dataclass
class TrendingContent:
    """Trending content analysis"""

    content_id: str
    content_type: ContentType
    title: str
    artist: str
    trending_score: float
    velocity: float  # Rate of growth
    current_rank: int
    previous_rank: int
    rank_change: int
    time_window: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.value,
            "title": self.title,
            "artist": self.artist,
            "trending_score": self.trending_score,
            "velocity": self.velocity,
            "current_rank": self.current_rank,
            "previous_rank": self.previous_rank,
            "rank_change": self.rank_change,
            "time_window": self.time_window,
        }
