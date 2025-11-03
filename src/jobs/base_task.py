"""
Base Task Class for Celery Background Jobs
Phase 2: Media Processing Optimization - Common Task Patterns
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

from celery import Task

from src.jobs.redis_manager import redis_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.base_task")


class BaseTask(Task):
    """Base task class with common functionality for all background jobs"""

    # Task configuration
    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def __init__(self):
        super().__init__()
        self.start_time = None
        self.job_id = None

    def before_start(self, task_id, args, kwargs):
        """Called before task execution starts"""
        self.start_time = time.time()
        self.job_id = task_id

        logger.info(f"Starting task {self.name} with ID {task_id}")

        # Set initial job status
        redis_manager.set_job_status(
            task_id,
            "STARTED",
            {
                "task_name": self.name,
                "started_at": datetime.utcnow().isoformat(),
                "args": args,
                "kwargs": kwargs,
            },
        )

        # Set initial progress
        redis_manager.set_job_progress(
            task_id, {"percent": 0, "message": "Task started", "status": "STARTED"}
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        execution_time = time.time() - self.start_time if self.start_time else 0

        logger.info(f"Task {self.name} completed successfully in {execution_time:.2f}s")

        # Update job status
        redis_manager.set_job_status(
            task_id,
            "SUCCESS",
            {
                "task_name": self.name,
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time": execution_time,
                "result": retval,
            },
        )

        # Set final progress
        redis_manager.set_job_progress(
            task_id,
            {
                "percent": 100,
                "message": "Task completed successfully",
                "status": "SUCCESS",
                "execution_time": execution_time,
            },
        )

        # Store result
        redis_manager.store_job_result(task_id, retval)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        execution_time = time.time() - self.start_time if self.start_time else 0

        logger.error(f"Task {self.name} failed after {execution_time:.2f}s: {exc}")

        # Update job status
        redis_manager.set_job_status(
            task_id,
            "FAILURE",
            {
                "task_name": self.name,
                "failed_at": datetime.utcnow().isoformat(),
                "execution_time": execution_time,
                "error": str(exc),
                "traceback": einfo.traceback,
            },
        )

        # Set failure progress
        redis_manager.set_job_progress(
            task_id,
            {
                "percent": -1,  # -1 indicates failure
                "message": f"Task failed: {exc}",
                "status": "FAILURE",
                "execution_time": execution_time,
                "error": str(exc),
            },
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried"""
        execution_time = time.time() - self.start_time if self.start_time else 0

        logger.warning(
            f"Task {self.name} retry {self.request.retries + 1}/{self.max_retries}: {exc}"
        )

        # Update job status
        redis_manager.set_job_status(
            task_id,
            "RETRY",
            {
                "task_name": self.name,
                "retry_at": datetime.utcnow().isoformat(),
                "retry_count": self.request.retries + 1,
                "max_retries": self.max_retries,
                "error": str(exc),
                "execution_time": execution_time,
            },
        )

        # Set retry progress
        redis_manager.set_job_progress(
            task_id,
            {
                "percent": 0,
                "message": f"Retrying ({self.request.retries + 1}/{self.max_retries}): {exc}",
                "status": "RETRY",
                "retry_count": self.request.retries + 1,
                "max_retries": self.max_retries,
            },
        )

    async def update_progress(self, percent: int, message: str, **kwargs):
        """Update task progress (async version for background tasks)"""
        if self.job_id:
            progress_data = {
                "percent": max(0, min(100, percent)),  # Clamp between 0-100
                "message": message,
                "status": "PROGRESS",
                "updated_at": datetime.utcnow().isoformat(),
                **kwargs,
            }

            redis_manager.set_job_progress(self.job_id, progress_data)

            # Also log progress at certain intervals
            if percent % 10 == 0 or percent in [25, 50, 75, 90, 95]:
                logger.info(f"Task {self.name} progress: {percent}% - {message}")

    def update_progress_sync(self, percent: int, message: str, **kwargs):
        """Update task progress (sync version for compatibility)"""
        if self.job_id:
            progress_data = {
                "percent": max(0, min(100, percent)),  # Clamp between 0-100
                "message": message,
                "status": "PROGRESS",
                "updated_at": datetime.utcnow().isoformat(),
                **kwargs,
            }

            redis_manager.set_job_progress(self.job_id, progress_data)

            # Also log progress at certain intervals
            if percent % 10 == 0 or percent in [25, 50, 75, 90, 95]:
                logger.info(f"Task {self.name} progress: {percent}% - {message}")

    def is_cancelled(self) -> bool:
        """Check if task has been cancelled"""
        if self.job_id:
            status = redis_manager.get_job_status(self.job_id)
            return status and status.get("status") == "CANCELLED"
        return False

    def cancel_task(self, reason: str = "Task cancelled"):
        """Cancel the current task"""
        if self.job_id:
            redis_manager.set_job_status(
                self.job_id,
                "CANCELLED",
                {
                    "task_name": self.name,
                    "cancelled_at": datetime.utcnow().isoformat(),
                    "reason": reason,
                },
            )

            redis_manager.set_job_progress(
                self.job_id,
                {
                    "percent": -2,  # -2 indicates cancellation
                    "message": f"Task cancelled: {reason}",
                    "status": "CANCELLED",
                },
            )

            logger.info(f"Task {self.name} cancelled: {reason}")


