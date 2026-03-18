"""
Content Analytics Engine - Phase 3 Week 27
Advanced analytics for music video content performance, discovery patterns, and optimization insights

Refactored into modular architecture for maintainability and scalability.
"""

import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.services.analytics_analysis import analyze_user_journey
from src.services.analytics_insights import (
    get_competitive_analysis,
    identify_optimization_opportunities,
)
from src.services.analytics_models import (
    ContentMetric,
    ContentPerformance,
    ContentType,
    MetricType,
    TimeWindow,
    TrendingContent,
)
from src.services.analytics_performance import analyze_content_performance
from src.services.analytics_trending import update_trending_analysis
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics")


class ContentAnalyticsEngine:
    """Advanced content analytics and insights engine"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize content analytics engine"""
        self.config = config or {
            "analysis_interval_minutes": 10,
            "trending_window_hours": 24,
            "quality_score_weight": 0.3,
            "popularity_weight": 0.4,
            "discovery_weight": 0.3,
            "max_metrics_buffer": 50000,
            "cache_ttl": 1800,  # 30 minutes
            "enable_real_time_processing": True,
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
            "content_analyzed": 0,
            "metrics_processed": 0,
            "trending_updates": 0,
            "total_processing_time": 0.0,
            "insights_generated": 0,
        }

        # Start background processing
        if self.config["enable_real_time_processing"]:
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
                await asyncio.sleep(self.config["analysis_interval_minutes"] * 60)
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
        metadata: Dict[str, Any] = None,
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
                metadata=metadata or {},
            )

            # Store metric
            self.content_metrics[content_id].append(metric)

            # Limit buffer size per content
            if len(self.content_metrics[content_id]) > 1000:
                self.content_metrics[content_id] = self.content_metrics[content_id][
                    -500:
                ]

            self.stats["metrics_processed"] += 1

            # Cache metric for real-time access
            cache_manager = await get_media_cache_manager()
            metric_key = f"content_metric_{content_id}_{int(metric.timestamp)}"
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                metric_key,
                metric.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            logger.debug(
                f"📈 Recorded {metric_type.value} metric for content {content_id}"
            )

        except Exception as e:
            logger.error(f"Failed to record content metric: {e}")

    async def _process_content_analytics(self):
        """Process content analytics and generate performance insights"""
        start_time = time.time()

        try:
            content_ids = list(self.content_metrics.keys())

            for content_id in content_ids:
                await analyze_content_performance(
                    content_id,
                    self.content_metrics,
                    self.content_performance,
                    self.config["cache_ttl"],
                )

            # Update processing stats
            processing_time = time.time() - start_time
            self.stats["content_analyzed"] = len(content_ids)
            self.stats["total_processing_time"] += processing_time
            self.last_analysis_time = time.time()

            # Track performance
            await track_media_processing_time(
                "content_analytics_processing", processing_time
            )

            logger.info(
                f"📈 Processed analytics for {len(content_ids)} content items in {processing_time:.2f}s"
            )

        except Exception as e:
            logger.error(f"Content analytics processing failed: {e}")

    async def _update_trending_analysis(self):
        """Update trending content analysis"""
        try:
            trending_content = await update_trending_analysis(
                self.content_performance,
                self.trending_history,
                self.content_metrics,
                self.config["cache_ttl"],
            )

            self.stats["trending_updates"] += 1

        except Exception as e:
            logger.error(f"Trending analysis update failed: {e}")

    async def get_content_performance(
        self, content_id: str
    ) -> Optional[ContentPerformance]:
        """Get performance analysis for specific content"""
        # Check cache first
        cache_manager = await get_media_cache_manager()
        cached_performance = await cache_manager.get(
            CacheType.MEDIA_METADATA, f"content_performance_{content_id}"
        )

        if cached_performance:
            cached_performance["content_type"] = ContentType(
                cached_performance["content_type"]
            )
            return ContentPerformance(**cached_performance)

        # Generate fresh analysis
        return await analyze_content_performance(
            content_id,
            self.content_metrics,
            self.content_performance,
            self.config["cache_ttl"],
        )

    async def get_trending_content(self, limit: int = 20) -> List[TrendingContent]:
        """Get current trending content"""
        # Check cache first
        cache_manager = await get_media_cache_manager()
        cached_trending = await cache_manager.get(
            CacheType.MEDIA_METADATA, "trending_content_current"
        )

        if cached_trending:
            trending_items = []
            for item_data in cached_trending[:limit]:
                item_data["content_type"] = ContentType(item_data["content_type"])
                trending_items.append(TrendingContent(**item_data))
            return trending_items

        return []

    async def get_popular_content(
        self,
        content_type: Optional[ContentType] = None,
        time_window: TimeWindow = TimeWindow.LAST_WEEK,
        limit: int = 20,
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
                TimeWindow.ALL_TIME: 0,
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
                    performance.total_views * 0.4
                    + performance.total_plays * 0.3
                    + performance.total_downloads * 0.2
                    + performance.unique_users * 0.1
                )

                content_scores.append(
                    {
                        "content_id": content_id,
                        "title": performance.title,
                        "artist": performance.artist,
                        "content_type": performance.content_type.value,
                        "popularity_score": popularity_score,
                        "total_views": performance.total_views,
                        "total_plays": performance.total_plays,
                        "total_downloads": performance.total_downloads,
                        "unique_users": performance.unique_users,
                        "quality_score": performance.quality_score,
                        "trending_score": performance.trending_score,
                    }
                )

            # Sort by popularity score
            content_scores.sort(key=lambda x: x["popularity_score"], reverse=True)

            return content_scores[:limit]

        except Exception as e:
            logger.error(f"Popular content analysis failed: {e}")
            return []

    async def get_content_insights(self, content_id: str) -> Dict[str, Any]:
        """Get comprehensive insights for specific content"""
        try:
            performance = await self.get_content_performance(content_id)
            if not performance:
                return {"error": "Content not found or insufficient data"}

            # Get related metrics
            metrics = self.content_metrics.get(content_id, [])
            recent_metrics = [
                m for m in metrics if m.timestamp >= (time.time() - (7 * 24 * 3600))
            ]

            # Calculate additional insights
            user_journey = analyze_user_journey(recent_metrics)
            competitive_analysis = await get_competitive_analysis(
                performance, self.content_performance
            )
            optimization_opportunities = identify_optimization_opportunities(
                performance
            )

            self.stats["insights_generated"] += 1

            return {
                "content_id": content_id,
                "performance_summary": performance.to_dict(),
                "user_journey": user_journey,
                "competitive_analysis": competitive_analysis,
                "optimization_opportunities": optimization_opportunities,
                "generated_at": time.time(),
            }

        except Exception as e:
            logger.error(f"Content insights generation failed: {e}")
            return {"error": str(e)}

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
                    "total_metrics": sum(
                        len(metrics) for metrics in self.content_metrics.values()
                    ),
                    "performance_analyses": len(self.content_performance),
                    "trending_history_entries": len(self.trending_history),
                },
                "capabilities": {
                    "performance_analysis": True,
                    "trending_analysis": True,
                    "user_journey_tracking": True,
                    "competitive_analysis": True,
                    "optimization_recommendations": True,
                },
            }
        except Exception as e:
            logger.error(f"Failed to get service statistics: {e}")
            return {"service": "Content Analytics Engine", "error": str(e)}


