"""
Content Analytics Performance - Phase 3 Week 27
Performance analysis function for content items
"""

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from src.services.analytics_analysis import (
    analyze_user_segments,
    calculate_conversion_funnel,
    generate_content_recommendations,
)
from src.services.analytics_models import (
    ContentMetric,
    ContentPerformance,
    MetricType,
)
from src.services.analytics_scoring import (
    calculate_discovery_score,
    calculate_retention_score,
    calculate_trending_score,
)
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics.performance")


async def analyze_content_performance(
    content_id: str,
    content_metrics: dict,
    content_performance: dict,
    cache_ttl: int,
) -> Optional[ContentPerformance]:
    """
    Analyze performance for a specific content item

    Args:
        content_id: Content identifier
        content_metrics: Dictionary of all content metrics
        content_performance: Dictionary to store performance results
        cache_ttl: Cache time-to-live in seconds

    Returns:
        ContentPerformance object or None if insufficient data
    """
    try:
        metrics = content_metrics.get(content_id, [])
        if not metrics:
            return None

        # Get content info from first metric
        first_metric = metrics[0]
        content_type = first_metric.content_type

        # Extract content metadata
        title = first_metric.metadata.get("title", "Unknown Title")
        artist = first_metric.metadata.get("artist", "Unknown Artist")

        # Calculate time window (last 7 days by default)
        import time

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
            analysis_period="7_days",
        )

        # Calculate basic metrics
        performance.total_views = len(
            [m for m in recent_metrics if m.metric_type == MetricType.VIEWS]
        )
        performance.total_downloads = len(
            [m for m in recent_metrics if m.metric_type == MetricType.DOWNLOADS]
        )
        performance.total_plays = len(
            [m for m in recent_metrics if m.metric_type == MetricType.PLAYS]
        )
        performance.total_searches = len(
            [m for m in recent_metrics if m.metric_type == MetricType.SEARCHES]
        )

        # Unique users
        unique_users = set(m.user_id for m in recent_metrics if m.user_id)
        performance.unique_users = len(unique_users)

        # Average engagement time
        engagement_metrics = [
            m for m in recent_metrics if m.metric_type == MetricType.ENGAGEMENT_TIME
        ]
        if engagement_metrics:
            performance.avg_engagement_time = sum(
                m.value for m in engagement_metrics
            ) / len(engagement_metrics)

        # Quality score
        quality_metrics = [
            m for m in recent_metrics if m.metric_type == MetricType.QUALITY_SCORE
        ]
        if quality_metrics:
            performance.quality_score = statistics.mean(
                m.value for m in quality_metrics
            )

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
            device = metric.metadata.get("device_type", "unknown")
            device_counts[device] += 1

        performance.device_distribution = dict(device_counts)

        # Calculate scores
        performance.trending_score = calculate_trending_score(
            content_id, recent_metrics
        )
        performance.discovery_score = calculate_discovery_score(recent_metrics)
        performance.retention_score = calculate_retention_score(
            content_id, recent_metrics
        )

        # Peak activity hours
        if hourly_counts:
            sorted_hours = sorted(
                hourly_counts.items(), key=lambda x: x[1], reverse=True
            )
            performance.peak_activity_hours = [hour for hour, count in sorted_hours[:3]]

        # User segments
        performance.user_segments = analyze_user_segments(recent_metrics)

        # Conversion funnel
        performance.conversion_funnel = calculate_conversion_funnel(recent_metrics)

        # Generate recommendations
        performance.recommendations = generate_content_recommendations(performance)

        # Store performance data
        content_performance[content_id] = performance

        # Cache performance data
        cache_manager = await get_media_cache_manager()
        await cache_manager.set(
            CacheType.MEDIA_METADATA,
            f"content_performance_{content_id}",
            performance.to_dict(),
            ttl=cache_ttl,
        )

        return performance

    except Exception as e:
        logger.error(f"Failed to analyze content performance for {content_id}: {e}")
        return None
