"""
Content Analytics Trending - Phase 3 Week 27
Trending content analysis and ranking functions
"""

from datetime import datetime
from typing import Dict, List, Optional

from src.services.analytics_models import ContentPerformance, TrendingContent
from src.services.analytics_scoring import calculate_velocity
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics.trending")


async def update_trending_analysis(
    content_performance: Dict[str, ContentPerformance],
    trending_history: Dict[str, List[TrendingContent]],
    content_metrics: Dict[str, List],
    cache_ttl: int,
) -> List[TrendingContent]:
    """
    Update trending content analysis

    Args:
        content_performance: Dictionary of content performance objects
        trending_history: Dictionary of trending history by time key
        content_metrics: Dictionary of content metrics
        cache_ttl: Cache time-to-live in seconds

    Returns:
        List of trending content items
    """
    try:
        import time

        current_time = time.time()

        # Get all content with recent activity
        trending_candidates = []

        for content_id, performance in content_performance.items():
            if performance.trending_score > 30:  # Minimum threshold
                trending_candidates.append((content_id, performance))

        # Sort by trending score
        trending_candidates.sort(key=lambda x: x[1].trending_score, reverse=True)

        # Create trending content objects
        trending_content = []
        for rank, (content_id, performance) in enumerate(trending_candidates[:50], 1):
            # Get previous rank if available
            previous_rank = get_previous_rank(content_id, trending_history)
            rank_change = previous_rank - rank if previous_rank else 0

            # Get metrics for velocity calculation
            metrics = content_metrics.get(content_id, [])

            trending_item = TrendingContent(
                content_id=content_id,
                content_type=performance.content_type,
                title=performance.title,
                artist=performance.artist,
                trending_score=performance.trending_score,
                velocity=calculate_velocity(content_id, metrics),
                current_rank=rank,
                previous_rank=previous_rank,
                rank_change=rank_change,
                time_window="24h",
            )

            trending_content.append(trending_item)

        # Store trending analysis with time-based key
        time_key = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d_%H")
        trending_history[time_key] = trending_content

        # Cache trending data
        cache_manager = await get_media_cache_manager()
        await cache_manager.set(
            CacheType.MEDIA_METADATA,
            "trending_content_current",
            [item.to_dict() for item in trending_content],
            ttl=cache_ttl,
        )

        logger.info(f"📈 Updated trending analysis with {len(trending_content)} items")
        return trending_content

    except Exception as e:
        logger.error(f"Trending analysis update failed: {e}")
        return []


def get_previous_rank(
    content_id: str, trending_history: Dict[str, List[TrendingContent]]
) -> Optional[int]:
    """
    Get previous rank for content from trending history

    Args:
        content_id: Content identifier
        trending_history: Dictionary of trending history by time key

    Returns:
        Previous rank or None if not found
    """
    try:
        # Get most recent trending data (excluding current)
        sorted_keys = sorted(trending_history.keys(), reverse=True)

        if len(sorted_keys) > 1:
            previous_trending = trending_history[sorted_keys[1]]
            for item in previous_trending:
                if item.content_id == content_id:
                    return item.current_rank

        return None

    except Exception as e:
        logger.debug(f"Failed to get previous rank: {e}")
        return None
