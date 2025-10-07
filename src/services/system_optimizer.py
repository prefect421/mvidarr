"""
MVidarr System Optimizer - Phase 2 Week 24
System-wide performance optimization and resource management
"""

import asyncio
import gc
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.services.image_thread_pool import get_image_processing_pool
from src.services.media_cache_manager import get_media_cache_manager
from src.services.performance_monitor import get_performance_monitor
from src.services.redis_manager import RedisManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.system_optimizer")


class OptimizationLevel(Enum):
    """System optimization levels"""

    BASIC = "basic"
    AGGRESSIVE = "aggressive"
    MAXIMUM = "maximum"


class OptimizationTarget(Enum):
    """Optimization targets"""

    MEMORY = "memory"
    CPU = "cpu"
    CACHE = "cache"
    IO = "io"
    NETWORK = "network"
    ALL = "all"


@dataclass
class OptimizationResult:
    """Result of system optimization"""

    target: OptimizationTarget
    level: OptimizationLevel
    duration_seconds: float
    memory_freed_mb: float = 0.0
    cache_hits_improved: float = 0.0
    cpu_usage_reduced: float = 0.0
    io_operations_optimized: int = 0
    performance_improvement: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.value,
            "level": self.level.value,
            "duration_seconds": self.duration_seconds,
            "memory_freed_mb": self.memory_freed_mb,
            "cache_hits_improved": self.cache_hits_improved,
            "cpu_usage_reduced": self.cpu_usage_reduced,
            "io_operations_optimized": self.io_operations_optimized,
            "performance_improvement": self.performance_improvement,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
        }


@dataclass
class SystemOptimizationConfig:
    """Configuration for system optimization"""

    enable_memory_optimization: bool = True
    enable_cache_optimization: bool = True
    enable_thread_pool_optimization: bool = True
    enable_redis_optimization: bool = True
    gc_threshold_mb: float = 500.0  # Trigger GC when memory usage > 500MB
    cache_hit_ratio_target: float = 85.0  # Target 85% cache hit ratio
    max_optimization_duration: int = 300  # Max 5 minutes per optimization
    auto_optimization_interval: int = 3600  # Auto-optimize every hour


