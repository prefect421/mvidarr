"""
Performance Monitoring FastAPI Router - Phase 3 Week 33
Real-time performance metrics and monitoring endpoints
"""

import asyncio
import time
from datetime import datetime
from typing import List, Optional

import psutil
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.media_cache_manager import MediaCacheManager
from src.services.performance_monitor import get_performance_monitor
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/performance",
    tags=["performance"],
    responses={
        404: {"description": "Performance metric not found"},
        500: {"description": "Performance monitoring error"},
    },
)

logger = get_logger("mvidarr.api.performance")


# Response Models
class SystemMetrics(BaseModel):
    """System resource usage metrics"""

    cpu_percent: float = Field(description="CPU usage percentage")
    memory_percent: float = Field(description="Memory usage percentage")
    memory_used_mb: float = Field(description="Memory used in MB")
    memory_available_mb: float = Field(description="Available memory in MB")
    disk_usage_percent: float = Field(description="Disk usage percentage")
    disk_free_gb: float = Field(description="Free disk space in GB")
    load_average: Optional[List[float]] = Field(
        None, description="System load average (1, 5, 15 min)"
    )


class APIMetrics(BaseModel):
    """API performance metrics"""

    total_requests: int = Field(description="Total API requests processed")
    avg_response_time: float = Field(description="Average response time in seconds")
    requests_per_minute: float = Field(description="Requests per minute (last 5 min)")
    error_rate: float = Field(description="Error rate percentage")
    active_connections: int = Field(description="Currently active connections")
    cache_hit_rate: float = Field(description="Cache hit rate percentage")


class CacheMetrics(BaseModel):
    """Cache performance metrics"""

    cache_hits: int = Field(description="Total cache hits")
    cache_misses: int = Field(description="Total cache misses")
    cache_hit_rate: float = Field(description="Cache hit rate percentage")
    cached_items: int = Field(description="Number of items in cache")
    cache_memory_usage: str = Field(description="Cache memory usage")
    average_cache_time: float = Field(description="Average cache retrieval time in ms")


class PerformanceOverview(BaseModel):
    """Complete performance overview"""

    timestamp: datetime = Field(description="Metrics timestamp")
    system: SystemMetrics = Field(description="System resource metrics")
    api: APIMetrics = Field(description="API performance metrics")
    cache: CacheMetrics = Field(description="Cache performance metrics")
    uptime_seconds: float = Field(description="Application uptime in seconds")
    status: str = Field(description="Overall performance status")


class EndpointPerformance(BaseModel):
    """Individual endpoint performance"""

    endpoint: str = Field(description="API endpoint path")
    method: str = Field(description="HTTP method")
    total_requests: int = Field(description="Total requests to this endpoint")
    avg_response_time: float = Field(description="Average response time in seconds")
    min_response_time: float = Field(description="Minimum response time in seconds")
    max_response_time: float = Field(description="Maximum response time in seconds")
    error_count: int = Field(description="Number of errors")
    error_rate: float = Field(description="Error rate percentage")
    cache_hit_rate: Optional[float] = Field(
        None, description="Cache hit rate for this endpoint"
    )


# Utility functions
async def get_system_metrics() -> SystemMetrics:
    """Get current system resource metrics"""
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Get memory info
        memory = psutil.virtual_memory()

        # Get disk usage for current directory
        disk = psutil.disk_usage("/")

        # Get load average (Unix only)
        load_avg = None
        try:
            load_avg = list(psutil.getloadavg())
        except (AttributeError, OSError):
            pass  # Windows doesn't have load average

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_available_mb=memory.available / (1024 * 1024),
            disk_usage_percent=(disk.used / disk.total) * 100,
            disk_free_gb=disk.free / (1024**3),
            load_average=load_avg,
        )
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        # Return default metrics on error
        return SystemMetrics(
            cpu_percent=0.0,
            memory_percent=0.0,
            memory_used_mb=0.0,
            memory_available_mb=0.0,
            disk_usage_percent=0.0,
            disk_free_gb=0.0,
        )


async def get_cache_metrics() -> CacheMetrics:
    """Get cache performance metrics"""
    try:
        cache_manager = MediaCacheManager()
        stats = await cache_manager.get_stats()

        total_requests = stats.get("hits", 0) + stats.get("misses", 0)
        hit_rate = (stats.get("hits", 0) / max(total_requests, 1)) * 100

        return CacheMetrics(
            cache_hits=stats.get("hits", 0),
            cache_misses=stats.get("misses", 0),
            cache_hit_rate=hit_rate,
            cached_items=stats.get("keys", 0),
            cache_memory_usage=stats.get("memory_usage", "0 MB"),
            average_cache_time=stats.get("avg_retrieval_time_ms", 0.0),
        )
    except Exception as e:
        logger.error(f"Error getting cache metrics: {e}")
        return CacheMetrics(
            cache_hits=0,
            cache_misses=0,
            cache_hit_rate=0.0,
            cached_items=0,
            cache_memory_usage="0 MB",
            average_cache_time=0.0,
        )


