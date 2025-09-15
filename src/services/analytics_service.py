"""
Analytics Service - Phase 3 Week 36
Real-time analytics collection and processing for monitoring dashboard
"""

import asyncio
import json
import statistics
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.middleware.auto_scaling_middleware import ResourceMetrics
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.analytics")


class MetricType(Enum):
    """Types of metrics collected"""

    SYSTEM = "system"
    APPLICATION = "application"
    PERFORMANCE = "performance"
    SECURITY = "security"
    USER = "user"
    BUSINESS = "business"


class AggregationType(Enum):
    """Metric aggregation types"""

    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"
    RATE = "rate"


@dataclass
class MetricPoint:
    """Individual metric data point"""

    timestamp: datetime
    metric_name: str
    metric_type: MetricType
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMetric:
    """Aggregated metric over time window"""

    metric_name: str
    time_window: str
    aggregation_type: AggregationType
    value: float
    sample_count: int
    start_time: datetime
    end_time: datetime
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Alert rule configuration"""

    rule_id: str
    metric_name: str
    threshold: float
    comparison: str  # >, <, >=, <=, ==
    time_window_minutes: int
    severity: str  # low, medium, high, critical
    enabled: bool = True
    notification_channels: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class Alert:
    """Active alert"""

    alert_id: str
    rule_id: str
    metric_name: str
    current_value: float
    threshold: float
    severity: str
    message: str
    triggered_at: datetime
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class AnalyticsService:
    """Comprehensive analytics service for monitoring dashboard"""

    def __init__(self):
        self.cache_manager = MediaCacheManager()

        # Metric storage (in-memory with cache persistence)
        self.metrics_buffer = deque(maxlen=10000)  # Last 10k metrics
        self.aggregated_metrics = defaultdict(lambda: deque(maxlen=1000))

        # Alert management
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history = deque(maxlen=1000)

        # Analytics processing
        self.processing_enabled = True
        self.last_aggregation_time = time.time()
        self.aggregation_interval = 60  # seconds

        # Performance tracking
        self.dashboard_metrics = {
            "total_metrics_processed": 0,
            "alerts_triggered": 0,
            "dashboard_views": 0,
            "last_update": datetime.utcnow(),
        }

        # Start background processing
        self._start_processing_tasks()

        logger.info("📊 Analytics service initialized")

    def _start_processing_tasks(self):
        """Start background analytics processing tasks"""
        asyncio.create_task(self._metrics_aggregation_loop())
        asyncio.create_task(self._alert_evaluation_loop())
        asyncio.create_task(self._cache_persistence_loop())

    async def _metrics_aggregation_loop(self):
        """Background loop for metrics aggregation"""
        while self.processing_enabled:
            try:
                await asyncio.sleep(self.aggregation_interval)
                await self._aggregate_metrics()
            except Exception as e:
                logger.error(f"Metrics aggregation error: {e}")

    async def _alert_evaluation_loop(self):
        """Background loop for alert evaluation"""
        while self.processing_enabled:
            try:
                await asyncio.sleep(30)  # Check alerts every 30 seconds
                await self._evaluate_alerts()
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")

    async def _cache_persistence_loop(self):
        """Background loop for cache persistence"""
        while self.processing_enabled:
            try:
                await asyncio.sleep(300)  # Persist every 5 minutes
                await self._persist_to_cache()
            except Exception as e:
                logger.error(f"Cache persistence error: {e}")

    async def record_metric(self, metric: MetricPoint):
        """Record a new metric data point"""
        try:
            self.metrics_buffer.append(metric)
            self.dashboard_metrics["total_metrics_processed"] += 1

            # Store in cache for real-time access
            cache_key = (
                f"metric:{metric.metric_name}:{int(metric.timestamp.timestamp())}"
            )
            await self.cache_manager.set(
                cache_key,
                json.dumps(asdict(metric), default=str),
                ttl=86400,  # 24 hours
            )

        except Exception as e:
            logger.error(f"Error recording metric: {e}")

    async def record_system_metrics(self, resource_metrics: ResourceMetrics):
        """Record system resource metrics"""
        timestamp = datetime.utcnow()

        # CPU metrics
        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="system.cpu.percent",
                metric_type=MetricType.SYSTEM,
                value=resource_metrics.cpu_percent,
                tags={"resource": "cpu"},
            )
        )

        # Memory metrics
        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="system.memory.percent",
                metric_type=MetricType.SYSTEM,
                value=resource_metrics.memory_percent,
                tags={"resource": "memory"},
            )
        )

        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="system.memory.used_gb",
                metric_type=MetricType.SYSTEM,
                value=resource_metrics.memory_used_gb,
                tags={"resource": "memory"},
            )
        )

        # Disk metrics
        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="system.disk.usage_percent",
                metric_type=MetricType.SYSTEM,
                value=resource_metrics.disk_usage_percent,
                tags={"resource": "disk"},
            )
        )

    async def record_application_metrics(
        self,
        active_connections: int,
        requests_per_second: float,
        avg_response_time: float,
        error_rate: float,
    ):
        """Record application performance metrics"""
        timestamp = datetime.utcnow()

        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="app.connections.active",
                metric_type=MetricType.APPLICATION,
                value=active_connections,
                tags={"category": "connections"},
            )
        )

        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="app.requests.per_second",
                metric_type=MetricType.PERFORMANCE,
                value=requests_per_second,
                tags={"category": "throughput"},
            )
        )

        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="app.response_time.avg_ms",
                metric_type=MetricType.PERFORMANCE,
                value=avg_response_time,
                tags={"category": "latency"},
            )
        )

        await self.record_metric(
            MetricPoint(
                timestamp=timestamp,
                metric_name="app.error_rate.percent",
                metric_type=MetricType.PERFORMANCE,
                value=error_rate,
                tags={"category": "errors"},
            )
        )

    async def _aggregate_metrics(self):
        """Aggregate metrics over time windows"""
        current_time = time.time()

        # Skip if not enough time has passed
        if current_time - self.last_aggregation_time < self.aggregation_interval:
            return

        try:
            # Get metrics from last aggregation window
            window_start = datetime.fromtimestamp(self.last_aggregation_time)
            window_end = datetime.fromtimestamp(current_time)

            # Group metrics by name
            metrics_by_name = defaultdict(list)
            for metric in self.metrics_buffer:
                if window_start <= metric.timestamp <= window_end:
                    metrics_by_name[metric.metric_name].append(metric.value)

            # Create aggregations for each metric
            for metric_name, values in metrics_by_name.items():
                if not values:
                    continue

                # Calculate different aggregations
                aggregations = [
                    (AggregationType.COUNT, len(values)),
                    (AggregationType.AVERAGE, statistics.mean(values)),
                    (AggregationType.MIN, min(values)),
                    (AggregationType.MAX, max(values)),
                ]

                # Add percentiles if enough data
                if len(values) >= 10:
                    sorted_values = sorted(values)
                    aggregations.extend(
                        [
                            (
                                AggregationType.PERCENTILE_95,
                                sorted_values[int(len(sorted_values) * 0.95)],
                            ),
                            (
                                AggregationType.PERCENTILE_99,
                                sorted_values[int(len(sorted_values) * 0.99)],
                            ),
                        ]
                    )

                # Store aggregated metrics
                for agg_type, agg_value in aggregations:
                    aggregated = AggregatedMetric(
                        metric_name=metric_name,
                        time_window="1min",
                        aggregation_type=agg_type,
                        value=agg_value,
                        sample_count=len(values),
                        start_time=window_start,
                        end_time=window_end,
                    )

                    self.aggregated_metrics[f"{metric_name}:{agg_type.value}"].append(
                        aggregated
                    )

            self.last_aggregation_time = current_time
            logger.debug(f"📊 Aggregated {len(metrics_by_name)} metric types")

        except Exception as e:
            logger.error(f"Metrics aggregation failed: {e}")

    async def _evaluate_alerts(self):
        """Evaluate alert rules against current metrics"""
        try:
            for rule_id, rule in self.alert_rules.items():
                if not rule.enabled:
                    continue

                # Get recent metrics for this rule
                recent_metrics = await self._get_recent_metrics(
                    rule.metric_name, rule.time_window_minutes
                )

                if not recent_metrics:
                    continue

                # Calculate current value (average over window)
                current_value = statistics.mean([m.value for m in recent_metrics])

                # Check threshold
                should_alert = False
                if rule.comparison == ">" and current_value > rule.threshold:
                    should_alert = True
                elif rule.comparison == "<" and current_value < rule.threshold:
                    should_alert = True
                elif rule.comparison == ">=" and current_value >= rule.threshold:
                    should_alert = True
                elif rule.comparison == "<=" and current_value <= rule.threshold:
                    should_alert = True
                elif (
                    rule.comparison == "=="
                    and abs(current_value - rule.threshold) < 0.01
                ):
                    should_alert = True

                # Trigger or resolve alert
                if should_alert and rule_id not in self.active_alerts:
                    await self._trigger_alert(rule, current_value)
                elif not should_alert and rule_id in self.active_alerts:
                    await self._resolve_alert(rule_id)

        except Exception as e:
            logger.error(f"Alert evaluation failed: {e}")

    async def _trigger_alert(self, rule: AlertRule, current_value: float):
        """Trigger a new alert"""
        alert_id = f"alert_{rule.rule_id}_{int(time.time())}"

        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            metric_name=rule.metric_name,
            current_value=current_value,
            threshold=rule.threshold,
            severity=rule.severity,
            message=f"{rule.description or rule.metric_name} is {current_value:.2f} (threshold: {rule.threshold})",
            triggered_at=datetime.utcnow(),
        )

        self.active_alerts[rule.rule_id] = alert
        self.alert_history.append(alert)
        self.dashboard_metrics["alerts_triggered"] += 1

        logger.warning(f"🚨 Alert triggered: {alert.message}")

        # Store in cache for dashboard
        await self.cache_manager.set(
            f"alert:active:{rule.rule_id}",
            json.dumps(asdict(alert), default=str),
            ttl=86400,
        )

    async def _resolve_alert(self, rule_id: str):
        """Resolve an active alert"""
        if rule_id in self.active_alerts:
            alert = self.active_alerts[rule_id]
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()

            del self.active_alerts[rule_id]

            logger.info(f"✅ Alert resolved: {alert.alert_id}")

            # Remove from active alerts in cache
            try:
                await self.cache_manager.delete(f"alert:active:{rule_id}")
            except:
                pass

    async def _get_recent_metrics(
        self, metric_name: str, time_window_minutes: int
    ) -> List[MetricPoint]:
        """Get recent metrics for a given time window"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)

        return [
            metric
            for metric in self.metrics_buffer
            if metric.metric_name == metric_name and metric.timestamp >= cutoff_time
        ]

    async def _persist_to_cache(self):
        """Persist analytics data to cache"""
        try:
            # Persist dashboard metrics
            await self.cache_manager.set(
                "analytics:dashboard_metrics",
                json.dumps(self.dashboard_metrics, default=str),
                ttl=3600,
            )

            # Persist recent aggregated metrics
            for metric_key, aggregations in self.aggregated_metrics.items():
                if aggregations:
                    recent_aggregations = list(aggregations)[
                        -10:
                    ]  # Last 10 aggregations
                    await self.cache_manager.set(
                        f"analytics:aggregated:{metric_key}",
                        json.dumps(
                            [
                                asdict(agg, dict_factory=dict)
                                for agg in recent_aggregations
                            ],
                            default=str,
                        ),
                        ttl=3600,
                    )

            logger.debug("💾 Analytics data persisted to cache")

        except Exception as e:
            logger.error(f"Cache persistence failed: {e}")

    # Public API methods
    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get dashboard summary statistics"""
        current_time = datetime.utcnow()

        # Recent system metrics
        recent_system_metrics = await self._get_recent_metrics("system.cpu.percent", 5)
        current_cpu = recent_system_metrics[-1].value if recent_system_metrics else 0

        recent_memory_metrics = await self._get_recent_metrics(
            "system.memory.percent", 5
        )
        current_memory = recent_memory_metrics[-1].value if recent_memory_metrics else 0

        recent_response_time = await self._get_recent_metrics(
            "app.response_time.avg_ms", 5
        )
        current_response_time = (
            recent_response_time[-1].value if recent_response_time else 0
        )

        return {
            "timestamp": current_time,
            "system": {
                "cpu_percent": current_cpu,
                "memory_percent": current_memory,
                "status": (
                    "healthy"
                    if current_cpu < 80 and current_memory < 85
                    else "degraded"
                ),
            },
            "application": {
                "response_time_ms": current_response_time,
                "active_alerts": len(self.active_alerts),
                "status": "operational" if len(self.active_alerts) < 3 else "issues",
            },
            "analytics": {
                "total_metrics": self.dashboard_metrics["total_metrics_processed"],
                "alerts_triggered": self.dashboard_metrics["alerts_triggered"],
                "dashboard_views": self.dashboard_metrics["dashboard_views"],
            },
        }

    async def get_metric_history(
        self, metric_name: str, time_window_hours: int = 1
    ) -> List[Dict[str, Any]]:
        """Get metric history for dashboard charts"""
        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        metrics = [
            {"timestamp": metric.timestamp, "value": metric.value, "tags": metric.tags}
            for metric in self.metrics_buffer
            if metric.metric_name == metric_name and metric.timestamp >= cutoff_time
        ]

        return sorted(metrics, key=lambda x: x["timestamp"])

    async def add_alert_rule(self, rule: AlertRule):
        """Add new alert rule"""
        self.alert_rules[rule.rule_id] = rule
        logger.info(f"➕ Alert rule added: {rule.rule_id}")

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [asdict(alert) for alert in self.active_alerts.values()]

    def increment_dashboard_views(self):
        """Track dashboard usage"""
        self.dashboard_metrics["dashboard_views"] += 1
        self.dashboard_metrics["last_update"] = datetime.utcnow()


# Global analytics service instance
analytics_service = None


async def get_analytics_service() -> AnalyticsService:
    """Get or create analytics service instance"""
    global analytics_service
    if analytics_service is None:
        analytics_service = AnalyticsService()
    return analytics_service
