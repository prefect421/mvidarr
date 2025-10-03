"""
MVidarr System Health API - Phase 2 Week 23
FastAPI endpoints for system health monitoring, performance metrics, and alerting
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.services.media_cache_manager import get_media_cache_manager
from src.services.performance_monitor import (
    AlertLevel,
    MetricType,
    MonitoringConfig,
    PerformanceMonitor,
    get_performance_alerts,
    get_performance_monitor,
    get_system_health,
)
from src.services.redis_manager import RedisManager
from src.services.system_optimizer import (
    OptimizationLevel,
    OptimizationTarget,
    get_system_optimizer,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.system_health")

router = APIRouter(
    prefix="/api/system-health",
    tags=["system-health"],
    responses={404: {"description": "Not found"}},
)

# Global WebSocket connections for real-time monitoring
websocket_connections: List[WebSocket] = []


# Request/Response Models
class SystemHealthResponse(BaseModel):
    """System health summary response"""

    health_score: float = Field(
        ..., ge=0, le=100, description="Overall health score (0-100)"
    )
    health_status: str = Field(
        ..., description="Health status: excellent, good, fair, poor, critical"
    )
    current_metrics: Dict[str, Any] = Field(..., description="Current system metrics")
    active_alerts_count: int = Field(..., description="Number of active alerts")
    critical_alerts: int = Field(..., description="Number of critical alerts")
    emergency_alerts: int = Field(..., description="Number of emergency alerts")
    monitoring_stats: Dict[str, Any] = Field(
        ..., description="Monitoring system statistics"
    )
    timestamp: float = Field(..., description="Timestamp of health check")


class MetricHistoryResponse(BaseModel):
    """Metric history response"""

    metric_type: str = Field(..., description="Type of metric")
    time_period_minutes: int = Field(..., description="Time period covered in minutes")
    data_points: List[Dict[str, Any]] = Field(..., description="Historical data points")
    summary: Dict[str, float] = Field(..., description="Statistical summary")


class PerformanceReportResponse(BaseModel):
    """Performance report response"""

    report_period_hours: int = Field(..., description="Report time period in hours")
    generated_at: float = Field(..., description="Report generation timestamp")
    system_health: Dict[str, Any] = Field(..., description="System health summary")
    metric_summaries: Dict[str, Any] = Field(..., description="Metric summaries")
    alert_summary: Dict[str, Any] = Field(..., description="Alert statistics")


class CacheStatisticsResponse(BaseModel):
    """Cache statistics response"""

    cache_metrics: Dict[str, Any] = Field(..., description="Cache performance metrics")
    redis_info: Dict[str, Any] = Field(..., description="Redis server information")
    configuration: Dict[str, Any] = Field(..., description="Cache configuration")
    cache_types: Dict[str, Any] = Field(..., description="Cache type configurations")


# Health Check Endpoints
@router.get("/status", response_model=SystemHealthResponse)
async def get_health_status():
    """
    Get comprehensive system health status

    Returns overall system health including CPU, memory, alerts, and performance metrics
    """
    try:
        health_summary = await get_system_health()

        return SystemHealthResponse(
            health_score=health_summary["health_score"],
            health_status=health_summary["health_status"],
            current_metrics=health_summary["current_metrics"],
            active_alerts_count=health_summary["active_alerts_count"],
            critical_alerts=health_summary["critical_alerts"],
            emergency_alerts=health_summary["emergency_alerts"],
            monitoring_stats=health_summary["monitoring_stats"],
            timestamp=health_summary["timestamp"],
        )

    except Exception as e:
        logger.error(f"❌ Failed to get health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quick-status")
async def get_quick_health_status():
    """
    Get quick health status for uptime monitoring

    Returns minimal health information for fast status checks
    """
    try:
        monitor = await get_performance_monitor()
        current_metrics = monitor.get_current_metrics()
        active_alerts = monitor.get_active_alerts()

        # Simple health calculation
        cpu_usage = current_metrics.get(MetricType.CPU_USAGE.value, {}).get("value", 0)
        memory_usage = current_metrics.get(MetricType.MEMORY_USAGE.value, {}).get(
            "value", 0
        )
        critical_alerts = len(
            [a for a in active_alerts if a["alert_level"] == "critical"]
        )

        status = "healthy"
        if critical_alerts > 0:
            status = "critical"
        elif cpu_usage > 90 or memory_usage > 90:
            status = "degraded"
        elif cpu_usage > 80 or memory_usage > 80:
            status = "warning"

        return {
            "status": status,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "active_alerts": len(active_alerts),
            "critical_alerts": critical_alerts,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to get quick health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Performance Metrics Endpoints
@router.get("/metrics/current")
async def get_current_metrics():
    """Get current performance metrics for all monitored systems"""
    try:
        monitor = await get_performance_monitor()
        metrics = monitor.get_current_metrics()

        return {
            "metrics": metrics,
            "timestamp": time.time(),
            "monitoring_active": monitor.monitoring_active,
        }

    except Exception as e:
        logger.error(f"❌ Failed to get current metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_type}/history", response_model=MetricHistoryResponse)
async def get_metric_history(
    metric_type: str,
    minutes: int = Query(
        10, ge=1, le=1440, description="Minutes of history to retrieve"
    ),
):
    """Get historical data for a specific metric type"""
    try:
        # Validate metric type
        try:
            metric_enum = MetricType(metric_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid metric type: {metric_type}"
            )

        monitor = await get_performance_monitor()
        history = monitor.get_metric_history(metric_enum, minutes)

        # Calculate summary statistics
        values = [point["value"] for point in history]
        summary = {}
        if values:
            summary = {
                "count": len(values),
                "average": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
                "latest": values[-1] if values else None,
            }

        return MetricHistoryResponse(
            metric_type=metric_type,
            time_period_minutes=minutes,
            data_points=history,
            summary=summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get metric history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/types")
async def get_available_metric_types():
    """Get list of available metric types for monitoring"""
    return {
        "metric_types": [
            {
                "value": metric.value,
                "name": metric.name,
                "description": _get_metric_description(metric),
            }
            for metric in MetricType
        ]
    }


def _get_metric_description(metric: MetricType) -> str:
    """Get human-readable description for metric type"""
    descriptions = {
        MetricType.CPU_USAGE: "CPU utilization percentage",
        MetricType.MEMORY_USAGE: "Memory utilization percentage",
        MetricType.DISK_IO: "Disk I/O throughput (bytes/sec)",
        MetricType.NETWORK_IO: "Network I/O throughput (bytes/sec)",
        MetricType.PROCESS_COUNT: "Number of running processes",
        MetricType.MEDIA_PROCESSING_TIME: "Media processing operation duration",
        MetricType.CACHE_PERFORMANCE: "Cache hit/miss performance metrics",
        MetricType.API_RESPONSE_TIME: "API endpoint response times",
        MetricType.ERROR_RATE: "Error rate percentage",
        MetricType.CONCURRENT_OPERATIONS: "Number of concurrent operations",
    }
    return descriptions.get(metric, "Performance metric")


# Alert Management Endpoints
@router.get("/alerts")
async def get_active_alerts():
    """Get all active performance alerts"""
    try:
        alerts = await get_performance_alerts()

        return {
            "active_alerts": alerts,
            "total_count": len(alerts),
            "by_level": {
                "info": len([a for a in alerts if a["alert_level"] == "info"]),
                "warning": len([a for a in alerts if a["alert_level"] == "warning"]),
                "critical": len([a for a in alerts if a["alert_level"] == "critical"]),
                "emergency": len(
                    [a for a in alerts if a["alert_level"] == "emergency"]
                ),
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{alert_level}")
async def get_alerts_by_level(alert_level: str):
    """Get alerts filtered by severity level"""
    try:
        # Validate alert level
        try:
            AlertLevel(alert_level)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid alert level: {alert_level}"
            )

        all_alerts = await get_performance_alerts()
        filtered_alerts = [a for a in all_alerts if a["alert_level"] == alert_level]

        return {
            "alert_level": alert_level,
            "alerts": filtered_alerts,
            "count": len(filtered_alerts),
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get alerts by level: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cache Performance Endpoints
@router.get("/cache/statistics", response_model=CacheStatisticsResponse)
async def get_cache_statistics():
    """Get comprehensive cache performance statistics"""
    try:
        cache_manager = await get_media_cache_manager()
        stats = await cache_manager.get_cache_statistics()

        return CacheStatisticsResponse(
            cache_metrics=stats["cache_metrics"],
            redis_info=stats["redis_info"],
            configuration=stats["configuration"],
            cache_types=stats["cache_types"],
        )

    except Exception as e:
        logger.error(f"❌ Failed to get cache statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/optimize")
async def optimize_cache_performance():
    """Trigger cache performance optimization"""
    try:
        cache_manager = await get_media_cache_manager()
        optimization_results = await cache_manager.optimize_cache_performance()

        return {
            "status": "completed",
            "optimization_results": optimization_results,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to optimize cache performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Performance Reports
@router.get("/reports/performance", response_model=PerformanceReportResponse)
async def get_performance_report(
    hours: int = Query(1, ge=1, le=24, description="Hours of data to include in report")
):
    """Generate comprehensive performance report"""
    try:
        monitor = await get_performance_monitor()
        report = await monitor.get_performance_report(hours)

        return PerformanceReportResponse(
            report_period_hours=report["report_period_hours"],
            generated_at=report["generated_at"],
            system_health=report["system_health"],
            metric_summaries=report["metric_summaries"],
            alert_summary=report["alert_summary"],
        )

    except Exception as e:
        logger.error(f"❌ Failed to generate performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Real-time Monitoring WebSocket
@router.websocket("/live-monitoring")
async def websocket_live_monitoring(websocket: WebSocket):
    """WebSocket endpoint for real-time system monitoring"""
    await websocket.accept()
    websocket_connections.append(websocket)

    try:
        logger.info("📡 Live monitoring WebSocket connected")

        # Send initial system status
        initial_health = await get_system_health()
        await websocket.send_json({"type": "initial_status", "data": initial_health})

        # Keep connection alive and send periodic updates
        while True:
            try:
                # Send health update every 5 seconds
                health_data = await get_system_health()
                await websocket.send_json(
                    {
                        "type": "health_update",
                        "timestamp": time.time(),
                        "data": health_data,
                    }
                )

                # Send alert updates
                alerts = await get_performance_alerts()
                if alerts:
                    await websocket.send_json(
                        {
                            "type": "alerts_update",
                            "timestamp": time.time(),
                            "data": {"alerts": alerts, "count": len(alerts)},
                        }
                    )

                await asyncio.sleep(5)  # 5-second updates

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"❌ WebSocket monitoring error: {e}")
                break

    except WebSocketDisconnect:
        logger.info("📡 Live monitoring WebSocket disconnected")
    except Exception as e:
        logger.error(f"❌ WebSocket connection error: {e}")
    finally:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)


# System Maintenance Endpoints
@router.post("/maintenance/cleanup")
async def perform_system_cleanup():
    """Perform system maintenance and cleanup operations"""
    try:
        results = {
            "cache_cleanup": False,
            "metrics_cleanup": False,
            "log_cleanup": False,
            "errors": [],
        }

        # Cache cleanup
        try:
            cache_manager = await get_media_cache_manager()
            cache_cleanup = await cache_manager.cleanup_expired_entries()
            results["cache_cleanup"] = True
            results["cache_cleanup_details"] = cache_cleanup
        except Exception as e:
            results["errors"].append(f"Cache cleanup failed: {e}")

        # Performance metrics cleanup (Redis)
        try:
            redis_manager = RedisManager()
            # Clean old performance metrics (keep last 24 hours)
            cutoff_time = time.time() - (24 * 3600)

            for metric_type in MetricType:
                key = f"performance:metrics:{metric_type.value}"
                # This is a simplified cleanup - in production you'd implement time-based cleanup
                await redis_manager.ltrim(
                    key, 0, 2880
                )  # Keep ~24 hours at 30s intervals

            results["metrics_cleanup"] = True
        except Exception as e:
            results["errors"].append(f"Metrics cleanup failed: {e}")

        # Log file cleanup
        try:
            log_path = Path("logs/performance_metrics.jsonl")
            if (
                log_path.exists() and log_path.stat().st_size > 100 * 1024 * 1024
            ):  # 100MB
                # Rotate log file
                backup_path = log_path.with_suffix(".jsonl.old")
                log_path.rename(backup_path)
                results["log_cleanup"] = True
        except Exception as e:
            results["errors"].append(f"Log cleanup failed: {e}")

        return {
            "status": "completed",
            "cleanup_results": results,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ System cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System Optimization Endpoints
@router.post("/optimization/optimize")
async def optimize_system_performance(
    target: str = Query(
        "all", description="Optimization target: memory, cpu, cache, io, all"
    ),
    level: str = Query(
        "basic", description="Optimization level: basic, aggressive, maximum"
    ),
):
    """Trigger system performance optimization"""
    try:
        # Validate parameters
        try:
            optimization_target = OptimizationTarget(target.lower())
            optimization_level = OptimizationLevel(level.lower())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")

        optimizer = await get_system_optimizer()
        result = await optimizer.optimize_system(
            optimization_target, optimization_level
        )

        return {
            "status": "completed",
            "optimization_result": result.to_dict(),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ System optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization/recommendations")
async def get_optimization_recommendations():
    """Get current system optimization recommendations"""
    try:
        optimizer = await get_system_optimizer()
        recommendations = await optimizer.get_optimization_recommendations()

        return {
            "recommendations": recommendations,
            "count": len(recommendations),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to get optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization/history")
async def get_optimization_history(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to retrieve")
):
    """Get system optimization history"""
    try:
        optimizer = await get_system_optimizer()
        history = optimizer.get_optimization_history(hours)

        return {
            "optimization_history": history,
            "period_hours": hours,
            "total_optimizations": len(history),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to get optimization history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/auto-start")
async def start_auto_optimization():
    """Start automatic system optimization"""
    try:
        optimizer = await get_system_optimizer()
        await optimizer.start_auto_optimization()

        return {
            "status": "started",
            "message": "Automatic system optimization started",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to start auto-optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/auto-stop")
async def stop_auto_optimization():
    """Stop automatic system optimization"""
    try:
        optimizer = await get_system_optimizer()
        await optimizer.stop_auto_optimization()

        return {
            "status": "stopped",
            "message": "Automatic system optimization stopped",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"❌ Failed to stop auto-optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_system_diagnostics():
    """Get detailed system diagnostics information"""
    try:
        import platform
        import sys

        import psutil

        diagnostics = {
            "system_info": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "python_version": sys.version,
            },
            "resources": {
                "cpu_count": psutil.cpu_count(),
                "cpu_count_logical": psutil.cpu_count(logical=True),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_usage": {},
            },
            "process_info": {
                "pid": os.getpid(),
                "memory_usage_mb": round(
                    psutil.Process().memory_info().rss / (1024**2), 2
                ),
                "cpu_percent": psutil.Process().cpu_percent(),
                "create_time": psutil.Process().create_time(),
            },
            "service_status": {},
            "timestamp": time.time(),
        }

        # Disk usage for main partitions
        for partition in psutil.disk_partitions():
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
                diagnostics["resources"]["disk_usage"][partition.mountpoint] = {
                    "total_gb": round(partition_usage.total / (1024**3), 2),
                    "used_gb": round(partition_usage.used / (1024**3), 2),
                    "free_gb": round(partition_usage.free / (1024**3), 2),
                    "percent": round(
                        partition_usage.used / partition_usage.total * 100, 1
                    ),
                }
            except PermissionError:
                continue

        # Service status checks
        try:
            monitor = await get_performance_monitor()
            diagnostics["service_status"]["performance_monitoring"] = {
                "active": monitor.monitoring_active,
                "stats": monitor.collection_stats,
            }
        except:
            diagnostics["service_status"]["performance_monitoring"] = {"active": False}

        try:
            cache_manager = await get_media_cache_manager()
            cache_stats = await cache_manager.get_cache_statistics()
            diagnostics["service_status"]["cache_manager"] = {
                "active": True,
                "hit_ratio": cache_stats["cache_metrics"]["hit_ratio_percent"],
            }
        except:
            diagnostics["service_status"]["cache_manager"] = {"active": False}

        return diagnostics

    except Exception as e:
        logger.error(f"❌ Failed to get system diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Broadcast system alerts to WebSocket connections
async def broadcast_system_alert(alert_data: Dict[str, Any]):
    """Broadcast system alert to all connected WebSocket clients"""
    if not websocket_connections:
        return

    message = {"type": "system_alert", "timestamp": time.time(), "data": alert_data}

    # Send to all connections, remove failed ones
    failed_connections = []
    for websocket in websocket_connections:
        try:
            await websocket.send_json(message)
        except:
            failed_connections.append(websocket)

    # Clean up failed connections
    for failed_ws in failed_connections:
        websocket_connections.remove(failed_ws)
