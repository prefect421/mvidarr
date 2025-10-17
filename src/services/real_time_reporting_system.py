"""
Real-Time Reporting System - Main Aggregator - Phase 3 Week 27
Advanced reporting system with scheduled reports, real-time dashboards, and automated insights
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

# Import analytics services for metrics collection
from src.services.analytics_service import get_analytics_service
from src.services.content_analytics_engine import get_content_analytics_engine
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import (
    get_performance_monitor,
    track_media_processing_time,
)
from src.services.reporting_charts import generate_report_charts
from src.services.reporting_delivery import deliver_report
from src.services.reporting_formatters import format_report
from src.services.reporting_generators import (
    generate_comprehensive_overview_report,
    generate_content_performance_report,
    generate_system_health_report,
    generate_trending_analysis_report,
    generate_user_engagement_report,
)
from src.services.reporting_insights import (
    generate_report_insights,
    generate_report_recommendations,
)
from src.services.reporting_models import (
    GeneratedReport,
    RealtimeMetrics,
    ReportConfiguration,
    ReportFormat,
    ReportSchedule,
    ReportType,
)
from src.services.user_behavior_analytics import get_user_behavior_analytics
from src.services.visualization_service import VisualizationService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.real_time_reporting")


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
                data = await generate_system_health_report(config)
            elif config.report_type == ReportType.USER_ENGAGEMENT:
                data = await generate_user_engagement_report(config)
            elif config.report_type == ReportType.CONTENT_PERFORMANCE:
                data = await generate_content_performance_report(config)
            elif config.report_type == ReportType.TRENDING_ANALYSIS:
                data = await generate_trending_analysis_report(config)
            elif config.report_type == ReportType.COMPREHENSIVE_OVERVIEW:
                data = await generate_comprehensive_overview_report(config)
            else:
                data = {"error": f"Unsupported report type: {config.report_type}"}

            # Generate charts if requested
            charts = []
            if config.include_charts and "error" not in data:
                charts = await generate_report_charts(
                    config, data, self.visualization_service
                )

            # Generate insights if requested
            insights = []
            if config.include_insights and "error" not in data:
                insights = await generate_report_insights(config, data)

            # Generate recommendations if requested
            recommendations = []
            if config.include_recommendations and "error" not in data:
                recommendations = await generate_report_recommendations(config, data)

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
                await format_report(report)

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
                await deliver_report(report, self.config["enable_webhook_delivery"])

            return report

        except Exception as e:
            logger.error(f"Report generation failed for {report_id}: {e}")
            return None

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
