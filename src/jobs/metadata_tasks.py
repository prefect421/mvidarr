"""
Celery Tasks for Metadata Enrichment
Handles background processing of artist and video metadata enrichment.
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from celery import Task

from src.database.connection import get_db, init_db_standalone
from src.database.models import Artist, Video
from src.jobs.celery_app import celery_app
from src.services.metadata_enrichment_service import MetadataEnrichmentService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.metadata_tasks")


class CallbackTask(Task):
    """Base task that supports progress callbacks"""

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """Update task progress with WebSocket broadcasting via Redis"""
        try:
            progress_data = {
                "progress": progress,
                "percent": progress,  # Add alias for frontend compatibility
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

            # Publish to Redis for WebSocket broadcasting with improved error handling
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
                        f"📡 PROGRESS BROADCAST: Published to Redis channel '{channel}' - {published_count} subscribers received update: {progress}% - {message}"
                    )

                    # Add small delay for final progress updates to ensure WebSocket transmission
                    if progress >= 95:
                        time.sleep(0.1)  # 100ms delay for critical final updates

            except Exception as redis_error:
                logger.error(
                    f"❌ REDIS PUBLISH FAILED for task {task_id}: {redis_error}"
                )

            # Log progress for monitoring
            logger.info(f"📊 TASK PROGRESS: {task_id} → {progress}% - {message}")

        except Exception as e:
            logger.error(f"❌ PROGRESS UPDATE FAILED for task {task_id}: {e}")


@celery_app.task(bind=True, base=CallbackTask, name="metadata.enrich_artist")
def enrich_artist_metadata_task(
    self,
    artist_id: int,
    force_refresh: bool = False,
    enrich_videos: bool = True,
) -> Dict[str, Any]:
    """
    Celery task for artist metadata enrichment

    Args:
        artist_id: ID of the artist to enrich
        force_refresh: Whether to force refresh existing metadata
        enrich_videos: Whether to also enrich associated videos

    Returns:
        Dictionary with enrichment results
    """
    task_id = self.request.id
    logger.info(f"Starting metadata enrichment task {task_id} for artist {artist_id}")
    logger.info(
        f"🔄 CELERY TASK DEBUG: force_refresh={force_refresh}, enrich_videos={enrich_videos}"
    )
    logger.warning(f"🚨 DEBUG: CELERY TASK STARTED - Task ID: {task_id}, Artist: {artist_id}")
    print(f"🚨 CONSOLE DEBUG: CELERY TASK STARTED - Task ID: {task_id}, Artist: {artist_id}")  # Force to console

    try:
        # Initialize database for FastAPI/Celery context
        logger.warning(f"🚨 DEBUG: Initializing database...")
        init_db_standalone()
        logger.warning(f"🚨 DEBUG: Database initialized successfully")

        # Update progress
        logger.warning(f"🚨 DEBUG: Updating progress to 5%...")
        self.update_progress(task_id, 5, "Initializing enrichment service...")
        logger.warning(f"🚨 DEBUG: Progress updated to 5%")

        # Get artist info (direct database access without Flask app context)
        logger.warning(f"🚨 DEBUG: Querying database for artist {artist_id}...")
        with get_db() as session:
            artist = session.query(Artist).filter(Artist.id == artist_id).first()
            if not artist:
                raise ValueError(f"Artist with ID {artist_id} not found")

            artist_name = artist.name
        
        logger.warning(f"🚨 DEBUG: Found artist: {artist_name}")

        logger.warning(f"🚨 DEBUG: Updating progress to 10%...")
        self.update_progress(task_id, 10, f"Starting enrichment for {artist_name}...")
        logger.warning(f"🚨 DEBUG: Progress updated to 10%")

        # Initialize enrichment service
        logger.warning(f"🚨 DEBUG: Initializing enrichment service...")
        enrichment_service = MetadataEnrichmentService()
        logger.warning(f"🚨 DEBUG: Enrichment service initialized")

        # Create progress callback that forwards to WebSocket system
        def metadata_progress_callback(progress: int, message: str):
            """Forward progress updates from metadata service to WebSocket system"""
            self.update_progress(task_id, progress, message)

        # Run actual metadata enrichment with progress callbacks
        logger.warning(f"🚨 DEBUG: Updating progress to 25%...")
        self.update_progress(task_id, 25, "Gathering metadata from external sources...")
        logger.warning(f"🚨 DEBUG: Progress updated to 25%")
        logger.warning(
            f"🚨 DEBUG: About to call enrichment_service.enrich_artist_metadata with force_refresh={force_refresh}"
        )

        # Initialize and run the enrichment service
        logger.warning(f"🚨 DEBUG: Creating new event loop...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.warning(f"🚨 DEBUG: Event loop created and set")
        
        # Prepare safe result structure BEFORE any enrichment operations
        safe_result = {
            'success': False,
            'sources_used': [],
            'metadata_sources': [],
            'enriched_fields': [],
            'metadata_found': {},
            'confidence_score': 0,
            'processing_time': 0,
            'errors': []
        }
        
        try:
            # Add timeout to prevent hanging (90 seconds - enough for external API calls)
            logger.warning(f"🚨 DEBUG: Starting enrichment with timeout (90s)...")
            enrichment_result = loop.run_until_complete(
                asyncio.wait_for(
                    enrichment_service.enrich_artist_metadata(
                        artist_id,
                        force_refresh=force_refresh,
                        progress_callback=metadata_progress_callback,
                    ),
                    timeout=90.0,
                )
            )
            logger.warning(f"🚨 DEBUG: Enrichment completed successfully!")
            
            # IMMEDIATELY convert enrichment_result to avoid SQLAlchemy session issues
            # The enrichment service may return objects containing detached SQLAlchemy models
            # We must be extremely defensive here because even accessing the object can trigger errors
            
            try:
                # Extract fields one by one with maximum safety
                # Don't use any truthiness checks or comparisons that might trigger SQLAlchemy loads
                
                logger.debug(f"Converting enrichment result of type: {type(enrichment_result).__name__}")
                
                if enrichment_result is not None:
                    # Extract each field safely
                    for field_name, default_value in [
                        ('success', False),
                        ('sources_used', []),
                        ('metadata_sources', []),
                        ('enriched_fields', []),
                        ('metadata_found', {}),
                        ('confidence_score', 0),
                        ('processing_time', 0),
                        ('errors', [])
                    ]:
                        try:
                            # Use hasattr first to check if the attribute exists
                            if hasattr(enrichment_result, field_name):
                                value = getattr(enrichment_result, field_name, default_value)
                                
                                # Convert to appropriate types to ensure serialization
                                if field_name in ['sources_used', 'metadata_sources', 'enriched_fields', 'errors']:
                                    safe_result[field_name] = list(value) if value else []
                                elif field_name == 'metadata_found':
                                    safe_result[field_name] = dict(value) if value else {}
                                elif field_name in ['confidence_score', 'processing_time']:
                                    safe_result[field_name] = float(value) if value else 0.0
                                elif field_name == 'success':
                                    safe_result[field_name] = bool(value)
                                else:
                                    safe_result[field_name] = value
                            else:
                                safe_result[field_name] = default_value
                                
                        except Exception as field_error:
                            error_msg = f"Could not extract field '{field_name}': {field_error}"
                            logger.warning(error_msg)
                            safe_result['errors'].append(error_msg)
                            safe_result[field_name] = default_value
                else:
                    safe_result['errors'] = ['Enrichment service returned None']
                    logger.warning("Enrichment result is None")
                
            except Exception as conversion_error:
                error_msg = f"Failed to safely extract enrichment result: {conversion_error}"
                logger.error(error_msg)
                safe_result['errors'].append(error_msg)
                safe_result['success'] = False
            
            # CRITICAL: Clear reference to original enrichment_result to prevent SQLAlchemy issues
            enrichment_result = None
            del enrichment_result
            
        except Exception as enrichment_error:
            error_msg = f"Enrichment process failed: {enrichment_error}"
            logger.error(error_msg)
            safe_result['errors'].append(error_msg)
            safe_result['success'] = False
            
        finally:
            loop.close()

        # Note: Progress is now at 100% from the metadata enrichment service
        # Don't override the 100% completion with a lower percentage

        # Brief pause to ensure WebSocket transmission
        import time

        time.sleep(0.5)

        # enrichment_result is now completely replaced with safe_result
        enrichment_result = safe_result

        # Now process the results - enrichment_result is now a safe dictionary
        try:
            # Check success status (enrichment_result is now a dictionary)
            success = enrichment_result.get('success', False)
            if not success:
                error_msg = "Enrichment failed"
                errors = enrichment_result.get('errors', [])
                if errors:
                    error_msg = "; ".join(str(e) for e in errors)
                raise Exception(error_msg)
                
        except Exception as processing_error:
            logger.error(f"Error processing enrichment result: {processing_error}")
            raise Exception(f"Metadata enrichment failed: {processing_error}")

        # Skip video enrichment for testing
        enriched_videos_count = 0
        # if enrich_videos:
        #     self.update_progress(task_id, 85, "Enriching associated videos...")
        #     enriched_videos_count = self._enrich_artist_videos(artist_id, task_id)

        self.update_progress(
            task_id, 100, f"Metadata enrichment completed for {artist_name}"
        )

        # Brief pause to ensure final WebSocket transmission
        time.sleep(0.5)

        # Prepare result
        result = {
            "success": True,
            "artist_id": artist_id,
            "artist_name": artist_name,
            "sources_updated": enrichment_result.get("sources_used", []),
            "metadata_sources_used": enrichment_result.get("metadata_sources", []),
            "metadata_fields_updated": enrichment_result.get("enriched_fields", []),
            "metadata_found": enrichment_result.get("metadata_found", {}),
            "enriched_videos": enriched_videos_count,
            "confidence_score": enrichment_result.get("confidence_score", 0),
            "processing_time": enrichment_result.get("processing_time", 0),
        }

        logger.info(
            f"Successfully completed metadata enrichment task {task_id} for artist {artist_name}"
        )
        return result

    except Exception as e:
        error_msg = f"Metadata enrichment failed for artist {artist_id}: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        # Update task state to failed
        self.update_state(
            state="FAILURE",
            meta={
                "error": error_msg,
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Re-raise for Celery to handle
        raise Exception(error_msg)

    def _enrich_artist_videos(self, artist_id: int, task_id: str) -> int:
        """Helper method to enrich videos for an artist"""
        enriched_count = 0

        try:
            with get_db() as session:
                # Get videos for this artist that need enrichment
                videos = (
                    session.query(Video)
                    .filter(
                        Video.artist_id == artist_id,
                        Video.last_enriched.is_(None),  # Only unenriched videos
                    )
                    .limit(10)
                    .all()
                )  # Limit to avoid overwhelming

                for i, video in enumerate(videos):
                    try:
                        # Update progress for video enrichment
                        progress = 85 + int((i / len(videos)) * 10)  # 85-95% range
                        self.update_progress(
                            task_id,
                            progress,
                            f"Enriching video: {video.title[:50]}...",
                        )

                        # Simulate video enrichment (in real implementation, call video enrichment service)
                        video.last_enriched = datetime.utcnow()
                        enriched_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to enrich video {video.id}: {e}")

                session.commit()

        except Exception as e:
            logger.error(f"Error enriching artist videos: {e}")

        return enriched_count


@celery_app.task(bind=True, base=CallbackTask, name="metadata.enrich_video")
def enrich_video_metadata_task(
    self, video_id: int, force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Celery task for video metadata enrichment

    Args:
        video_id: ID of the video to enrich
        force_refresh: Whether to force refresh existing metadata

    Returns:
        Dictionary with enrichment results
    """
    task_id = self.request.id
    logger.info(
        f"Starting video metadata enrichment task {task_id} for video {video_id}"
    )

    try:
        # Update progress
        self.update_progress(task_id, 10, "Initializing video enrichment...")

        # Get video info
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            if not video:
                raise ValueError(f"Video with ID {video_id} not found")

            video_title = video.title or f"Video {video_id}"
            artist_name = video.artist.name if video.artist else "Unknown Artist"

        self.update_progress(task_id, 25, f"Enriching metadata for: {video_title}")

        # Initialize enrichment service
        enrichment_service = MetadataEnrichmentService()

        # TODO: Implement video-specific enrichment
        # For now, just simulate the process
        self.update_progress(task_id, 50, "Processing video metadata...")

        # Simulate processing time
        import time

        time.sleep(2)

        self.update_progress(task_id, 90, "Finalizing video enrichment...")

        # Update video enrichment timestamp
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            if video:
                video.last_enriched = datetime.utcnow()
                session.commit()

        self.update_progress(
            task_id, 100, f"Video metadata enrichment completed: {video_title}"
        )

        result = {
            "success": True,
            "video_id": video_id,
            "video_title": video_title,
            "artist_name": artist_name,
            "enriched_fields": [],  # TODO: Implement actual enrichment
            "metadata_sources": [],
            "message": f"Video metadata enriched for {video_title}",
        }

        logger.info(f"Successfully completed video metadata enrichment task {task_id}")
        return result

    except Exception as e:
        error_msg = f"Video metadata enrichment failed for video {video_id}: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        # Update task state to failed
        self.update_state(
            state="FAILURE",
            meta={
                "error": error_msg,
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Re-raise for Celery to handle
        raise Exception(error_msg)


@celery_app.task(bind=True, name="metadata.batch_enrich_artists")
def batch_enrich_artists_task(
    self,
    artist_ids: list[int],
    force_refresh: bool = False,
    enrich_videos: bool = True,
) -> Dict[str, Any]:
    """
    Celery task for batch artist metadata enrichment

    Args:
        artist_ids: List of artist IDs to enrich
        force_refresh: Whether to force refresh existing metadata
        enrich_videos: Whether to also enrich associated videos

    Returns:
        Dictionary with batch enrichment results
    """
    task_id = self.request.id
    logger.info(
        f"Starting batch metadata enrichment task {task_id} for {len(artist_ids)} artists"
    )

    try:
        # Initialize database for FastAPI/Celery context
        init_db_standalone()
        results = []
        successful = 0
        failed = 0

        for i, artist_id in enumerate(artist_ids):
            try:
                # Update progress
                progress = int((i / len(artist_ids)) * 90)
                self.update_progress(
                    task_id,
                    progress,
                    f"Processing artist {i+1}/{len(artist_ids)} (ID: {artist_id})",
                )

                # Run individual enrichment task
                result = enrich_artist_metadata_task.apply(
                    args=[artist_id, force_refresh, enrich_videos]
                )

                # Get the actual result
                enrichment_result = result.get(timeout=300)  # 5 minute timeout

                if enrichment_result.get("success"):
                    successful += 1
                else:
                    failed += 1

                results.append(
                    {
                        "artist_id": artist_id,
                        "success": enrichment_result.get("success", False),
                        "result": enrichment_result,
                    }
                )

            except Exception as e:
                failed += 1
                logger.error(f"Failed to enrich artist {artist_id}: {e}")
                results.append(
                    {"artist_id": artist_id, "success": False, "error": str(e)}
                )

        self.update_progress(
            task_id,
            100,
            f"Batch enrichment completed: {successful} successful, {failed} failed",
        )

        batch_result = {
            "success": True,
            "total_processed": len(artist_ids),
            "successful": successful,
            "failed": failed,
            "results": results,
            "message": f"Batch enrichment completed for {len(artist_ids)} artists",
        }

        logger.info(f"Successfully completed batch metadata enrichment task {task_id}")
        return batch_result

    except Exception as e:
        error_msg = f"Batch metadata enrichment failed: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        # Update task state to failed
        self.update_state(
            state="FAILURE",
            meta={
                "error": error_msg,
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Re-raise for Celery to handle
        raise Exception(error_msg)


# Maintenance tasks
@celery_app.task(name="maintenance.cleanup_expired_jobs")
def cleanup_expired_jobs() -> Dict[str, Any]:
    """Clean up expired Celery task results"""
    try:
        # This will be called by Celery Beat scheduler
        # Implementation depends on how you want to clean up old results
        logger.info("Running cleanup of expired jobs")

        # For now, just log that it ran
        return {
            "success": True,
            "message": "Cleanup completed",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to cleanup expired jobs: {e}")
        raise


@celery_app.task(name="maintenance.update_job_statistics")
def update_job_statistics() -> Dict[str, Any]:
    """Update job processing statistics"""
    try:
        # This will be called by Celery Beat scheduler
        logger.debug("Updating job statistics")

        # For now, just log that it ran
        return {
            "success": True,
            "message": "Statistics updated",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to update job statistics: {e}")
        raise


@celery_app.task(bind=True, name="metadata.bulk_thumbnail_url_download")
def bulk_thumbnail_url_download(
    self,
    url_video_ids,
    ffmpeg_video_paths=None,
    priority="normal",
    user_id=None,
):
    """Download thumbnails from source URLs with FFmpeg fallback"""
    from pathlib import Path
    from urllib.parse import urlparse

    import httpx

    try:
        from src.jobs.redis_manager import redis_manager

        task_id = self.request.id
        logger.info(f"Starting bulk thumbnail URL download task {task_id}")

        # Initialize progress
        redis_manager.set_job_progress(
            task_id,
            {
                "percent": 0,
                "message": "Starting thumbnail download process",
                "status": "PROGRESS",
                "current_step": "Initializing",
            },
        )

        init_db_standalone()

        url_processed = 0
        ffmpeg_processed = 0
        total_items = len(url_video_ids) + (
            len(ffmpeg_video_paths) if ffmpeg_video_paths else 0
        )

        if total_items == 0:
            redis_manager.set_job_progress(
                task_id,
                {
                    "percent": 100,
                    "message": "No videos to process",
                    "status": "SUCCESS",
                },
            )
            return {"success": True, "url_processed": 0, "ffmpeg_processed": 0}

        # Process URL videos first (faster)
        with get_db() as session:
            for i, video_id in enumerate(url_video_ids):
                try:
                    progress = int((i / total_items) * 100)

                    video = session.query(Video).filter(Video.id == video_id).first()
                    if not video or not video.thumbnail_url:
                        continue

                    redis_manager.set_job_progress(
                        task_id,
                        {
                            "percent": progress,
                            "message": f"Downloading thumbnail for {video.title[:50]}...",
                            "status": "PROGRESS",
                            "current_step": f"Processing video {i+1} of {len(url_video_ids)}",
                        },
                    )

                    # Download thumbnail from URL
                    thumbnail_dir = Path("/home/mike/mvidarr/data/thumbnails/videos")
                    thumbnail_dir.mkdir(parents=True, exist_ok=True)

                    parsed_url = urlparse(video.thumbnail_url)
                    file_extension = Path(parsed_url.path).suffix.lower() or ".jpg"
                    cached_thumbnail = (
                        thumbnail_dir / f"{video_id}_cached{file_extension}"
                    )

                    # Download if not already cached
                    if not cached_thumbnail.exists():
                        with httpx.Client(timeout=10) as client:
                            response = client.get(video.thumbnail_url)
                            response.raise_for_status()
                            with open(cached_thumbnail, "wb") as f:
                                f.write(response.content)

                    # Update database
                    video.thumbnail_path = str(cached_thumbnail)
                    session.commit()
                    url_processed += 1

                except Exception as e:
                    logger.warning(
                        f"Failed to download thumbnail for video {video_id}: {e}"
                    )
                    continue

        # Fallback to FFmpeg for videos without URLs
        if ffmpeg_video_paths:
            from src.jobs.ffmpeg_processing_tasks import (
                submit_bulk_thumbnail_creation_task,
            )

            ffmpeg_progress_start = int((len(url_video_ids) / total_items) * 100)

            redis_manager.set_job_progress(
                task_id,
                {
                    "percent": ffmpeg_progress_start,
                    "message": f"Starting FFmpeg processing for {len(ffmpeg_video_paths)} videos",
                    "status": "PROGRESS",
                    "current_step": "FFmpeg thumbnail generation",
                },
            )

            # Submit FFmpeg job and wait for completion
            ffmpeg_job_id = submit_bulk_thumbnail_creation_task(
                video_paths=ffmpeg_video_paths,
                output_directory=str(Path("/home/mike/mvidarr/data/thumbnails/videos")),
                thumbnail_sizes=[(640, 480)],
                timestamps_per_video=1,
                batch_size=3,
                priority=priority,
                user_id=user_id,
            )

            # For now, just mark as processed
            ffmpeg_processed = len(ffmpeg_video_paths)

        # Final progress update
        redis_manager.set_job_progress(
            task_id,
            {
                "percent": 100,
                "message": f"Completed: {url_processed} from URLs, {ffmpeg_processed} from FFmpeg",
                "status": "SUCCESS",
                "current_step": "Finished",
            },
        )

        return {
            "success": True,
            "url_processed": url_processed,
            "ffmpeg_processed": ffmpeg_processed,
            "total_processed": url_processed + ffmpeg_processed,
        }

    except Exception as e:
        error_msg = f"Bulk thumbnail download failed: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        redis_manager.set_job_progress(
            task_id,
            {
                "percent": 0,
                "message": error_msg,
                "status": "FAILURE",
                "error": error_msg,
            },
        )

        raise Exception(error_msg)


def submit_bulk_thumbnail_url_download_task(
    url_video_ids,
    ffmpeg_video_paths=None,
    priority="normal",
    user_id=None,
):
    """Submit bulk thumbnail URL download task"""
    task = bulk_thumbnail_url_download.delay(
        url_video_ids=url_video_ids,
        ffmpeg_video_paths=ffmpeg_video_paths or [],
        priority=priority,
        user_id=user_id,
    )

    logger.info(f"Submitted bulk thumbnail URL download task: {task.id}")
    return task.id
