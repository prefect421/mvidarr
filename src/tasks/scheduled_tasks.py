"""
Scheduled Tasks for Scheduler V2
Version: v0.10.1
Phase 3: Celery Tasks Implementation

Celery tasks for automated video discovery and downloads.
Uses SchedulerServiceV2, VideoDiscoveryService, and VideoBatchService.

Tasks:
- scheduled_discovery_task: Discover videos for all monitored artists
- artist_specific_discovery_task: Discover videos for a specific artist
- scheduled_downloads_task: Download wanted videos with priority ordering
- retry_failed_downloads_task: Retry failed downloads with exponential backoff
- scheduler_health_check_task: Monitor scheduler system health
- artist_discovery_check_task: Check which artists need discovery
- playlist_sync_task: Sync all monitored YouTube playlists
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from celery import Task
from celery.utils.log import get_task_logger

from src.database.connection import get_db
from src.database.models import Artist, Download, ScheduledJob, Video, VideoStatus
from src.jobs.celery_app import celery_app
from src.services.settings_service import SettingsService
from src.services.video_batch_service import (
    download_all_wanted_videos_internal,
    get_wanted_videos_for_download,
)
from src.services.video_discovery_service import VideoDiscoveryService

logger = get_task_logger(__name__)


class ScheduledTaskBase(Task):
    """Base class for scheduled tasks with automatic retry and job tracking"""

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True

    def before_start(self, task_id, args, kwargs):
        """Create ScheduledJob record before task starts"""
        try:
            with get_db() as db:
                job_type = kwargs.get("job_type", self.name.split(".")[-1])
                artist_id = kwargs.get("artist_id") or (
                    args[0] if args and isinstance(args[0], int) else None
                )

                job = ScheduledJob(
                    job_type=job_type,
                    artist_id=artist_id,
                    status="pending",
                    celery_task_id=task_id,
                    triggered_by=kwargs.get("triggered_by", "scheduler"),
                )
                db.add(job)
                db.commit()
                logger.info(f"Created ScheduledJob record for task {task_id}")

        except Exception as e:
            logger.error(f"Failed to create ScheduledJob record: {e}")

    def on_success(self, retval, task_id, args, kwargs):
        """Update ScheduledJob record on task success"""
        try:
            with get_db() as db:
                job = db.query(ScheduledJob).filter_by(celery_task_id=task_id).first()

                if job:
                    job.status = "completed"
                    job.completed_at = datetime.utcnow()
                    job.result_summary = retval if isinstance(retval, dict) else {}

                    # Calculate execution time
                    if job.started_at:
                        execution_time = (
                            datetime.utcnow() - job.started_at
                        ).total_seconds()
                        job.execution_time_seconds = int(execution_time)

                    db.commit()
                    logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Failed to update ScheduledJob on success: {e}")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Update ScheduledJob record on task failure"""
        try:
            with get_db() as db:
                job = db.query(ScheduledJob).filter_by(celery_task_id=task_id).first()

                if job:
                    job.status = "failed"
                    job.completed_at = datetime.utcnow()
                    job.error_message = str(exc)
                    job.retry_count += 1

                    db.commit()
                    logger.error(f"Task {task_id} failed: {exc}")

        except Exception as e:
            logger.error(f"Failed to update ScheduledJob on failure: {e}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Update ScheduledJob record on task retry"""
        try:
            with get_db() as db:
                job = db.query(ScheduledJob).filter_by(celery_task_id=task_id).first()

                if job:
                    job.status = "retrying"
                    job.retry_count += 1
                    job.error_message = str(exc)

                    db.commit()
                    logger.warning(
                        f"Task {task_id} retrying (attempt {job.retry_count})"
                    )

        except Exception as e:
            logger.error(f"Failed to update ScheduledJob on retry: {e}")


@celery_app.task(
    base=ScheduledTaskBase, name="src.tasks.scheduled_tasks.scheduled_discovery_task"
)
def scheduled_discovery_task(**kwargs) -> Dict[str, Any]:
    """
    Scheduled video discovery for all monitored artists

    This task runs on a schedule (default: every 6 hours) and discovers
    new videos for all artists marked as monitored and with discovery enabled.

    Returns:
        Dict with discovery results
    """
    start_time = datetime.utcnow()
    logger.info("Starting scheduled video discovery for all artists")

    try:
        discovery_service = VideoDiscoveryService()

        # Get settings
        max_per_artist = SettingsService.get_int(
            "auto_discovery_max_videos_per_artist", 5
        )
        batch_size = SettingsService.get_int("discovery_batch_size", 10)

        # Run discovery for all monitored artists
        result = discovery_service.discover_videos_for_all_artists(
            limit_per_artist=max_per_artist
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"Scheduled discovery completed in {execution_time:.2f}s: "
            f"{result.get('total_discovered', 0)} videos discovered"
        )

        return {
            "success": result.get("success", False),
            "total_artists": result.get("total_artists", 0),
            "total_discovered": result.get("total_discovered", 0),
            "total_stored": result.get("total_stored", 0),
            "execution_time": execution_time,
            "triggered_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.error(f"Scheduled discovery failed: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase,
    name="src.tasks.scheduled_tasks.artist_specific_discovery_task",
)
def artist_specific_discovery_task(artist_id: int, **kwargs) -> Dict[str, Any]:
    """
    Discover videos for a specific artist

    This task is triggered for individual artists based on their
    custom discovery_interval_hours setting, OR can be manually
    triggered by users regardless of discovery_enabled status.

    Note: Does NOT check discovery_enabled - allows manual discovery
    even when auto-discovery is disabled for the artist.

    Args:
        artist_id: Artist ID to discover videos for

    Returns:
        Dict with discovery results
    """
    start_time = datetime.utcnow()
    logger.info(f"Starting discovery for artist {artist_id}")

    try:
        discovery_service = VideoDiscoveryService()

        # Run discovery for the specific artist
        result = discovery_service.discover_videos_for_artist(artist_id)

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"Artist {artist_id} discovery completed in {execution_time:.2f}s: "
            f"{result.get('stored_count', 0)} videos stored"
        )

        return {
            "success": result.get("success", False),
            "artist_id": artist_id,
            "artist_name": result.get("artist_name", "Unknown"),
            "discovered_count": result.get("discovered_count", 0),
            "stored_count": result.get("stored_count", 0),
            "execution_time": execution_time,
            "triggered_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.error(f"Discovery failed for artist {artist_id}: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase, name="src.tasks.scheduled_tasks.scheduled_downloads_task"
)
def scheduled_downloads_task(**kwargs) -> Dict[str, Any]:
    """
    Scheduled downloads of wanted videos

    This task runs on a schedule (default: every 2 hours) and processes
    videos marked as WANTED, ordering them by artist priority.

    Returns:
        Dict with download results
    """
    start_time = datetime.utcnow()
    logger.info("Starting scheduled downloads")

    try:
        # Get settings
        max_downloads = SettingsService.get_int("auto_download_max_videos", 50)
        max_concurrent = SettingsService.get_int("download_max_concurrent", 3)

        # Get wanted videos with priority ordering (Scheduler V2)
        # Priority order: artist.schedule_priority (high > medium > low),
        # then artist.priority, then video.created_at (oldest first)
        wanted_videos = get_wanted_videos_for_download(limit=max_downloads)

        if not wanted_videos:
            logger.info("No wanted videos to download")
            return {
                "success": True,
                "message": "No wanted videos to download",
                "queued": 0,
                "failed": 0,
                "execution_time": 0,
            }

        logger.info(f"Found {len(wanted_videos)} wanted videos to download")

        # Pass the priority-ordered IDs so the download function processes
        # videos in scheduling priority order rather than DB insertion order
        priority_video_ids = [v["id"] for v in wanted_videos]
        result = download_all_wanted_videos_internal(video_ids=priority_video_ids)

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"Scheduled downloads completed in {execution_time:.2f}s: "
            f"{result.get('success_count', 0)} queued, "
            f"{result.get('failed_count', 0)} failed"
        )

        return {
            "success": result.get("success", False),
            "queued": result.get("success_count", 0),
            "failed": result.get("failed_count", 0),
            "execution_time": execution_time,
            "triggered_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.error(f"Scheduled downloads failed: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase,
    name="src.tasks.scheduled_tasks.retry_failed_downloads_task",
)
def retry_failed_downloads_task(
    video_id: Optional[int] = None, **kwargs
) -> Dict[str, Any]:
    """
    Retry failed downloads with exponential backoff

    This task retries downloads that failed, using the retry tracking
    fields from Phase 1 (retry_count, next_retry_at, last_error).

    Args:
        video_id: Optional specific video to retry. If None, retries all eligible.

    Returns:
        Dict with retry results
    """
    start_time = datetime.utcnow()
    logger.info(f"Starting retry for failed downloads (video_id: {video_id})")

    try:
        with get_db() as db:
            # Get settings
            max_retries = SettingsService.get_int("download_retry_max_attempts", 3)
            backoff_base = SettingsService.get_int("download_retry_backoff_base", 300)

            # Build query for failed downloads ready to retry
            query = db.query(Download).filter(Download.status == "failed")

            if video_id:
                query = query.filter(Download.video_id == video_id)
            else:
                # Only retry downloads that are ready (next_retry_at passed)
                query = query.filter(
                    (Download.next_retry_at == None)
                    | (Download.next_retry_at <= datetime.utcnow())
                )

            # Filter by max retries
            query = query.filter(Download.retry_count < max_retries)

            failed_downloads = query.all()

            if not failed_downloads:
                logger.info("No failed downloads ready to retry")
                return {
                    "success": True,
                    "message": "No failed downloads ready to retry",
                    "retried": 0,
                }

            logger.info(f"Found {len(failed_downloads)} downloads to retry")

            retried_count = 0
            failed_retry_count = 0

            for download in failed_downloads:
                try:
                    # Update retry tracking
                    download.retry_count += 1
                    download.last_attempt = datetime.utcnow()
                    download.status = "pending"  # Reset to pending for retry

                    # Calculate next retry time with exponential backoff
                    backoff_seconds = backoff_base * (2**download.retry_count)
                    download.next_retry_at = datetime.utcnow() + timedelta(
                        seconds=backoff_seconds
                    )

                    db.commit()

                    # Queue for download (reuses existing download infrastructure)
                    # The download system will pick it up as a pending download
                    retried_count += 1

                    logger.info(
                        f"Queued retry for download {download.id} "
                        f"(attempt {download.retry_count}/{max_retries})"
                    )

                except Exception as e:
                    failed_retry_count += 1
                    download.last_error = str(e)
                    db.commit()
                    logger.error(f"Failed to retry download {download.id}: {e}")

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"Retry task completed in {execution_time:.2f}s: "
                f"{retried_count} retried, {failed_retry_count} failed"
            )

            return {
                "success": True,
                "retried": retried_count,
                "failed": failed_retry_count,
                "execution_time": execution_time,
                "triggered_at": start_time.isoformat(),
            }

    except Exception as e:
        logger.error(f"Retry task failed: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase,
    name="src.tasks.scheduled_tasks.scheduler_health_check_task",
)
def scheduler_health_check_task(**kwargs) -> Dict[str, Any]:
    """
    Scheduler system health check

    This task runs periodically (default: every 5 minutes) to monitor
    the health of the scheduler system.

    Checks:
    - Celery worker availability
    - Redis connectivity
    - Database connectivity
    - Recent job success rate

    Returns:
        Dict with health status
    """
    start_time = datetime.utcnow()
    logger.info("Running scheduler health check")

    try:
        health_status = {
            "timestamp": start_time.isoformat(),
            "celery_workers": False,
            "redis_connected": False,
            "database_connected": False,
            "recent_job_success_rate": 0.0,
            "status": "unknown",
        }

        # Check Celery workers
        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            health_status["celery_workers"] = stats is not None and len(stats) > 0
            health_status["worker_count"] = len(stats) if stats else 0
        except Exception as e:
            logger.error(f"Celery worker check failed: {e}")

        # Check Redis (via Celery broker connection)
        try:
            celery_app.connection().ensure_connection(max_retries=1)
            health_status["redis_connected"] = True
        except Exception as e:
            logger.error(f"Redis connection check failed: {e}")

        # Check database
        try:
            with get_db() as db:
                # Simple query to verify DB connection
                db.execute("SELECT 1")
                health_status["database_connected"] = True

                # Calculate recent job success rate
                recent_jobs = (
                    db.query(ScheduledJob)
                    .filter(
                        ScheduledJob.created_at
                        >= datetime.utcnow() - timedelta(hours=1)
                    )
                    .all()
                )

                if recent_jobs:
                    completed = len([j for j in recent_jobs if j.status == "completed"])
                    success_rate = (completed / len(recent_jobs)) * 100
                    health_status["recent_job_success_rate"] = round(success_rate, 2)
                    health_status["recent_jobs_count"] = len(recent_jobs)

        except Exception as e:
            logger.error(f"Database check failed: {e}")

        # Determine overall status
        all_healthy = (
            health_status["celery_workers"]
            and health_status["redis_connected"]
            and health_status["database_connected"]
        )

        if all_healthy:
            health_status["status"] = "healthy"
        elif health_status["database_connected"]:
            health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        health_status["execution_time"] = execution_time

        logger.info(f"Health check completed: {health_status['status']}")

        return health_status

    except Exception as e:
        logger.error(f"Health check task failed: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase,
    name="src.tasks.scheduled_tasks.artist_discovery_check_task",
)
def artist_discovery_check_task(**kwargs) -> Dict[str, Any]:
    """
    Check which artists need discovery and trigger tasks

    This task runs periodically (default: every 30 minutes) and checks
    which artists need discovery based on their custom discovery_interval_hours.
    Triggers artist_specific_discovery_task for eligible artists.

    Returns:
        Dict with check results
    """
    start_time = datetime.utcnow()
    logger.info("Checking which artists need discovery")

    try:
        with get_db() as db:
            # Get all monitored artists with discovery enabled
            query = (
                db.query(Artist)
                .filter(Artist.monitored == True)
                .filter(Artist.discovery_enabled == True)
            )

            artists = query.all()

            if not artists:
                logger.info("No monitored artists found")
                return {
                    "success": True,
                    "message": "No monitored artists found",
                    "checked": 0,
                    "triggered": 0,
                }

            logger.info(f"Checking {len(artists)} artists for discovery eligibility")

            triggered_count = 0
            discovery_service = VideoDiscoveryService()

            for artist in artists:
                # Check if artist needs discovery
                if discovery_service._should_discover_for_artist(artist):
                    # Trigger artist-specific discovery task
                    artist_specific_discovery_task.apply_async(
                        args=[artist.id],
                        queue="scheduler",
                        kwargs={"triggered_by": "artist_discovery_check"},
                    )

                    triggered_count += 1
                    logger.info(
                        f"Triggered discovery for artist {artist.id} ({artist.name})"
                    )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"Artist discovery check completed in {execution_time:.2f}s: "
                f"{triggered_count}/{len(artists)} discoveries triggered"
            )

            return {
                "success": True,
                "checked": len(artists),
                "triggered": triggered_count,
                "execution_time": execution_time,
                "triggered_at": start_time.isoformat(),
            }

    except Exception as e:
        logger.error(f"Artist discovery check failed: {e}")
        raise


