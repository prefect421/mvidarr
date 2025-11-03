"""
Content Analytics Insights - Phase 3 Week 27
Insights generation functions for competitive analysis and optimization opportunities
"""

import statistics
from typing import Any, Dict, List

from src.services.analytics_models import ContentPerformance
from src.utils.logger import get_logger

logger = get_logger("mvidarr.content_analytics.insights")


async def get_competitive_analysis(
    performance: ContentPerformance, content_performance: Dict[str, ContentPerformance]
) -> Dict[str, Any]:
    """
    Get competitive analysis for content

    Args:
        performance: Content performance object
        content_performance: Dictionary of all content performance objects

    Returns:
        Dictionary containing competitive analysis
    """
    try:
        # Compare with similar content (same artist or genre)
        similar_content = []

        for content_id, other_performance in content_performance.items():
            if (
                content_id != performance.content_id
                and other_performance.artist == performance.artist
            ):
                similar_content.append(other_performance)

        if not similar_content:
            return {"message": "No similar content found for comparison"}

        # Calculate comparative metrics
        avg_views = statistics.mean(p.total_views for p in similar_content)
        avg_engagement = statistics.mean(p.avg_engagement_time for p in similar_content)
        avg_quality = statistics.mean(p.quality_score for p in similar_content)

        return {
            "similar_content_count": len(similar_content),
            "performance_vs_average": {
                "views": {
                    "current": performance.total_views,
                    "average": avg_views,
                    "relative_performance": (
                        (performance.total_views / avg_views - 1) * 100
                        if avg_views > 0
                        else 0
                    ),
                },
                "engagement_time": {
                    "current": performance.avg_engagement_time,
                    "average": avg_engagement,
                    "relative_performance": (
                        (performance.avg_engagement_time / avg_engagement - 1) * 100
                        if avg_engagement > 0
                        else 0
                    ),
                },
                "quality_score": {
                    "current": performance.quality_score,
                    "average": avg_quality,
                    "relative_performance": (
                        (performance.quality_score / avg_quality - 1) * 100
                        if avg_quality > 0
                        else 0
                    ),
                },
            },
        }

    except Exception as e:
        logger.error(f"Competitive analysis failed: {e}")
        return {}


def identify_optimization_opportunities(
    performance: ContentPerformance,
) -> List[Dict[str, Any]]:
    """
    Identify specific optimization opportunities

    Args:
        performance: Content performance object

    Returns:
        List of optimization opportunity dictionaries
    """
    opportunities = []

    try:
        # Low conversion opportunity
        if "search_to_view" in performance.conversion_funnel:
            search_to_view_rate = performance.conversion_funnel["search_to_view"]
            if search_to_view_rate < 30:
                opportunities.append(
                    {
                        "type": "conversion_optimization",
                        "priority": "high",
                        "issue": "Low search-to-view conversion",
                        "current_rate": f"{search_to_view_rate:.1f}%",
                        "recommendation": "Improve thumbnails and titles to increase click-through rate",
                    }
                )

        # Quality improvement opportunity
        if performance.quality_score < 70:
            opportunities.append(
                {
                    "type": "quality_improvement",
                    "priority": "medium",
                    "issue": "Below-average quality score",
                    "current_score": performance.quality_score,
                    "recommendation": "Consider video quality enhancement or better source material",
                }
            )

        # Engagement improvement opportunity
        if performance.avg_engagement_time < 45:  # Less than 45 seconds
            opportunities.append(
                {
                    "type": "engagement_optimization",
                    "priority": "high",
                    "issue": "Low average engagement time",
                    "current_time": f"{performance.avg_engagement_time:.1f}s",
                    "recommendation": "Optimize content to capture attention within first 15 seconds",
                }
            )

        # Discovery optimization opportunity
        if performance.discovery_score < 40:
            opportunities.append(
                {
                    "type": "discovery_optimization",
                    "priority": "medium",
                    "issue": "Low discoverability through search",
                    "current_score": performance.discovery_score,
                    "recommendation": "Improve metadata, tags, and search keywords",
                }
            )

        return opportunities

    except Exception as e:
        logger.error(f"Optimization opportunity identification failed: {e}")
        return []
