"""
FastAPI Health Check API Endpoints
Enhanced for self-hosted production monitoring
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.database.connection import get_db_session
from src.utils.async_subprocess import get_git_branch, get_git_version
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.health")


# Pydantic response models
class HealthResponse(BaseModel):
    status: str
    service: str = "mvidarr"


class DetailedHealthResponse(BaseModel):
    status: str
    components: Dict[str, str]
    timestamp: str


class DatabaseHealthResponse(BaseModel):
    status: str
    message: str


class VersionInfoResponse(BaseModel):
    version: str
    git_commit: str
    git_branch: str


class ServiceHealthResponse(BaseModel):
    status: str
    service: str
    message: Optional[str] = None
    error: Optional[str] = None


class SystemMetricsResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    load_average: Optional[list] = None
    uptime_seconds: int


class ProductionHealthResponse(BaseModel):
    status: str
    timestamp: str
    application: Dict[str, Any]
    database: Dict[str, Any]
    system: SystemMetricsResponse
    services: Dict[str, Any]
    alerts: list


# Create router
health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/", response_model=HealthResponse)
async def health_check(session=Depends(get_db_session)):
    """Simple health check endpoint for Docker health checks"""
    try:
        # Quick database connectivity check
        from sqlalchemy import text

        session.execute(text("SELECT 1"))
        return HealthResponse(status="healthy")

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "error": str(e)}
        )


@health_router.get("/status", response_model=DetailedHealthResponse)
async def get_health_status(session=Depends(get_db_session)):
    """Get overall system health status"""
    try:
        status = {
            "status": "healthy",
            "components": {"database": "healthy", "api": "healthy"},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Check database health
        try:
            from sqlalchemy import text

            session.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            status["components"]["database"] = "unhealthy"
            status["status"] = "unhealthy"

        return DetailedHealthResponse(**status)

    except Exception as e:
        logger.error(f"Health status check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@health_router.get("/database", response_model=DatabaseHealthResponse)
async def check_database(session=Depends(get_db_session)):
    """Check database connectivity and health"""
    try:
        from sqlalchemy import text

        result = session.execute(text("SELECT 1 as test"))
        row = result.fetchone()

        if row and row.test == 1:
            return DatabaseHealthResponse(
                status="healthy", message="Database is accessible and healthy"
            )
        else:
            raise HTTPException(
                status_code=503,
                detail={"status": "unhealthy", "message": "Database query failed"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "error": str(e)}
        )


@health_router.get("/imvdb", response_model=ServiceHealthResponse)
async def check_imvdb():
    """Check IMVDB API connectivity with async HTTP client"""
    try:
        from src.services.imvdb_service import imvdb_service

        # If the service has async methods, use them; otherwise wrap in async
        result = await asyncio.create_task(
            asyncio.to_thread(imvdb_service.test_connection)
        )

        if result["status"] == "success":
            return ServiceHealthResponse(
                status="healthy", service="imvdb", message=result.get("message")
            )
        else:
            raise HTTPException(status_code=503, detail=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IMVDB health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "service": "imvdb", "error": str(e)},
        )


@health_router.get("/metube", response_model=ServiceHealthResponse)
async def check_metube():
    """Check yt-dlp Web UI connectivity with async HTTP client"""
    try:
        from src.services.ytdlp_service import ytdlp_service

        # If the service has async methods, use them; otherwise wrap in async
        result = await asyncio.create_task(
            asyncio.to_thread(ytdlp_service.test_connection)
        )

        if result["status"] == "success":
            return ServiceHealthResponse(
                status="healthy", service="metube", message=result.get("message")
            )
        else:
            raise HTTPException(status_code=503, detail=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"yt-dlp Web UI health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "service": "metube", "error": str(e)},
        )


@health_router.get("/version", response_model=VersionInfoResponse)
async def get_version_info():
    """Get version information with async git commands (non-blocking)"""
    try:
        # Get version from src/__init__.py
        from src import __version__

        version_info = {
            "version": __version__,
            "git_commit": "unknown",
            "git_branch": "unknown",
        }

        # Read version.json first — baked in at build time, works in all environments
        try:
            version_json_path = (
                Path(__file__).parent.parent.parent.parent / "version.json"
            )
            if version_json_path.exists():
                with open(version_json_path) as f:
                    version_data = json.load(f)
                    version_info["git_commit"] = version_data.get(
                        "git_commit", "unknown"
                    )
                    version_info["git_branch"] = version_data.get(
                        "git_branch", "unknown"
                    )
        except Exception as e:
            logger.debug(f"Could not read version.json: {e}")

        # Fall back to live git commands only if version.json didn't provide the info
        # (not available in Docker — git binary is not installed in the image)
        if version_info["git_commit"] == "unknown":
            try:
                git_commit = await get_git_version()
                if git_commit:
                    version_info["git_commit"] = git_commit
            except Exception as e:
                logger.debug(f"Could not get git commit: {e}")

        if version_info["git_branch"] == "unknown":
            try:
                git_branch = await get_git_branch()
                if git_branch:
                    version_info["git_branch"] = git_branch
            except Exception as e:
                logger.debug(f"Could not get git branch: {e}")

        return VersionInfoResponse(**version_info)

    except Exception as e:
        logger.error(f"Version info retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/performance", response_model=Dict[str, Any])
async def get_performance_stats():
    """Get subprocess performance statistics for monitoring"""
    try:
        from src.utils.async_subprocess import async_subprocess_manager

        stats = async_subprocess_manager.get_performance_stats()

        return {
            "subprocess_performance": stats,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
        }

    except Exception as e:
        logger.error(f"Performance stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/system", response_model=SystemMetricsResponse)
async def get_system_metrics():
    """Get system resource metrics for self-hosted monitoring"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_gb = memory.available / (1024**3)

        # Disk usage
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
        disk_free_gb = disk.free / (1024**3)

        # Load average (Unix only)
        load_average = None
        if hasattr(os, "getloadavg"):
            load_average = list(os.getloadavg())

        # System uptime
        uptime_seconds = int(time.time() - psutil.boot_time())

        return SystemMetricsResponse(
            cpu_percent=round(cpu_percent, 1),
            memory_percent=round(memory_percent, 1),
            memory_available_gb=round(memory_available_gb, 1),
            disk_percent=round(disk_percent, 1),
            disk_free_gb=round(disk_free_gb, 1),
            load_average=load_average,
            uptime_seconds=uptime_seconds,
        )

    except Exception as e:
        logger.error(f"System metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/production", response_model=ProductionHealthResponse)
