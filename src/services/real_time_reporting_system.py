"""
Real-Time Reporting System - Phase 3 Week 27
Advanced reporting system with scheduled reports, real-time dashboards, and automated insights
"""

import asyncio
import hashlib
import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.services.analytics_service import get_analytics_service
from src.services.content_analytics_engine import get_content_analytics_engine
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import (
    get_performance_monitor,
    track_media_processing_time,
)
from src.services.user_behavior_analytics import get_user_behavior_analytics
from src.services.visualization_service import (
    ChartConfig,
    ChartType,
    TimeRange,
    VisualizationService,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.real_time_reporting")


class ReportType(Enum):
    """Types of reports available"""

    SYSTEM_HEALTH = "system_health"
    USER_ENGAGEMENT = "user_engagement"
    CONTENT_PERFORMANCE = "content_performance"
    TRENDING_ANALYSIS = "trending_analysis"
    COMPREHENSIVE_OVERVIEW = "comprehensive_overview"
    CUSTOM_DASHBOARD = "custom_dashboard"


class ReportFormat(Enum):
    """Report output formats"""

    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"
    DASHBOARD = "dashboard"


class ReportSchedule(Enum):
    """Report scheduling options"""

    REAL_TIME = "real_time"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


@dataclass
class ReportConfiguration:
    """Report configuration settings"""

    report_id: str
    report_type: ReportType
    format: ReportFormat
    schedule: ReportSchedule
    title: str
    description: str
    enabled: bool = True

    # Data filters
    time_window_hours: int = 24
    content_types: List[str] = field(default_factory=list)
    user_segments: List[str] = field(default_factory=list)

    # Output settings
    include_charts: bool = True
    include_insights: bool = True
    include_recommendations: bool = True

    # Delivery settings
    recipients: List[str] = field(default_factory=list)
    webhook_urls: List[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)
    last_generated: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "format": self.format.value,
            "schedule": self.schedule.value,
            "title": self.title,
            "description": self.description,
            "enabled": self.enabled,
            "time_window_hours": self.time_window_hours,
            "content_types": self.content_types,
            "user_segments": self.user_segments,
            "include_charts": self.include_charts,
            "include_insights": self.include_insights,
            "include_recommendations": self.include_recommendations,
            "recipients": self.recipients,
            "webhook_urls": self.webhook_urls,
            "created_at": self.created_at,
            "last_generated": self.last_generated,
        }


@dataclass
class GeneratedReport:
    """Generated report data"""

    report_id: str
    config: ReportConfiguration
    data: Dict[str, Any]
    charts: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    generation_time: float = field(default_factory=time.time)
    processing_time_seconds: float = 0.0
    data_freshness: float = 0.0  # How fresh the underlying data is

    file_path: Optional[str] = None
    dashboard_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "config": self.config.to_dict(),
            "data": self.data,
            "charts": self.charts,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "generation_time": self.generation_time,
            "processing_time_seconds": self.processing_time_seconds,
            "data_freshness": self.data_freshness,
            "file_path": self.file_path,
            "dashboard_url": self.dashboard_url,
        }


@dataclass
class RealtimeMetrics:
    """Real-time system metrics"""

    timestamp: float
    system_metrics: Dict[str, Any]
    user_metrics: Dict[str, Any]
    content_metrics: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    alerts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "system_metrics": self.system_metrics,
            "user_metrics": self.user_metrics,
            "content_metrics": self.content_metrics,
            "performance_metrics": self.performance_metrics,
            "alerts": self.alerts,
        }