# API Endpoints
@router.get("/", response_model=PerformanceOverview)
async def get_performance_overview():
    """Get complete performance overview"""
    try:
        start_time = time.time()

        # Get all metrics concurrently
        system_metrics, cache_metrics = await asyncio.gather(
            get_system_metrics(), get_cache_metrics()
        )

        # Get performance monitor data
        try:
            monitor = await get_performance_monitor()
            monitor_stats = await monitor.get_stats()

            api_metrics = APIMetrics(
                total_requests=monitor_stats.get("total_requests", 0),
                avg_response_time=monitor_stats.get("avg_response_time", 0.0),
                requests_per_minute=monitor_stats.get("requests_per_minute", 0.0),
                error_rate=monitor_stats.get("error_rate", 0.0),
                active_connections=monitor_stats.get("active_connections", 0),
                cache_hit_rate=cache_metrics.cache_hit_rate,
            )
        except Exception as e:
            logger.warning(f"Error getting API metrics: {e}")
            api_metrics = APIMetrics(
                total_requests=0,
                avg_response_time=0.0,
                requests_per_minute=0.0,
                error_rate=0.0,
                active_connections=0,
                cache_hit_rate=cache_metrics.cache_hit_rate,
            )

        # Determine overall status
        status = "healthy"
        if system_metrics.cpu_percent > 80 or system_metrics.memory_percent > 85:
            status = "warning"
        if system_metrics.cpu_percent > 95 or system_metrics.memory_percent > 95:
            status = "critical"

        processing_time = time.time() - start_time
        logger.debug(f"Performance overview generated in {processing_time:.3f}s")

        return PerformanceOverview(
            timestamp=datetime.utcnow(),
            system=system_metrics,
            api=api_metrics,
            cache=cache_metrics,
            uptime_seconds=time.time() - start_time,  # Placeholder
            status=status,
        )

    except Exception as e:
        logger.error(f"Error getting performance overview: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/system", response_model=SystemMetrics)
async def get_system_performance():
    """Get system resource metrics"""
    return await get_system_metrics()


@router.get("/cache", response_model=CacheMetrics)
async def get_cache_performance():
    """Get cache performance metrics"""
    return await get_cache_metrics()


@router.get("/endpoints", response_model=List[EndpointPerformance])
async def get_endpoint_performance(
    limit: int = Query(20, ge=1, le=100, description="Maximum endpoints to return")
):
    """Get performance metrics for individual endpoints"""
    try:
        monitor = await get_performance_monitor()
        endpoint_stats = await monitor.get_endpoint_stats(limit=limit)

        performance_data = []
        for endpoint, stats in endpoint_stats.items():
            endpoint_perf = EndpointPerformance(
                endpoint=stats.get("path", endpoint),
                method=stats.get("method", "GET"),
                total_requests=stats.get("total_requests", 0),
                avg_response_time=stats.get("avg_response_time", 0.0),
                min_response_time=stats.get("min_response_time", 0.0),
                max_response_time=stats.get("max_response_time", 0.0),
                error_count=stats.get("error_count", 0),
                error_rate=stats.get("error_rate", 0.0),
                cache_hit_rate=stats.get("cache_hit_rate"),
            )
            performance_data.append(endpoint_perf)

        return performance_data

    except Exception as e:
        logger.error(f"Error getting endpoint performance: {e}")
        return []


@router.get("/trends")
async def get_performance_trends(
    hours: int = Query(24, ge=1, le=168, description="Hours of trend data")
):
    """Get performance trends over time"""
    try:
        monitor = await get_performance_monitor()
        trends = await monitor.get_trends(hours=hours)

        return {
            "period_hours": hours,
            "data_points": len(trends),
            "trends": trends,
            "summary": {
                "avg_response_time": sum(t.get("avg_response_time", 0) for t in trends)
                / max(len(trends), 1),
                "peak_requests_per_minute": max(
                    (t.get("requests_per_minute", 0) for t in trends), default=0
                ),
                "avg_error_rate": sum(t.get("error_rate", 0) for t in trends)
                / max(len(trends), 1),
            },
        }

    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        return {"error": str(e)}


@router.post("/cache/clear")
async def clear_performance_cache():
    """Clear performance and response caches"""
    try:
        cache_manager = MediaCacheManager()

        # Clear API response cache
        api_cache_cleared = await cache_manager.clear_pattern("api_cache:*")

        # Clear function cache
        func_cache_cleared = await cache_manager.clear_pattern("func_cache:*")

        # Clear performance cache
        perf_cache_cleared = await cache_manager.clear_pattern("performance:*")

        logger.info("Performance caches cleared via API request")

        return {
            "success": True,
            "message": "Performance caches cleared successfully",
            "cleared": {
                "api_responses": api_cache_cleared,
                "function_cache": func_cache_cleared,
                "performance_cache": perf_cache_cleared,
            },
        }

    except Exception as e:
        logger.error(f"Error clearing performance cache: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def performance_health_check():
    """Quick performance health check"""
    start_time = time.time()

    try:
        # Quick system check
        cpu_usage = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        # Quick cache check
        cache_manager = MediaCacheManager()
        cache_available = await cache_manager.health_check()

        processing_time = time.time() - start_time

        status = "healthy"
        if cpu_usage > 80 or memory.percent > 85:
            status = "warning"
        if cpu_usage > 95 or memory.percent > 95 or not cache_available:
            status = "critical"

        return {
            "status": status,
            "processing_time": f"{processing_time:.3f}s",
            "cpu_usage": f"{cpu_usage:.1f}%",
            "memory_usage": f"{memory.percent:.1f}%",
            "cache_available": cache_available,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Performance health check error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
