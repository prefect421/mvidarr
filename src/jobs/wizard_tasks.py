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

    def update_progress(
        self,
        task_id: str,
        progress: int,
        message: str = "",
        extra_data: Optional[Dict[str, Any]] = None,
    ):
        """Update task progress with WebSocket broadcasting via Redis"""
        try:
            progress_data = {
                "progress": progress,
                "percent": progress,  # Alias for frontend compatibility
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "PROGRESS" if progress < 100 else "SUCCESS",
            }

            # Include any extra data (e.g., error details, file counts)
            if extra_data:
                progress_data.update(extra_data)

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
    self,
    directory: Optional[str] = None,
    fetch_metadata: bool = True,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Celery task for wizard video indexing with progress tracking

    Args:
        directory: Directory to scan for videos (uses default if not specified)
        fetch_metadata: Whether to fetch IMVDb metadata for each video
        max_files: Optional limit on number of files to process

    Returns:
        Dictionary with indexing results
    """
    task_id = self.request.id
    logger.info(
        f"Starting wizard video indexing task {task_id} (directory={directory}, fetch_metadata={fetch_metadata}, max_files={max_files})"
    )

    try:
        # Initialize database for Celery worker context
        logger.info("Initializing database for wizard video indexing...")
        init_db_standalone()

        # Initial progress update
        self.update_progress(task_id, 5, "Starting video indexing process...")

        # Prepare directory parameter
        scan_directory = Path(directory) if directory else None
        if scan_directory:
            logger.info(f"Using wizard-configured directory: {scan_directory}")

        # Scan for video files
        self.update_progress(task_id, 10, "Scanning directory for video files...")
        video_files = video_indexing_service.scan_video_files(directory=scan_directory)

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
        error_details = []  # Track detailed error information for frontend

        for i, file_path in enumerate(video_files, 1):
            try:
                # Calculate progress (15% -> 95%, saving 5% for completion)
                progress = 15 + int((i / total_files) * 80)

                # Update progress with detailed stats
                self.update_progress(
                    task_id,
                    progress,
                    f"Processing file {i}/{total_files}: {file_path.name}",
                    extra_data={
                        "videos_processed": i - 1,  # Previous count
                        "videos_success": successful,
                        "videos_failed": failed,
                        "videos_skipped": already_indexed,  # Duplicates skipped
                        "current_file": file_path.name,
                        "errors": (
                            error_details[-5:] if error_details else []
                        ),  # Last 5 errors
                    },
                )

                # Index the video file (skip auto-processing to avoid session conflicts)
                result = video_indexing_service.index_single_file(
                    file_path, fetch_metadata, skip_auto_processing=True
                )
                results.append(result)

                if result["success"]:
                    if result["already_indexed"]:
                        already_indexed += 1
                    else:
                        successful += 1
                else:
                    failed += 1
                    error_msg = result.get("error", "Unknown error")
                    logger.warning(f"Failed to index {file_path.name}: {error_msg}")

                    # Track error details for frontend
                    error_details.append(
                        {"file": file_path.name, "error": error_msg, "timestamp": i}
                    )

                # Log progress milestones
                if i % 10 == 0:
                    logger.info(
                        f"Progress: {i}/{total_files} files processed ({successful} successful, {failed} failed, {already_indexed} already indexed)"
                    )

            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"Error indexing file {file_path}: {error_msg}")

                # Track error details for frontend
                error_details.append(
                    {"file": file_path.name, "error": error_msg, "timestamp": i}
                )

                results.append(
                    {
                        "file_path": str(file_path),
                        "success": False,
                        "error": error_msg,
                    }
                )

        # Final progress update with complete stats
        self.update_progress(
            task_id,
            100,
            f"Indexing complete: {successful} successful, {failed} failed, {already_indexed} already indexed",
            extra_data={
                "videos_processed": total_files,
                "videos_success": successful,
                "videos_failed": failed,
                "videos_skipped": already_indexed,  # Duplicates skipped
                "current_file": "",
                "errors": (
                    error_details[-10:] if error_details else []
                ),  # Last 10 errors for final display
            },
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
    name="wizard.process_artists_batch",
    time_limit=7200,  # 2 hour timeout for large libraries
    soft_time_limit=6900,  # 115 minute soft limit
)
def process_artists_batch_task(
    self,
    artist_ids: Optional[list[int]] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Celery task for batch artist auto-processing after wizard import

    This runs AFTER video indexing to avoid session conflicts.
    Processes artists for auto-matching and metadata enrichment.

    Args:
        artist_ids: Optional list of specific artist IDs to process (None = all unprocessed)
        force_refresh: Force reprocessing even if already processed

    Returns:
        Dictionary with processing results
    """
    task_id = self.request.id
    logger.info(
        f"Starting batch artist processing task {task_id} (artist_ids={artist_ids}, force_refresh={force_refresh})"
    )

    try:
        # Initialize database for Celery worker context
        logger.info("Initializing database for batch artist processing...")
        init_db_standalone()

        # Initial progress update
        self.update_progress(task_id, 5, "Starting batch artist processing...")

        from src.database.models import Artist
        from src.services.artist_auto_processing_service import (
            artist_auto_processing_service,
        )

        with get_db() as session:
            # Determine which artists to process
            if artist_ids:
                # Process specific artists
                artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
                logger.info(f"Processing {len(artists)} specified artists")
            else:
                # Process all artists without external IDs (newly created)
                artists = (
                    session.query(Artist)
                    .filter(
                        (Artist.imvdb_id.is_(None))
                        | (Artist.spotify_id.is_(None))
                        | (Artist.lastfm_name.is_(None))
                    )
                    .all()
                )
                logger.info(f"Found {len(artists)} unprocessed artists")

            if not artists:
                logger.info("No artists to process")
                self.update_progress(task_id, 100, "No artists to process")
                return {
                    "success": True,
                    "total_artists": 0,
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "message": "No artists to process",
                }

            total_artists = len(artists)
            self.update_progress(
                task_id, 10, f"Found {total_artists} artists to process..."
            )

            # Process each artist
            results = []
            successful = 0
            failed = 0

            for i, artist in enumerate(artists, 1):
                # Capture artist info before try block to avoid DetachedInstanceError
                artist_id = artist.id
                artist_name = artist.name

                try:
                    # Calculate progress (10% -> 95%, saving 5% for completion)
                    progress = 10 + int((i / total_artists) * 85)
                    self.update_progress(
                        task_id,
                        progress,
                        f"Processing artist {i}/{total_artists}: {artist_name}",
                    )

                    # Process the artist with auto-matching and metadata enrichment
                    result = artist_auto_processing_service.process_new_artist(
                        artist, session
                    )

                    # Commit after each artist to persist changes
                    session.commit()

                    # Track success/failure
                    if result.get("errors"):
                        failed += 1
                        logger.warning(
                            f"Artist processing had errors for {artist_name}: {result['errors']}"
                        )
                    else:
                        successful += 1

                    match_count = result.get("auto_match", {}).get("match_count", 0)
                    logger.info(
                        f"Processed {artist_name} - {match_count} services matched"
                    )

                    results.append(
                        {
                            "artist_id": artist_id,
                            "artist_name": artist_name,
                            "success": not result.get("errors"),
                            "match_count": match_count,
                            "errors": result.get("errors", []),
                        }
                    )

                    # Log progress milestones
                    if i % 10 == 0:
                        logger.info(
                            f"Progress: {i}/{total_artists} artists processed ({successful} successful, {failed} failed)"
                        )

                except Exception as e:
                    failed += 1
                    logger.error(f"Error processing artist {artist_name}: {e}")
                    results.append(
                        {
                            "artist_id": artist_id,
                            "artist_name": artist_name,
                            "success": False,
                            "error": str(e),
                        }
                    )

            # Final progress update
            self.update_progress(
                task_id,
                100,
                f"Batch processing complete: {successful} successful, {failed} failed",
            )

            # Return summary
            summary = {
                "success": True,
                "total_artists": total_artists,
                "processed": len(results),
                "successful": successful,
                "failed": failed,
                "message": f"Batch artist processing completed: {successful}/{total_artists} artists processed successfully",
                "results": results,
            }

            logger.info(
                f"Batch artist processing task {task_id} completed: {successful}/{total_artists} successful"
            )

            return summary

    except Exception as e:
        error_msg = f"Batch artist processing task failed: {str(e)}"
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