class RealTimeReportingSystem:
    """Advanced real-time reporting and dashboard system"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize real-time reporting system"""
        self.config = config or {
            "enable_real_time_updates": True,
            "update_interval_seconds": 30,
            "report_cache_ttl": 900,  # 15 minutes
            "max_cached_reports": 100,
            "enable_webhook_delivery": True,
            "dashboard_refresh_seconds": 10,
            "insight_generation_enabled": True,
        }

        # Service initialization
        self.visualization_service = VisualizationService()

        # Report management
        self.report_configs: Dict[str, ReportConfiguration] = {}
        self.scheduled_reports: Dict[str, asyncio.Task] = {}
        self.generated_reports: Dict[str, GeneratedReport] = {}

        # Real-time data
        self.current_metrics: Optional[RealtimeMetrics] = None
        self.metrics_history = []
        self.max_history_size = 1000

        # Processing state
        self.system_active = True
        self.last_update_time = time.time()

        # Performance tracking
        self.stats = {
            "reports_generated": 0,
            "dashboards_served": 0,
            "real_time_updates": 0,
            "total_processing_time": 0.0,
            "active_subscribers": 0,
        }

        # Start background services
        if self.config["enable_real_time_updates"]:
            self._start_background_services()

        logger.info("📊 Real-time reporting system initialized")

    def _start_background_services(self):
        """Start background reporting services"""
        asyncio.create_task(self._real_time_metrics_loop())
        asyncio.create_task(self._scheduled_reports_loop())

    async def _real_time_metrics_loop(self):
        """Background loop for real-time metrics collection"""
        while self.system_active:
            try:
                await asyncio.sleep(self.config["update_interval_seconds"])
                await self._collect_real_time_metrics()
            except Exception as e:
                logger.error(f"Real-time metrics collection error: {e}")

    async def _scheduled_reports_loop(self):
        """Background loop for scheduled report generation"""
        while self.system_active:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._process_scheduled_reports()
            except Exception as e:
                logger.error(f"Scheduled reports processing error: {e}")

    async def _collect_real_time_metrics(self):
        """Collect real-time metrics from all analytics services"""
        try:
            start_time = time.time()

            # Collect from all analytics services
            analytics_service = await get_analytics_service()
            user_analytics = await get_user_behavior_analytics()
            content_analytics = await get_content_analytics_engine()
            performance_monitor = await get_performance_monitor()

            # Get current metrics
            system_summary = await analytics_service.get_dashboard_summary()
            user_summary = await user_analytics.get_analytics_summary()
            performance_health = await performance_monitor.get_system_health_summary()

            # Get popular content
            popular_content = await content_analytics.get_popular_content(limit=10)
            trending_content = await content_analytics.get_trending_content(limit=10)

            # Get active alerts
            alerts = await analytics_service.get_active_alerts()

            # Create real-time metrics object
            self.current_metrics = RealtimeMetrics(
                timestamp=time.time(),
                system_metrics=system_summary,
                user_metrics=user_summary,
                content_metrics={
                    "popular_content": popular_content,
                    "trending_content": [item.to_dict() for item in trending_content],
                },
                performance_metrics=performance_health,
                alerts=alerts,
            )

            # Store in history
            self.metrics_history.append(self.current_metrics)
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history = self.metrics_history[-self.max_history_size :]

            # Cache metrics
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.ANALYTICS_DATA,
                "real_time_metrics_current",
                self.current_metrics.to_dict(),
                ttl=60,  # 1 minute
            )

            # Update stats
            processing_time = time.time() - start_time
            self.stats["real_time_updates"] += 1
            self.last_update_time = time.time()

            await track_media_processing_time(
                "real_time_metrics_collection", processing_time
            )

        except Exception as e:
            logger.error(f"Real-time metrics collection failed: {e}")

    async def create_report_configuration(self, config: ReportConfiguration) -> str:
        """Create a new report configuration"""
        try:
            # Store configuration
            self.report_configs[config.report_id] = config

            # If scheduled, create background task
            if config.schedule != ReportSchedule.ON_DEMAND and config.enabled:
                await self._schedule_report(config)

            # Cache configuration
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.ANALYTICS_DATA,
                f"report_config_{config.report_id}",
                config.to_dict(),
                ttl=86400,  # 24 hours
            )

            logger.info(f"📊 Created report configuration: {config.title}")
            return config.report_id

        except Exception as e:
            logger.error(f"Failed to create report configuration: {e}")
            return ""

    async def _schedule_report(self, config: ReportConfiguration):
        """Schedule a report for automatic generation"""
        try:
            # Cancel existing task if present
            if config.report_id in self.scheduled_reports:
                self.scheduled_reports[config.report_id].cancel()

            # Calculate schedule interval
            schedule_intervals = {
                ReportSchedule.HOURLY: 3600,
                ReportSchedule.DAILY: 86400,
                ReportSchedule.WEEKLY: 604800,
                ReportSchedule.MONTHLY: 2592000,
            }

            interval = schedule_intervals.get(config.schedule, 86400)

            # Create scheduled task
            async def scheduled_task():
                while config.enabled and self.system_active:
                    try:
                        await asyncio.sleep(interval)
                        await self.generate_report(config.report_id)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Scheduled report generation failed: {e}")

            task = asyncio.create_task(scheduled_task())
            self.scheduled_reports[config.report_id] = task

        except Exception as e:
            logger.error(f"Report scheduling failed: {e}")

    async def generate_report(self, report_id: str) -> Optional[GeneratedReport]:
        """Generate a report based on configuration"""
        try:
            config = self.report_configs.get(report_id)
            if not config:
                logger.error(f"Report configuration not found: {report_id}")
                return None

            start_time = time.time()
            logger.info(f"📊 Generating report: {config.title}")

            # Generate report data based on type
            if config.report_type == ReportType.SYSTEM_HEALTH:
                data = await self._generate_system_health_report(config)
            elif config.report_type == ReportType.USER_ENGAGEMENT:
                data = await self._generate_user_engagement_report(config)
            elif config.report_type == ReportType.CONTENT_PERFORMANCE:
                data = await self._generate_content_performance_report(config)
            elif config.report_type == ReportType.TRENDING_ANALYSIS:
                data = await self._generate_trending_analysis_report(config)
            elif config.report_type == ReportType.COMPREHENSIVE_OVERVIEW:
                data = await self._generate_comprehensive_overview_report(config)
            else:
                data = {"error": f"Unsupported report type: {config.report_type}"}

            # Generate charts if requested
            charts = []
            if config.include_charts and "error" not in data:
                charts = await self._generate_report_charts(config, data)

            # Generate insights if requested
            insights = []
            if config.include_insights and "error" not in data:
                insights = await self._generate_report_insights(config, data)

            # Generate recommendations if requested
            recommendations = []
            if config.include_recommendations and "error" not in data:
                recommendations = await self._generate_report_recommendations(
                    config, data
                )

            # Calculate data freshness
            data_freshness = time.time() - self.last_update_time

            # Create generated report
            processing_time = time.time() - start_time
            report = GeneratedReport(
                report_id=report_id,
                config=config,
                data=data,
                charts=charts,
                insights=insights,
                recommendations=recommendations,
                processing_time_seconds=processing_time,
                data_freshness=data_freshness,
            )

            # Format report if needed
            if config.format != ReportFormat.JSON:
                await self._format_report(report)

            # Store generated report
            self.generated_reports[report_id] = report
            config.last_generated = time.time()

            # Cache report
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.ANALYTICS_DATA,
                f"generated_report_{report_id}",
                report.to_dict(),
                ttl=self.config["report_cache_ttl"],
            )

            # Update stats
            self.stats["reports_generated"] += 1
            self.stats["total_processing_time"] += processing_time

            await track_media_processing_time("report_generation", processing_time)

            logger.info(
                f"✅ Generated report '{config.title}' in {processing_time:.2f}s"
            )

            # Deliver report if configured
            if config.recipients or config.webhook_urls:
                await self._deliver_report(report)

            return report

        except Exception as e:
            logger.error(f"Report generation failed for {report_id}: {e}")
            return None

    async def _generate_system_health_report(
        self, config: ReportConfiguration
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

    async def _generate_user_engagement_report(
        self, config: ReportConfiguration
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

    async def _generate_content_performance_report(
        self, config: ReportConfiguration
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

    async def _generate_trending_analysis_report(
        self, config: ReportConfiguration
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
                        "high_velocity": len(
                            [v for v in trending_velocities if v > 50]
                        ),
                        "medium_velocity": len(
                            [v for v in trending_velocities if 0 <= v <= 50]
                        ),
                        "negative_velocity": len(
                            [v for v in trending_velocities if v < 0]
                        ),
                    },
                },
            }

        except Exception as e:
            logger.error(f"Trending analysis report generation failed: {e}")
            return {"error": str(e)}

    async def _generate_comprehensive_overview_report(
        self, config: ReportConfiguration
    ) -> Dict[str, Any]:
        """Generate comprehensive overview report combining all analytics"""
        try:
            # Get all component reports
            system_health = await self._generate_system_health_report(config)
            user_engagement = await self._generate_user_engagement_report(config)
            content_performance = await self._generate_content_performance_report(
                config
            )
            trending_analysis = await self._generate_trending_analysis_report(config)

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

    async def _generate_report_charts(
        self, config: ReportConfiguration, data: Dict[str, Any]
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
                        cpu_chart = self.visualization_service.create_gauge_chart(
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
                            bar_chart = self.visualization_service.create_bar_chart(
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
                        popularity_scores = [
                            item["popularity_score"] for item in content
                        ]

                        bar_config = ChartConfig(
                            chart_type=ChartType.BAR,
                            title="Content Popularity Scores",
                            metric_name="popularity_score",
                            time_range=TimeRange.LAST_WEEK,
                        )
                        bar_chart = self.visualization_service.create_bar_chart(
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

    async def _generate_report_insights(
        self, config: ReportConfiguration, data: Dict[str, Any]
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
                avg_engagement = data.get("key_metrics", {}).get(
                    "avg_engagement_score", 0
                )

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

    async def _generate_report_recommendations(
        self, config: ReportConfiguration, data: Dict[str, Any]
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
                    recommendations.append(
                        "Review and resolve active performance alerts"
                    )

            elif config.report_type == ReportType.USER_ENGAGEMENT:
                avg_engagement = data.get("key_metrics", {}).get(
                    "avg_engagement_score", 0
                )
                if avg_engagement < 60:
                    recommendations.append("Implement user onboarding improvements")
                    recommendations.append(
                        "Consider personalized content recommendations"
                    )
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

    async def _format_report(self, report: GeneratedReport):
        """Format report in specified output format"""
        try:
            config = report.config

            if config.format == ReportFormat.HTML:
                report.file_path = await self._generate_html_report(report)
            elif config.format == ReportFormat.PDF:
                report.file_path = await self._generate_pdf_report(report)
            elif config.format == ReportFormat.CSV:
                report.file_path = await self._generate_csv_report(report)
            elif config.format == ReportFormat.DASHBOARD:
                report.dashboard_url = await self._generate_dashboard_url(report)

        except Exception as e:
            logger.error(f"Report formatting failed: {e}")

    async def _generate_html_report(self, report: GeneratedReport) -> str:
        """Generate HTML format report"""
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{report.config.title}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                    .section {{ margin: 20px 0; padding: 15px; border-left: 3px solid #007bff; }}
                    .metric {{ display: inline-block; margin: 10px; padding: 10px; background: #e9ecef; border-radius: 3px; }}
                    .chart {{ margin: 20px 0; text-align: center; }}
                    .insight {{ background: #d4edda; padding: 10px; margin: 5px 0; border-radius: 3px; }}
                    .recommendation {{ background: #f8d7da; padding: 10px; margin: 5px 0; border-radius: 3px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>{report.config.title}</h1>
                    <p>{report.config.description}</p>
                    <p>Generated: {datetime.fromtimestamp(report.generation_time).strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Processing Time: {report.processing_time_seconds:.2f} seconds</p>
                </div>
                
                <div class="section">
                    <h2>Report Data</h2>
                    <pre>{json.dumps(report.data, indent=2, default=str)}</pre>
                </div>
                
                {f'''<div class="section">
                    <h2>Insights</h2>
                    {''.join(f'<div class="insight">{insight}</div>' for insight in report.insights)}
                </div>''' if report.insights else ''}
                
                {f'''<div class="section">
                    <h2>Recommendations</h2>
                    {''.join(f'<div class="recommendation">{rec}</div>' for rec in report.recommendations)}
                </div>''' if report.recommendations else ''}
            </body>
            </html>
            """

            # Save to temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False
            ) as f:
                f.write(html_content)
                return f.name

        except Exception as e:
            logger.error(f"HTML report generation failed: {e}")
            return ""

    async def _generate_pdf_report(self, report: GeneratedReport) -> str:
        """Generate PDF format report (placeholder - would need additional libraries)"""
        # This would require libraries like reportlab or weasyprint
        logger.info("PDF report generation not implemented - returning HTML")
        return await self._generate_html_report(report)

    async def _generate_csv_report(self, report: GeneratedReport) -> str:
        """Generate CSV format report"""
        try:
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(["Report", report.config.title])
            writer.writerow(
                [
                    "Generated",
                    datetime.fromtimestamp(report.generation_time).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                ]
            )
            writer.writerow(
                ["Processing Time", f"{report.processing_time_seconds:.2f} seconds"]
            )
            writer.writerow([])

            # Write data (flatten JSON structure)
            def write_dict(data, prefix=""):
                for key, value in data.items():
                    if isinstance(value, dict):
                        write_dict(value, f"{prefix}{key}.")
                    elif isinstance(value, list):
                        writer.writerow(
                            [f"{prefix}{key}", f"List with {len(value)} items"]
                        )
                    else:
                        writer.writerow([f"{prefix}{key}", str(value)])

            writer.writerow(["Key", "Value"])
            write_dict(report.data)

            # Save to temporary file
            csv_content = output.getvalue()
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            ) as f:
                f.write(csv_content)
                return f.name

        except Exception as e:
            logger.error(f"CSV report generation failed: {e}")
            return ""

    async def _generate_dashboard_url(self, report: GeneratedReport) -> str:
        """Generate dashboard URL for report"""
        # This would integrate with your web dashboard
        base_url = "http://localhost:5000/dashboard"
        return f"{base_url}/reports/{report.report_id}"

    async def _deliver_report(self, report: GeneratedReport):
        """Deliver report via configured channels"""
        try:
            config = report.config

            # Webhook delivery
            if config.webhook_urls and self.config["enable_webhook_delivery"]:
                await self._deliver_via_webhook(report)

            # Email delivery would be implemented here
            # File system delivery would be implemented here

        except Exception as e:
            logger.error(f"Report delivery failed: {e}")

    async def _deliver_via_webhook(self, report: GeneratedReport):
        """Deliver report via webhook"""
        try:
            import aiohttp

            payload = {
                "report_id": report.report_id,
                "title": report.config.title,
                "type": report.config.report_type.value,
                "generated_at": report.generation_time,
                "data": report.data,
                "insights": report.insights,
                "recommendations": report.recommendations,
            }

            async with aiohttp.ClientSession() as session:
                for webhook_url in report.config.webhook_urls:
                    try:
                        async with session.post(
                            webhook_url, json=payload, timeout=10
                        ) as response:
                            if response.status == 200:
                                logger.info(
                                    f"📊 Report delivered to webhook: {webhook_url}"
                                )
                            else:
                                logger.warning(
                                    f"Webhook delivery failed: {webhook_url} - Status {response.status}"
                                )
                    except Exception as e:
                        logger.error(f"Webhook delivery error for {webhook_url}: {e}")

        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")

    async def _process_scheduled_reports(self):
        """Process scheduled reports that need generation"""
        try:
            current_time = time.time()

            for report_id, config in self.report_configs.items():
                if not config.enabled or config.schedule == ReportSchedule.ON_DEMAND:
                    continue

                # Check if report needs generation
                should_generate = False

                if config.last_generated is None:
                    should_generate = True
                else:
                    time_since_last = current_time - config.last_generated

                    if (
                        config.schedule == ReportSchedule.HOURLY
                        and time_since_last >= 3600
                    ):
                        should_generate = True
                    elif (
                        config.schedule == ReportSchedule.DAILY
                        and time_since_last >= 86400
                    ):
                        should_generate = True
                    elif (
                        config.schedule == ReportSchedule.WEEKLY
                        and time_since_last >= 604800
                    ):
                        should_generate = True
                    elif (
                        config.schedule == ReportSchedule.MONTHLY
                        and time_since_last >= 2592000
                    ):
                        should_generate = True

                if should_generate:
                    await self.generate_report(report_id)

        except Exception as e:
            logger.error(f"Scheduled reports processing failed: {e}")

    async def get_real_time_metrics(self) -> Optional[RealtimeMetrics]:
        """Get current real-time metrics"""
        return self.current_metrics

    async def get_metrics_history(self, minutes: int = 60) -> List[RealtimeMetrics]:
        """Get historical real-time metrics"""
        cutoff_time = time.time() - (minutes * 60)
        return [
            metrics
            for metrics in self.metrics_history
            if metrics.timestamp >= cutoff_time
        ]

    async def get_generated_report(self, report_id: str) -> Optional[GeneratedReport]:
        """Get a generated report"""
        if report_id in self.generated_reports:
            return self.generated_reports[report_id]

        # Check cache
        cache_manager = await get_media_cache_manager()
        cached_report = await cache_manager.get(
            CacheType.ANALYTICS_DATA, f"generated_report_{report_id}"
        )

        if cached_report:
            # Reconstruct report object
            config_data = cached_report["config"]
            config_data["report_type"] = ReportType(config_data["report_type"])
            config_data["format"] = ReportFormat(config_data["format"])
            config_data["schedule"] = ReportSchedule(config_data["schedule"])

            config = ReportConfiguration(**config_data)
            cached_report["config"] = config

            return GeneratedReport(**cached_report)

        return None

    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get real-time reporting service statistics"""
        try:
            return {
                "service": "Real-Time Reporting System",
                "status": "active" if self.system_active else "inactive",
                "stats": self.stats,
                "configuration": self.config,
                "system_status": {
                    "active_report_configs": len(self.report_configs),
                    "scheduled_reports": len(self.scheduled_reports),
                    "generated_reports_cached": len(self.generated_reports),
                    "metrics_history_size": len(self.metrics_history),
                    "last_metrics_update": self.last_update_time,
                    "data_freshness_seconds": (
                        time.time() - self.last_update_time
                        if self.current_metrics
                        else None
                    ),
                },
                "capabilities": {
                    "real_time_metrics": True,
                    "scheduled_reports": True,
                    "multiple_formats": True,
                    "webhook_delivery": True,
                    "chart_generation": True,
                    "insights_generation": True,
                },
            }
        except Exception as e:
            logger.error(f"Failed to get service statistics: {e}")
            return {"service": "Real-Time Reporting System", "error": str(e)}


# Global real-time reporting system instance
_real_time_reporting_system: Optional[RealTimeReportingSystem] = None


async def get_real_time_reporting_system(
    config: Optional[Dict[str, Any]] = None
) -> RealTimeReportingSystem:
    """Get or create global real-time reporting system instance"""
    global _real_time_reporting_system

    if _real_time_reporting_system is None:
        _real_time_reporting_system = RealTimeReportingSystem(config)

    return _real_time_reporting_system