@celery_app.task(
    base=ScheduledTaskBase,
    name="src.tasks.scheduled_tasks.playlist_sync_task",
)
def playlist_sync_task(**kwargs) -> Dict[str, Any]:
    """
    Sync all monitored YouTube playlists

    This task runs on a schedule (default: every 6 hours) and syncs
    all monitored YouTube playlists, adding new videos and optionally
    queuing downloads based on each monitor's auto_download setting.

    Returns:
        Dict with sync results
    """
    start_time = datetime.utcnow()
    logger.info("Starting scheduled YouTube playlist sync")

    try:
        from src.services.youtube_playlist_service import youtube_playlist_service

        result = youtube_playlist_service.sync_all_playlists()

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"Scheduled playlist sync completed in {execution_time:.2f}s: "
            f"{result.get('synced_playlists', 0)}/{result.get('total_playlists', 0)} playlists synced, "
            f"{result.get('total_new_videos', 0)} new videos found"
        )

        return {
            "success": True,
            "total_playlists": result.get("total_playlists", 0),
            "synced_playlists": result.get("synced_playlists", 0),
            "total_new_videos": result.get("total_new_videos", 0),
            "total_downloads": result.get("total_downloads", 0),
            "errors": result.get("errors", []),
            "execution_time": execution_time,
            "triggered_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.error(f"Scheduled playlist sync failed: {e}")
        raise
