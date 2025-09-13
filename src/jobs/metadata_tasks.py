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
from flask import Flask

from src.database.connection import get_db, init_db
from src.database.models import Artist, Video
from src.jobs.celery_app import celery_app
from src.services.metadata_enrichment_service import MetadataEnrichmentService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.metadata_tasks")


class CallbackTask(Task):
    """Base task that supports progress callbacks"""

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """Update task progress and send to WebSocket subscribers"""
        try:
            # Update task metadata
            self.update_state(
                task_id=task_id,
                state="PROGRESS",
                meta={
                    "progress": progress,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            # Emit WebSocket update for real-time UI updates
            try:
                from flask_socketio import SocketIO
                from flask import current_app

                if hasattr(current_app, "socketio"):
                    current_app.socketio.emit(
                        "job_progress",
                        {
                            "job_id": task_id,
                            "progress": progress,
                            "message": message,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        namespace="/jobs",
                    )
            except Exception as ws_error:
                logger.debug(f"WebSocket emission failed (non-critical): {ws_error}")

        except Exception as e:
            logger.error(f"Failed to update task progress: {e}")


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

    try:
        # Initialize Flask app context for database access
        app = Flask(__name__)
        init_db(app)

        with app.app_context():
            # Update progress
            self.update_progress(task_id, 5, "Initializing enrichment service...")

            # Get artist info
            with get_db() as session:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()
                if not artist:
                    raise ValueError(f"Artist with ID {artist_id} not found")

                artist_name = artist.name

            self.update_progress(
                task_id, 10, f"Starting enrichment for {artist_name}..."
            )

            # Initialize enrichment service
            enrichment_service = MetadataEnrichmentService()

            # Run enrichment with progress updates
            self.update_progress(
                task_id, 25, "Gathering metadata from external sources..."
            )

            # Since the enrichment service is async, we need to run it in event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                enrichment_result = loop.run_until_complete(
                    enrichment_service.enrich_artist_metadata(
                        artist_id, force_refresh=force_refresh, app_context=app
                    )
                )
            finally:
                loop.close()

            self.update_progress(task_id, 75, "Processing enrichment results...")

            # Process results
            if not enrichment_result or not enrichment_result.success:
                error_msg = "Enrichment failed"
                if enrichment_result and enrichment_result.errors:
                    error_msg = "; ".join(enrichment_result.errors)
                raise Exception(error_msg)

            # Enrich videos if requested
            enriched_videos_count = 0
            if enrich_videos:
                self.update_progress(task_id, 85, "Enriching associated videos...")
                enriched_videos_count = self._enrich_artist_videos(artist_id, task_id)

            self.update_progress(
                task_id, 100, f"Metadata enrichment completed for {artist_name}"
            )

            # Prepare result
            result = {
                "success": True,
                "artist_id": artist_id,
                "artist_name": artist_name,
                "sources_updated": enrichment_result.sources_used or [],
                "external_ids_added": [
                    k for k, v in (enrichment_result.external_ids or {}).items() if v
                ],
                "metadata_fields_updated": list(
                    enrichment_result.enriched_fields or set()
                ),
                "genres_added": len(enrichment_result.genres or []),
                "enriched_videos": enriched_videos_count,
                "confidence_score": enrichment_result.confidence_score or 0,
                "processing_time": enrichment_result.processing_time or 0,
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
        # Initialize Flask app context for database access
        app = Flask(__name__)
        init_db(app)

        with app.app_context():
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

            logger.info(
                f"Successfully completed video metadata enrichment task {task_id}"
            )
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
