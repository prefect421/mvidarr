"""
Celery Application Configuration for Background Job Processing
Phase 2: Media Processing Optimization - Redis & Celery Infrastructure
"""

import os
from datetime import timedelta

from celery import Celery
from celery.signals import worker_ready, worker_shutting_down
from kombu import Queue

from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.celery_app")

# Celery configuration
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0")
)
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "redis://localhost:6379/0")
)

# Create Celery application
celery_app = Celery(
    "mvidarr_jobs",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "src.jobs.metadata_tasks",
        "src.jobs.image_processing_tasks",
        "src.jobs.ffmpeg_processing_tasks",
        "src.jobs.download_processor_task",
        "src.jobs.wizard_tasks",  # Wizard video indexing tasks
        "src.tasks.scheduled_tasks",  # Scheduler V2 tasks (v0.10.1)
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task routing and queues
    task_routes={
        "src.jobs.video_download_tasks.*": {"queue": "video_downloads"},
        "src.jobs.metadata_tasks.*": {"queue": "metadata"},
        "src.jobs.image_processing_tasks.*": {"queue": "image_processing"},
        "src.jobs.ffmpeg_processing_tasks.*": {"queue": "ffmpeg_processing"},
        "src.tasks.scheduled_tasks.*": {"queue": "scheduler"},  # Scheduler V2 (v0.10.1)
    },
    # Queue definitions
    task_queues=(
        Queue("video_downloads", routing_key="video_downloads"),
        Queue("metadata", routing_key="metadata"),
        Queue("image_processing", routing_key="image_processing"),
        Queue("ffmpeg_processing", routing_key="ffmpeg_processing"),
        Queue("scheduler", routing_key="scheduler"),  # Scheduler V2 queue (v0.10.1)
        Queue("default", routing_key="default"),
    ),
    task_default_queue="default",
    task_default_routing_key="default",
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "mvidarr",
        "retry_on_timeout": True,
    },
    # Worker settings
    worker_max_tasks_per_child=1000,  # Restart workers after 1000 tasks
    worker_disable_rate_limits=False,
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    # Retry settings
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Beat schedule (if using celery beat for periodic tasks)
    # NOTE: Scheduler V2 (v0.10.1) - These schedules are dynamically updated from database settings
    # See src/services/scheduler_service_v2.py for dynamic schedule management
    beat_schedule={
        "process-downloads": {
            "task": "download_processor.process_downloads",
            "schedule": timedelta(seconds=30),
        },
        # Scheduler V2 tasks (v0.10.1) - Default schedules, overridden by database settings
        "scheduled-discovery": {
            "task": "src.tasks.scheduled_tasks.scheduled_discovery_task",
            "schedule": timedelta(hours=6),  # Default: every 6 hours
            "options": {"queue": "scheduler"},
        },
        "scheduled-downloads": {
            "task": "src.tasks.scheduled_tasks.scheduled_downloads_task",
            "schedule": timedelta(hours=2),  # Default: every 2 hours
            "options": {"queue": "scheduler"},
        },
        "artist-discovery-check": {
            "task": "src.tasks.scheduled_tasks.artist_discovery_check_task",
            "schedule": timedelta(
                minutes=30
            ),  # Check every 30 minutes for artist-specific schedules
            "options": {"queue": "scheduler"},
        },
        "scheduler-health-check": {
            "task": "src.tasks.scheduled_tasks.scheduler_health_check_task",
            "schedule": timedelta(minutes=5),  # Health check every 5 minutes
            "options": {"queue": "scheduler"},
        },
        "playlist-sync": {
            "task": "src.tasks.scheduled_tasks.playlist_sync_task",
            "schedule": timedelta(hours=6),  # Sync monitored playlists every 6 hours
            "options": {"queue": "scheduler"},
        },
    },
    beat_schedule_filename=os.environ.get(
        "CELERYBEAT_SCHEDULE_FILE", "data/celerybeat-schedule"
    ),
)

