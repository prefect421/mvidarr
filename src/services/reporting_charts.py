"""
Real-Time Reporting System - Chart Generation
Functions for generating charts and visualizations for reports
"""

from typing import Any, Dict, List

from src.services.reporting_models import ReportConfiguration, ReportType
from src.services.visualization_service import (
    ChartConfig,
    ChartType,
    TimeRange,
    VisualizationService,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reporting_charts")


async def generate_report_charts(
    config: ReportConfiguration,
    data: Dict[str, Any],
    visualization_service: VisualizationService,
) -> List[Dict[str, Any]]:
    """Generate charts for report"""
    try:
        charts = []

        # System health charts
        if config.report_type == ReportType.SYSTEM_HEALTH:
            if "system_status" in data:
                health_data = data["system_status"]["overall_health"]
                current_metrics = health_data.get("current_metrics", {})

                # CPU usage gauge
                if "cpu_usage" in current_metrics:
                    cpu_config = ChartConfig(
                        chart_type=ChartType.GAUGE,
                        title="CPU Usage",
                        metric_name="cpu_usage",
                        time_range=TimeRange.LAST_HOUR,
                    )
                    cpu_chart = visualization_service.create_gauge_chart(
                        cpu_config,
                        current_metrics["cpu_usage"].get("value", 0),
                        100,
                        {"warning": 80, "critical": 95},
                    )
                    charts.append(
                        {
                            "type": "gauge",
                            "title": "CPU Usage",
                            "config": cpu_chart.chart_definition,
                        }
                    )

        # User engagement charts
        elif config.report_type == ReportType.USER_ENGAGEMENT:
            if "popular_content" in data:
                popular_data = data["popular_content"]
                if "popular_videos" in popular_data:
                    videos = popular_data["popular_videos"][:10]
                    if videos:
                        video_titles = [
                            (
                                v["video_id"][:20] + "..."
                                if len(v["video_id"]) > 20
                                else v["video_id"]
                            )
                            for v in videos
                        ]
                        interaction_counts = [v["interactions"] for v in videos]

                        bar_config = ChartConfig(
                            chart_type=ChartType.BAR,
                            title="Top Videos by Interactions",
                            metric_name="video_interactions",
                            time_range=TimeRange.LAST_DAY,
                        )
                        bar_chart = visualization_service.create_bar_chart(
                            bar_config, video_titles, interaction_counts
                        )
                        charts.append(
                            {
                                "type": "bar",
                                "title": "Top Videos by Interactions",
                                "config": bar_chart.chart_definition,
                            }
                        )

        # Content performance charts
        elif config.report_type == ReportType.CONTENT_PERFORMANCE:
            if "popular_content" in data:
                content = data["popular_content"][:10]
                if content:
                    content_titles = [
                        (
                            item["title"][:30] + "..."
                            if len(item["title"]) > 30
                            else item["title"]
                        )
                        for item in content
                    ]
                    popularity_scores = [item["popularity_score"] for item in content]

                    bar_config = ChartConfig(
                        chart_type=ChartType.BAR,
                        title="Content Popularity Scores",
                        metric_name="popularity_score",
                        time_range=TimeRange.LAST_WEEK,
                    )
                    bar_chart = visualization_service.create_bar_chart(
                        bar_config, content_titles, popularity_scores
                    )
                    charts.append(
                        {
                            "type": "bar",
                            "title": "Content Popularity Scores",
                            "config": bar_chart.chart_definition,
                        }
                    )

        return charts

    except Exception as e:
        logger.error(f"Report chart generation failed: {e}")
        return []
