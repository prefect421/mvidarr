"""
Celery Tasks for Installation Wizard Operations
Handles background processing during first-run setup.
Issue #163: Installation Wizard Implementation
"""

import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from celery import Task

from src.database.connection import get_db, init_db_standalone
from src.jobs.celery_app import celery_app
from src.services.video_indexing_service import video_indexing_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.wizard_tasks")


class WizardCallbackTask(Task):
    """Base task for wizard operations with progress callbacks"""

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """Update task progress with WebSocket broadcasting via Redis"""
        try:
            progress_data = {
                "progress": progress,
                "percent": progress,  # Alias for frontend compatibility
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "PROGRESS" if progress < 100 else "SUCCESS",
            }

            # Update task metadata
            self.update_state(
                task_id=task_id,
                state="PROGRESS" if progress < 100 else "SUCCESS",
                meta=progress_data,
            )

            # Publish to Redis for WebSocket broadcasting
            try:
                import json
                import time

                from src.jobs.redis_manager import redis_manager

                # Ensure Redis connection is established
                if not redis_manager.ensure_connection():
                    logger.warning(
                        f"Redis connection failed, skipping progress broadcast for task {task_id}"
                    )
                    return

                if redis_manager.redis_client:
                    # Store job progress for status queries
                    progress_key = f"job_progress:{task_id}"
                    redis_manager.redis_client.setex(
                        progress_key, 3600, json.dumps(progress_data)  # 1 hour TTL
                    )

                    # Publish progress update for WebSocket broadcasting
                    channel = f"progress:{task_id}"
                    published_count = redis_manager.redis_client.publish(
                        channel, json.dumps(progress_data)
                    )

                    logger.debug(
                        f"📡 Progress published to Redis channel '{channel}': {progress}% - {message}"
                    )

                    # Small delay for final progress updates to ensure transmission
                    if progress >= 95:
                        time.sleep(0.1)

            except Exception as redis_error:
                logger.error(f"Redis publish failed for task {task_id}: {redis_error}")

            # Log progress for monitoring
            logger.info(f"📊 Task {task_id} progress: {progress}% - {message}")

        except Exception as e:
            logger.error(f"Progress update failed for task {task_id}: {e}")


@celery_app.task(
    bind=True,
    base=WizardCallbackTask,
    name="wizard.index_videos",
    time_limit=3600,  # 1 hour timeout for large libraries
    soft_time_limit=3300,  # 55 minute soft limit
)
def index_videos_task(
    self, fetch_metadata: bool = True, max_files: Optional[int] = None
) -> Dict[str, Any]:
    """
    Celery task for wizard video indexing with progress tracking

    Args:
        fetch_metadata: Whether to fetch IMVDb metadata for each video
        max_files: Optional limit on number of files to process

    Returns:
        Dictionary with indexing results
    """
    task_id = self.request.id
    logger.info(
        f"Starting wizard video indexing task {task_id} (fetch_metadata={fetch_metadata}, max_files={max_files})"
    )

    try:
        # Initialize database for Celery worker context
        logger.info("Initializing database for wizard video indexing...")
        init_db_standalone()

        # Initial progress update
        self.update_progress(task_id, 5, "Starting video indexing process...")

        # Scan for video files
        self.update_progress(task_id, 10, "Scanning directory for video files...")
        video_files = video_indexing_service.scan_video_files()

        if not video_files:
            logger.warning("No video files found in music videos directory")
            self.update_progress(task_id, 100, "No video files found")
            return {
                "success": True,
                "total_files": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "already_indexed": 0,
                "message": "No video files found in directory",
            }

        # Apply max_files limit if specified
        if max_files:
            video_files = video_files[:max_files]
            logger.info(f"Limited processing to {max_files} files")

        total_files = len(video_files)
        logger.info(f"Found {total_files} video files to index")

        self.update_progress(
            task_id, 15, f"Found {total_files} video files. Starting indexing..."
        )

        # Process files with progress updates
        results = []
        successful = 0
        failed = 0
        already_indexed = 0

        for i, file_path in enumerate(video_files, 1):
            try:
                # Calculate progress (15% -> 95%, saving 5% for completion)
                progress = 15 + int((i / total_files) * 80)
                self.update_progress(
                    task_id,
                    progress,
                    f"Processing file {i}/{total_files}: {file_path.name}",
                )

                # Index the video file
                result = video_indexing_service.index_single_file(
                    file_path, fetch_metadata
                )
                results.append(result)

                if result["success"]:
                    if result["already_indexed"]:
                        already_indexed += 1
                    else:
                        successful += 1
                else:
                    failed += 1
                    logger.warning(
                        f"Failed to index {file_path.name}: {result.get('error')}"
                    )

                # Log progress milestones
                if i % 10 == 0:
                    logger.info(
                        f"Progress: {i}/{total_files} files processed ({successful} successful, {failed} failed, {already_indexed} already indexed)"
                    )

            except Exception as e:
                failed += 1
                logger.error(f"Error indexing file {file_path}: {e}")
                results.append(
                    {
                        "file_path": str(file_path),
                        "success": False,
                        "error": str(e),
                    }
                )

        # Final progress update
        self.update_progress(
            task_id,
            100,
            f"Indexing complete: {successful} successful, {failed} failed, {already_indexed} already indexed",
        )

        # Return summary
        summary = {
            "success": True,
            "total_files": total_files,
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "already_indexed": already_indexed,
            "fetch_metadata": fetch_metadata,
            "message": f"Video indexing completed: {successful}/{total_files} files indexed successfully",
        }

        logger.info(
            f"Wizard video indexing task {task_id} completed: {successful}/{total_files} successful"
        )

        return summary

    except Exception as e:
        error_msg = f"Video indexing task failed: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        # Update task state to FAILURE
        self.update_state(
            task_id=task_id,
            state="FAILURE",
            meta={
                "error": error_msg,
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Re-raise to mark task as failed in Celery
        raise


@celery_app.task(
    bind=True,
    base=WizardCallbackTask,
    name="wizard.validate_directory",
    time_limit=60,  # 1 minute timeout
)
def validate_directory_task(self, directory_path: str) -> Dict[str, Any]:
    """
    Celery task for validating video directory and counting files

    Args:
        directory_path: Path to directory to validate

    Returns:
        Dictionary with validation results
    """
    task_id = self.request.id
    logger.info(f"Starting directory validation task {task_id}: {directory_path}")

    try:
        self.update_progress(task_id, 10, "Validating directory...")

        directory = Path(directory_path)

        # Check if directory exists
        if not directory.exists():
            return {
                "success": False,
                "error": "Directory does not exist",
                "directory": directory_path,
                "video_count": 0,
            }

        # Check if it's a directory
        if not directory.is_dir():
            return {
                "success": False,
                "error": "Path is not a directory",
                "directory": directory_path,
                "video_count": 0,
            }

        self.update_progress(task_id, 50, "Scanning for video files...")

        # Count video files
        video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        video_count = sum(
            1
            for file_path in directory.rglob("*")
            if file_path.is_file() and file_path.suffix.lower() in video_extensions
        )

        self.update_progress(task_id, 100, f"Found {video_count} video files")

        return {
            "success": True,
            "directory": directory_path,
            "video_count": video_count,
            "message": f"Found {video_count} video files in directory",
        }

    except Exception as e:
        error_msg = f"Directory validation failed: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        return {
            "success": False,
            "error": error_msg,
            "directory": directory_path,
            "video_count": 0,
        }