# Task priority levels
TASK_PRIORITIES = {
    "HIGH": 9,
    "NORMAL": 5,
    "LOW": 1,
}


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handle worker ready event"""
    logger.info(f"Celery worker ready: {sender}")


@worker_shutting_down.connect
def worker_shutting_down_handler(sender=None, **kwargs):
    """Handle worker shutdown event"""
    logger.info(f"Celery worker shutting down: {sender}")


# Utility functions for job management
class JobManager:
    """Utility class for managing Celery jobs"""

    @staticmethod
    def get_active_jobs():
        """Get list of active jobs across all workers"""
        try:
            inspect = celery_app.control.inspect()
            active_jobs = inspect.active()
            return active_jobs or {}
        except Exception as e:
            logger.error(f"Error getting active jobs: {e}")
            return {}

    @staticmethod
    def get_job_stats():
        """Get job processing statistics"""
        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            return stats or {}
        except Exception as e:
            logger.error(f"Error getting job stats: {e}")
            return {}

    @staticmethod
    def cancel_job(task_id):
        """Cancel a running job by task ID"""
        try:
            celery_app.control.revoke(task_id, terminate=True)
            logger.info(f"Job {task_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling job {task_id}: {e}")
            return False

    @staticmethod
    def get_queue_length(queue_name="default"):
        """Get the length of a specific queue"""
        try:
            # Use Celery's inspect API to get queue length from Redis
            inspect = celery_app.control.inspect()

            # Get active, scheduled, and reserved tasks
            active = inspect.active()
            scheduled = inspect.scheduled()
            reserved = inspect.reserved()

            # Count tasks in the specified queue across all workers
            total_count = 0

            for task_dict in [active, scheduled, reserved]:
                if task_dict:
                    for worker, tasks in task_dict.items():
                        if tasks:
                            # Filter by queue name
                            queue_tasks = [
                                t
                                for t in tasks
                                if t.get("delivery_info", {}).get("routing_key")
                                == queue_name
                            ]
                            total_count += len(queue_tasks)

            return total_count
        except Exception as e:
            logger.error(f"Error getting queue length for {queue_name}: {e}")
            return 0  # Return 0 instead of -1 to avoid UI issues

    @staticmethod
    def purge_queue(queue_name="default"):
        """Purge all tasks from a queue"""
        try:
            celery_app.control.purge()
            logger.info(f"Queue {queue_name} purged")
            return True
        except Exception as e:
            logger.error(f"Error purging queue {queue_name}: {e}")
            return False


# Global job manager instance
job_manager = JobManager()


# Health check function for Celery workers
def check_celery_health():
    """Check if Celery workers are available and healthy"""
    try:
        # Check if any workers are available
        inspect = celery_app.control.inspect()
        stats = inspect.stats()

        if not stats:
            return {
                "status": "unhealthy",
                "message": "No Celery workers available",
                "workers": 0,
            }

        # Check worker health
        active_workers = len(stats)
        total_jobs = sum(
            len(worker_stats.get("total", {})) for worker_stats in stats.values()
        )

        return {
            "status": "healthy",
            "message": f"{active_workers} workers available",
            "workers": active_workers,
            "total_jobs_processed": total_jobs,
        }

    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Health check failed: {e}",
            "workers": 0,
        }


if __name__ == "__main__":
    # For testing: python -m src.jobs.celery_app
    print("Celery App Configuration:")
    print(f"Broker URL: {CELERY_BROKER_URL}")
    print(f"Result Backend: {CELERY_RESULT_BACKEND}")
    print("Task Routes:")
    for route, config in celery_app.conf.task_routes.items():
        print(f"  {route} -> {config}")

    # Test Celery connection
    try:
        health = check_celery_health()
        print(f"\nCelery Health: {health}")
    except Exception as e:
        print(f"\nCelery Health Check Failed: {e}")