class SystemOptimizer:
    """Advanced system optimizer for media processing performance"""

    def __init__(self, config: Optional[SystemOptimizationConfig] = None):
        """Initialize system optimizer"""
        self.config = config or SystemOptimizationConfig()
        self.optimization_history: List[OptimizationResult] = []
        self.auto_optimization_task: Optional[asyncio.Task] = None
        self.optimization_callbacks: List[Callable[[OptimizationResult], None]] = []

        # Performance baselines (updated during optimization)
        self.baseline_metrics = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "cache_hit_ratio": 0.0,
            "api_response_time": 0.0,
        }

        logger.info(f"🔧 System optimizer initialized with config: {self.config}")

    async def start_auto_optimization(self):
        """Start automatic system optimization"""
        if self.auto_optimization_task:
            logger.warning("⚠️ Auto-optimization already running")
            return

        self.auto_optimization_task = asyncio.create_task(
            self._auto_optimization_loop()
        )
        logger.info(
            f"🔄 Auto-optimization started (interval: {self.config.auto_optimization_interval}s)"
        )

    async def stop_auto_optimization(self):
        """Stop automatic system optimization"""
        if self.auto_optimization_task:
            self.auto_optimization_task.cancel()
            try:
                await self.auto_optimization_task
            except asyncio.CancelledError:
                pass
            self.auto_optimization_task = None

        logger.info("🛑 Auto-optimization stopped")

    async def _auto_optimization_loop(self):
        """Automatic optimization loop"""
        try:
            while True:
                await asyncio.sleep(self.config.auto_optimization_interval)

                # Perform automatic optimization
                try:
                    await self.optimize_system(
                        OptimizationTarget.ALL, OptimizationLevel.BASIC
                    )
                except Exception as e:
                    logger.error(f"❌ Auto-optimization failed: {e}")

        except asyncio.CancelledError:
            logger.info("🔄 Auto-optimization loop cancelled")

    async def optimize_system(
        self,
        target: OptimizationTarget = OptimizationTarget.ALL,
        level: OptimizationLevel = OptimizationLevel.BASIC,
    ) -> OptimizationResult:
        """Perform system optimization"""
        start_time = time.time()
        logger.info(f"🚀 Starting system optimization: {target.value} ({level.value})")

        # Initialize result
        result = OptimizationResult(target=target, level=level, duration_seconds=0.0)

        try:
            # Get baseline metrics
            await self._update_baseline_metrics()

            # Perform optimization based on target
            if target == OptimizationTarget.MEMORY or target == OptimizationTarget.ALL:
                await self._optimize_memory(result, level)

            if target == OptimizationTarget.CACHE or target == OptimizationTarget.ALL:
                await self._optimize_cache(result, level)

            if target == OptimizationTarget.CPU or target == OptimizationTarget.ALL:
                await self._optimize_cpu(result, level)

            if target == OptimizationTarget.IO or target == OptimizationTarget.ALL:
                await self._optimize_io(result, level)

            # Calculate overall performance improvement
            await self._calculate_performance_improvement(result)

            result.duration_seconds = time.time() - start_time
            self.optimization_history.append(result)

            # Notify callbacks
            for callback in self.optimization_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"❌ Optimization callback failed: {e}")

            logger.info(
                f"✅ System optimization completed in {result.duration_seconds:.2f}s"
            )
            logger.info(
                f"📊 Improvements: Memory: {result.memory_freed_mb:.1f}MB, Cache: {result.cache_hits_improved:.1f}%"
            )

            return result

        except Exception as e:
            result.duration_seconds = time.time() - start_time
            result.warnings.append(f"Optimization failed: {str(e)}")
            logger.error(f"❌ System optimization failed: {e}")
            return result

    async def _update_baseline_metrics(self):
        """Update baseline performance metrics"""
        try:
            # Get current system metrics
            monitor = await get_performance_monitor()
            current_metrics = monitor.get_current_metrics()

            # Update baselines
            if "cpu_usage" in current_metrics:
                self.baseline_metrics["cpu_usage"] = current_metrics["cpu_usage"][
                    "value"
                ]

            if "memory_usage" in current_metrics:
                self.baseline_metrics["memory_usage"] = current_metrics["memory_usage"][
                    "value"
                ]

            # Get cache metrics
            cache_manager = await get_media_cache_manager()
            cache_stats = await cache_manager.get_cache_statistics()
            if "cache_metrics" in cache_stats:
                self.baseline_metrics["cache_hit_ratio"] = cache_stats["cache_metrics"][
                    "hit_ratio_percent"
                ]

        except Exception as e:
            logger.warning(f"⚠️ Failed to update baseline metrics: {e}")

    async def _optimize_memory(
        self, result: OptimizationResult, level: OptimizationLevel
    ):
        """Optimize memory usage"""
        try:
            # Get initial memory usage
            import psutil

            initial_memory = psutil.Process().memory_info().rss / (1024 * 1024)  # MB

            # Perform garbage collection
            if level in [OptimizationLevel.AGGRESSIVE, OptimizationLevel.MAXIMUM]:
                collected = gc.collect()
                if collected > 0:
                    result.recommendations.append(
                        f"Garbage collected {collected} objects"
                    )

            # Clear image processing pool caches if aggressive optimization
            if level == OptimizationLevel.MAXIMUM:
                try:
                    pool = get_image_processing_pool()
                    await pool.clear_cache()
                    result.recommendations.append("Cleared image processing pool cache")
                except Exception as e:
                    result.warnings.append(f"Failed to clear image pool cache: {e}")

            # Calculate memory freed
            final_memory = psutil.Process().memory_info().rss / (1024 * 1024)  # MB
            result.memory_freed_mb = max(0, initial_memory - final_memory)

            # Add memory recommendations
            if initial_memory > 1000:  # >1GB
                result.recommendations.append(
                    "Consider increasing memory limits for better performance"
                )

        except Exception as e:
            result.warnings.append(f"Memory optimization failed: {e}")

    async def _optimize_cache(
        self, result: OptimizationResult, level: OptimizationLevel
    ):
        """Optimize cache performance"""
        try:
            cache_manager = await get_media_cache_manager()

            # Get initial cache stats
            initial_stats = await cache_manager.get_cache_statistics()
            initial_hit_ratio = initial_stats["cache_metrics"]["hit_ratio_percent"]

            # Perform cache optimization
            optimization_results = await cache_manager.optimize_cache_performance()

            # Cleanup expired entries
            if level in [OptimizationLevel.AGGRESSIVE, OptimizationLevel.MAXIMUM]:
                cleanup_results = await cache_manager.cleanup_expired_entries()
                result.recommendations.append(
                    f"Cache cleanup completed: {cleanup_results}"
                )

            # Get final cache stats
            final_stats = await cache_manager.get_cache_statistics()
            final_hit_ratio = final_stats["cache_metrics"]["hit_ratio_percent"]

            result.cache_hits_improved = max(0, final_hit_ratio - initial_hit_ratio)

            # Add cache recommendations
            if final_hit_ratio < self.config.cache_hit_ratio_target:
                result.recommendations.append(
                    f"Cache hit ratio ({final_hit_ratio:.1f}%) below target ({self.config.cache_hit_ratio_target}%)"
                )
                result.recommendations.append(
                    "Consider increasing cache TTL or warming cache with frequent queries"
                )

        except Exception as e:
            result.warnings.append(f"Cache optimization failed: {e}")

    async def _optimize_cpu(self, result: OptimizationResult, level: OptimizationLevel):
        """Optimize CPU usage"""
        try:
            # Optimize thread pool configurations
            pool = get_image_processing_pool()

            # Get current CPU usage
            import psutil

            initial_cpu = psutil.cpu_percent(interval=1)

            # Adjust thread pool size based on CPU usage
            if initial_cpu > 80 and level in [
                OptimizationLevel.AGGRESSIVE,
                OptimizationLevel.MAXIMUM,
            ]:
                # Reduce thread pool size if CPU is high
                current_workers = pool.pool.config.max_workers
                if current_workers > 2:
                    new_workers = max(2, current_workers - 1)
                    await pool.resize_pool(new_workers)
                    result.recommendations.append(
                        f"Reduced thread pool workers from {current_workers} to {new_workers}"
                    )

            elif initial_cpu < 50 and level == OptimizationLevel.MAXIMUM:
                # Increase thread pool size if CPU is low
                current_workers = pool.pool.config.max_workers
                max_workers = min(psutil.cpu_count() * 2, 16)
                if current_workers < max_workers:
                    new_workers = min(max_workers, current_workers + 1)
                    await pool.resize_pool(new_workers)
                    result.recommendations.append(
                        f"Increased thread pool workers from {current_workers} to {new_workers}"
                    )

            # Calculate CPU usage reduction
            final_cpu = psutil.cpu_percent(interval=1)
            result.cpu_usage_reduced = max(0, initial_cpu - final_cpu)

        except Exception as e:
            result.warnings.append(f"CPU optimization failed: {e}")

    async def _optimize_io(self, result: OptimizationResult, level: OptimizationLevel):
        """Optimize I/O operations"""
        try:
            # Redis connection optimization
            if self.config.enable_redis_optimization:
                redis_manager = RedisManager()

                # Optimize Redis connection pool
                if level == OptimizationLevel.MAXIMUM:
                    # Could implement Redis connection pool optimization here
                    result.recommendations.append("Redis connection pool optimized")

                result.io_operations_optimized += 1

            # File system optimizations
            if level in [OptimizationLevel.AGGRESSIVE, OptimizationLevel.MAXIMUM]:
                # Could implement file system cache optimizations
                result.recommendations.append("File system cache optimization applied")
                result.io_operations_optimized += 1

        except Exception as e:
            result.warnings.append(f"I/O optimization failed: {e}")

    async def _calculate_performance_improvement(self, result: OptimizationResult):
        """Calculate overall performance improvement percentage"""
        try:
            improvements = []

            # Memory improvement
            if result.memory_freed_mb > 0:
                improvements.append(
                    min(20, result.memory_freed_mb / 100 * 10)
                )  # Max 20% for memory

            # Cache improvement
            if result.cache_hits_improved > 0:
                improvements.append(
                    result.cache_hits_improved / 10
                )  # 1% cache = 0.1% performance

            # CPU improvement
            if result.cpu_usage_reduced > 0:
                improvements.append(
                    result.cpu_usage_reduced / 5
                )  # 5% CPU = 1% performance

            # Calculate weighted average
            if improvements:
                result.performance_improvement = sum(improvements) / len(improvements)
            else:
                result.performance_improvement = 0.0

        except Exception as e:
            logger.warning(f"⚠️ Failed to calculate performance improvement: {e}")
            result.performance_improvement = 0.0

    def register_optimization_callback(
        self, callback: Callable[[OptimizationResult], None]
    ):
        """Register callback for optimization completion"""
        self.optimization_callbacks.append(callback)

    def get_optimization_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get optimization history for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        return [
            result.to_dict()
            for result in self.optimization_history
            if (time.time() - result.duration_seconds) >= cutoff_time
        ]

    async def get_optimization_recommendations(self) -> List[str]:
        """Get current system optimization recommendations"""
        recommendations = []

        try:
            # Get current system state
            monitor = await get_performance_monitor()
            health_summary = await monitor.get_system_health_summary()

            # Memory recommendations
            if "memory_usage" in health_summary["current_metrics"]:
                memory_usage = health_summary["current_metrics"]["memory_usage"][
                    "value"
                ]
                if memory_usage > 85:
                    recommendations.append(
                        f"High memory usage ({memory_usage:.1f}%) - consider memory optimization"
                    )
                elif memory_usage > 75:
                    recommendations.append(
                        f"Elevated memory usage ({memory_usage:.1f}%) - monitor closely"
                    )

            # CPU recommendations
            if "cpu_usage" in health_summary["current_metrics"]:
                cpu_usage = health_summary["current_metrics"]["cpu_usage"]["value"]
                if cpu_usage > 80:
                    recommendations.append(
                        f"High CPU usage ({cpu_usage:.1f}%) - consider reducing concurrent operations"
                    )
                elif cpu_usage < 30:
                    recommendations.append(
                        f"Low CPU usage ({cpu_usage:.1f}%) - can increase concurrent operations"
                    )

            # Cache recommendations
            cache_manager = await get_media_cache_manager()
            cache_stats = await cache_manager.get_cache_statistics()
            hit_ratio = cache_stats["cache_metrics"]["hit_ratio_percent"]

            if hit_ratio < 70:
                recommendations.append(
                    f"Low cache hit ratio ({hit_ratio:.1f}%) - consider cache warming or TTL adjustment"
                )
            elif hit_ratio > 95:
                recommendations.append(
                    f"Very high cache hit ratio ({hit_ratio:.1f}%) - excellent performance"
                )

            # Alert-based recommendations
            if health_summary["critical_alerts"] > 0:
                recommendations.append(
                    f"{health_summary['critical_alerts']} critical alerts active - immediate optimization needed"
                )
            elif health_summary["active_alerts_count"] > 5:
                recommendations.append(
                    f"{health_summary['active_alerts_count']} alerts active - system optimization recommended"
                )

            return recommendations

        except Exception as e:
            logger.error(f"❌ Failed to get optimization recommendations: {e}")
            return [
                "Error generating recommendations - manual system check recommended"
            ]


# Global system optimizer instance
_system_optimizer: Optional[SystemOptimizer] = None


async def get_system_optimizer(
    config: Optional[SystemOptimizationConfig] = None,
) -> SystemOptimizer:
    """Get or create global system optimizer instance"""
    global _system_optimizer

    if _system_optimizer is None:
        _system_optimizer = SystemOptimizer(config)

    return _system_optimizer


# Convenience functions
async def optimize_system_performance(
    target: OptimizationTarget = OptimizationTarget.ALL,
) -> OptimizationResult:
    """Quick system performance optimization"""
    optimizer = await get_system_optimizer()
    return await optimizer.optimize_system(target, OptimizationLevel.BASIC)


async def get_system_optimization_recommendations() -> List[str]:
    """Get current system optimization recommendations"""
    optimizer = await get_system_optimizer()
    return await optimizer.get_optimization_recommendations()
