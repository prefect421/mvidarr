"""
System health monitoring service for MVidarr.

Provides simple health checks for home self-hosters:
- Disk space usage
- Memory and CPU usage
- Database connection status
- Celery worker status
- Redis connection status
"""

import os
import psutil
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def get_disk_usage(paths: Optional[List[str]] = None) -> Dict[str, Dict]:
    """
    Get disk usage for specified paths.

    Args:
        paths: List of paths to check. If None, checks common MVidarr paths.

    Returns:
        Dict with path as key and usage info as value
    """
    if paths is None:
        # Default paths for MVidarr
        paths = [
            "/app/data",
            "/app/data/musicvideos",
            "/app/data/thumbnails",
            "/app/data/database",
            "/app/data/logs",
        ]

    disk_info = {}

    for path in paths:
        try:
            if not os.path.exists(path):
                disk_info[path] = {
                    "exists": False,
                    "error": "Path does not exist"
                }
                continue

            usage = psutil.disk_usage(path)
            disk_info[path] = {
                "exists": True,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent,
                "warning": usage.percent > 90,
                "critical": usage.percent > 95,
            }
        except Exception as e:
            logger.error(f"Error getting disk usage for {path}: {e}")
            disk_info[path] = {
                "exists": False,
                "error": str(e)
            }

    return disk_info


def get_memory_usage() -> Dict:
    """
    Get current memory usage statistics.

    Returns:
        Dict with memory usage information
    """
    try:
        memory = psutil.virtual_memory()
        return {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent_used": memory.percent,
            "warning": memory.percent > 85,
            "critical": memory.percent > 95,
        }
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        return {"error": str(e)}


def get_cpu_usage(interval: float = 1.0) -> Dict:
    """
    Get current CPU usage statistics.

    Args:
        interval: Time interval to measure CPU usage (seconds)

    Returns:
        Dict with CPU usage information
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=interval)
        cpu_count = psutil.cpu_count()

        return {
            "percent_used": cpu_percent,
            "cpu_count": cpu_count,
            "warning": cpu_percent > 80,
            "critical": cpu_percent > 95,
        }
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return {"error": str(e)}


def get_database_status() -> Dict:
    """
    Check database connection status.

    Returns:
        Dict with database connection information
    """
    try:
        from src.database.connection import get_db
        from sqlalchemy import text

        with get_db() as session:
            # Try a simple query to verify connection
            session.execute(text("SELECT 1"))

        return {
            "connected": True,
            "status": "healthy",
            "checked_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return {
            "connected": False,
            "status": "error",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat(),
        }


def get_celery_status() -> Dict:
    """
    Check Celery worker status.

    Returns:
        Dict with Celery status information
    """
    try:
        # Try to import celery app - may not exist in all environments
        try:
            from src.celery_app import celery_app
        except ImportError:
            from celery import Celery
            celery_app = Celery('mvidarr')

        # Get active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        stats = inspect.stats()

        if not active_workers:
            return {
                "running": False,
                "status": "no workers available",
                "workers": [],
            }

        worker_list = []
        for worker_name, tasks in active_workers.items():
            worker_stats = stats.get(worker_name, {}) if stats else {}
            worker_list.append({
                "name": worker_name,
                "active_tasks": len(tasks),
                "status": "active",
                "pool": worker_stats.get("pool", {}).get("max-concurrency", "unknown"),
            })

        return {
            "running": True,
            "status": "healthy",
            "workers": worker_list,
            "worker_count": len(worker_list),
        }
    except Exception as e:
        logger.error(f"Error getting Celery status: {e}")
        return {
            "running": False,
            "status": "error",
            "error": str(e),
            "workers": [],
        }


def get_redis_status() -> Dict:
    """
    Check Redis connection status.

    Returns:
        Dict with Redis connection information
    """
    try:
        import redis
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)

        # Ping Redis
        r.ping()

        # Get some basic info
        info = r.info()

        return {
            "connected": True,
            "status": "healthy",
            "version": info.get("redis_version", "unknown"),
            "used_memory_mb": round(info.get("used_memory", 0) / (1024**2), 2),
            "connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return {
            "connected": False,
            "status": "error",
            "error": str(e),
        }


def get_recent_logs(log_file: Optional[str] = None, lines: int = 100) -> List[str]:
    """
    Get recent log entries.

    Args:
        log_file: Path to log file. If None, uses default MVidarr log.
        lines: Number of recent lines to return

    Returns:
        List of log lines
    """
    if log_file is None:
        log_file = "/app/data/logs/mvidarr.log"

    try:
        if not os.path.exists(log_file):
            return [f"Log file not found: {log_file}"]

        with open(log_file, "r") as f:
            all_lines = f.readlines()
            return all_lines[-lines:] if len(all_lines) > lines else all_lines

    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return [f"Error reading logs: {str(e)}"]


def get_overall_health() -> Dict:
    """
    Get overall system health summary.

    Returns:
        Dict with overall health status and all component statuses
    """
    disk = get_disk_usage()
    memory = get_memory_usage()
    cpu = get_cpu_usage(interval=0.1)  # Quick check
    database = get_database_status()
    celery = get_celery_status()
    redis = get_redis_status()

    # Determine overall health
    critical_issues = []
    warnings = []

    # Check disk
    for path, info in disk.items():
        if info.get("critical"):
            critical_issues.append(f"Disk critical: {path} at {info['percent_used']}%")
        elif info.get("warning"):
            warnings.append(f"Disk warning: {path} at {info['percent_used']}%")

    # Check memory
    if memory.get("critical"):
        critical_issues.append(f"Memory critical: {memory['percent_used']}%")
    elif memory.get("warning"):
        warnings.append(f"Memory warning: {memory['percent_used']}%")

    # Check CPU
    if cpu.get("critical"):
        critical_issues.append(f"CPU critical: {cpu['percent_used']}%")
    elif cpu.get("warning"):
        warnings.append(f"CPU warning: {cpu['percent_used']}%")

    # Check services
    if not database.get("connected"):
        critical_issues.append("Database not connected")

    if not celery.get("running"):
        warnings.append("Celery workers not running")

    if not redis.get("connected"):
        warnings.append("Redis not connected")

    # Determine overall status
    if critical_issues:
        status = "critical"
    elif warnings:
        status = "warning"
    else:
        status = "healthy"

    return {
        "status": status,
        "checked_at": datetime.utcnow().isoformat(),
        "critical_issues": critical_issues,
        "warnings": warnings,
        "components": {
            "disk": disk,
            "memory": memory,
            "cpu": cpu,
            "database": database,
            "celery": celery,
            "redis": redis,
        },
    }
