"""
Analytics Middleware - Phase 3 Week 36
Automatic metrics collection from requests for monitoring dashboard
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, Optional

import psutil
from fastapi import Request
from src.middleware.auto_scaling_middleware import ResourceMetrics
from src.services.analytics_service import (
    MetricPoint,
    MetricType,
    get_analytics_service,
)
from src.utils.logger import get_logger
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger("mvidarr.middleware.analytics")


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically collect analytics from requests"""

    def __init__(self, app):
        super().__init__(app)
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        self.last_metrics_collection = 0
        self.metrics_collection_interval = 30  # seconds

        # Start background metrics collection
        asyncio.create_task(self._background_metrics_collection())

        logger.info("📊 Analytics middleware initialized")

    async def dispatch(self, request: Request, call_next):
        """Process request and collect analytics"""
        start_time = time.time()
        self.request_count += 1

        try:
            # Process request
            response = await call_next(request)

            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            self.total_response_time += response_time_ms

            # Track errors
            is_error = response.status_code >= 400
            if is_error:
                self.error_count += 1

            # Record request metrics
            await self._record_request_metrics(
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                is_error=is_error,
            )

            # Add analytics headers
            response.headers["X-Request-Count"] = str(self.request_count)
            response.headers["X-Analytics-Enabled"] = "true"

            return response

        except Exception as e:
            # Record error metrics
            response_time_ms = (time.time() - start_time) * 1000
            self.error_count += 1

            await self._record_request_metrics(
                endpoint=request.url.path,
                method=request.method,
                status_code=500,
                response_time_ms=response_time_ms,
                is_error=True,
                error=str(e),
            )

            raise

    async def _record_request_metrics(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        is_error: bool,
        error: Optional[str] = None,
    ):
        """Record individual request metrics"""
        try:
            analytics_service = await get_analytics_service()
            timestamp = datetime.utcnow()

            # Request count metric
            await analytics_service.record_metric(
                MetricPoint(
                    timestamp=timestamp,
                    metric_name="requests.count",
                    metric_type=MetricType.APPLICATION,
                    value=1,
                    tags={
                        "endpoint": endpoint,
                        "method": method,
                        "status_code": str(status_code),
                    },
                )
            )

            # Response time metric
            await analytics_service.record_metric(
                MetricPoint(
                    timestamp=timestamp,
                    metric_name="requests.response_time_ms",
                    metric_type=MetricType.PERFORMANCE,
                    value=response_time_ms,
                    tags={"endpoint": endpoint, "method": method},
                )
            )

            # Error metrics
            if is_error:
                await analytics_service.record_metric(
                    MetricPoint(
                        timestamp=timestamp,
                        metric_name="requests.errors",
                        metric_type=MetricType.APPLICATION,
                        value=1,
                        tags={
                            "endpoint": endpoint,
                            "status_code": str(status_code),
                            "error_type": "http_error" if not error else "exception",
                        },
                        metadata={"error_message": error} if error else {},
                    )
                )

        except Exception as e:
            logger.error(f"Failed to record request metrics: {e}")

    async def _background_metrics_collection(self):
        """Background task to collect system and application metrics"""
        while True:
            try:
                await asyncio.sleep(self.metrics_collection_interval)

                current_time = time.time()
                if (
                    current_time - self.last_metrics_collection
                    < self.metrics_collection_interval
                ):
                    continue

                # Collect system metrics
                await self._collect_system_metrics()

                # Collect application metrics
                await self._collect_application_metrics()

                self.last_metrics_collection = current_time

            except Exception as e:
                logger.error(f"Background metrics collection error: {e}")

    async def _collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            analytics_service = await get_analytics_service()

            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            # Create resource metrics object
            resource_metrics = ResourceMetrics(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024**3),
                memory_available_gb=memory.available / (1024**3),
                disk_usage_percent=(disk.used / disk.total) * 100,
                active_connections=0,  # Will be updated by connection tracking
                requests_per_second=0.0,  # Will be calculated
                avg_response_time_ms=0.0,  # Will be calculated
                error_rate_percent=0.0,  # Will be calculated
            )

            # Record system metrics
            await analytics_service.record_system_metrics(resource_metrics)

        except Exception as e:
            logger.error(f"System metrics collection error: {e}")

    async def _collect_application_metrics(self):
        """Collect application performance metrics"""
        try:
            analytics_service = await get_analytics_service()

            # Calculate metrics since last collection
            time_window = self.metrics_collection_interval

            # Requests per second
            rps = self.request_count / time_window if time_window > 0 else 0

            # Average response time
            avg_response_time = (
                (self.total_response_time / self.request_count)
                if self.request_count > 0
                else 0
            )

            # Error rate
            error_rate = (
                (self.error_count / self.request_count * 100)
                if self.request_count > 0
                else 0
            )

            # Record application metrics
            await analytics_service.record_application_metrics(
                active_connections=0,  # TODO: Track active connections
                requests_per_second=rps,
                avg_response_time=avg_response_time,
                error_rate=error_rate,
            )

            # Reset counters for next window
            self.request_count = 0
            self.error_count = 0
            self.total_response_time = 0.0

        except Exception as e:
            logger.error(f"Application metrics collection error: {e}")

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current middleware statistics"""
        return {
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "avg_response_time_ms": (
                (self.total_response_time / self.request_count)
                if self.request_count > 0
                else 0
            ),
            "error_rate_percent": (
                (self.error_count / self.request_count * 100)
                if self.request_count > 0
                else 0
            ),
            "metrics_collection_interval": self.metrics_collection_interval,
            "last_collection": self.last_metrics_collection,
        }
