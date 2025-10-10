"""
Background Scheduler Service for MVidarr
Handles scheduled tasks like automated video downloads
"""

import threading
import time
from datetime import datetime
from datetime import time as dt_time
from typing import Any, Dict, Optional

import schedule

from src.database.connection import get_db
from src.database.models import Setting
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.scheduler")


class SchedulerService:
    """Service for managing scheduled tasks"""

    def __init__(self):
        self.scheduler_thread: Optional[threading.Thread] = None
        self.running = False
        self._last_check_time = None

    def start(self):
        """Start the scheduler service"""
        if self.running:
            logger.warning("Scheduler service is already running")
            return

        logger.info("Starting scheduler service...")
        self.running = True

        # Clear any existing jobs
        schedule.clear()

        # Set up scheduled jobs based on current settings
        self._setup_scheduled_jobs()

        # Start the scheduler thread
        self.scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self.scheduler_thread.start()

        logger.info("Scheduler service started successfully")

    def stop(self):
        """Stop the scheduler service"""
        if not self.running:
            logger.warning("Scheduler service is not running")
            return

        logger.info("Stopping scheduler service...")
        self.running = False

        # Clear scheduled jobs
        schedule.clear()

        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        logger.info("Scheduler service stopped")

    def reload_schedule(self):
        """Reload the schedule from current settings"""
        logger.info("Reloading scheduled jobs from settings...")

        # Clear existing jobs
        schedule.clear()

        # Set up jobs again
        self._setup_scheduled_jobs()

        logger.info("Scheduled jobs reloaded")

    def _setup_scheduled_jobs(self):
        """Set up scheduled jobs based on current settings"""
        try:
            # Check if scheduled downloads are enabled
            if not SettingsService.get_bool("auto_download_schedule_enabled", True):
                logger.info("Scheduled downloads are disabled")
                return

            # Get schedule settings
            schedule_time = SettingsService.get("auto_download_schedule_time", "02:00")
            schedule_days = SettingsService.get("auto_download_schedule_days", "hourly")

            logger.info(
                f"Setting up scheduled downloads for {schedule_days} at {schedule_time}"
            )

            # Parse time
            try:
                hour, minute = map(int, schedule_time.split(":"))
                schedule_time_obj = dt_time(hour, minute)
            except (ValueError, IndexError):
                logger.error(
                    f"Invalid schedule time format: {schedule_time}. Using default 02:00"
                )
                schedule_time_obj = dt_time(2, 0)
                hour, minute = 2, 0

            # Schedule based on frequency
            if schedule_days == "hourly":
                # Schedule hourly downloads - ignore the time setting for hourly
                schedule.every().hour.do(self._run_scheduled_download)
                logger.info("Scheduled hourly downloads (every hour)")

            elif schedule_days.startswith("every_") and schedule_days.endswith(
                "_hours"
            ):
                # Handle "every_X_hours" format (e.g., "every_2_hours", "every_6_hours")
                try:
                    hours_str = schedule_days.replace("every_", "").replace(
                        "_hours", ""
                    )
                    hours = int(hours_str)
                    if 1 <= hours <= 24:
                        schedule.every(hours).hours.do(self._run_scheduled_download)
                        logger.info(f"Scheduled downloads every {hours} hours")
                    else:
                        logger.error(
                            f"Invalid hours value: {hours}. Must be 1-24. Defaulting to hourly"
                        )
                        schedule.every().hour.do(self._run_scheduled_download)
                except (ValueError, IndexError):
                    logger.error(
                        f"Invalid schedule format: {schedule_days}. Defaulting to hourly"
                    )
                    schedule.every().hour.do(self._run_scheduled_download)
            elif schedule_days == "daily":
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
                    self._run_scheduled_download
                )
                logger.info(f"Scheduled daily downloads at {hour:02d}:{minute:02d}")

            elif schedule_days == "weekly":
                # Default to Sunday for weekly
                schedule.every().sunday.at(f"{hour:02d}:{minute:02d}").do(
                    self._run_scheduled_download
                )
                logger.info(
                    f"Scheduled weekly downloads on Sunday at {hour:02d}:{minute:02d}"
                )

            else:
                # Handle specific days (comma-separated: monday,wednesday,friday)
                days_map = {
                    "monday": schedule.every().monday,
                    "tuesday": schedule.every().tuesday,
                    "wednesday": schedule.every().wednesday,
                    "thursday": schedule.every().thursday,
                    "friday": schedule.every().friday,
                    "saturday": schedule.every().saturday,
                    "sunday": schedule.every().sunday,
                }

                if "," in schedule_days:
                    selected_days = [
                        day.strip().lower() for day in schedule_days.split(",")
                    ]
                    for day in selected_days:
                        if day in days_map:
                            days_map[day].at(f"{hour:02d}:{minute:02d}").do(
                                self._run_scheduled_download
                            )
                            logger.info(
                                f"Scheduled downloads on {day.capitalize()} at {hour:02d}:{minute:02d}"
                            )
                        else:
                            logger.warning(f"Invalid day name: {day}")
                else:
                    # Single day
                    day = schedule_days.strip().lower()
                    if day in days_map:
                        days_map[day].at(f"{hour:02d}:{minute:02d}").do(
                            self._run_scheduled_download
                        )
                        logger.info(
                            f"Scheduled downloads on {day.capitalize()} at {hour:02d}:{minute:02d}"
                        )
                    else:
                        logger.error(
                            f"Invalid schedule days: {schedule_days}. Defaulting to hourly"
                        )
                        schedule.every().hour.do(self._run_scheduled_download)

            # Set up video discovery scheduling if enabled
            discovery_enabled = SettingsService.get_bool(
                "auto_discovery_schedule_enabled", True
            )
            if discovery_enabled:
                # Get discovery schedule settings
                discovery_schedule_time = SettingsService.get(
                    "auto_discovery_schedule_time", "06:00"
                )
                discovery_schedule_days = SettingsService.get(
                    "auto_discovery_schedule_days", "daily"
                )

                logger.info(
                    f"Setting up scheduled video discovery for {discovery_schedule_days} at {discovery_schedule_time}"
                )

                # Parse discovery time
                try:
                    disc_hour, disc_minute = map(
                        int, discovery_schedule_time.split(":")
                    )
                except (ValueError, IndexError):
                    logger.error(
                        f"Invalid discovery schedule time format: {discovery_schedule_time}. Using default 06:00"
                    )
                    disc_hour, disc_minute = 6, 0

                # Schedule discovery based on frequency
                if discovery_schedule_days == "daily":
                    schedule.every().day.at(f"{disc_hour:02d}:{disc_minute:02d}").do(
                        self._run_scheduled_discovery
                    )
                    logger.info(
                        f"Scheduled daily video discovery at {disc_hour:02d}:{disc_minute:02d}"
                    )

                elif discovery_schedule_days == "weekly":
                    # Default to Saturday for weekly discovery (different from Sunday downloads)
                    schedule.every().saturday.at(
                        f"{disc_hour:02d}:{disc_minute:02d}"
                    ).do(self._run_scheduled_discovery)
                    logger.info(
                        f"Scheduled weekly video discovery on Saturday at {disc_hour:02d}:{disc_minute:02d}"
                    )

                elif discovery_schedule_days == "twice_daily":
                    # Morning and evening discovery
                    schedule.every().day.at(f"{disc_hour:02d}:{disc_minute:02d}").do(
                        self._run_scheduled_discovery
                    )
                    # Evening run 12 hours later
                    evening_hour = (disc_hour + 12) % 24
                    schedule.every().day.at(f"{evening_hour:02d}:{disc_minute:02d}").do(
                        self._run_scheduled_discovery
                    )
                    logger.info(
                        f"Scheduled twice-daily video discovery at {disc_hour:02d}:{disc_minute:02d} and {evening_hour:02d}:{disc_minute:02d}"
                    )

                else:
                    # Handle specific days for discovery
                    days_map = {
                        "monday": schedule.every().monday,
                        "tuesday": schedule.every().tuesday,
                        "wednesday": schedule.every().wednesday,
                        "thursday": schedule.every().thursday,
                        "friday": schedule.every().friday,
                        "saturday": schedule.every().saturday,
                        "sunday": schedule.every().sunday,
                    }

                    if "," in discovery_schedule_days:
                        selected_days = [
                            day.strip().lower()
                            for day in discovery_schedule_days.split(",")
                        ]
                        for day in selected_days:
                            if day in days_map:
                                days_map[day].at(
                                    f"{disc_hour:02d}:{disc_minute:02d}"
                                ).do(self._run_scheduled_discovery)
                                logger.info(
                                    f"Scheduled video discovery on {day.capitalize()} at {disc_hour:02d}:{disc_minute:02d}"
                                )
                            else:
                                logger.warning(f"Invalid discovery day name: {day}")
                    else:
                        # Single day
                        day = discovery_schedule_days.strip().lower()
                        if day in days_map:
                            days_map[day].at(f"{disc_hour:02d}:{disc_minute:02d}").do(
                                self._run_scheduled_discovery
                            )
                            logger.info(
                                f"Scheduled video discovery on {day.capitalize()} at {disc_hour:02d}:{disc_minute:02d}"
                            )
                        else:
                            logger.error(
                                f"Invalid discovery schedule days: {discovery_schedule_days}. Defaulting to daily"
                            )
                            schedule.every().day.at("06:00").do(
                                self._run_scheduled_discovery
                            )
            else:
                logger.info("Scheduled video discovery is disabled")

        except Exception as e:
            logger.error(f"Failed to set up scheduled jobs: {e}")

    def _run_scheduler(self):
        """Main scheduler loop"""
        logger.info("Scheduler thread started")

        while self.running:
            try:
                # Run pending scheduled jobs
                schedule.run_pending()

                # Check for settings changes every 5 minutes
                current_time = datetime.now()
                if (
                    self._last_check_time is None
                    or (current_time - self._last_check_time).total_seconds() > 300
                ):
                    self._check_settings_changes()
                    self._last_check_time = current_time

                # Sleep for 1 minute before checking again
                time.sleep(60)

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(60)

        logger.info("Scheduler thread stopped")

    def _check_settings_changes(self):
        """Check if schedule settings have changed and reload if necessary"""
        try:
            # Check if schedule settings have changed and reload if necessary
            # Also check for new wanted videos and monitored artists periodically
            download_enabled = SettingsService.get_bool(
                "auto_download_schedule_enabled", True
            )
            discovery_enabled = SettingsService.get_bool(
                "auto_discovery_schedule_enabled", True
            )

            if download_enabled:
                current_schedule_days = SettingsService.get(
                    "auto_download_schedule_days", "hourly"
                )

                # For hourly downloads, log wanted video count periodically
                if current_schedule_days == "hourly":
                    wanted_count = self._get_wanted_video_count()
                    if wanted_count > 0:
                        logger.info(
                            f"Hourly scheduler: {wanted_count} videos currently marked as WANTED"
                        )

            if discovery_enabled:
                # Log monitored artist count periodically for discovery
                monitored_count = self._get_monitored_artist_count()
                if monitored_count > 0:
                    logger.debug(
                        f"Discovery scheduler: {monitored_count} artists currently monitored for video discovery"
                    )

            # Settings might have changed, reload the schedule
            if download_enabled or discovery_enabled:
                self.reload_schedule()
        except Exception as e:
            logger.error(f"Error checking settings changes: {e}")

    def _run_scheduled_download(self):
        """Execute the scheduled download of wanted videos"""
        try:
            schedule_frequency = SettingsService.get(
                "auto_download_schedule_days", "hourly"
            )
            logger.info(
                f"Starting {schedule_frequency} scheduled download of wanted videos..."
            )

            # Get maximum videos setting - default varies by frequency
            default_max = 10 if schedule_frequency == "hourly" else 50
            max_videos = SettingsService.get_int(
                "auto_download_max_videos", default_max
            )

            # For hourly downloads, check if there are wanted videos first
            if schedule_frequency == "hourly":
                wanted_count = self._get_wanted_video_count()
                if wanted_count == 0:
                    logger.debug(
                        "Hourly check: No wanted videos found, skipping download attempt"
                    )
                    return
                else:
                    logger.info(
                        f"Hourly check: Found {wanted_count} wanted videos, attempting to download up to {max_videos}"
                    )

            # Import here to avoid circular imports
            from src.services.video_batch_service import (
                download_all_wanted_videos_internal,
            )

            # Run the download function
            result = download_all_wanted_videos_internal(limit=max_videos)

            if result.get("success"):
                success_count = result.get("success_count", 0)
                failed_count = result.get("failed_count", 0)
                total_wanted = result.get("total_wanted", 0)

                logger.info(
                    f"{schedule_frequency.capitalize()} download completed: {success_count} queued, {failed_count} failed, {total_wanted} total wanted videos"
                )

                # Log summary
                if success_count > 0:
                    logger.info(
                        f"Successfully queued {success_count} videos for download"
                    )
                if failed_count > 0:
                    logger.warning(f"{failed_count} videos failed to queue")
                if total_wanted == 0:
                    if schedule_frequency == "hourly":
                        logger.debug("Hourly check completed: No wanted videos found")
                    else:
                        logger.info("No wanted videos found to download")

            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Scheduled download failed: {error}")

        except Exception as e:
            logger.error(f"Error running scheduled download: {e}")
            # Continue running even if one download fails

    def _run_scheduled_discovery(self):
        """Execute the scheduled discovery of new videos for monitored artists"""
        try:
            discovery_frequency = SettingsService.get(
                "auto_discovery_schedule_days", "daily"
            )
            logger.info(f"Starting {discovery_frequency} scheduled video discovery...")

            # Get maximum videos per artist setting
            max_videos_per_artist = SettingsService.get_int(
                "auto_discovery_max_videos_per_artist", 5
            )

            # Check if there are monitored artists first
            monitored_count = self._get_monitored_artist_count()
            if monitored_count == 0:
                logger.info("No monitored artists found for video discovery")
                return

            logger.info(
                f"Discovery check: Found {monitored_count} monitored artists, attempting to discover up to {max_videos_per_artist} videos per artist"
            )

            # Import here to avoid circular imports
            from src.services.video_discovery_service import video_discovery_service

            # Run the discovery function
            result = video_discovery_service.discover_videos_for_all_artists(
                limit_per_artist=max_videos_per_artist
            )

            if result.get("success"):
                total_artists = result.get("total_artists", 0)
                processed_artists = result.get("processed_artists", 0)
                total_discovered = result.get("total_discovered", 0)
                total_stored = result.get("total_stored", 0)

                logger.info(
                    f"{discovery_frequency.capitalize()} discovery completed: {processed_artists}/{total_artists} artists processed, {total_discovered} videos discovered, {total_stored} videos stored"
                )

                # Log summary
                if total_stored > 0:
                    logger.info(
                        f"Successfully discovered and stored {total_stored} new videos"
                    )
                if total_discovered > total_stored:
                    logger.info(
                        f"{total_discovered - total_stored} videos were duplicates and not stored"
                    )
                if processed_artists == 0:
                    logger.info(
                        "No artists needed discovery (too recent or no monitored artists)"
                    )

            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Scheduled discovery failed: {error}")

        except Exception as e:
            logger.error(f"Error running scheduled discovery: {e}")
            # Continue running even if discovery fails

    def _get_wanted_video_count(self) -> int:
        """Get the current count of wanted videos"""
        try:
            from src.database.connection import get_db
            from src.database.models import Video, VideoStatus

            with get_db() as session:
                count = (
                    session.query(Video)
                    .filter(Video.status == VideoStatus.WANTED)
                    .count()
                )
                return count
        except Exception as e:
            logger.error(f"Error getting wanted video count: {e}")
            return 0

    def _get_monitored_artist_count(self) -> int:
        """Get the current count of monitored artists"""
        try:
            from src.database.connection import get_db
            from src.database.models import Artist

            with get_db() as session:
                count = session.query(Artist).filter(Artist.monitored == True).count()
                return count
        except Exception as e:
            logger.error(f"Error getting monitored artist count: {e}")
            return 0

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time"""
        try:
            if not schedule.jobs:
                return None

            # Get the next run time from all jobs
            next_times = [job.next_run for job in schedule.jobs if job.next_run]
            if next_times:
                return min(next_times)
            return None

        except Exception as e:
            logger.error(f"Error getting next run time: {e}")
            return None

    def get_schedule_info(self) -> Dict[str, Any]:
        """Get information about current schedule"""
        try:
            download_enabled = SettingsService.get_bool(
                "auto_download_schedule_enabled", True
            )
            discovery_enabled = SettingsService.get_bool(
                "auto_discovery_schedule_enabled", True
            )

            if not download_enabled and not discovery_enabled:
                return {
                    "enabled": False,
                    "next_run": None,
                    "schedule": "Both downloads and discovery disabled",
                }

            next_run = self.get_next_run_time()
            info = {
                "enabled": download_enabled or discovery_enabled,
                "next_run": next_run.isoformat() if next_run else None,
                "next_run_human": (
                    next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None
                ),
                "job_count": len(schedule.jobs),
            }

            # Add download schedule info if enabled
            if download_enabled:
                download_schedule_time = SettingsService.get(
                    "auto_download_schedule_time", "02:00"
                )
                download_schedule_days = SettingsService.get(
                    "auto_download_schedule_days", "hourly"
                )
                max_videos = SettingsService.get_int("auto_download_max_videos", 10)

                info["downloads"] = {
                    "enabled": True,
                    "schedule_time": download_schedule_time,
                    "schedule_days": download_schedule_days,
                    "max_videos": max_videos,
                }
            else:
                info["downloads"] = {"enabled": False}

            # Add discovery schedule info if enabled
            if discovery_enabled:
                discovery_schedule_time = SettingsService.get(
                    "auto_discovery_schedule_time", "06:00"
                )
                discovery_schedule_days = SettingsService.get(
                    "auto_discovery_schedule_days", "daily"
                )
                max_videos_per_artist = SettingsService.get_int(
                    "auto_discovery_max_videos_per_artist", 5
                )
                monitored_count = self._get_monitored_artist_count()

                info["discovery"] = {
                    "enabled": True,
                    "schedule_time": discovery_schedule_time,
                    "schedule_days": discovery_schedule_days,
                    "max_videos_per_artist": max_videos_per_artist,
                    "monitored_artists": monitored_count,
                }
            else:
                info["discovery"] = {"enabled": False}

            return info

        except Exception as e:
            logger.error(f"Error getting schedule info: {e}")
            return {"enabled": False, "error": str(e)}


# Global scheduler instance
scheduler_service = SchedulerService()
