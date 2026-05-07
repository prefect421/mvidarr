"""
MVidarr Performance Monitor - Phase 2 Week 23
System performance tracking with real-time metrics and alerting for media operations
"""

import asyncio
import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.performance_monitor")


class MetricType(Enum):
    """Types of performance metrics"""

    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    PROCESS_COUNT = "process_count"
    MEDIA_PROCESSING_TIME = "media_processing_time"
    CACHE_PERFORMANCE = "cache_performance"
    API_RESPONSE_TIME = "api_response_time"
    ERROR_RATE = "error_rate"
    CONCURRENT_OPERATIONS = "concurrent_operations"


class AlertLevel(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class PerformanceMetric:
    """Individual performance metric data point"""

    metric_type: MetricType
    timestamp: float
    value: float
    unit: str
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_type": self.metric_type.value,
            "timestamp": self.timestamp,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags,
        }


@dataclass
class PerformanceAlert:
    """Performance alert data"""

    alert_id: str
    alert_level: AlertLevel
    metric_type: MetricType
    message: str
    threshold: float
    current_value: float
    timestamp: float
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_level": self.alert_level.value,
            "metric_type": self.metric_type.value,
            "message": self.message,
            "threshold": self.threshold,
            "current_value": self.current_value,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


@dataclass
class MonitoringConfig:
    """Configuration for performance monitoring"""

    collection_interval_seconds: float = 5.0
    metric_retention_minutes: int = 60
    alert_thresholds: Dict[MetricType, Dict[AlertLevel, float]] = field(
        default_factory=lambda: {
            MetricType.CPU_USAGE: {
                AlertLevel.WARNING: 80.0,
                AlertLevel.CRITICAL: 90.0,
                AlertLevel.EMERGENCY: 95.0,
            },
            MetricType.MEMORY_USAGE: {
                AlertLevel.WARNING: 75.0,
                AlertLevel.CRITICAL: 85.0,
                AlertLevel.EMERGENCY: 95.0,
            },
            MetricType.MEDIA_PROCESSING_TIME: {
                AlertLevel.WARNING: 30.0,  # seconds
                AlertLevel.CRITICAL: 60.0,
                AlertLevel.EMERGENCY: 120.0,
            },
            MetricType.ERROR_RATE: {
                AlertLevel.WARNING: 5.0,  # percentage
                AlertLevel.CRITICAL: 15.0,
                AlertLevel.EMERGENCY: 25.0,
            },
        }
    )
    enable_redis_storage: bool = True
    enable_file_logging: bool = True
    log_file_path: str = "logs/performance_metrics.jsonl"
    enable_real_time_alerts: bool = True