# Global content analytics engine instance
_content_analytics_engine: Optional[ContentAnalyticsEngine] = None


async def get_content_analytics_engine(
    config: Optional[Dict[str, Any]] = None,
) -> ContentAnalyticsEngine:
    """Get or create global content analytics engine instance"""
    global _content_analytics_engine

    if _content_analytics_engine is None:
        _content_analytics_engine = ContentAnalyticsEngine(config)

    return _content_analytics_engine


# Convenience functions for recording common content metrics
async def record_video_view(
    content_id: str, user_id: str, session_id: str, metadata: Dict[str, Any] = None
):
    """Record a video view"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.VIEWS,
        value=1.0,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )


async def record_video_download(
    content_id: str, user_id: str, session_id: str, metadata: Dict[str, Any] = None
):
    """Record a video download"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.DOWNLOADS,
        value=1.0,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )


async def record_engagement_time(
    content_id: str, engagement_seconds: float, user_id: str, session_id: str
):
    """Record user engagement time"""
    engine = await get_content_analytics_engine()
    return await engine.record_content_metric(
        content_id=content_id,
        content_type=ContentType.MUSIC_VIDEO,
        metric_type=MetricType.ENGAGEMENT_TIME,
        value=engagement_seconds,
        user_id=user_id,
        session_id=session_id,
    )
