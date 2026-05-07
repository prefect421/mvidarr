"""
Auto-Scaling Middleware - Phase 3 Week 35
Intelligent resource adaptation and load balancing for production environments
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import psutil
from fastapi import Request
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger("mvidarr.middleware.auto_scaling")


class ScalingAction(Enum):
    """Scaling action types"""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    OPTIMIZE = "optimize"
    MAINTAIN = "maintain"


class LoadLevel(Enum):
    """System load levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    OVERLOAD = "overload"


@dataclass
class ResourceMetrics:
    """System resource metrics"""

    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_usage_percent: float
    active_connections: int
    requests_per_second: float
    avg_response_time_ms: float
    error_rate_percent: float


@dataclass
class ScalingDecision:
    """Auto-scaling decision"""

    action: ScalingAction
    reason: str
    confidence: float  # 0.0 - 1.0
    target_capacity: Optional[int] = None
    estimated_impact: Optional[str] = None
    recommended_actions: List[str] = field(default_factory=list)


class AdaptiveResourceManager:
    """Intelligent resource management and adaptation"""

    def __init__(self):
        self.metrics_history = deque(maxlen=300)  # 5 minutes at 1-second intervals
        self.scaling_decisions = deque(maxlen=50)
        self.last_scaling_action_time = 0
        self.scaling_cooldown_seconds = 300  # 5 minutes

        # Adaptive thresholds (will be adjusted based on observed patterns)
        self.thresholds = {
            "cpu_high": 75.0,
            "cpu_critical": 90.0,
            "memory_high": 80.0,
            "memory_critical": 95.0,
            "response_time_high": 1000,  # ms
            "response_time_critical": 2000,  # ms
            "error_rate_high": 2.0,  # percent
            "error_rate_critical": 5.0,  # percent
        }

        # Performance baselines (learned from historical data)
        self.baselines = {
            "normal_cpu": 30.0,
            "normal_memory": 50.0,
            "normal_response_time": 200.0,
            "normal_throughput": 50.0,
        }

        logger.info("🔄 Adaptive resource manager initialized")

    def add_metrics(self, metrics: ResourceMetrics):
        """Add new metrics to history"""
        self.metrics_history.append(metrics)

        # Update adaptive thresholds periodically
        if len(self.metrics_history) % 60 == 0:  # Every minute
            self._update_adaptive_thresholds()

    def _update_adaptive_thresholds(self):
        """Update thresholds based on observed patterns"""
        if len(self.metrics_history) < 30:
            return

        recent_metrics = list(self.metrics_history)[-30:]  # Last 30 samples

        # Calculate percentiles for adaptive thresholds
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]
        response_times = [m.avg_response_time_ms for m in recent_metrics]

        # Adaptive CPU thresholds
        avg_cpu = sum(cpu_values) / len(cpu_values)
        if avg_cpu > self.baselines["normal_cpu"] * 1.5:
            self.thresholds["cpu_high"] = min(85.0, avg_cpu * 1.3)

        # Adaptive memory thresholds
        avg_memory = sum(memory_values) / len(memory_values)
        if avg_memory > self.baselines["normal_memory"] * 1.3:
            self.thresholds["memory_high"] = min(85.0, avg_memory * 1.2)

        # Adaptive response time thresholds
        avg_response_time = sum(response_times) / len(response_times)
        if avg_response_time > self.baselines["normal_response_time"] * 2:
            self.thresholds["response_time_high"] = min(1500, avg_response_time * 1.5)

        logger.debug(
            f"🔧 Updated adaptive thresholds: CPU={self.thresholds['cpu_high']:.1f}%, Memory={self.thresholds['memory_high']:.1f}%"
        )

    def assess_load_level(self) -> LoadLevel:
        """Assess current system load level"""
        if not self.metrics_history:
            return LoadLevel.NORMAL

        latest = self.metrics_history[-1]

        # Critical conditions
        if (
            latest.cpu_percent >= self.thresholds["cpu_critical"]
            or latest.memory_percent >= self.thresholds["memory_critical"]
            or latest.avg_response_time_ms >= self.thresholds["response_time_critical"]
            or latest.error_rate_percent >= self.thresholds["error_rate_critical"]
        ):
            return LoadLevel.CRITICAL

        # High load conditions
        if (
            latest.cpu_percent >= self.thresholds["cpu_high"]
            or latest.memory_percent >= self.thresholds["memory_high"]
            or latest.avg_response_time_ms >= self.thresholds["response_time_high"]
            or latest.error_rate_percent >= self.thresholds["error_rate_high"]
        ):
            return LoadLevel.HIGH

        # Low load conditions
        if (
            latest.cpu_percent <= self.baselines["normal_cpu"] * 0.5
            and latest.memory_percent <= self.baselines["normal_memory"] * 0.7
            and latest.avg_response_time_ms
            <= self.baselines["normal_response_time"] * 0.8
        ):
            return LoadLevel.LOW

        return LoadLevel.NORMAL

    def make_scaling_decision(self) -> Optional[ScalingDecision]:
        """Make intelligent scaling decision"""
        if not self.metrics_history:
            return None

        # Check cooldown period
        if time.time() - self.last_scaling_action_time < self.scaling_cooldown_seconds:
            return None

        load_level = self.assess_load_level()
        latest_metrics = self.metrics_history[-1]

        # Analyze trends over last 5 minutes
        trend_analysis = self._analyze_trends()

        decision = None

        if load_level == LoadLevel.CRITICAL:
            decision = ScalingDecision(
                action=ScalingAction.SCALE_UP,
                reason=f"Critical load detected: CPU={latest_metrics.cpu_percent:.1f}%, Memory={latest_metrics.memory_percent:.1f}%, Response Time={latest_metrics.avg_response_time_ms:.0f}ms",
                confidence=0.9,
                recommended_actions=[
                    "Increase worker processes",
                    "Scale up database connections",
                    "Enable emergency cache modes",
                    "Activate circuit breakers",
                ],
            )

        elif load_level == LoadLevel.HIGH and trend_analysis["trend"] == "increasing":
            decision = ScalingDecision(
                action=ScalingAction.SCALE_UP,
                reason=f"High load with increasing trend: {trend_analysis['details']}",
                confidence=0.7,
                recommended_actions=[
                    "Gradually increase capacity",
                    "Optimize slow queries",
                    "Enable additional caching",
                ],
            )

        elif load_level == LoadLevel.LOW and trend_analysis["trend"] == "decreasing":
            # Only scale down if we've been at low load for extended period
            recent_low_count = sum(
                1
                for m in list(self.metrics_history)[-30:]
                if m.cpu_percent <= self.baselines["normal_cpu"] * 0.5
            )

            if recent_low_count >= 25:  # 25 out of last 30 samples
                decision = ScalingDecision(
                    action=ScalingAction.SCALE_DOWN,
                    reason=f"Sustained low load: {recent_low_count}/30 samples below threshold",
                    confidence=0.6,
                    recommended_actions=[
                        "Reduce worker processes gradually",
                        "Scale down non-essential services",
                        "Optimize resource allocation",
                    ],
                )

        elif (
            load_level == LoadLevel.HIGH
            and latest_metrics.avg_response_time_ms
            > self.baselines["normal_response_time"] * 3
        ):
            decision = ScalingDecision(
                action=ScalingAction.OPTIMIZE,
                reason=f"Performance degradation detected: Response time {latest_metrics.avg_response_time_ms:.0f}ms",
                confidence=0.8,
                recommended_actions=[
                    "Analyze slow endpoints",
                    "Optimize database queries",
                    "Increase cache hit rates",
                    "Review memory usage patterns",
                ],
            )

        if decision:
            self.scaling_decisions.append(decision)
            self.last_scaling_action_time = time.time()

        return decision

    def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze resource usage trends"""
        if len(self.metrics_history) < 10:
            return {"trend": "unknown", "details": "Insufficient data"}

        # Get recent samples for trend analysis
        recent_samples = list(self.metrics_history)[-10:]
        older_samples = (
            list(self.metrics_history)[-20:-10]
            if len(self.metrics_history) >= 20
            else recent_samples
        )

        # Calculate averages
        recent_cpu = sum(m.cpu_percent for m in recent_samples) / len(recent_samples)
        older_cpu = sum(m.cpu_percent for m in older_samples) / len(older_samples)

        recent_memory = sum(m.memory_percent for m in recent_samples) / len(
            recent_samples
        )
        older_memory = sum(m.memory_percent for m in older_samples) / len(older_samples)

        recent_response = sum(m.avg_response_time_ms for m in recent_samples) / len(
            recent_samples
        )
        older_response = sum(m.avg_response_time_ms for m in older_samples) / len(
            older_samples
        )

        # Determine trend
        cpu_trend = recent_cpu - older_cpu
        memory_trend = recent_memory - older_memory
        response_trend = recent_response - older_response

        # Combined trend assessment
        trend_score = 0
        details = []

        if cpu_trend > 5:
            trend_score += 1
            details.append(f"CPU increasing (+{cpu_trend:.1f}%)")
        elif cpu_trend < -5:
            trend_score -= 1
            details.append(f"CPU decreasing ({cpu_trend:.1f}%)")

        if memory_trend > 5:
            trend_score += 1
            details.append(f"Memory increasing (+{memory_trend:.1f}%)")
        elif memory_trend < -5:
            trend_score -= 1
            details.append(f"Memory decreasing ({memory_trend:.1f}%)")

        if response_trend > 100:
            trend_score += 1
            details.append(f"Response time increasing (+{response_trend:.0f}ms)")
        elif response_trend < -100:
            trend_score -= 1
            details.append(f"Response time decreasing ({response_trend:.0f}ms)")

        if trend_score > 0:
            trend = "increasing"
        elif trend_score < 0:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "trend_score": trend_score,
            "details": "; ".join(details) if details else "No significant changes",
            "cpu_change": cpu_trend,
            "memory_change": memory_trend,
            "response_time_change": response_trend,
        }

    def get_optimization_recommendations(self) -> List[str]:
        """Get performance optimization recommendations"""
        if not self.metrics_history:
            return []

        recommendations = []
        latest = self.metrics_history[-1]

        # CPU optimization
        if latest.cpu_percent > self.thresholds["cpu_high"]:
            recommendations.extend(
                [
                    "Consider increasing worker process pool size",
                    "Review CPU-intensive operations for optimization",
                    "Implement async processing for long-running tasks",
                ]
            )

        # Memory optimization
        if latest.memory_percent > self.thresholds["memory_high"]:
            recommendations.extend(
                [
                    "Implement more aggressive caching cleanup",
                    "Review memory leaks in application code",
                    "Consider memory-efficient data structures",
                ]
            )

        # Response time optimization
        if latest.avg_response_time_ms > self.thresholds["response_time_high"]:
            recommendations.extend(
                [
                    "Optimize database query performance",
                    "Implement connection pooling optimizations",
                    "Add caching for frequently accessed data",
                ]
            )

        # Error rate optimization
        if latest.error_rate_percent > self.thresholds["error_rate_high"]:
            recommendations.extend(
                [
                    "Implement circuit breakers for external services",
                    "Add retry mechanisms with exponential backoff",
                    "Review error handling and logging",
                ]
            )

        return recommendations


class AutoScalingMiddleware(BaseHTTPMiddleware):
    """Auto-scaling middleware with intelligent resource adaptation"""

    def __init__(self, app):
        super().__init__(app)
        self.resource_manager = AdaptiveResourceManager()
        self.cache_manager = MediaCacheManager()

        # Request tracking
        self.active_requests = 0
        self.total_requests = 0
        self.total_response_time = 0.0
        self.error_count = 0
        self.last_metrics_update = 0

        # Start background monitoring
        self._start_monitoring_task()

        logger.info("🔄 Auto-scaling middleware initialized")

    def _start_monitoring_task(self):
        """Start background monitoring task"""
        asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Background monitoring and scaling decision loop"""
        while True:
            try:
                await asyncio.sleep(10)  # Monitor every 10 seconds

                # Collect current metrics
                metrics = await self._collect_metrics()
                self.resource_manager.add_metrics(metrics)

                # Make scaling decision
                decision = self.resource_manager.make_scaling_decision()
                if decision:
                    await self._execute_scaling_decision(decision)

                # Update cache with current status
                await self._update_scaling_status()

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    async def _collect_metrics(self) -> ResourceMetrics:
        """Collect current system and application metrics"""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            # Application metrics
            current_time = time.time()
            time_window = current_time - 60  # Last minute

            if self.total_requests > 0:
                avg_response_time = self.total_response_time / self.total_requests
                error_rate = (self.error_count / self.total_requests) * 100
            else:
                avg_response_time = 0.0
                error_rate = 0.0

            # Estimate RPS (simple approximation)
            requests_per_second = (
                self.total_requests / 60 if self.total_requests > 0 else 0
            )

            return ResourceMetrics(
                timestamp=current_time,
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024**3),
                memory_available_gb=memory.available / (1024**3),
                disk_usage_percent=(disk.used / disk.total) * 100,
                active_connections=self.active_requests,
                requests_per_second=requests_per_second,
                avg_response_time_ms=avg_response_time,
                error_rate_percent=error_rate,
            )

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            # Return default metrics on error
            return ResourceMetrics(
                timestamp=time.time(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_gb=0.0,
                memory_available_gb=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                requests_per_second=0.0,
                avg_response_time_ms=0.0,
                error_rate_percent=0.0,
            )

    async def _execute_scaling_decision(self, decision: ScalingDecision):
        """Execute scaling decision"""
        logger.info(
            f"🔄 Executing scaling decision: {decision.action.value} - {decision.reason}"
        )

        try:
            if decision.action == ScalingAction.SCALE_UP:
                await self._scale_up_resources(decision)
            elif decision.action == ScalingAction.SCALE_DOWN:
                await self._scale_down_resources(decision)
            elif decision.action == ScalingAction.OPTIMIZE:
                await self._optimize_resources(decision)

            logger.info(f"✅ Scaling action {decision.action.value} completed")

        except Exception as e:
            logger.error(f"❌ Failed to execute scaling decision: {e}")

    async def _scale_up_resources(self, decision: ScalingDecision):
        """Scale up resources"""
        # Implement scaling up actions
        actions_taken = []

        # Increase cache capacity
        try:
            await self.cache_manager.set("scaling_mode", "scale_up", ttl=3600)
            actions_taken.append("Enabled scale-up cache mode")
        except Exception as e:
            logger.error(f"Cache scaling error: {e}")

        # Log recommendations for external scaling
        for action in decision.recommended_actions:
            logger.info(f"📝 Scaling recommendation: {action}")
            actions_taken.append(f"Logged: {action}")

        # Store scaling event
        scaling_event = {
            "timestamp": time.time(),
            "action": "scale_up",
            "reason": decision.reason,
            "confidence": decision.confidence,
            "actions_taken": actions_taken,
        }

        try:
            await self.cache_manager.set(
                f"scaling_event_{int(time.time())}", str(scaling_event), ttl=86400
            )
        except Exception as e:
            logger.error(f"Failed to log scaling event: {e}")

    async def _scale_down_resources(self, decision: ScalingDecision):
        """Scale down resources"""
        actions_taken = []

        # Enable resource conservation mode
        try:
            await self.cache_manager.set("scaling_mode", "scale_down", ttl=3600)
            actions_taken.append("Enabled scale-down conservation mode")
        except Exception as e:
            logger.error(f"Cache scaling error: {e}")

        # Log scaling down recommendations
        for action in decision.recommended_actions:
            logger.info(f"📝 Scale-down recommendation: {action}")
            actions_taken.append(f"Logged: {action}")

        logger.info(f"⬇️ Scale-down actions: {', '.join(actions_taken)}")

    async def _optimize_resources(self, decision: ScalingDecision):
        """Optimize current resources"""
        optimizations = []

        # Enable aggressive caching
        try:
            await self.cache_manager.set("cache_optimization", "aggressive", ttl=1800)
            optimizations.append("Enabled aggressive caching")
        except Exception as e:
            logger.error(f"Cache optimization error: {e}")

        # Get and apply optimization recommendations
        recommendations = self.resource_manager.get_optimization_recommendations()
        for rec in recommendations:
            logger.info(f"🔧 Optimization: {rec}")
            optimizations.append(f"Recommended: {rec}")

        logger.info(f"⚡ Optimizations applied: {', '.join(optimizations)}")

    async def _update_scaling_status(self):
        """Update scaling status in cache"""
        try:
            load_level = self.resource_manager.assess_load_level()

            status = {
                "timestamp": time.time(),
                "load_level": load_level.value,
                "active_requests": self.active_requests,
                "total_requests": self.total_requests,
                "last_scaling_action": self.resource_manager.last_scaling_action_time,
                "scaling_decisions_count": len(self.resource_manager.scaling_decisions),
            }

            await self.cache_manager.set("auto_scaling_status", str(status), ttl=60)

        except Exception as e:
            logger.error(f"Failed to update scaling status: {e}")

    async def dispatch(self, request: Request, call_next):
        """Process request with auto-scaling monitoring"""
        start_time = time.time()

        # Track active requests
        self.active_requests += 1
        self.total_requests += 1

        try:
            # Process request
            response = await call_next(request)

            # Track response time
            response_time_ms = (time.time() - start_time) * 1000
            self.total_response_time += response_time_ms

            # Track errors
            if response.status_code >= 400:
                self.error_count += 1

            # Add scaling headers
            load_level = self.resource_manager.assess_load_level()
            response.headers["X-Load-Level"] = load_level.value
            response.headers["X-Active-Requests"] = str(self.active_requests)
            response.headers["X-Auto-Scaling"] = "enabled"

            return response

        except Exception as e:
            self.error_count += 1
            logger.error(f"Request processing error: {e}")
            raise
        finally:
            self.active_requests -= 1


# API endpoint for scaling status
async def get_scaling_status() -> Dict[str, Any]:
    """Get current auto-scaling status"""
    try:
        cache_manager = MediaCacheManager()
        status_data = await cache_manager.get("auto_scaling_status") or "{}"

        return {
            "auto_scaling_enabled": True,
            "current_status": status_data,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error getting scaling status: {e}")
        return {"error": str(e)}
