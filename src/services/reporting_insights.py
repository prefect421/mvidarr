"""
Real-Time Reporting System - Insights and Recommendations
Functions for generating insights and recommendations from report data
"""

from typing import Any, Dict, List

from src.services.reporting_models import ReportConfiguration, ReportType
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reporting_insights")


async def generate_report_insights(
    config: ReportConfiguration, data: Dict[str, Any]
) -> List[str]:
    """Generate insights for report"""
    insights = []

    try:
        if config.report_type == ReportType.SYSTEM_HEALTH:
            health_score = (
                data.get("system_status", {})
                .get("overall_health", {})
                .get("health_score", 0)
            )
            if health_score >= 90:
                insights.append("System is operating at optimal performance levels")
            elif health_score >= 75:
                insights.append(
                    "System performance is good with minor optimization opportunities"
                )
            else:
                insights.append(
                    "System performance requires attention and optimization"
                )

        elif config.report_type == ReportType.USER_ENGAGEMENT:
            active_users = data.get("key_metrics", {}).get("active_users_24h", 0)
            avg_engagement = data.get("key_metrics", {}).get("avg_engagement_score", 0)

            if avg_engagement > 75:
                insights.append(
                    f"High user engagement with {active_users} active users showing strong interaction patterns"
                )
            elif avg_engagement > 50:
                insights.append(
                    f"Moderate user engagement across {active_users} active users - consider engagement improvements"
                )
            else:
                insights.append(
                    f"User engagement is below optimal levels - recommend targeted retention strategies"
                )

        elif config.report_type == ReportType.CONTENT_PERFORMANCE:
            trending_count = len(data.get("trending_content", []))
            popular_count = len(data.get("popular_content", []))

            if trending_count > 10:
                insights.append(
                    f"Strong content trends with {trending_count} items showing positive momentum"
                )

            if popular_count > 0:
                avg_score = data.get("content_summary", {}).get(
                    "avg_popularity_score", 0
                )
                insights.append(
                    f"Content library shows average popularity score of {avg_score:.1f} across {popular_count} items"
                )

        elif config.report_type == ReportType.TRENDING_ANALYSIS:
            high_velocity = (
                data.get("trending_analysis", {})
                .get("velocity_distribution", {})
                .get("high_velocity", 0)
            )
            if high_velocity > 5:
                insights.append(
                    f"Significant trending momentum with {high_velocity} items showing rapid growth"
                )

        return insights

    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
        return ["Unable to generate specific insights for this report"]


async def generate_report_recommendations(
    config: ReportConfiguration, data: Dict[str, Any]
) -> List[str]:
    """Generate recommendations for report"""
    recommendations = []

    try:
        if config.report_type == ReportType.SYSTEM_HEALTH:
            health_score = (
                data.get("system_status", {})
                .get("overall_health", {})
                .get("health_score", 0)
            )
            if health_score < 75:
                recommendations.append(
                    "Consider system optimization and resource scaling"
                )
                recommendations.append("Review and resolve active performance alerts")

        elif config.report_type == ReportType.USER_ENGAGEMENT:
            avg_engagement = data.get("key_metrics", {}).get("avg_engagement_score", 0)
            if avg_engagement < 60:
                recommendations.append("Implement user onboarding improvements")
                recommendations.append("Consider personalized content recommendations")
                recommendations.append(
                    "Analyze user drop-off points and optimize user experience"
                )

        elif config.report_type == ReportType.CONTENT_PERFORMANCE:
            trending_count = len(data.get("trending_content", []))
            if trending_count < 5:
                recommendations.append("Focus on content quality improvements")
                recommendations.append(
                    "Analyze successful content patterns and replicate"
                )
                recommendations.append("Consider content promotion strategies")

        elif config.report_type == ReportType.COMPREHENSIVE_OVERVIEW:
            exec_summary = data.get("executive_summary", {})
            if exec_summary.get("system_health_score", 0) < 80:
                recommendations.append("Prioritize system performance optimization")
            if exec_summary.get("avg_engagement_score", 0) < 60:
                recommendations.append(
                    "Implement comprehensive user engagement strategy"
                )

        return recommendations

    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        return ["Unable to generate specific recommendations for this report"]