class PerformanceMonitor:
    """Advanced system performance monitoring with real-time metrics and alerting"""

    def __init__(self, config: Optional[MonitoringConfig] = None):
        """Initialize performance monitor"""
        self.config = config or MonitoringConfig()
        self.cache_manager = (
            MediaCacheManager() if self.config.enable_redis_storage else None
        )

        # Metric storage - in-memory ring buffers for fast access
        self.metrics_buffer: Dict[MetricType, deque] = defaultdict(
            lambda: deque(
                maxlen=int(
                    self.config.metric_retention_minutes
                    * 60
                    / self.config.collection_interval_seconds
                )
            )
        )

        # Alert management
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []

        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.stats_lock = threading.Lock()

        # Performance tracking
        self.collection_stats = {
            "metrics_collected": 0,
            "alerts_generated": 0,
            "monitoring_uptime": 0,
            "last_collection_time": 0,
        }

        logger.info(
            f"📊 Performance monitor initialized with {self.config.collection_interval_seconds}s intervals"
        )

    async def start_monitoring(self):
        """Start continuous performance monitoring"""
        if self.monitoring_active:
            logger.warning("⚠️ Performance monitoring is already active")
            return

        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        logger.info("🚀 Performance monitoring started")

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        if not self.monitoring_active:
            return

        self.monitoring_active = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("🛑 Performance monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        start_time = time.time()

        try:
            while self.monitoring_active:
                collection_start = time.time()

                # Collect all metrics
                await self._collect_system_metrics()

                # Check for alerts
                await self._check_alert_thresholds()

                # Update stats
                with self.stats_lock:
                    self.stats["metrics_collected"] += len(MetricType)
                    self.stats["monitoring_uptime"] = time.time() - start_time
                    self.stats["last_collection_time"] = time.time()

                # Wait for next collection interval
                collection_time = time.time() - collection_start
                sleep_time = max(
                    0, self.config.collection_interval_seconds - collection_time
                )

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("📊 Monitoring loop cancelled")
        except Exception as e:
            logger.error(f"❌ Monitoring loop error: {e}")

    async def _collect_system_metrics(self):
        """Collect system performance metrics"""
        current_time = time.time()

        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            await self._store_metric(
                MetricType.CPU_USAGE,
                cpu_percent,
                "percent",
                {"cpu_count": str(cpu_count)},
            )

            # Memory metrics
            memory = psutil.virtual_memory()
            await self._store_metric(
                MetricType.MEMORY_USAGE,
                memory.percent,
                "percent",
                {
                    "total_gb": str(round(memory.total / (1024**3), 2)),
                    "available_gb": str(round(memory.available / (1024**3), 2)),
                },
            )

            # Disk I/O metrics
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # Calculate I/O rates if we have previous data
                if hasattr(self, "_last_disk_io"):
                    time_diff = current_time - self._last_disk_collection
                    read_rate = (
                        disk_io.read_bytes - self._last_disk_io.read_bytes
                    ) / time_diff
                    write_rate = (
                        disk_io.write_bytes - self._last_disk_io.write_bytes
                    ) / time_diff

                    await self._store_metric(
                        MetricType.DISK_IO,
                        read_rate,
                        "bytes/sec",
                        {"direction": "read"},
                    )
                    await self._store_metric(
                        MetricType.DISK_IO,
                        write_rate,
                        "bytes/sec",
                        {"direction": "write"},
                    )

                self._last_disk_io = disk_io
                self._last_disk_collection = current_time

            # Process count
            process_count = len(psutil.pids())
            await self._store_metric(MetricType.PROCESS_COUNT, process_count, "count")

            # Network I/O metrics
            network_io = psutil.net_io_counters()
            if network_io:
                # Calculate network rates if we have previous data
                if hasattr(self, "_last_network_io"):
                    time_diff = current_time - self._last_network_collection
                    bytes_sent_rate = (
                        network_io.bytes_sent - self._last_network_io.bytes_sent
                    ) / time_diff
                    bytes_recv_rate = (
                        network_io.bytes_recv - self._last_network_io.bytes_recv
                    ) / time_diff

                    await self._store_metric(
                        MetricType.NETWORK_IO,
                        bytes_sent_rate,
                        "bytes/sec",
                        {"direction": "sent"},
                    )
                    await self._store_metric(
                        MetricType.NETWORK_IO,
                        bytes_recv_rate,
                        "bytes/sec",
                        {"direction": "received"},
                    )

                self._last_network_io = network_io
                self._last_network_collection = current_time

        except Exception as e:
            logger.error(f"❌ Error collecting system metrics: {e}")

    async def _store_metric(
        self,
        metric_type: MetricType,
        value: float,
        unit: str,
        tags: Dict[str, str] = None,
    ):
        """Store a performance metric"""
        metric = PerformanceMetric(
            metric_type=metric_type,
            timestamp=time.time(),
            value=value,
            unit=unit,
            tags=tags or {},
        )

        # Store in memory buffer
        self.metrics_buffer[metric_type].append(metric)

        # Store in Redis if enabled
        if self.cache_manager and self.config.enable_redis_storage:
            try:
                await self.cache_manager.set(
                    f"performance:metrics:{metric_type.value}:{int(time.time())}",
                    json.dumps(metric.to_dict()),
                    ttl=int(self.config.metric_retention_minutes * 60),
                )
            except Exception as e:
                logger.error(f"❌ Failed to store metric in Redis: {e}")

        # Log to file if enabled
        if self.config.enable_file_logging:
            await self._log_metric_to_file(metric)

    async def _log_metric_to_file(self, metric: PerformanceMetric):
        """Log metric to file"""
        try:
            log_path = Path(self.config.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            with open(log_path, "a") as f:
                f.write(json.dumps(metric.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"❌ Failed to log metric to file: {e}")

    async def _check_alert_thresholds(self):
        """Check metrics against alert thresholds"""
        if not self.config.enable_real_time_alerts:
            return

        for metric_type, thresholds in self.config.alert_thresholds.items():
            if (
                metric_type not in self.metrics_buffer
                or not self.metrics_buffer[metric_type]
            ):
                continue

            # Get latest metric value
            latest_metric = self.metrics_buffer[metric_type][-1]
            current_value = latest_metric.value

            # Check each alert level
            for alert_level, threshold in thresholds.items():
                alert_id = f"{metric_type.value}_{alert_level.value}"

                # Check if threshold is exceeded
                if current_value >= threshold:
                    if alert_id not in self.active_alerts:
                        # Create new alert
                        alert = PerformanceAlert(
                            alert_id=alert_id,
                            alert_level=alert_level,
                            metric_type=metric_type,
                            message=f"{metric_type.value} is {current_value}{latest_metric.unit} (threshold: {threshold}{latest_metric.unit})",
                            threshold=threshold,
                            current_value=current_value,
                            timestamp=time.time(),
                        )

                        self.active_alerts[alert_id] = alert
                        await self._handle_alert(alert)

                        with self.stats_lock:
                            self.collection_stats["alerts_generated"] += 1
                else:
                    # Resolve alert if it exists
                    if alert_id in self.active_alerts:
                        alert = self.active_alerts[alert_id]
                        alert.resolved = True
                        await self._handle_alert_resolution(alert)
                        del self.active_alerts[alert_id]

    async def _handle_alert(self, alert: PerformanceAlert):
        """Handle a new performance alert"""
        logger.warning(
            f"🚨 Performance Alert [{alert.alert_level.value.upper()}]: {alert.message}"
        )

        # Store alert in cache
        if self.cache_manager:
            try:
                await self.cache_manager.set(
                    f"performance:alerts:{int(time.time())}",
                    json.dumps(alert.to_dict()),
                    ttl=86400,  # 24 hours
                )
            except Exception as e:
                logger.error(f"❌ Failed to store alert in cache: {e}")

        # Call registered alert callbacks
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"❌ Error in alert callback: {e}")

    async def _handle_alert_resolution(self, alert: PerformanceAlert):
        """Handle alert resolution"""
        logger.info(f"✅ Performance Alert Resolved: {alert.message}")

    def register_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Register callback for alert notifications"""
        self.alert_callbacks.append(callback)

    def get_current_metrics(
        self, metric_type: Optional[MetricType] = None
    ) -> Dict[str, Any]:
        """Get current metric values"""
        if metric_type:
            metrics = self.metrics_buffer.get(metric_type, [])
            return {
                "metric_type": metric_type.value,
                "current_value": metrics[-1].value if metrics else None,
                "unit": metrics[-1].unit if metrics else None,
                "timestamp": metrics[-1].timestamp if metrics else None,
            }

        result = {}
        for mtype, metrics in self.metrics_buffer.items():
            if metrics:
                latest = metrics[-1]
                result[mtype.value] = {
                    "value": latest.value,
                    "unit": latest.unit,
                    "timestamp": latest.timestamp,
                }

        return result

    def get_metric_history(
        self, metric_type: MetricType, minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """Get historical metrics for specified time period"""
        cutoff_time = time.time() - (minutes * 60)
        metrics = self.metrics_buffer.get(metric_type, [])

        return [
            metric.to_dict() for metric in metrics if metric.timestamp >= cutoff_time
        ]

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [alert.to_dict() for alert in self.active_alerts.values()]

    async def get_system_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive system health summary"""
        current_metrics = self.get_current_metrics()

        # Calculate health score (0-100)
        health_score = 100.0

        # Deduct points for high resource usage
        if MetricType.CPU_USAGE.value in current_metrics:
            cpu_usage = current_metrics[MetricType.CPU_USAGE.value]["value"]
            if cpu_usage > 80:
                health_score -= min((cpu_usage - 80) * 2, 30)

        if MetricType.MEMORY_USAGE.value in current_metrics:
            memory_usage = current_metrics[MetricType.MEMORY_USAGE.value]["value"]
            if memory_usage > 75:
                health_score -= min((memory_usage - 75) * 1.5, 25)

        # Deduct points for active alerts
        critical_alerts = len(
            [
                a
                for a in self.active_alerts.values()
                if a.alert_level == AlertLevel.CRITICAL
            ]
        )
        emergency_alerts = len(
            [
                a
                for a in self.active_alerts.values()
                if a.alert_level == AlertLevel.EMERGENCY
            ]
        )

        health_score -= critical_alerts * 10
        health_score -= emergency_alerts * 20
        health_score = max(0, health_score)

        # Determine health status
        if health_score >= 90:
            health_status = "excellent"
        elif health_score >= 75:
            health_status = "good"
        elif health_score >= 50:
            health_status = "fair"
        elif health_score >= 25:
            health_status = "poor"
        else:
            health_status = "critical"

        return {
            "health_score": health_score,
            "health_status": health_status,
            "current_metrics": current_metrics,
            "active_alerts_count": len(self.active_alerts),
            "critical_alerts": critical_alerts,
            "emergency_alerts": emergency_alerts,
            "monitoring_stats": self.collection_stats,
            "timestamp": time.time(),
        }

    async def record_media_processing_time(
        self,
        operation_type: str,
        processing_time: float,
        file_path: Optional[str] = None,
    ):
        """Record media processing time for performance tracking"""
        tags = {"operation_type": operation_type}
        if file_path:
            tags["file_extension"] = Path(file_path).suffix.lower()

        await self._store_metric(
            MetricType.MEDIA_PROCESSING_TIME, processing_time, "seconds", tags
        )

    async def record_api_response_time(
        self, endpoint: str, response_time: float, status_code: int
    ):
        """Record API response time"""
        await self._store_metric(
            MetricType.API_RESPONSE_TIME,
            response_time,
            "milliseconds",
            {"endpoint": endpoint, "status_code": str(status_code)},
        )

    async def record_error_rate(
        self, operation_type: str, error_count: int, total_operations: int
    ):
        """Record error rate for operations"""
        error_rate = (
            (error_count / total_operations * 100) if total_operations > 0 else 0
        )

        await self._store_metric(
            MetricType.ERROR_RATE,
            error_rate,
            "percent",
            {"operation_type": operation_type},
        )

    async def record_concurrent_operations(self, operation_type: str, count: int):
        """Record number of concurrent operations"""
        await self._store_metric(
            MetricType.CONCURRENT_OPERATIONS,
            count,
            "count",
            {"operation_type": operation_type},
        )

    async def get_performance_report(self, hours: int = 1) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report_data = {
            "report_period_hours": hours,
            "generated_at": time.time(),
            "system_health": await self.get_system_health_summary(),
            "metric_summaries": {},
            "alert_summary": {
                "total_alerts": len(self.active_alerts),
                "alerts_by_level": defaultdict(int),
                "most_frequent_alerts": [],
            },
        }

        # Calculate metric summaries
        minutes = hours * 60
        for metric_type in MetricType:
            history = self.get_metric_history(metric_type, minutes)
            if history:
                values = [h["value"] for h in history]
                report_data["metric_summaries"][metric_type.value] = {
                    "current": values[-1],
                    "average": sum(values) / len(values),
                    "minimum": min(values),
                    "maximum": max(values),
                    "data_points": len(values),
                }

        # Alert summary
        for alert in self.active_alerts.values():
            report_data["alert_summary"]["alerts_by_level"][
                alert.alert_level.value
            ] += 1

        return report_data


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


async def get_performance_monitor(
    config: Optional[MonitoringConfig] = None,
) -> PerformanceMonitor:
    """Get or create global performance monitor instance"""
    global _performance_monitor

    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor(config)
        await _performance_monitor.start_monitoring()

    return _performance_monitor


# Convenience functions for performance tracking
async def track_media_processing_time(
    operation_type: str, processing_time: float, file_path: Optional[str] = None
):
    """Track media processing time"""
    monitor = await get_performance_monitor()
    await monitor.record_media_processing_time(
        operation_type, processing_time, file_path
    )


async def track_api_response_time(
    endpoint: str, response_time: float, status_code: int
):
    """Track API response time"""
    monitor = await get_performance_monitor()
    await monitor.record_api_response_time(endpoint, response_time, status_code)


async def track_error_rate(
    operation_type: str, error_count: int, total_operations: int
):
    """Track error rate"""
    monitor = await get_performance_monitor()
    await monitor.record_error_rate(operation_type, error_count, total_operations)


async def get_system_health() -> Dict[str, Any]:
    """Get current system health summary"""
    monitor = await get_performance_monitor()
    return await monitor.get_system_health_summary()


async def get_performance_alerts() -> List[Dict[str, Any]]:
    """Get active performance alerts"""
    monitor = await get_performance_monitor()
    return monitor.get_active_alerts()
