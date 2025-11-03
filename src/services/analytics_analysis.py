"""
Content Analytics Analysis - Phase 3 Week 27
Analysis functions for user segments, conversion funnel, user journey, and recommendations
"""

from collections import defaultdict
from typing import Dict, List

from src.services.analytics_models import ContentMetric, ContentPerformance, MetricType
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics.analysis")


def analyze_user_segments(metrics: List[ContentMetric]) -> Dict[str, int]:
    """
    Analyze user segments based on engagement patterns

    Args:
        metrics: List of content metrics

    Returns:
        Dictionary of user segment counts
    """
    try:
        user_engagement = defaultdict(int)
        for metric in metrics:
            if metric.user_id and metric.metric_type in [
                MetricType.VIEWS,
                MetricType.PLAYS,
                MetricType.DOWNLOADS,
            ]:
                user_engagement[metric.user_id] += 1

        # Segment users by engagement level
        segments = {
            "high_engagement": 0,  # 10+ interactions
            "medium_engagement": 0,  # 3-9 interactions
            "low_engagement": 0,  # 1-2 interactions
            "single_interaction": 0,  # 1 interaction
        }

        for user_id, interaction_count in user_engagement.items():
            if interaction_count >= 10:
                segments["high_engagement"] += 1
            elif interaction_count >= 3:
                segments["medium_engagement"] += 1
            elif interaction_count >= 2:
                segments["low_engagement"] += 1
            else:
                segments["single_interaction"] += 1

        return segments

    except Exception as e:
        logger.error(f"User segment analysis failed: {e}")
        return {}


def calculate_conversion_funnel(metrics: List[ContentMetric]) -> Dict[str, float]:
    """
    Calculate conversion funnel from discovery to engagement

    Args:
        metrics: List of content metrics

    Returns:
        Dictionary of conversion rates
    """
    try:
        funnel_counts = {
            "searches": len(
                [m for m in metrics if m.metric_type == MetricType.SEARCHES]
            ),
            "views": len([m for m in metrics if m.metric_type == MetricType.VIEWS]),
            "plays": len([m for m in metrics if m.metric_type == MetricType.PLAYS]),
            "downloads": len(
                [m for m in metrics if m.metric_type == MetricType.DOWNLOADS]
            ),
        }

        # Calculate conversion rates
        total_searches = funnel_counts["searches"]
        if total_searches == 0:
            return {}

        conversion_rates = {
            "search_to_view": (funnel_counts["views"] / total_searches) * 100,
            "view_to_play": (funnel_counts["plays"] / max(funnel_counts["views"], 1))
            * 100,
            "play_to_download": (
                funnel_counts["downloads"] / max(funnel_counts["plays"], 1)
            )
            * 100,
        }

        return conversion_rates

    except Exception as e:
        logger.error(f"Conversion funnel calculation failed: {e}")
        return {}


def analyze_user_journey(metrics: List[ContentMetric]) -> Dict[str, any]:
    """
    Analyze user journey patterns

    Args:
        metrics: List of content metrics

    Returns:
        Dictionary containing user journey analysis
    """
    try:
        user_journeys = defaultdict(list)
        for metric in metrics:
            if metric.user_id:
                user_journeys[metric.user_id].append(metric)

        # Analyze common journey patterns
        journey_patterns = {
            "search_to_view": 0,
            "view_to_play": 0,
            "play_to_download": 0,
            "direct_play": 0,  # Play without search/view
            "return_users": 0,
        }

        for user_id, user_metrics in user_journeys.items():
            user_metrics.sort(key=lambda m: m.timestamp)

            # Check for return users
            sessions = set(m.session_id for m in user_metrics if m.session_id)
            if len(sessions) > 1:
                journey_patterns["return_users"] += 1

            # Analyze action sequences
            metric_types = [m.metric_type for m in user_metrics]

            if MetricType.SEARCHES in metric_types and MetricType.VIEWS in metric_types:
                journey_patterns["search_to_view"] += 1

            if MetricType.VIEWS in metric_types and MetricType.PLAYS in metric_types:
                journey_patterns["view_to_play"] += 1

            if (
                MetricType.PLAYS in metric_types
                and MetricType.DOWNLOADS in metric_types
            ):
                journey_patterns["play_to_download"] += 1

            if (
                MetricType.PLAYS in metric_types
                and MetricType.SEARCHES not in metric_types
            ):
                journey_patterns["direct_play"] += 1

        return {
            "total_users": len(user_journeys),
            "journey_patterns": journey_patterns,
            "avg_actions_per_user": (
                sum(len(journey) for journey in user_journeys.values())
                / len(user_journeys)
                if user_journeys
                else 0
            ),
        }

    except Exception as e:
        logger.error(f"User journey analysis failed: {e}")
        return {}


def generate_content_recommendations(performance: ContentPerformance) -> List[str]:
    """
    Generate optimization recommendations based on performance data

    Args:
        performance: Content performance object

    Returns:
        List of recommendation strings
    """
    recommendations = []

    try:
        # Low engagement recommendations
        if performance.avg_engagement_time < 30:  # Less than 30 seconds
            recommendations.append(
                "Consider improving content quality or thumbnail to increase engagement time"
            )

        # Discovery recommendations
        if performance.discovery_score < 50:
            recommendations.append(
                "Optimize tags and metadata to improve discoverability through search"
            )

        # Trending recommendations
        if performance.trending_score > 70:
            recommendations.append(
                "Content is trending - consider promoting or creating similar content"
            )
        elif performance.trending_score < 30:
            recommendations.append(
                "Consider refreshing content or improving promotional strategy"
            )

        # Quality score recommendations
        if performance.quality_score < 60:
            recommendations.append(
                "Consider improving video quality or technical specifications"
            )

        # User retention recommendations
        if performance.retention_score < 40:
            recommendations.append(
                "Focus on creating more engaging content to improve user retention"
            )

        # Peak hours optimization
        if performance.peak_activity_hours:
            peak_hours_str = ", ".join(str(h) for h in performance.peak_activity_hours)
            recommendations.append(
                f"Optimize content promotion for peak hours: {peak_hours_str}"
            )

        # Device optimization
        if (
            "mobile" in performance.device_distribution
            and performance.device_distribution["mobile"] > 50
        ):
            recommendations.append("Optimize content for mobile viewing experience")

        return recommendations

    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        return ["Unable to generate specific recommendations"]
