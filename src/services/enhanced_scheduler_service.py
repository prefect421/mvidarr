"""
Enhanced Docker-Native Scheduler Service for MVidarr
Docker-optimized background scheduler with improved container support
"""

import os
import signal
import sys
import threading
import time
from datetime import datetime
from datetime import time as dt_time
from typing import Any, Dict, Optional

import schedule

from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.enhanced_scheduler")


class EnhancedSchedulerService:
    """Enhanced Docker-native scheduler service with improved container support"""

    def __init__(self):
        self.scheduler_thread: Optional[threading.Thread] = None
        self.running = False
        self._shutdown_event = threading.Event()
        self._last_run_times: Dict[str, datetime] = {}
        self._health_check_interval = 300  # 5 minutes
        self._last_health_check = None

        # Environment variable configuration support
        self._load_env_config()

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

    def _load_env_config(self):
        """Load configuration from environment variables (Docker-friendly)"""
        self.env_config = {
            "auto_download_enabled": os.getenv(
                "MVIDARR_AUTO_DOWNLOAD_ENABLED", "true"
            ).lower()
            == "true",
            "auto_download_schedule": os.getenv(
                "MVIDARR_AUTO_DOWNLOAD_SCHEDULE", "daily"
            ),
            "auto_download_time": os.getenv("MVIDARR_AUTO_DOWNLOAD_TIME", "03:30"),
            "auto_discovery_enabled": os.getenv(
                "MVIDARR_AUTO_DISCOVERY_ENABLED", "false"
            ).lower()
            == "true",
            "auto_discovery_schedule": os.getenv(
                "MVIDARR_AUTO_DISCOVERY_SCHEDULE", "daily"
            ),
            "auto_discovery_time": os.getenv("MVIDARR_AUTO_DISCOVERY_TIME", "06:00"),
            "max_downloads_per_run": int(
                os.getenv("MVIDARR_MAX_DOWNLOADS_PER_RUN", "10")
            ),
            "scheduler_health_check": os.getenv(
                "MVIDARR_SCHEDULER_HEALTH_CHECK", "true"
            ).lower()
            == "true",
            "scheduler_log_level": os.getenv(
                "MVIDARR_SCHEDULER_LOG_LEVEL", "INFO"
            ).upper(),
        }

        logger.info(f"Environment configuration loaded: {self.env_config}")

    def _register_signal_handlers(self):
        """Register signal handlers for graceful Docker shutdown"""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, "SIGQUIT"):
            signal.signal(signal.SIGQUIT, signal_handler)

    def start(self):
        """Start the enhanced scheduler service"""
        if self.running:
            logger.warning("Enhanced scheduler service is already running")
            return

        logger.info("Starting enhanced Docker-native scheduler service...")
        self.running = True
        self._shutdown_event.clear()

        # Clear any existing jobs
        schedule.clear()

        # Set up scheduled jobs
        self._setup_scheduled_jobs()

        # Start the scheduler thread
        self.scheduler_thread = threading.Thread(
            target=self._run_enhanced_scheduler, daemon=True, name="MVidarrScheduler"
        )
        self.scheduler_thread.start()

        logger.info("Enhanced scheduler service started successfully")

    def stop(self):
        """Stop the scheduler service gracefully"""
        if not self.running:
            logger.warning("Enhanced scheduler service is not running")
            return

        logger.info("Stopping enhanced scheduler service...")
        self.running = False
        self._shutdown_event.set()

        # Clear scheduled jobs
        schedule.clear()

        if self.scheduler_thread and self.scheduler_thread.is_alive():
            logger.info("Waiting for scheduler thread to finish...")
            self.scheduler_thread.join(timeout=10)
            if self.scheduler_thread.is_alive():
                logger.warning(
                    "Scheduler thread did not stop gracefully within timeout"
                )

        logger.info("Enhanced scheduler service stopped")

    def reload_schedule(self):
        """Reload the schedule from current settings and environment"""
        logger.info("Reloading scheduled jobs from settings and environment...")

        # Reload environment configuration
        self._load_env_config()

        # Clear existing jobs
        schedule.clear()

        # Set up jobs again
        self._setup_scheduled_jobs()

        logger.info("Scheduled jobs reloaded")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive scheduler status for health checks"""
        return {
            "running": self.running,
            "thread_alive": (
                self.scheduler_thread.is_alive() if self.scheduler_thread else False
            ),
            "jobs_count": len(schedule.jobs),
            "scheduled_jobs": [
                {
                    "job_id": id(job),
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "job_func": job.job_func.__name__ if job.job_func else None,
                    "unit": str(job.unit),
                    "interval": job.interval,
                }
                for job in schedule.jobs
            ],
            "last_run_times": {
                task: timestamp.isoformat()
                for task, timestamp in self._last_run_times.items()
            },
            "last_health_check": (
                self._last_health_check.isoformat() if self._last_health_check else None
            ),
            "environment_config": self.env_config,
        }

    def trigger_download_now(self) -> Dict[str, Any]:
        """Manually trigger download task"""
        logger.info("Manual download trigger requested")
        try:
            result = self._run_scheduled_download()
            return {
                "success": True,
                "message": "Download task triggered successfully",
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Manual download trigger failed: {e}")
            return {
                "success": False,
                "message": f"Download trigger failed: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }

    def trigger_discovery_now(self) -> Dict[str, Any]:
        """Manually trigger discovery task"""
        logger.info("Manual discovery trigger requested")
        try:
            result = self._run_scheduled_discovery()
            return {
                "success": True,
                "message": "Discovery task triggered successfully",
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Manual discovery trigger failed: {e}")
            return {
                "success": False,
                "message": f"Discovery trigger failed: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }

    def _setup_scheduled_jobs(self):
        """Set up scheduled jobs with enhanced Docker support"""
        try:
            # Combine database settings with environment overrides
            download_enabled = self._get_setting(
                "auto_download_schedule_enabled",
                self.env_config["auto_download_enabled"],
            )

            if not download_enabled:
                logger.info("Scheduled downloads are disabled")
            else:
                self._setup_download_schedule()

            # Set up discovery scheduling
            discovery_enabled = self._get_setting(
                "auto_discovery_schedule_enabled",
                self.env_config["auto_discovery_enabled"],
            )

            if discovery_enabled:
                self._setup_discovery_schedule()
            else:
                logger.info("Scheduled video discovery is disabled")

            # Set up health check scheduling if enabled
            if self.env_config["scheduler_health_check"]:
                schedule.every(self._health_check_interval).seconds.do(
                    self._run_health_check
                )
                logger.info(
                    f"Scheduled health checks every {self._health_check_interval} seconds"
                )

        except Exception as e:
            logger.error(f"Error setting up scheduled jobs: {e}")

    def _setup_download_schedule(self):
        """Set up download scheduling with environment variable support"""
        schedule_time = self._get_setting(
            "auto_download_schedule_time", self.env_config["auto_download_time"]
        )
        schedule_frequency = self._get_setting(
            "auto_download_schedule_frequency",
            self.env_config["auto_download_schedule"],
        )

        logger.info(
            f"Setting up scheduled downloads for {schedule_frequency} at {schedule_time}"
        )

        # Parse time
        try:
            hour, minute = map(int, schedule_time.split(":"))
            schedule_time_obj = dt_time(hour, minute)
        except (ValueError, IndexError):
            logger.error(
                f"Invalid schedule time format: {schedule_time}. Using default 03:30"
            )
            hour, minute = 3, 30

        # Schedule based on frequency with enhanced options
        if schedule_frequency == "hourly":
            schedule.every().hour.at(f":{minute:02d}").do(self._run_scheduled_download)
            logger.info(f"Scheduled hourly downloads at minute {minute}")

        elif schedule_frequency.startswith("every_") and "hours" in schedule_frequency:
            try:
                hours = int(schedule_frequency.split("_")[1])
                if 1 <= hours <= 24:
                    schedule.every(hours).hours.do(self._run_scheduled_download)
                    logger.info(f"Scheduled downloads every {hours} hours")
                else:
                    raise ValueError("Hours must be 1-24")
            except (ValueError, IndexError):
                logger.error(
                    f"Invalid schedule format: {schedule_frequency}. Defaulting to daily"
                )
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
                    self._run_scheduled_download
                )

        elif schedule_frequency == "daily":
            schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
                self._run_scheduled_download
            )
            logger.info(f"Scheduled daily downloads at {hour:02d}:{minute:02d}")

        elif schedule_frequency == "weekly":
            schedule.every().sunday.at(f"{hour:02d}:{minute:02d}").do(
                self._run_scheduled_download
            )
            logger.info(
                f"Scheduled weekly downloads on Sunday at {hour:02d}:{minute:02d}"
            )

        else:
            # Handle comma-separated days or single day
            self._schedule_for_days(
                schedule_frequency,
                hour,
                minute,
                self._run_scheduled_download,
                "downloads",
            )

    def _setup_discovery_schedule(self):
        """Set up discovery scheduling with environment variable support"""
        discovery_time = self._get_setting(
            "auto_discovery_schedule_time", self.env_config["auto_discovery_time"]
        )
        discovery_frequency = self._get_setting(
            "auto_discovery_schedule_days", self.env_config["auto_discovery_schedule"]
        )

        logger.info(
            f"Setting up scheduled discovery for {discovery_frequency} at {discovery_time}"
        )

        try:
            hour, minute = map(int, discovery_time.split(":"))
        except (ValueError, IndexError):
            logger.error(
                f"Invalid discovery time format: {discovery_time}. Using default 06:00"
            )
            hour, minute = 6, 0

        if discovery_frequency == "daily":
            schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
                self._run_scheduled_discovery
            )
            logger.info(f"Scheduled daily discovery at {hour:02d}:{minute:02d}")
        elif discovery_frequency == "weekly":
            schedule.every().saturday.at(f"{hour:02d}:{minute:02d}").do(
                self._run_scheduled_discovery
            )
            logger.info(
                f"Scheduled weekly discovery on Saturday at {hour:02d}:{minute:02d}"
            )
        else:
            self._schedule_for_days(
                discovery_frequency,
                hour,
                minute,
                self._run_scheduled_discovery,
                "discovery",
            )

    def _schedule_for_days(
        self, days_config: str, hour: int, minute: int, func, task_name: str
    ):
        """Schedule a function for specific days"""
        days_map = {
            "monday": schedule.every().monday,
            "tuesday": schedule.every().tuesday,
            "wednesday": schedule.every().wednesday,
            "thursday": schedule.every().thursday,
            "friday": schedule.every().friday,
            "saturday": schedule.every().saturday,
            "sunday": schedule.every().sunday,
        }

        if "," in days_config:
            selected_days = [day.strip().lower() for day in days_config.split(",")]
            for day in selected_days:
                if day in days_map:
                    days_map[day].at(f"{hour:02d}:{minute:02d}").do(func)
                    logger.info(
                        f"Scheduled {task_name} on {day.capitalize()} at {hour:02d}:{minute:02d}"
                    )
        else:
            day = days_config.strip().lower()
            if day in days_map:
                days_map[day].at(f"{hour:02d}:{minute:02d}").do(func)
                logger.info(
                    f"Scheduled {task_name} on {day.capitalize()} at {hour:02d}:{minute:02d}"
                )
            else:
                logger.error(
                    f"Invalid day: {day}. Defaulting to daily at {hour:02d}:{minute:02d}"
                )
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(func)

    def _get_setting(self, key: str, env_default: Any) -> Any:
        """Get setting from database with environment variable fallback"""
        try:
            return SettingsService.get(key, env_default)
        except Exception:
            logger.warning(
                f"Could not read setting {key} from database, using environment default: {env_default}"
            )
            return env_default

    def _run_enhanced_scheduler(self):
        """Enhanced scheduler loop with better error handling and health monitoring"""
        logger.info("Enhanced scheduler thread started")

        while self.running and not self._shutdown_event.is_set():
            try:
                # Run pending scheduled jobs
                schedule.run_pending()

                # Wait with early exit on shutdown signal
                if self._shutdown_event.wait(timeout=60):  # Check every minute
                    break

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                # Don't exit on error, just log and continue
                time.sleep(60)

        logger.info("Enhanced scheduler thread stopped")

    def _run_scheduled_download(self) -> Dict[str, Any]:
        """Run scheduled download using background job system"""
        logger.info("🔽 Starting scheduled download task (background job)...")
        start_time = datetime.now()

        try:
            import asyncio

            from src.services.job_queue import (
                BackgroundJob,
                JobPriority,
                JobType,
                get_job_queue,
            )

            max_downloads = self._get_setting(
                "scheduler_max_downloads_per_run",
                self.env_config["max_downloads_per_run"],
            )

            # Create background job for scheduled download
            job = BackgroundJob(
                type=JobType.SCHEDULED_DOWNLOAD,
                priority=JobPriority.NORMAL,
                payload={
                    "max_downloads": max_downloads,
                    "scheduled_time": start_time.isoformat(),
                },
            )

            # Enqueue job
            async def queue_job():
                job_queue = await get_job_queue()
                return await job_queue.enqueue(job)

            job_id = asyncio.run(queue_job())

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self._last_run_times["download"] = start_time

            result = {
                "status": "completed",
                "job_id": job_id,
                "max_downloads": max_downloads,
                "duration_seconds": duration,
            }

            logger.info(
                f"🔽 Scheduled download job {job_id} queued (took {duration:.1f}s)"
            )
            return result

        except Exception as e:
            error_msg = f"Scheduled download failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self._last_run_times["download"] = start_time
            return {"status": "error", "message": error_msg}

    def _run_scheduled_discovery(self) -> Dict[str, Any]:
        """Run scheduled video discovery using background job system"""
        logger.info("🔍 Starting scheduled video discovery task (background job)...")
        start_time = datetime.now()

        try:
            import asyncio

            from src.services.job_queue import (
                BackgroundJob,
                JobPriority,
                JobType,
                get_job_queue,
            )

            # Get discovery settings
            max_artists = self._get_setting("scheduler_max_artists_per_discovery", 5)
            max_videos_per_artist = self._get_setting(
                "scheduler_max_videos_per_artist", 3
            )

            logger.info(
                f"🎯 Queueing discovery for up to {max_artists} artists, {max_videos_per_artist} videos each"
            )

            # Create background job for scheduled discovery
            job = BackgroundJob(
                type=JobType.SCHEDULED_DISCOVERY,
                priority=JobPriority.NORMAL,
                payload={
                    "max_artists": max_artists,
                    "max_videos_per_artist": max_videos_per_artist,
                    "scheduled_time": start_time.isoformat(),
                },
            )

            # Enqueue job
            async def queue_job():
                job_queue = await get_job_queue()
                return await job_queue.enqueue(job)

            job_id = asyncio.run(queue_job())

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self._last_run_times["discovery"] = start_time

            result = {
                "status": "completed",
                "job_id": job_id,
                "max_artists": max_artists,
                "max_videos_per_artist": max_videos_per_artist,
                "duration_seconds": duration,
            }

            logger.info(
                f"🔍 Scheduled discovery job {job_id} queued (took {duration:.1f}s)"
            )
            return result

        except Exception as e:
            error_msg = f"Scheduled discovery failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self._last_run_times["discovery"] = start_time
            return {"status": "error", "message": error_msg}

    def _run_health_check(self):
        """Run scheduler health check"""
        logger.debug("🏥 Running scheduler health check...")
        self._last_health_check = datetime.now()

        # Check thread health
        if not self.scheduler_thread or not self.scheduler_thread.is_alive():
            logger.warning("⚠️ Scheduler thread is not alive")

        # Check job status
        if not schedule.jobs:
            logger.warning("⚠️ No scheduled jobs found")
        else:
            logger.debug(f"✅ Health check passed: {len(schedule.jobs)} jobs scheduled")


# Create singleton instance
enhanced_scheduler_service = EnhancedSchedulerService()
