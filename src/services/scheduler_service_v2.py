"""
Scheduler Service V2 - Celery Beat Integration
Version: v0.10.1
Phase 2: Core Services

Unified scheduler service using Celery Beat for production-grade reliability.
Replaces thread-based scheduler with distributed task scheduling.

Features:
- Celery Beat integration for robust scheduling
- Dynamic schedule updates from database settings
- Manual trigger capabilities
- Job status tracking via ScheduledJob model
- Health check monitoring
- Per-artist scheduling support
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from celery import Celery
from celery.beat import ScheduleEntry
from celery.schedules import crontab
from celery.schedules import schedule as celery_schedule
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, ScheduledJob
from src.jobs.celery_app import celery_app
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.scheduler_v2")


class SchedulerServiceV2:
    """
    Unified scheduler service using Celery Beat for production-grade scheduling.

    This service manages scheduled tasks for video discovery and downloads,
    replacing the legacy thread-based scheduler with Celery Beat.
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize Scheduler Service V2

        Args:
            db_session: Optional database session. If not provided, will use get_db()
        """
        self.db = db_session
        self.celery = celery_app
        self._is_running = False

    def _get_db(self) -> Session:
        """Get database session"""
        if self.db:
            return self.db
        return next(get_db())

    def is_enabled(self) -> bool:
        """Check if Scheduler V2 is enabled in settings"""
        return SettingsService.get_bool("scheduler_v2_enabled", True)

    def start(self) -> Dict[str, Any]:
        """
        Start the Scheduler V2 service

        Returns:
            Dict with status and message
        """
        if not self.is_enabled():
            logger.warning("Scheduler V2 is disabled in settings")
            return {
                "status": "disabled",
                "message": "Scheduler V2 is disabled in settings",
            }

        if self._is_running:
            logger.warning("Scheduler V2 is already running")
            return {
                "status": "already_running",
                "message": "Scheduler V2 is already running",
            }

        try:
            logger.info("Starting Scheduler V2...")

            # Update schedules from database settings
            self.update_schedule_from_settings()

            self._is_running = True

            logger.info("Scheduler V2 started successfully")
            return {
                "status": "started",
                "message": "Scheduler V2 started successfully",
                "schedules": self.get_current_schedules(),
            }

        except Exception as e:
            logger.error(f"Failed to start Scheduler V2: {e}")
            return {"status": "error", "message": f"Failed to start: {str(e)}"}

    def stop(self) -> Dict[str, Any]:
        """
        Stop the Scheduler V2 service

        Returns:
            Dict with status and message
        """
        if not self._is_running:
            logger.warning("Scheduler V2 is not running")
            return {"status": "not_running", "message": "Scheduler V2 is not running"}

        try:
            logger.info("Stopping Scheduler V2...")

            self._is_running = False

            logger.info("Scheduler V2 stopped successfully")
            return {"status": "stopped", "message": "Scheduler V2 stopped successfully"}

        except Exception as e:
            logger.error(f"Failed to stop Scheduler V2: {e}")
            return {"status": "error", "message": f"Failed to stop: {str(e)}"}

    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status

        Returns:
            Dict with scheduler status information
        """
        try:
            # Use get_db() as a context manager
            with get_db() as db:
                # Get recent job statistics
                recent_jobs = (
                    db.query(ScheduledJob)
                    .filter(
                        ScheduledJob.created_at
                        >= datetime.utcnow() - timedelta(hours=24)
                    )
                    .all()
                )

                total_jobs = len(recent_jobs)
                completed_jobs = len(
                    [j for j in recent_jobs if j.status == "completed"]
                )
                failed_jobs = len([j for j in recent_jobs if j.status == "failed"])
                running_jobs = len([j for j in recent_jobs if j.status == "running"])

                # Calculate success rate
                success_rate = (
                    (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
                )

            return {
                "status": "running" if self._is_running else "stopped",
                "enabled": self.is_enabled(),
                "celery_connected": self._check_celery_connection(),
                "schedules": self.get_current_schedules(),
                "statistics": {
                    "total_jobs_24h": total_jobs,
                    "completed": completed_jobs,
                    "failed": failed_jobs,
                    "running": running_jobs,
                    "success_rate": round(success_rate, 2),
                },
                "worker_count": SettingsService.get_int("scheduler_v2_worker_count", 3),
                "health_check_enabled": SettingsService.get_bool(
                    "scheduler_v2_health_check_enabled", True
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get scheduler status: {e}")
            # Return all required fields with safe defaults
            return {
                "status": "error",
                "enabled": False,
                "celery_connected": False,
                "schedules": {},
                "statistics": {
                    "total_jobs_24h": 0,
                    "completed": 0,
                    "failed": 0,
                    "running": 0,
                    "success_rate": 0,
                },
                "worker_count": 0,
                "health_check_enabled": False,
            }

    def update_schedule_from_settings(self) -> Dict[str, Any]:
        """
        Update Celery Beat schedule from database settings

        This method reads scheduler settings from the database and updates
        the Celery Beat schedule dynamically.

        Returns:
            Dict with updated schedules
        """
        try:
            logger.info("Updating Celery Beat schedule from database settings...")

            updated_schedules = {}

            # Get discovery schedule settings
            discovery_enabled = SettingsService.get_bool(
                "auto_discovery_schedule_enabled", True
            )
            discovery_time = SettingsService.get(
                "auto_discovery_schedule_time", "06:00"
            )
            discovery_days = SettingsService.get(
                "auto_discovery_schedule_days", "daily"
            )

            if discovery_enabled:
                discovery_schedule = self._parse_schedule(
                    discovery_days, discovery_time
                )
                if discovery_schedule:
                    updated_schedules["scheduled-discovery"] = {
                        "task": "src.tasks.scheduled_tasks.scheduled_discovery_task",
                        "schedule": discovery_schedule,
                        "options": {"queue": "scheduler"},
                    }

            # Get download schedule settings
            download_enabled = SettingsService.get_bool(
                "auto_download_schedule_enabled", True
            )
            download_time = SettingsService.get("auto_download_schedule_time", "02:00")
            download_days = SettingsService.get("auto_download_schedule_days", "hourly")

            if download_enabled:
                download_schedule = self._parse_schedule(download_days, download_time)
                if download_schedule:
                    updated_schedules["scheduled-downloads"] = {
                        "task": "src.tasks.scheduled_tasks.scheduled_downloads_task",
                        "schedule": download_schedule,
                        "options": {"queue": "scheduler"},
                    }

            # Update Celery Beat schedule
            # Note: This updates the in-memory schedule. For persistent changes,
            # Celery Beat needs to be restarted or use dynamic beat schedulers.
            if updated_schedules:
                self.celery.conf.beat_schedule.update(updated_schedules)
                logger.info(
                    f"Updated {len(updated_schedules)} schedules in Celery Beat"
                )

            return {
                "status": "updated",
                "schedules_updated": len(updated_schedules),
                "schedules": updated_schedules,
            }

        except Exception as e:
            logger.error(f"Failed to update schedule from settings: {e}")
            return {"status": "error", "message": str(e)}

    def _parse_schedule(
        self, frequency: str, time_str: str
    ) -> Optional[celery_schedule]:
        """
        Parse schedule frequency and time into Celery schedule object

        Args:
            frequency: Schedule frequency (hourly, daily, weekly, etc.)
            time_str: Time in HH:MM format

        Returns:
            Celery schedule object or None if parsing fails
        """
        try:
            # Parse time
            hour, minute = map(int, time_str.split(":"))

            if frequency == "hourly":
                return celery_schedule(run_every=timedelta(hours=1))

            elif frequency == "daily":
                return crontab(hour=hour, minute=minute)

            elif frequency == "weekly":
                return crontab(hour=hour, minute=minute, day_of_week=1)  # Monday

            elif frequency == "twice_daily":
                # Run at specified time and 12 hours later
                return crontab(hour=f"{hour},{(hour + 12) % 24}", minute=minute)

            elif frequency.startswith("every_"):
                # Parse "every_N_hours" format
                try:
                    hours = int(frequency.split("_")[1])
                    return celery_schedule(run_every=timedelta(hours=hours))
                except (IndexError, ValueError):
                    logger.warning(f"Invalid every_N_hours format: {frequency}")
                    return None

            else:
                # Try to parse as comma-separated days (monday,wednesday,friday)
                days_map = {
                    "monday": 1,
                    "tuesday": 2,
                    "wednesday": 3,
                    "thursday": 4,
                    "friday": 5,
                    "saturday": 6,
                    "sunday": 0,
                }

                if "," in frequency:
                    day_names = [d.strip().lower() for d in frequency.split(",")]
                    day_numbers = [days_map.get(d) for d in day_names if d in days_map]

                    if day_numbers:
                        return crontab(
                            hour=hour,
                            minute=minute,
                            day_of_week=",".join(map(str, day_numbers)),
                        )

                logger.warning(f"Unknown schedule frequency: {frequency}")
                return None

        except Exception as e:
            logger.error(f"Failed to parse schedule: {e}")
            return None

    def get_current_schedules(self) -> Dict[str, Any]:
        """
        Get current Celery Beat schedules

        Returns:
            Dict of current schedules
        """
        try:
            schedules = {}
            for name, entry in self.celery.conf.beat_schedule.items():
                if name.startswith("scheduled-") or name.startswith("artist-"):
                    schedules[name] = {
                        "task": entry.get("task"),
                        "schedule": str(entry.get("schedule")),
                        "enabled": True,
                    }

            return schedules

        except Exception as e:
            logger.error(f"Failed to get current schedules: {e}")
            return {}

    def trigger_discovery_now(self, artist_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Manually trigger discovery task

        Args:
            artist_id: Optional artist ID for artist-specific discovery

        Returns:
            Dict with task information
        """
        try:
            if artist_id:
                # Trigger artist-specific discovery
                from src.tasks.scheduled_tasks import artist_specific_discovery_task

                result = artist_specific_discovery_task.apply_async(
                    args=[artist_id], queue="scheduler"
                )

                logger.info(
                    f"Triggered discovery for artist {artist_id}, task_id: {result.id}"
                )

                return {
                    "status": "triggered",
                    "task_id": result.id,
                    "artist_id": artist_id,
                    "message": f"Discovery triggered for artist {artist_id}",
                }

            else:
                # Trigger global discovery
                from src.tasks.scheduled_tasks import scheduled_discovery_task

                result = scheduled_discovery_task.apply_async(queue="scheduler")

                logger.info(f"Triggered global discovery, task_id: {result.id}")

                return {
                    "status": "triggered",
                    "task_id": result.id,
                    "message": "Global discovery triggered for all artists",
                }

        except Exception as e:
            logger.error(f"Failed to trigger discovery: {e}")
            return {"status": "error", "message": str(e), "celery_failed": True}

    def trigger_downloads_now(self) -> Dict[str, Any]:
        """
        Manually trigger downloads task

        Returns:
            Dict with task information
        """
        try:
            from src.tasks.scheduled_tasks import scheduled_downloads_task

            result = scheduled_downloads_task.apply_async(queue="scheduler")

            logger.info(f"Triggered scheduled downloads, task_id: {result.id}")

            return {
                "status": "triggered",
                "task_id": result.id,
                "message": "Scheduled downloads triggered",
            }

        except Exception as e:
            logger.error(f"Failed to trigger downloads: {e}")
            return {"status": "error", "message": str(e), "celery_failed": True}

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get Celery task status by task ID

        Args:
            job_id: Celery task ID

        Returns:
            Dict with task status
        """
        try:
            from celery.result import AsyncResult

            result = AsyncResult(job_id, app=self.celery)

            return {
                "task_id": job_id,
                "status": result.state,
                "result": result.result if result.ready() else None,
                "traceback": result.traceback if result.failed() else None,
            }

        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return {"status": "error", "message": str(e)}

    def get_scheduled_jobs_history(
        self, limit: int = 50, job_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent scheduled job history from database

        Args:
            limit: Maximum number of jobs to return
            job_type: Optional filter by job type (discovery, download)

        Returns:
            List of job dictionaries
        """
        try:
            db = self._get_db()

            query = db.query(ScheduledJob).order_by(ScheduledJob.created_at.desc())

            if job_type:
                query = query.filter(ScheduledJob.job_type == job_type)

            jobs = query.limit(limit).all()

            return [job.to_dict() for job in jobs]

        except Exception as e:
            logger.error(f"Failed to get scheduled jobs history: {e}")
            return []

    def _check_celery_connection(self) -> bool:
        """
        Check if Celery is connected and workers are available

        Returns:
            True if connected, False otherwise
        """
        # First try: Celery inspect API with explicit timeout
        try:
            inspect = self.celery.control.inspect(timeout=2.0)
            stats = inspect.stats()
            if stats is not None and len(stats) > 0:
                return True
        except Exception as e:
            logger.warning(f"Celery inspect check failed: {e}")

        # Fallback: check for celery worker processes via ps
        try:
            import subprocess

            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            celery_processes = [
                line
                for line in result.stdout.split("\n")
                if "celery" in line and "worker" in line
            ]
            if celery_processes:
                logger.debug(
                    f"Celery detected via process check: {len(celery_processes)} worker processes"
                )
                return True
        except Exception as e:
            logger.warning(f"Celery process check failed: {e}")

        return False

    def get_health(self) -> Dict[str, Any]:
        """
        Get comprehensive scheduler health status

        Returns:
            Dict with health information
        """
        try:
            celery_connected = self._check_celery_connection()
            enabled = self.is_enabled()
            running = self._is_running

            # Determine overall health
            if enabled and running and celery_connected:
                health_status = "healthy"
            elif enabled and not running:
                health_status = "stopped"
            elif not celery_connected:
                health_status = "degraded"
            else:
                health_status = "unhealthy"

            return {
                "status": health_status,
                "enabled": enabled,
                "running": running,
                "celery_connected": celery_connected,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get health status: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }


# Global scheduler instance
scheduler_v2 = SchedulerServiceV2()