async def get_production_health(session=Depends(get_db_session)):
    """Comprehensive health check for self-hosted production monitoring"""
    try:
        overall_status = "healthy"
        alerts = []

        # Application health
        app_health = {
            "status": "healthy",
            "version": "unknown",
            "uptime": int(time.time() - psutil.Process().create_time()),
            "workers": os.getenv("WORKERS", "unknown"),
        }

        try:
            from src import __version__

            app_health["version"] = __version__
        except:
            pass

        # Database health
        db_health = {"status": "unhealthy", "error": "Not checked"}
        try:
            from sqlalchemy import text

            result = session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables")
            )
            table_count = result.scalar()
            db_health = {
                "status": "healthy",
                "table_count": table_count,
                "connection": "active",
            }
        except Exception as e:
            db_health = {"status": "unhealthy", "error": str(e)}
            overall_status = "unhealthy"
            alerts.append(f"Database connection failed: {str(e)}")

        # System metrics
        system_metrics = await get_system_metrics()

        # Check for system alerts
        if system_metrics.cpu_percent > 90:
            alerts.append(f"High CPU usage: {system_metrics.cpu_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.memory_percent > 90:
            alerts.append(f"High memory usage: {system_metrics.memory_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.disk_percent > 90:
            alerts.append(
                f"Low disk space: {system_metrics.disk_free_gb:.1f}GB remaining"
            )
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        # Service health checks
        services = {}

        # Check Redis if available
        try:
            import redis

            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
                r.ping()
                services["redis"] = {"status": "healthy", "connection": "active"}
            else:
                services["redis"] = {"status": "not_configured"}
        except Exception as e:
            services["redis"] = {"status": "unhealthy", "error": str(e)}
            if "redis" in str(e).lower():
                alerts.append(f"Redis connection failed: {str(e)}")

        # Check background job system
        try:
            from src.jobs.celery_app import celery_app

            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            if stats:
                services["celery"] = {"status": "healthy", "workers": len(stats)}
            else:
                services["celery"] = {
                    "status": "unhealthy",
                    "error": "No workers available",
                }
        except Exception as e:
            services["celery"] = {"status": "not_configured"}

        # Check scheduler service for scheduled downloads and video discovery
        try:
            from src.services.scheduler_service import scheduler_service
            from src.services.settings_service import SettingsService

            scheduler_info = {
                "status": "healthy" if scheduler_service.running else "stopped",
                "running": scheduler_service.running,
                "downloads_enabled": SettingsService.get_bool(
                    "auto_download_schedule_enabled", False
                ),
                "discovery_enabled": SettingsService.get_bool(
                    "auto_discovery_schedule_enabled", False
                ),
            }

            # Add next run time if scheduler is running
            if scheduler_service.running:
                next_run = scheduler_service.get_next_run_time()
                if next_run:
                    scheduler_info["next_run"] = next_run.isoformat()
                else:
                    scheduler_info["next_run"] = None

            services["scheduler"] = scheduler_info

            # Alert if scheduler should be running but isn't
            downloads_enabled = scheduler_info["downloads_enabled"]
            discovery_enabled = scheduler_info["discovery_enabled"]
            if (
                downloads_enabled or discovery_enabled
            ) and not scheduler_service.running:
                alerts.append(
                    "Scheduler service is not running but scheduled downloads/discovery are enabled"
                )
                overall_status = (
                    "warning" if overall_status == "healthy" else overall_status
                )

        except Exception as e:
            services["scheduler"] = {"status": "error", "error": str(e)}
            logger.error(f"Error checking scheduler service: {e}")

        return ProductionHealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            application=app_health,
            database=db_health,
            system=system_metrics,
            services=services,
            alerts=alerts,
        )

    except Exception as e:
        logger.error(f"Production health check failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@health_router.get("/readiness")
async def readiness_check(session=Depends(get_db_session)):
    """Kubernetes-style readiness check for load balancers"""
    try:
        # Check database connectivity
        from sqlalchemy import text

        session.execute(text("SELECT 1"))

        return {"status": "ready", "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@health_router.get("/liveness")
async def liveness_check():
    """Kubernetes-style liveness check for container health"""
    try:
        # Basic application health
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_alive",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


class WizardHealthResponse(BaseModel):
    status: str
    wizard_completed: bool
    current_step: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class BackupHealthResponse(BaseModel):
    status: str
    total_backups: int
    latest_backup: Optional[str] = None
    total_size_mb: float
    backups_by_type: Dict[str, int]
    error: Optional[str] = None


class MigrationHealthResponse(BaseModel):
    status: str
    current_revision: str
    pending_migrations: int
    error: Optional[str] = None


class V1ComponentsHealthResponse(BaseModel):
    status: str
    timestamp: str
    wizard: WizardHealthResponse
    backups: BackupHealthResponse
    migrations: MigrationHealthResponse
    alerts: list


@health_router.get("/v1-components", response_model=V1ComponentsHealthResponse)
async def get_v1_components_health(session=Depends(get_db_session)):
    """
    Monitor v1.0.0 infrastructure components
    - Installation Wizard state
    - Backup & Recovery system status
    - Database Migration version tracking
    """
    try:
        overall_status = "healthy"
        alerts = []

        # Check Installation Wizard state
        wizard_health = WizardHealthResponse(
            status="healthy",
            wizard_completed=False,
            current_step=None,
            completed_at=None,
        )
        try:
            from src.database.models import WizardState

            wizard_state = session.query(WizardState).first()
            if wizard_state:
                wizard_health.wizard_completed = (
                    wizard_state.status.value == "COMPLETED"
                )
                wizard_health.current_step = wizard_state.current_step.value
                if wizard_state.completed_at:
                    wizard_health.completed_at = wizard_state.completed_at.isoformat()

                if wizard_state.status.value in ["IN_PROGRESS", "NOT_STARTED"]:
                    alerts.append(
                        f"Installation wizard not completed (step: {wizard_state.current_step.value})"
                    )
                    overall_status = (
                        "warning" if overall_status == "healthy" else overall_status
                    )
        except Exception as e:
            wizard_health.status = "error"
            wizard_health.error = str(e)
            logger.warning(f"Could not check wizard state: {e}")

        # Check Backup & Recovery system
        backup_health = BackupHealthResponse(
            status="healthy",
            total_backups=0,
            latest_backup=None,
            total_size_mb=0.0,
            backups_by_type={},
        )
        try:
            from src.services.backup_service import BackupService

            backup_service = BackupService()
            all_backups = backup_service.list_backups()

            if all_backups:
                # Sort by timestamp to get latest
                sorted_backups = sorted(
                    all_backups, key=lambda b: b.timestamp, reverse=True
                )
                latest = sorted_backups[0]

                backup_health.total_backups = len(all_backups)
                backup_health.latest_backup = latest.timestamp.isoformat()

                # Calculate total size and count by type
                total_size = 0
                type_counts = {}
                for backup in all_backups:
                    total_size += backup.file_size
                    backup_type = backup.backup_type.value
                    type_counts[backup_type] = type_counts.get(backup_type, 0) + 1

                backup_health.total_size_mb = round(total_size / (1024 * 1024), 2)
                backup_health.backups_by_type = type_counts

                # Check backup freshness (warn if no recent backup)
                import datetime as dt

                time_since_last = dt.datetime.now(dt.timezone.utc) - latest.timestamp
                if time_since_last.days > 7:
                    alerts.append(
                        f"Latest backup is {time_since_last.days} days old (consider creating a new backup)"
                    )
                    overall_status = (
                        "warning" if overall_status == "healthy" else overall_status
                    )
            else:
                alerts.append("No backups found (consider creating a backup)")
                overall_status = (
                    "warning" if overall_status == "healthy" else overall_status
                )

        except Exception as e:
            backup_health.status = "error"
            backup_health.error = str(e)
            logger.error(f"Could not check backup status: {e}")
            alerts.append(f"Backup system error: {str(e)}")
            overall_status = "unhealthy"

        # Check Database Migration status
        migration_health = MigrationHealthResponse(
            status="healthy", current_revision="unknown", pending_migrations=0
        )
        try:
            import subprocess
            from pathlib import Path

            # Find alembic executable
            project_root = Path(__file__).parent.parent.parent.parent
            venv_alembic = project_root / "venv" / "bin" / "alembic"

            if venv_alembic.exists():
                alembic_cmd = str(venv_alembic)
            else:
                alembic_cmd = "alembic"

            # Get current revision
            result = subprocess.run(
                [alembic_cmd, "current"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # Parse output: "79107aab2257 (head)" or "No revision"
                output = result.stdout.strip()
                if "No revision" in output or not output:
                    migration_health.current_revision = "none"
                    migration_health.status = "warning"
                    alerts.append("Database migrations not initialized")
                    overall_status = (
                        "warning" if overall_status == "healthy" else overall_status
                    )
                else:
                    # Extract revision hash
                    parts = output.split()
                    if parts:
                        migration_health.current_revision = parts[0]

            # Check for pending migrations
            heads_result = subprocess.run(
                [alembic_cmd, "heads"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )

            if heads_result.returncode == 0:
                heads_output = heads_result.stdout.strip()
                current_rev = migration_health.current_revision
                if current_rev != "none" and current_rev not in heads_output:
                    migration_health.pending_migrations = 1
                    migration_health.status = "warning"
                    alerts.append(
                        "Database migrations pending (run alembic upgrade head)"
                    )
                    overall_status = (
                        "warning" if overall_status == "healthy" else overall_status
                    )

        except subprocess.TimeoutExpired:
            migration_health.status = "error"
            migration_health.error = "Migration check timed out"
            logger.error("Migration check timed out")
        except Exception as e:
            migration_health.status = "error"
            migration_health.error = str(e)
            logger.warning(f"Could not check migration status: {e}")

        return V1ComponentsHealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            wizard=wizard_health,
            backups=backup_health,
            migrations=migration_health,
            alerts=alerts,
        )

    except Exception as e:
        logger.error(f"v1.0.0 components health check failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


class BackgroundJobHealthResponse(BaseModel):
    status: str
    active_jobs: int
    pending_jobs: int
    completed_jobs: int
    failed_jobs: int
    error: Optional[str] = None


class MonitoringDashboardResponse(BaseModel):
    status: str
    timestamp: str
    application: Dict[str, Any]
    database: Dict[str, Any]
    system: SystemMetricsResponse
    v1_components: V1ComponentsHealthResponse
    background_jobs: BackgroundJobHealthResponse
    alerts: list
    summary: Dict[str, Any]


@health_router.get("/background-jobs", response_model=BackgroundJobHealthResponse)
async def get_background_jobs_health(session=Depends(get_db_session)):
    """Monitor background job system status"""
    try:
        from src.database.job_models import BackgroundJobModel

        # Count jobs by status (stored as strings)
        active_count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.status == "running")
            .count()
        )
        pending_count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.status.in_(["pending", "queued"]))
            .count()
        )
        completed_count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.status == "completed")
            .count()
        )
        failed_count = (
            session.query(BackgroundJobModel)
            .filter(BackgroundJobModel.status == "failed")
            .count()
        )

        return BackgroundJobHealthResponse(
            status="healthy",
            active_jobs=active_count,
            pending_jobs=pending_count,
            completed_jobs=completed_count,
            failed_jobs=failed_count,
        )

    except Exception as e:
        logger.error(f"Background jobs health check failed: {e}")
        return BackgroundJobHealthResponse(
            status="error",
            active_jobs=0,
            pending_jobs=0,
            completed_jobs=0,
            failed_jobs=0,
            error=str(e),
        )


