"""
Content Analytics Engine - Phase 3 Week 27
Advanced analytics for music video content performance, discovery patterns, and optimization insights
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import statistics
import hashlib

from src.services.media_cache_manager import get_media_cache_manager, CacheType
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics")


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
            'content_id': self.content_id,
            'content_type': self.content_type.value,
            'metric_type': self.metric_type.value,
            'value': self.value,
            'timestamp': self.timestamp,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'metadata': self.metadata
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
            'content_id': self.content_id,
            'content_type': self.content_type.value,
            'title': self.title,
            'artist': self.artist,
            'analysis_period': self.analysis_period,
            'performance_metrics': {
                'total_views': self.total_views,
                'total_downloads': self.total_downloads,
                'total_plays': self.total_plays,
                'total_searches': self.total_searches,
                'unique_users': self.unique_users,
                'avg_engagement_time': self.avg_engagement_time,
                'quality_score': self.quality_score
            },
            'trends': {
                'daily_views': self.daily_views,
                'hourly_distribution': self.hourly_distribution,
                'geographic_distribution': self.geographic_distribution,
                'device_distribution': self.device_distribution
            },
            'scores': {
                'popularity_rank': self.popularity_rank,
                'trending_score': self.trending_score,
                'discovery_score': self.discovery_score,
                'retention_score': self.retention_score
            },
            'insights': {
                'peak_activity_hours': self.peak_activity_hours,
                'user_segments': self.user_segments,
                'conversion_funnel': self.conversion_funnel,
                'recommendations': self.recommendations
            },
            'created_at': self.created_at
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
            'content_id': self.content_id,
            'content_type': self.content_type.value,
            'title': self.title,
            'artist': self.artist,
            'trending_score': self.trending_score,
            'velocity': self.velocity,
            'current_rank': self.current_rank,
            'previous_rank': self.previous_rank,
            'rank_change': self.rank_change,
            'time_window': self.time_window
        }


class ContentAnalyticsEngine:
    """Advanced content analytics and insights engine"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize content analytics engine"""
        self.config = config or {
            'analysis_interval_minutes': 10,
            'trending_window_hours': 24,
            'quality_score_weight': 0.3,
            'popularity_weight': 0.4,
            'discovery_weight': 0.3,
            'max_metrics_buffer': 50000,
            'cache_ttl': 1800,  # 30 minutes
            'enable_real_time_processing': True
        }
        
        # Data storage
        self.content_metrics = defaultdict(list)  # content_id -> List[ContentMetric]
        self.content_performance: Dict[str, ContentPerformance] = {}
        self.trending_history: Dict[str, List[TrendingContent]] = {}
        
        # Processing state
        self.processing_active = True
        self.last_analysis_time = time.time()
        
        # Performance tracking
        self.stats = {
            'content_analyzed': 0,
            'metrics_processed': 0,
            'trending_updates': 0,
            'total_processing_time': 0.0,
            'insights_generated': 0
        }
        
        # Start background processing
        if self.config['enable_real_time_processing']:
            self._start_background_processing()
        
        logger.info("📈 Content analytics engine initialized")
    
    def _start_background_processing(self):
        """Start background analytics processing"""
        asyncio.create_task(self._analysis_loop())
        asyncio.create_task(self._trending_analysis_loop())
    
    async def _analysis_loop(self):
        """Background content analysis loop"""
        while self.processing_active:
            try:
                await asyncio.sleep(self.config['analysis_interval_minutes'] * 60)
                await self._process_content_analytics()
            except Exception as e:
                logger.error(f"Content analytics processing error: {e}")
    
    async def _trending_analysis_loop(self):
        """Background trending analysis loop"""
        while self.processing_active:
            try:
                await asyncio.sleep(600)  # Every 10 minutes
                await self._update_trending_analysis()
            except Exception as e:
                logger.error(f"Trending analysis error: {e}")
    
    async def record_content_metric(
        self,
        content_id: str,
        content_type: ContentType,
        metric_type: MetricType,
        value: float,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ):
        """
        Record a content performance metric
        
        Args:
            content_id: Unique content identifier
            content_type: Type of content
            metric_type: Type of metric being recorded
            value: Metric value
            user_id: Optional user identifier
            session_id: Optional session identifier
            metadata: Additional context data
        """
        try:
            metric = ContentMetric(
                content_id=content_id,
                content_type=content_type,
                metric_type=metric_type,
                value=value,
                timestamp=time.time(),
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {}
            )
            
            # Store metric
            self.content_metrics[content_id].append(metric)
            
            # Limit buffer size per content
            if len(self.content_metrics[content_id]) > 1000:
                self.content_metrics[content_id] = self.content_metrics[content_id][-500:]
            
            self.stats['metrics_processed'] += 1
            
            # Cache metric for real-time access
            cache_manager = await get_media_cache_manager()
            metric_key = f"content_metric_{content_id}_{int(metric.timestamp)}"
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                metric_key,
                metric.to_dict(),
                ttl=self.config['cache_ttl']
            )
            
            logger.debug(f"📈 Recorded {metric_type.value} metric for content {content_id}")
            
        except Exception as e:
            logger.error(f"Failed to record content metric: {e}")
    
    async def _process_content_analytics(self):
        """Process content analytics and generate performance insights"""
        start_time = time.time()
        
        try:
            content_ids = list(self.content_metrics.keys())
            
            for content_id in content_ids:
                await self._analyze_content_performance(content_id)
            
            # Update processing stats
            processing_time = time.time() - start_time
            self.stats['content_analyzed'] = len(content_ids)
            self.stats['total_processing_time'] += processing_time
            self.last_analysis_time = time.time()
            
            # Track performance
            await track_media_processing_time("content_analytics_processing", processing_time)
            
            logger.info(f"📈 Processed analytics for {len(content_ids)} content items in {processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Content analytics processing failed: {e}")
    
    async def _analyze_content_performance(self, content_id: str) -> ContentPerformance:
        """Analyze performance for a specific content item"""
        try:
            metrics = self.content_metrics.get(content_id, [])
            if not metrics:
                return None
            
            # Get content info from first metric
            first_metric = metrics[0]
            content_type = first_metric.content_type
            
            # Extract content metadata
            title = first_metric.metadata.get('title', 'Unknown Title')
            artist = first_metric.metadata.get('artist', 'Unknown Artist')
            
            # Calculate time window (last 7 days by default)
            current_time = time.time()
            week_ago = current_time - (7 * 24 * 3600)
            recent_metrics = [m for m in metrics if m.timestamp >= week_ago]
            
            if not recent_metrics:
                return None
            
            # Initialize performance object
            performance = ContentPerformance(
                content_id=content_id,
                content_type=content_type,
                title=title,
                artist=artist,
                analysis_period="7_days"
            )
            
            # Calculate basic metrics
            performance.total_views = len([m for m in recent_metrics if m.metric_type == MetricType.VIEWS])
            performance.total_downloads = len([m for m in recent_metrics if m.metric_type == MetricType.DOWNLOADS])
            performance.total_plays = len([m for m in recent_metrics if m.metric_type == MetricType.PLAYS])
            performance.total_searches = len([m for m in recent_metrics if m.metric_type == MetricType.SEARCHES])
            
            # Unique users
            unique_users = set(m.user_id for m in recent_metrics if m.user_id)
            performance.unique_users = len(unique_users)
            
            # Average engagement time
            engagement_metrics = [m for m in recent_metrics if m.metric_type == MetricType.ENGAGEMENT_TIME]
            if engagement_metrics:
                performance.avg_engagement_time = sum(m.value for m in engagement_metrics) / len(engagement_metrics)
            
            # Quality score
            quality_metrics = [m for m in recent_metrics if m.metric_type == MetricType.QUALITY_SCORE]
            if quality_metrics:
                performance.quality_score = statistics.mean(m.value for m in quality_metrics)
            
            # Daily views trend
            daily_counts = defaultdict(int)
            for metric in recent_metrics:
                if metric.metric_type == MetricType.VIEWS:
                    day = datetime.fromtimestamp(metric.timestamp).date()
                    daily_counts[day] += 1
            
            # Fill in missing days with 0
            performance.daily_views = []
            for i in range(7):
                day = (datetime.now() - timedelta(days=i)).date()
                performance.daily_views.insert(0, daily_counts.get(day, 0))
            
            # Hourly distribution
            hourly_counts = defaultdict(int)
            for metric in recent_metrics:
                if metric.metric_type == MetricType.VIEWS:
                    hour = datetime.fromtimestamp(metric.timestamp).hour
                    hourly_counts[hour] += 1
            
            performance.hourly_distribution = dict(hourly_counts)
            
            # Device distribution from metadata
            device_counts = defaultdict(int)
            for metric in recent_metrics:
                device = metric.metadata.get('device_type', 'unknown')
                device_counts[device] += 1
            
            performance.device_distribution = dict(device_counts)
            
            # Calculate scores
            performance.trending_score = self._calculate_trending_score(content_id, recent_metrics)
            performance.discovery_score = self._calculate_discovery_score(recent_metrics)
            performance.retention_score = self._calculate_retention_score(content_id, recent_metrics)
            
            # Peak activity hours
            if hourly_counts:
                sorted_hours = sorted(hourly_counts.items(), key=lambda x: x[1], reverse=True)
                performance.peak_activity_hours = [hour for hour, count in sorted_hours[:3]]
            
            # User segments
            performance.user_segments = self._analyze_user_segments(recent_metrics)
            
            # Conversion funnel
            performance.conversion_funnel = self._calculate_conversion_funnel(recent_metrics)
            
            # Generate recommendations
            performance.recommendations = self._generate_content_recommendations(performance)
            
            # Store performance data
            self.content_performance[content_id] = performance
            
            # Cache performance data
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                f"content_performance_{content_id}",
                performance.to_dict(),
                ttl=self.config['cache_ttl']
            )
            
            return performance
            
        except Exception as e:
            logger.error(f"Failed to analyze content performance for {content_id}: {e}")
            return None
    
    def _calculate_trending_score(self, content_id: str, metrics: List[ContentMetric]) -> float:
        """Calculate trending score based on recent activity velocity"""
        try:
            if len(metrics) < 2:
                return 0.0
            
            # Split into time periods
            current_time = time.time()
            half_period = (current_time - metrics[0].timestamp) / 2
            midpoint = current_time - half_period
            
            recent_activity = len([m for m in metrics if m.timestamp >= midpoint])
            earlier_activity = len([m for m in metrics if m.timestamp < midpoint])
            
            if earlier_activity == 0:
                return 100.0 if recent_activity > 0 else 0.0
            
            # Calculate velocity (rate of change)
            velocity = (recent_activity - earlier_activity) / earlier_activity
            
            # Normalize to 0-100 scale
            trending_score = max(0, min(100, 50 + (velocity * 25)))
            
            return trending_score
            
        except Exception as e:
            logger.error(f"Trending score calculation failed: {e}")
            return 0.0
    
    def _calculate_discovery_score(self, metrics: List[ContentMetric]) -> float:
        """Calculate how well content is discovered through search"""
        try:
            search_count = len([m for m in metrics if m.metric_type == MetricType.SEARCHES])
            view_count = len([m for m in metrics if m.metric_type == MetricType.VIEWS])
            
            if search_count == 0:
                return 0.0
            
            # Discovery score = searches that led to views
            discovery_ratio = min(view_count / search_count, 1.0) if search_count > 0 else 0.0
            
            return discovery_ratio * 100
            
        except Exception as e:
            logger.error(f"Discovery score calculation failed: {e}")
            return 0.0
    
    def _calculate_retention_score(self, content_id: str, metrics: List[ContentMetric]) -> float:
        """Calculate user retention and return engagement"""
        try:
            # Get unique users and their interaction patterns
            user_interactions = defaultdict(list)
            for metric in metrics:
                if metric.user_id:
                    user_interactions[metric.user_id].append(metric)
            
            if not user_interactions:
                return 0.0
            
            # Calculate return users (users with multiple sessions)
            return_users = 0
            total_users = len(user_interactions)
            
            for user_id, user_metrics in user_interactions.items():
                sessions = set(m.session_id for m in user_metrics if m.session_id)
                if len(sessions) > 1:
                    return_users += 1
            
            retention_ratio = return_users / total_users if total_users > 0 else 0.0
            return retention_ratio * 100
            
        except Exception as e:
            logger.error(f"Retention score calculation failed: {e}")
            return 0.0
    
    def _analyze_user_segments(self, metrics: List[ContentMetric]) -> Dict[str, int]:
        """Analyze user segments based on engagement patterns"""
        try:
            user_engagement = defaultdict(int)
            for metric in metrics:
                if metric.user_id and metric.metric_type in [MetricType.VIEWS, MetricType.PLAYS, MetricType.DOWNLOADS]:
                    user_engagement[metric.user_id] += 1
            
            # Segment users by engagement level
            segments = {
                'high_engagement': 0,  # 10+ interactions
                'medium_engagement': 0,  # 3-9 interactions
                'low_engagement': 0,  # 1-2 interactions
                'single_interaction': 0  # 1 interaction
            }
            
            for user_id, interaction_count in user_engagement.items():
                if interaction_count >= 10:
                    segments['high_engagement'] += 1
                elif interaction_count >= 3:
                    segments['medium_engagement'] += 1
                elif interaction_count >= 2:
                    segments['low_engagement'] += 1
                else:
                    segments['single_interaction'] += 1
            
            return segments
            
        except Exception as e:
            logger.error(f"User segment analysis failed: {e}")
            return {}
    
    def _calculate_conversion_funnel(self, metrics: List[ContentMetric]) -> Dict[str, float]:
        """Calculate conversion funnel from discovery to engagement"""
        try:
            funnel_counts = {
                'searches': len([m for m in metrics if m.metric_type == MetricType.SEARCHES]),
                'views': len([m for m in metrics if m.metric_type == MetricType.VIEWS]),
                'plays': len([m for m in metrics if m.metric_type == MetricType.PLAYS]),
                'downloads': len([m for m in metrics if m.metric_type == MetricType.DOWNLOADS])
            }
            
            # Calculate conversion rates
            total_searches = funnel_counts['searches']
            if total_searches == 0:
                return {}
            
            conversion_rates = {
                'search_to_view': (funnel_counts['views'] / total_searches) * 100,
                'view_to_play': (funnel_counts['plays'] / max(funnel_counts['views'], 1)) * 100,
                'play_to_download': (funnel_counts['downloads'] / max(funnel_counts['plays'], 1)) * 100
            }
            
            return conversion_rates
            
        except Exception as e:
            logger.error(f"Conversion funnel calculation failed: {e}")
            return {}
    
    def _generate_content_recommendations(self, performance: ContentPerformance) -> List[str]:
        """Generate optimization recommendations based on performance data"""
        recommendations = []
        
        try:
            # Low engagement recommendations
            if performance.avg_engagement_time < 30:  # Less than 30 seconds
                recommendations.append("Consider improving content quality or thumbnail to increase engagement time")
            
            # Discovery recommendations
            if performance.discovery_score < 50:
                recommendations.append("Optimize tags and metadata to improve discoverability through search")
            
            # Trending recommendations
            if performance.trending_score > 70:
                recommendations.append("Content is trending - consider promoting or creating similar content")
            elif performance.trending_score < 30:
                recommendations.append("Consider refreshing content or improving promotional strategy")
            
            # Quality score recommendations
            if performance.quality_score < 60:
                recommendations.append("Consider improving video quality or technical specifications")
            
            # User retention recommendations
            if performance.retention_score < 40:
                recommendations.append("Focus on creating more engaging content to improve user retention")
            
            # Peak hours optimization
            if performance.peak_activity_hours:
                peak_hours_str = ', '.join(str(h) for h in performance.peak_activity_hours)
                recommendations.append(f"Optimize content promotion for peak hours: {peak_hours_str}")
            
            # Device optimization
            if 'mobile' in performance.device_distribution and performance.device_distribution['mobile'] > 50:
                recommendations.append("Optimize content for mobile viewing experience")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return ["Unable to generate specific recommendations"]
    
    async def _update_trending_analysis(self):
        """Update trending content analysis"""
        try:
            current_time = time.time()
            
            # Get all content with recent activity
            trending_candidates = []
            
            for content_id, performance in self.content_performance.items():
                if performance.trending_score > 30:  # Minimum threshold
                    trending_candidates.append((content_id, performance))
            
            # Sort by trending score
            trending_candidates.sort(key=lambda x: x[1].trending_score, reverse=True)
            
            # Create trending content objects
            trending_content = []
            for rank, (content_id, performance) in enumerate(trending_candidates[:50], 1):
                # Get previous rank if available
                previous_rank = self._get_previous_rank(content_id)
                rank_change = previous_rank - rank if previous_rank else 0
                
                trending_item = TrendingContent(
                    content_id=content_id,
                    content_type=performance.content_type,
                    title=performance.title,
                    artist=performance.artist,
                    trending_score=performance.trending_score,
                    velocity=self._calculate_velocity(content_id),
                    current_rank=rank,
                    previous_rank=previous_rank,
                    rank_change=rank_change,
                    time_window="24h"
                )
                
                trending_content.append(trending_item)
            
            # Store trending analysis
            time_key = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d_%H")
            self.trending_history[time_key] = trending_content
            
            # Cache trending data
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                "trending_content_current",
                [item.to_dict() for item in trending_content],
                ttl=self.config['cache_ttl']
            )
            
            self.stats['trending_updates'] += 1
            logger.info(f"📈 Updated trending analysis with {len(trending_content)} items")
            
        except Exception as e:
            logger.error(f"Trending analysis update failed: {e}")
    
    def _get_previous_rank(self, content_id: str) -> Optional[int]:
        """Get previous rank for content from trending history"""
        try:
            # Get most recent trending data (excluding current)
            sorted_keys = sorted(self.trending_history.keys(), reverse=True)
            
            if len(sorted_keys) > 1:
                previous_trending = self.trending_history[sorted_keys[1]]
                for item in previous_trending:
                    if item.content_id == content_id:
                        return item.current_rank
            
            return None
            
        except Exception as e:
            logger.debug(f"Failed to get previous rank: {e}")
            return None
    
    def _calculate_velocity(self, content_id: str) -> float:
        """Calculate content velocity (rate of growth)"""
        try:
            metrics = self.content_metrics.get(content_id, [])
            if len(metrics) < 2:
                return 0.0
            
            # Calculate recent vs older activity
            current_time = time.time()
            day_ago = current_time - (24 * 3600)
            two_days_ago = current_time - (48 * 3600)
            
            recent_activity = len([m for m in metrics if m.timestamp >= day_ago])
            previous_activity = len([m for m in metrics if two_days_ago <= m.timestamp < day_ago])
            
            if previous_activity == 0:
                return 100.0 if recent_activity > 0 else 0.0
            
            velocity = ((recent_activity - previous_activity) / previous_activity) * 100
            return round(velocity, 2)
            
        except Exception as e:
            logger.error(f"Velocity calculation failed: {e}")
            return 0.0
    
    async def get_content_performance(self, content_id: str) -> Optional[ContentPerformance]:
        """Get performance analysis for specific content"""
        # Check cache first
        cache_manager = await get_media_cache_manager()
        cached_performance = await cache_manager.get(
            CacheType.MEDIA_METADATA,
            f"content_performance_{content_id}"
        )
        
        if cached_performance:
            cached_performance['content_type'] = ContentType(cached_performance['content_type'])
            return ContentPerformance(**cached_performance)
        
        # Generate fresh analysis
        return await self._analyze_content_performance(content_id)
    
    async def get_trending_content(self, limit: int = 20) -> List[TrendingContent]:
        """Get current trending content"""
        # Check cache first
        cache_manager = await get_media_cache_manager()
        cached_trending = await cache_manager.get(CacheType.MEDIA_METADATA, "trending_content_current")
        
        if cached_trending:
            trending_items = []
            for item_data in cached_trending[:limit]:
                item_data['content_type'] = ContentType(item_data['content_type'])
                trending_items.append(TrendingContent(**item_data))
            return trending_items
        
        return []
    
    async def get_popular_content(
        self,
        content_type: Optional[ContentType] = None,
        time_window: TimeWindow = TimeWindow.LAST_WEEK,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get popular content based on various metrics"""
        try:
            # Calculate time cutoff
            current_time = time.time()
            time_cutoffs = {
                TimeWindow.LAST_HOUR: current_time - 3600,
                TimeWindow.LAST_DAY: current_time - (24 * 3600),
                TimeWindow.LAST_WEEK: current_time - (7 * 24 * 3600),
                TimeWindow.LAST_MONTH: current_time - (30 * 24 * 3600),
                TimeWindow.ALL_TIME: 0
            }
            
            cutoff_time = time_cutoffs.get(time_window, current_time - (7 * 24 * 3600))
            
            # Collect popularity scores
            content_scores = []
            
            for content_id, performance in self.content_performance.items():
                if content_type and performance.content_type != content_type:
                    continue
                
                # Calculate popularity score
                weights = self.config
                popularity_score = (
                    performance.total_views * 0.4 +
                    performance.total_plays * 0.3 +
                    performance.total_downloads * 0.2 +
                    performance.unique_users * 0.1
                )
                
                content_scores.append({
                    'content_id': content_id,
                    'title': performance.title,
                    'artist': performance.artist,
                    'content_type': performance.content_type.value,
                    'popularity_score': popularity_score,
                    'total_views': performance.total_views,
                    'total_plays': performance.total_plays,
                    'total_downloads': performance.total_downloads,
                    'unique_users': performance.unique_users,
                    'quality_score': performance.quality_score,
                    'trending_score': performance.trending_score
                })
            
            # Sort by popularity score
            content_scores.sort(key=lambda x: x['popularity_score'], reverse=True)
            
            return content_scores[:limit]
            
        except Exception as e:
            logger.error(f"Popular content analysis failed: {e}")
            return []
    
    async def get_content_insights(self, content_id: str) -> Dict[str, Any]:
        """Get comprehensive insights for specific content"""
        try:
            performance = await self.get_content_performance(content_id)
            if not performance:
                return {'error': 'Content not found or insufficient data'}
            
            # Get related metrics
            metrics = self.content_metrics.get(content_id, [])
            recent_metrics = [m for m in metrics if m.timestamp >= (time.time() - (7 * 24 * 3600))]
            
            # Calculate additional insights
            user_journey = self._analyze_user_journey(recent_metrics)
            competitive_analysis = await self._get_competitive_analysis(performance)
            optimization_opportunities = self._identify_optimization_opportunities(performance)
            
            return {
                'content_id': content_id,
                'performance_summary': performance.to_dict(),
                'user_journey': user_journey,
                'competitive_analysis': competitive_analysis,
                'optimization_opportunities': optimization_opportunities,
                'generated_at': time.time()
            }
            
        except Exception as e:
            logger.error(f"Content insights generation failed: {e}")
            return {'error': str(e)}
    
    def _analyze_user_journey(self, metrics: List[ContentMetric]) -> Dict[str, Any]:
        """Analyze user journey patterns"""
        try:
            user_journeys = defaultdict(list)
            for metric in metrics:
                if metric.user_id:
                    user_journeys[metric.user_id].append(metric)
            
            # Analyze common journey patterns
            journey_patterns = {
                'search_to_view': 0,
                'view_to_play': 0,
                'play_to_download': 0,
                'direct_play': 0,  # Play without search/view
                'return_users': 0
            }
            
            for user_id, user_metrics in user_journeys.items():
                user_metrics.sort(key=lambda m: m.timestamp)
                
                # Check for return users
                sessions = set(m.session_id for m in user_metrics if m.session_id)
                if len(sessions) > 1:
                    journey_patterns['return_users'] += 1
                
                # Analyze action sequences
                metric_types = [m.metric_type for m in user_metrics]
                
                if MetricType.SEARCHES in metric_types and MetricType.VIEWS in metric_types:
                    journey_patterns['search_to_view'] += 1
                
                if MetricType.VIEWS in metric_types and MetricType.PLAYS in metric_types:
                    journey_patterns['view_to_play'] += 1
                
                if MetricType.PLAYS in metric_types and MetricType.DOWNLOADS in metric_types:
                    journey_patterns['play_to_download'] += 1
                
                if MetricType.PLAYS in metric_types and MetricType.SEARCHES not in metric_types:
                    journey_patterns['direct_play'] += 1
            
            return {
                'total_users': len(user_journeys),
                'journey_patterns': journey_patterns,
                'avg_actions_per_user': sum(len(journey) for journey in user_journeys.values()) / len(user_journeys) if user_journeys else 0
            }
            
        except Exception as e:
            logger.error(f"User journey analysis failed: {e}")
            return {}
    
    async def _get_competitive_analysis(self, performance: ContentPerformance) -> Dict[str, Any]:
        """Get competitive analysis for content"""
        try:
            # Compare with similar content (same artist or genre)
            similar_content = []
            
            for content_id, other_performance in self.content_performance.items():
                if (content_id != performance.content_id and 
                    other_performance.artist == performance.artist):
                    similar_content.append(other_performance)
            
            if not similar_content:
                return {'message': 'No similar content found for comparison'}
            
            # Calculate comparative metrics
            avg_views = statistics.mean(p.total_views for p in similar_content)
            avg_engagement = statistics.mean(p.avg_engagement_time for p in similar_content)
            avg_quality = statistics.mean(p.quality_score for p in similar_content)
            
            return {
                'similar_content_count': len(similar_content),
                'performance_vs_average': {
                    'views': {
                        'current': performance.total_views,
                        'average': avg_views,
                        'relative_performance': (performance.total_views / avg_views - 1) * 100 if avg_views > 0 else 0
                    },
                    'engagement_time': {
                        'current': performance.avg_engagement_time,
                        'average': avg_engagement,
                        'relative_performance': (performance.avg_engagement_time / avg_engagement - 1) * 100 if avg_engagement > 0 else 0
                    },
                    'quality_score': {
                        'current': performance.quality_score,
                        'average': avg_quality,
                        'relative_performance': (performance.quality_score / avg_quality - 1) * 100 if avg_quality > 0 else 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Competitive analysis failed: {e}")
            return {}
    
    def _identify_optimization_opportunities(self, performance: ContentPerformance) -> List[Dict[str, Any]]:
        """Identify specific optimization opportunities"""
        opportunities = []
        
        try:
            # Low conversion opportunity
            if 'search_to_view' in performance.conversion_funnel:
                search_to_view_rate = performance.conversion_funnel['search_to_view']
                if search_to_view_rate < 30:
                    opportunities.append({
                        'type': 'conversion_optimization',
                        'priority': 'high',
                        'issue': 'Low search-to-view conversion',
                        'current_rate': f"{search_to_view_rate:.1f}%",
                        'recommendation': 'Improve thumbnails and titles to increase click-through rate'
                    })
            
            # Quality improvement opportunity
            if performance.quality_score < 70:
                opportunities.append({
                    'type': 'quality_improvement',
                    'priority': 'medium',
                    'issue': 'Below-average quality score',
                    'current_score': performance.quality_score,
                    'recommendation': 'Consider video quality enhancement or better source material'
                })
            
            # Engagement improvement opportunity
            if performance.avg_engagement_time < 45:  # Less than 45 seconds
                opportunities.append({
                    'type': 'engagement_optimization',
                    'priority': 'high',
                    'issue': 'Low average engagement time',
                    'current_time': f"{performance.avg_engagement_time:.1f}s",
                    'recommendation': 'Optimize content to capture attention within first 15 seconds'
                })
            
            # Discovery optimization opportunity
            if performance.discovery_score < 40:
                opportunities.append({
                    'type': 'discovery_optimization',
                    'priority': 'medium',
                    'issue': 'Low discoverability through search',
                    'current_score': performance.discovery_score,
                    'recommendation': 'Improve metadata, tags, and search keywords'
                })
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Optimization opportunity identification failed: {e}")
            return []
    
    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get content analytics engine statistics"""
        try:
            return {
                "service": "Content Analytics Engine",
                "status": "active" if self.processing_active else "inactive",
                "stats": self.stats,
                "configuration": self.config,
                "data_status": {
                    "content_items_tracked": len(self.content_metrics),
                    "total_metrics": sum(len(metrics) for metrics in self.content_metrics.values()),
                    "performance_analyses": len(self.content_performance),
                    "trending_history_entries": len(self.trending_history)
                },
                "capabilities": {
                    "performance_analysis": True,
                    "trending_analysis": True,
                    "user_journey_tracking": True,
                    "competitive_analysis": True,
                    "optimization_recommendations": True
                }
            }
        except Exception as e:
            logger.error(f"Failed to get service statistics: {e}")
            return {"service": "Content Analytics Engine", "error": str(e)}


# Global content analytics engine instance
_content_analytics_engine: Optional[ContentAnalyticsEngine] = None

async def get_content_analytics_engine(config: Optional[Dict[str, Any]] = None) -> ContentAnalyticsEngine:
    """Get or create global content analytics engine instance"""
    global _content_analytics_engine
    
    if _content_analytics_engine is None:
        _content_analytics_engine = ContentAnalyticsEngine(config)
    
    return _content_analytics_engine


# Convenience functions for recording common content metrics
async def record_video_view(content_id: str, user_id: str, session_id: str, metadata: Dict[str, Any] = None):
    """Record a video view"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.VIEWS,
        value=1.0,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata
    )


async def record_video_download(content_id: str, user_id: str, session_id: str, metadata: Dict[str, Any] = None):
    """Record a video download"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.DOWNLOADS,
        value=1.0,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata
    )


async def record_engagement_time(content_id: str, engagement_seconds: float, user_id: str, session_id: str):
    """Record user engagement time"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.ENGAGEMENT_TIME,
        value=engagement_seconds,
        user_id=user_id,
        session_id=session_id
    )