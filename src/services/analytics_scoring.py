"""
Content Analytics Scoring - Phase 3 Week 27
Score calculation functions for trending, discovery, and retention analysis
"""

import time
from collections import defaultdict
from typing import List, Optional

from src.services.analytics_models import ContentMetric
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics.scoring")


def calculate_trending_score(content_id: str, metrics: List[ContentMetric]) -> float:
    """
    Calculate trending score based on recent activity velocity

    Args:
        content_id: Content identifier
        metrics: List of content metrics

    Returns:
        Trending score (0-100)
    """
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


def calculate_discovery_score(metrics: List[ContentMetric]) -> float:
    """
    Calculate how well content is discovered through search

    Args:
        metrics: List of content metrics

    Returns:
        Discovery score (0-100)
    """
    try:
        from src.services.analytics_models import MetricType

        search_count = len([m for m in metrics if m.metric_type == MetricType.SEARCHES])
        view_count = len([m for m in metrics if m.metric_type == MetricType.VIEWS])

        if search_count == 0:
            return 0.0

        # Discovery score = searches that led to views
        discovery_ratio = (
            min(view_count / search_count, 1.0) if search_count > 0 else 0.0
        )

        return discovery_ratio * 100

    except Exception as e:
        logger.error(f"Discovery score calculation failed: {e}")
        return 0.0


def calculate_retention_score(content_id: str, metrics: List[ContentMetric]) -> float:
    """
    Calculate user retention and return engagement

    Args:
        content_id: Content identifier
        metrics: List of content metrics

    Returns:
        Retention score (0-100)
    """
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


def calculate_velocity(content_id: str, metrics: List[ContentMetric]) -> float:
    """
    Calculate content velocity (rate of growth)

    Args:
        content_id: Content identifier
        metrics: List of content metrics

    Returns:
        Velocity percentage
    """
    try:
        if len(metrics) < 2:
            return 0.0

        # Calculate recent vs older activity
        current_time = time.time()
        day_ago = current_time - (24 * 3600)
        two_days_ago = current_time - (48 * 3600)

        recent_activity = len([m for m in metrics if m.timestamp >= day_ago])
        previous_activity = len(
            [m for m in metrics if two_days_ago <= m.timestamp < day_ago]
        )

        if previous_activity == 0:
            return 100.0 if recent_activity > 0 else 0.0

        velocity = ((recent_activity - previous_activity) / previous_activity) * 100
        return round(velocity, 2)

    except Exception as e:
        logger.error(f"Velocity calculation failed: {e}")
        return 0.0
