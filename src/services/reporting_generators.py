"""
Real-Time Reporting System - Report Generators
Functions for generating different types of reports
"""

import time
from typing import Any, Dict

from src.services.analytics_service import get_analytics_service
from src.services.content_analytics_engine import get_content_analytics_engine
from src.services.performance_monitor import get_performance_monitor
from src.services.reporting_models import ReportConfiguration
from src.services.user_behavior_analytics import get_user_behavior_analytics
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reporting_generators")


async def generate_system_health_report(
    config: ReportConfiguration,
) -> Dict[str, Any]:
    """Generate system health report"""
    try:
        analytics_service = await get_analytics_service()
        performance_monitor = await get_performance_monitor()

        # Get system health data
        dashboard_summary = await analytics_service.get_dashboard_summary()
        system_health = await performance_monitor.get_system_health_summary()
        performance_report = await performance_monitor.get_performance_report(
            hours=config.time_window_hours
        )

        return {
            "report_type": "system_health",
            "time_window_hours": config.time_window_hours,
            "generated_at": time.time(),
            "system_status": {
                "overall_health": system_health,
                "dashboard_summary": dashboard_summary,
                "performance_report": performance_report,
            },
            "metrics_summary": {
                "uptime_hours": system_health.get("monitoring_stats", {}).get(
                    "monitoring_uptime", 0
                )
                / 3600,
                "total_alerts": len(
                    dashboard_summary.get("application", {}).get("active_alerts", 0)
                ),
                "system_load": system_health.get("current_metrics", {})
                .get("cpu_usage", {})
                .get("value", 0),
            },
        }

    except Exception as e:
        logger.error(f"System health report generation failed: {e}")
        return {"error": str(e)}


async def generate_user_engagement_report(
    config: ReportConfiguration,
) -> Dict[str, Any]:
    """Generate user engagement report"""
    try:
        user_analytics = await get_user_behavior_analytics()

        # Get user engagement data
        analytics_summary = await user_analytics.get_analytics_summary()
        popular_content = await user_analytics.get_popular_content(
            hours=config.time_window_hours
        )

        return {
            "report_type": "user_engagement",
            "time_window_hours": config.time_window_hours,
            "generated_at": time.time(),
            "engagement_overview": analytics_summary,
            "popular_content": popular_content,
            "key_metrics": {
                "active_users_24h": analytics_summary.get("active_users", {}).get(
                    "last_24_hours", 0
                ),
                "active_sessions": analytics_summary.get("active_sessions", 0),
                "avg_engagement_score": analytics_summary.get(
                    "avg_engagement_score", 0
                ),
                "total_interactions": popular_content.get("total_interactions", 0),
            },
        }

    except Exception as e:
        logger.error(f"User engagement report generation failed: {e}")
        return {"error": str(e)}


async def generate_content_performance_report(
    config: ReportConfiguration,
) -> Dict[str, Any]:
    """Generate content performance report"""
    try:
        content_analytics = await get_content_analytics_engine()

        # Get content performance data
        popular_content = await content_analytics.get_popular_content(limit=20)
        trending_content = await content_analytics.get_trending_content(limit=15)

        return {
            "report_type": "content_performance",
            "time_window_hours": config.time_window_hours,
            "generated_at": time.time(),
            "popular_content": popular_content,
            "trending_content": [item.to_dict() for item in trending_content],
            "content_summary": {
                "total_content_analyzed": len(popular_content),
                "trending_content_count": len(trending_content),
                "avg_popularity_score": (
                    sum(item["popularity_score"] for item in popular_content)
                    / len(popular_content)
                    if popular_content
                    else 0
                ),
                "avg_trending_score": (
                    sum(item.trending_score for item in trending_content)
                    / len(trending_content)
                    if trending_content
                    else 0
                ),
            },
        }

    except Exception as e:
        logger.error(f"Content performance report generation failed: {e}")
        return {"error": str(e)}


async def generate_trending_analysis_report(
    config: ReportConfiguration,
) -> Dict[str, Any]:
    """Generate trending analysis report"""
    try:
        content_analytics = await get_content_analytics_engine()

        # Get trending analysis
        trending_content = await content_analytics.get_trending_content(limit=25)

        # Analyze trending patterns
        trending_artists = {}
        trending_velocities = []

        for item in trending_content:
            # Count trending artists
            if item.artist not in trending_artists:
                trending_artists[item.artist] = 0
            trending_artists[item.artist] += 1

            # Collect velocities
            trending_velocities.append(item.velocity)

        # Top trending artists
        top_artists = sorted(
            trending_artists.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "report_type": "trending_analysis",
            "time_window_hours": config.time_window_hours,
            "generated_at": time.time(),
            "trending_content": [item.to_dict() for item in trending_content],
            "trending_analysis": {
                "total_trending_items": len(trending_content),
                "top_trending_artists": top_artists,
                "avg_velocity": (
                    sum(trending_velocities) / len(trending_velocities)
                    if trending_velocities
                    else 0
                ),
                "max_velocity": (
                    max(trending_velocities) if trending_velocities else 0
                ),
                "velocity_distribution": {
                    "high_velocity": len([v for v in trending_velocities if v > 50]),
                    "medium_velocity": len(
                        [v for v in trending_velocities if 0 <= v <= 50]
                    ),
                    "negative_velocity": len([v for v in trending_velocities if v < 0]),
                },
            },
        }

    except Exception as e:
        logger.error(f"Trending analysis report generation failed: {e}")
        return {"error": str(e)}


async def generate_comprehensive_overview_report(
    config: ReportConfiguration,
) -> Dict[str, Any]:
    """Generate comprehensive overview report combining all analytics"""
    try:
        # Get all component reports
        system_health = await generate_system_health_report(config)
        user_engagement = await generate_user_engagement_report(config)
        content_performance = await generate_content_performance_report(config)
        trending_analysis = await generate_trending_analysis_report(config)

        return {
            "report_type": "comprehensive_overview",
            "time_window_hours": config.time_window_hours,
            "generated_at": time.time(),
            "executive_summary": {
                "system_health_score": system_health.get("system_status", {})
                .get("overall_health", {})
                .get("health_score", 0),
                "total_active_users": user_engagement.get("key_metrics", {}).get(
                    "active_users_24h", 0
                ),
                "trending_content_count": len(
                    trending_analysis.get("trending_content", [])
                ),
                "avg_engagement_score": user_engagement.get("key_metrics", {}).get(
                    "avg_engagement_score", 0
                ),
            },
            "detailed_sections": {
                "system_health": system_health,
                "user_engagement": user_engagement,
                "content_performance": content_performance,
                "trending_analysis": trending_analysis,
            },
        }

    except Exception as e:
        logger.error(f"Comprehensive overview report generation failed: {e}")
        return {"error": str(e)}