class VideoProcessingTask(BaseTask):
    """Base class for video processing tasks"""

    # Video processing specific settings
    max_retries = 2  # Fewer retries for video tasks
    task_soft_time_limit = 1800  # 30 minutes
    task_time_limit = 3600  # 1 hour

    def validate_video_args(self, video_id: str, **kwargs) -> bool:
        """Validate video processing arguments"""
        if not video_id:
            raise ValueError("video_id is required for video processing tasks")

        # Check if video ID is valid format
        if not isinstance(video_id, str) or len(video_id) < 5:
            raise ValueError(f"Invalid video_id format: {video_id}")

        return True

    def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video information from database"""
        try:
            # This would typically query the database
            # For now, return a placeholder
            return {
                "id": video_id,
                "title": f"Video {video_id}",
                "duration": 0,
                "status": "active",
            }
        except Exception as e:
            logger.error(f"Error getting video info for {video_id}: {e}")
            return None


class MetadataProcessingTask(BaseTask):
    """Base class for metadata processing tasks"""

    # Metadata processing specific settings
    max_retries = 3
    task_soft_time_limit = 300  # 5 minutes
    task_time_limit = 600  # 10 minutes

    def validate_metadata_args(self, **kwargs) -> bool:
        """Validate metadata processing arguments"""
        return True

    def process_metadata_batch(self, items: list, process_func, batch_size: int = 10):
        """Process metadata in batches with progress updates"""
        total_items = len(items)
        processed = 0

        for i in range(0, total_items, batch_size):
            batch = items[i : i + batch_size]

            # Check for cancellation
            if self.is_cancelled():
                logger.info(f"Task {self.name} cancelled during batch processing")
                break

            # Process batch
            try:
                for item in batch:
                    process_func(item)
                    processed += 1

                    # Update progress
                    percent = int((processed / total_items) * 100)
                    self.update_progress(
                        percent,
                        f"Processed {processed}/{total_items} items",
                        processed=processed,
                        total=total_items,
                    )

            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                raise

        return processed


class ImageProcessingTask(BaseTask):
    """Base class for image processing tasks"""

    # Image processing specific settings
    max_retries = 2
    task_soft_time_limit = 600  # 10 minutes
    task_time_limit = 1200  # 20 minutes

    def validate_image_args(self, **kwargs) -> bool:
        """Validate image processing arguments"""
        return True

    def process_image_safely(self, image_path: str, process_func):
        """Process image with error handling and resource cleanup"""
        try:
            return process_func(image_path)
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            raise
        finally:
            # Clean up any temporary resources
            pass


# Utility functions for task management
def get_task_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Get progress for a specific task"""
    return redis_manager.get_job_progress(task_id)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get status for a specific task"""
    return redis_manager.get_job_status(task_id)


def get_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    """Get result for a completed task"""
    return redis_manager.get_job_result(task_id)


def cancel_task(task_id: str, reason: str = "Task cancelled") -> bool:
    """Cancel a running task"""
    return redis_manager.set_job_status(
        task_id,
        "CANCELLED",
        {"cancelled_at": datetime.utcnow().isoformat(), "reason": reason},
    )


if __name__ == "__main__":
    # For testing: python -m src.jobs.base_task
    print("Base Task Classes Test")
    print("=" * 50)

    # Test task ID generation
    import uuid

    test_task_id = str(uuid.uuid4())

    # Create base task instance
    base_task = BaseTask()
    base_task.job_id = test_task_id

    # Test progress updates
    print("Testing progress updates...")
    base_task.update_progress(25, "Processing data...")
    progress = get_task_progress(test_task_id)
    print(f"Progress: {progress}")

    # Test status updates
    print("\nTesting status updates...")
    redis_manager.set_job_status(test_task_id, "RUNNING", {"step": "data_processing"})
    status = get_task_status(test_task_id)
    print(f"Status: {status}")

    print("\n✅ Base Task test completed successfully!")