@health_router.get("/dashboard", response_model=MonitoringDashboardResponse)
async def get_monitoring_dashboard(session=Depends(get_db_session)):
    """
    Comprehensive monitoring dashboard for MVidarr v1.0.0
    Aggregates all health checks, metrics, and status information in a single view
    """
    try:
        overall_status = "healthy"
        all_alerts = []

        # Application health
        app_health = {
            "status": "healthy",
            "version": "unknown",
            "uptime": int(time.time() - psutil.Process().create_time()),
            "workers": os.getenv("WORKERS", "unknown"),
        }

        try:
            from src import __version__

            app_health["version"] = __version__
        except:
            pass

        # Database health
        db_health = {"status": "unhealthy", "error": "Not checked"}
        try:
            from sqlalchemy import text

            result = session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables")
            )
            table_count = result.scalar()

            # Count videos
            video_count = session.execute(text("SELECT COUNT(*) FROM videos")).scalar()

            db_health = {
                "status": "healthy",
                "table_count": table_count,
                "video_count": video_count,
                "connection": "active",
            }
        except Exception as e:
            db_health = {"status": "unhealthy", "error": str(e)}
            overall_status = "unhealthy"
            all_alerts.append(f"Database connection failed: {str(e)}")

        # System metrics
        system_metrics = await get_system_metrics()

        # Check for system alerts
        if system_metrics.cpu_percent > 90:
            all_alerts.append(f"High CPU usage: {system_metrics.cpu_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.memory_percent > 90:
            all_alerts.append(f"High memory usage: {system_metrics.memory_percent}%")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        if system_metrics.disk_percent > 90:
            all_alerts.append(
                f"Low disk space: {system_metrics.disk_free_gb:.1f}GB remaining"
            )
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        # v1.0.0 Components health
        v1_components = await get_v1_components_health(session)
        if v1_components.status != "healthy":
            overall_status = (
                v1_components.status
                if overall_status != "unhealthy"
                else overall_status
            )
        all_alerts.extend(v1_components.alerts)

        # Background jobs health
        background_jobs = await get_background_jobs_health(session)
        if background_jobs.status != "healthy":
            all_alerts.append(f"Background jobs system error: {background_jobs.error}")
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        # Check for stuck or failed jobs
        if background_jobs.failed_jobs > 0:
            all_alerts.append(
                f"{background_jobs.failed_jobs} background jobs have failed"
            )
            overall_status = (
                "warning" if overall_status == "healthy" else overall_status
            )

        # Create summary
        summary = {
            "overall_status": overall_status,
            "total_alerts": len(all_alerts),
            "components_checked": 6,  # app, db, system, v1, jobs, services
            "healthy_components": sum(
                [
                    app_health["status"] == "healthy",
                    db_health["status"] == "healthy",
                    system_metrics.cpu_percent < 90
                    and system_metrics.memory_percent < 90
                    and system_metrics.disk_percent < 90,
                    v1_components.status == "healthy",
                    background_jobs.status == "healthy",
                    True,  # API itself is healthy if we got here
                ]
            ),
        }

        return MonitoringDashboardResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            application=app_health,
            database=db_health,
            system=system_metrics,
            v1_components=v1_components,
            background_jobs=background_jobs,
            alerts=all_alerts,
            summary=summary,
        )

    except Exception as e:
        logger.error(f"Monitoring dashboard failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