@celery_app.task(
    bind=True,
    base=WizardCallbackTask,
    name="wizard.import_from_custom_directory",
    time_limit=7200,  # 2 hour timeout for large imports
    soft_time_limit=6900,  # 115 minute soft limit
)
def import_from_custom_directory_task(
    self,
    source_directory: str,
    fetch_metadata: bool = True,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Celery task for importing videos from a custom directory

    This task:
    1. Scans source directory for video files
    2. Copies files to music_videos_path (organizing by artist/title)
    3. Indexes the copied files
    4. Provides progress tracking

    Args:
        source_directory: Custom directory to import videos from
        fetch_metadata: Whether to fetch IMVDb metadata for each video
        max_files: Optional limit on number of files to process

    Returns:
        Dictionary with import results
    """
    import os
    import shutil
    from pathlib import Path

    task_id = self.request.id
    logger.info(
        f"Starting custom directory import task {task_id} (source={source_directory}, "
        f"fetch_metadata={fetch_metadata}, max_files={max_files})"
    )

    try:
        # Initialize database for Celery worker context
        logger.info("Initializing database for custom directory import...")
        init_db_standalone()

        # Initial progress update
        self.update_progress(task_id, 5, "Starting custom directory import...")

        # Get music videos path from settings
        from src.services.settings_service import settings

        music_videos_path = Path(settings.get("music_videos_path", "data/musicvideos"))

        # Validate source directory
        source_dir = Path(source_directory)
        if not source_dir.exists() or not source_dir.is_dir():
            raise ValueError(f"Source directory does not exist: {source_directory}")

        logger.info(f"Source directory: {source_dir}")
        logger.info(f"Destination directory: {music_videos_path}")

        # Scan source directory for video files
        self.update_progress(
            task_id, 10, "Scanning source directory for video files..."
        )

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
        video_files = [
            file_path
            for file_path in source_dir.rglob("*")
            if file_path.is_file() and file_path.suffix.lower() in video_extensions
        ]

        if not video_files:
            logger.warning(f"No video files found in {source_directory}")
            self.update_progress(
                task_id, 100, "No video files found in source directory"
            )
            return {
                "success": True,
                "total_files": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "copied": 0,
                "already_indexed": 0,
                "message": "No video files found in source directory",
            }

        # Apply max_files limit if specified
        if max_files:
            video_files = video_files[:max_files]
            logger.info(f"Limited processing to {max_files} files")

        total_files = len(video_files)
        logger.info(f"Found {total_files} video files to import")

        self.update_progress(
            task_id, 15, f"Found {total_files} video files. Starting import..."
        )

        # Process files with progress updates
        results = []
        successful = 0
        failed = 0
        copied = 0
        already_indexed = 0
        error_details = []

        for i, source_file in enumerate(video_files, 1):
            try:
                # Calculate progress (15% -> 95%, saving 5% for completion)
                progress = 15 + int((i / total_files) * 80)

                # Update progress with detailed stats
                self.update_progress(
                    task_id,
                    progress,
                    f"Processing file {i}/{total_files}: {source_file.name}",
                    extra_data={
                        "videos_processed": i - 1,
                        "videos_success": successful,
                        "videos_failed": failed,
                        "videos_copied": copied,
                        "videos_skipped": already_indexed,
                        "current_file": source_file.name,
                        "errors": error_details[-5:] if error_details else [],
                    },
                )

                # Parse filename to extract artist and title
                # Expected format: "Artist - Title.ext" or "Artist-Title.ext"
                filename_no_ext = source_file.stem

                # Try to parse artist and title from filename
                if " - " in filename_no_ext:
                    parts = filename_no_ext.split(" - ", 1)
                    artist_name = parts[0].strip()
                    title = parts[1].strip()
                elif "-" in filename_no_ext:
                    parts = filename_no_ext.split("-", 1)
                    artist_name = parts[0].strip()
                    title = parts[1].strip()
                else:
                    # No artist separator found, use "Unknown Artist"
                    artist_name = "Unknown Artist"
                    title = filename_no_ext.strip()

                # Create artist directory in destination
                artist_dir = music_videos_path / artist_name
                artist_dir.mkdir(parents=True, exist_ok=True)

                # Destination file path
                dest_file = artist_dir / source_file.name

                # Check if file already exists
                if dest_file.exists():
                    logger.info(f"File already exists, skipping copy: {dest_file}")
                    # Still try to index it in case it's not in the database
                    result = video_indexing_service.index_single_file(
                        dest_file, fetch_metadata, skip_auto_processing=True
                    )

                    if result.get("already_indexed"):
                        already_indexed += 1
                    else:
                        successful += 1

                    results.append(result)
                    continue

                # Copy file to destination
                logger.info(f"Copying {source_file} -> {dest_file}")
                shutil.copy2(source_file, dest_file)
                copied += 1

                # Index the copied file
                result = video_indexing_service.index_single_file(
                    dest_file, fetch_metadata, skip_auto_processing=True
                )
                results.append(result)

                if result["success"]:
                    if result["already_indexed"]:
                        already_indexed += 1
                    else:
                        successful += 1
                else:
                    failed += 1
                    error_msg = result.get("error", "Unknown error")
                    logger.warning(f"Failed to index {source_file.name}: {error_msg}")

                    # Track error details for frontend
                    error_details.append(
                        {"file": source_file.name, "error": error_msg, "timestamp": i}
                    )

                # Log progress milestones
                if i % 10 == 0:
                    logger.info(
                        f"Progress: {i}/{total_files} files processed "
                        f"({copied} copied, {successful} successful, {failed} failed, "
                        f"{already_indexed} already indexed)"
                    )

            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(
                    f"Error importing file {source_file}: {error_msg}\n{traceback.format_exc()}"
                )

                # Track error details for frontend
                error_details.append(
                    {"file": source_file.name, "error": error_msg, "timestamp": i}
                )

                results.append(
                    {
                        "file_path": str(source_file),
                        "success": False,
                        "error": error_msg,
                    }
                )

        # Final progress update with complete stats
        self.update_progress(
            task_id,
            100,
            f"Import complete: {copied} copied, {successful} indexed, "
            f"{failed} failed, {already_indexed} already indexed",
            extra_data={
                "videos_processed": total_files,
                "videos_success": successful,
                "videos_failed": failed,
                "videos_copied": copied,
                "videos_skipped": already_indexed,
                "current_file": "",
                "errors": error_details[-10:] if error_details else [],
            },
        )

        # Return summary
        summary = {
            "success": True,
            "total_files": total_files,
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "copied": copied,
            "already_indexed": already_indexed,
            "fetch_metadata": fetch_metadata,
            "message": (
                f"Custom directory import completed: {copied} files copied, "
                f"{successful}/{total_files} files indexed successfully"
            ),
        }

        logger.info(
            f"Custom directory import task {task_id} completed: "
            f"{copied} copied, {successful}/{total_files} indexed successfully"
        )

        # Clean up temporary upload directory if this was an upload import
        if "mvidarr_upload_" in source_directory:
            try:
                logger.info(
                    f"Cleaning up temporary upload directory: {source_directory}"
                )
                import shutil

                shutil.rmtree(source_directory, ignore_errors=True)
                logger.info("✅ Temporary upload directory cleaned up")
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to clean up temp directory {source_directory}: {cleanup_error}"
                )
                # Don't fail the task if cleanup fails

        return summary

    except Exception as e:
        error_msg = f"Custom directory import task failed: {str(e)}"
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
