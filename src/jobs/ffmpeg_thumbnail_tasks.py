"""
FFmpeg thumbnail generation background tasks

Provides Celery tasks for bulk thumbnail creation with progress tracking,
multiple size options, and database integration.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.jobs.base_task import BaseTask
from src.jobs.celery_app import celery_app
from src.jobs.redis_manager import redis_manager
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.ffmpeg_thumbnail")


class FFmpegBulkThumbnailCreationTask(BaseTask):
    """Bulk thumbnail creation with progress tracking and multiple size options"""

    name = "ffmpeg.bulk_thumbnails"
    description = (
        "Create thumbnails for multiple videos with progress tracking and size options"
    )

    async def execute_async(
        self,
        video_paths: List[str],
        output_directory: str,
        thumbnail_sizes: List[Tuple[int, int]] = None,
        timestamps_per_video: int = 3,
        batch_size: int = 5,
        **kwargs,
    ) -> Dict:
        """
        Generate thumbnails for multiple videos with progress tracking

        Args:
            video_paths: List of video file paths
            output_directory: Directory to save thumbnails
            thumbnail_sizes: List of (width, height) tuples for thumbnail sizes
            timestamps_per_video: Number of thumbnails per video
            batch_size: Number of videos to process concurrently
            **kwargs: Additional task arguments

        Returns:
            Dict: Bulk thumbnail creation results
        """
        if thumbnail_sizes is None:
            thumbnail_sizes = [
                (320, 240),
                (640, 480),
                (1280, 720),
            ]  # Small, medium, large

        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        total_videos = len(video_paths)
        processed_videos = 0
        successful_thumbnails = 0
        failed_thumbnails = 0
        thumbnail_results = []

        try:
            await self.update_progress(
                5, f"Starting bulk thumbnail creation for {total_videos} videos"
            )

            # Process videos in batches
            for i in range(0, total_videos, batch_size):
                batch = video_paths[i : i + batch_size]

                # Execute batch concurrently
                batch_results = await asyncio.gather(
                    *[
                        self._create_video_thumbnails(
                            video_path,
                            output_dir,
                            thumbnail_sizes,
                            timestamps_per_video,
                            processed_videos + j + 1,
                            total_videos,
                        )
                        for j, video_path in enumerate(batch)
                    ],
                    return_exceptions=True,
                )

                # Process batch results
                for j, result in enumerate(batch_results):
                    processed_videos += 1

                    if isinstance(result, Exception):
                        failed_thumbnails += 1
                        thumbnail_results.append(
                            {
                                "video_path": batch[j],
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        if result["success"]:
                            successful_thumbnails += len(result["thumbnails"])
                        else:
                            failed_thumbnails += 1
                        thumbnail_results.append(result)

                    # Update progress
                    progress = int((processed_videos / total_videos) * 90) + 5
                    await self.update_progress(
                        progress,
                        f"Created thumbnails for {processed_videos}/{total_videos} videos",
                    )

            # Generate thumbnail summary
            thumbnail_summary = self._generate_thumbnail_summary(
                thumbnail_results, thumbnail_sizes
            )

            await self.update_progress(
                100,
                f"Bulk thumbnail creation complete: {successful_thumbnails} thumbnails created",
            )

            return {
                "success": True,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
                "successful_thumbnails": successful_thumbnails,
                "failed_thumbnails": failed_thumbnails,
                "thumbnail_results": thumbnail_results,
                "thumbnail_summary": thumbnail_summary,
                "output_directory": str(output_dir),
            }

        except Exception as e:
            error_msg = f"Bulk thumbnail creation failed: {e}"
            logger.error(error_msg)
            await self.update_progress(0, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
            }

    async def _create_video_thumbnails(
        self,
        video_path: str,
        output_dir: Path,
        thumbnail_sizes: List[Tuple[int, int]],
        timestamps_per_video: int,
        video_number: int,
        total_videos: int,
    ) -> Dict:
        """Create thumbnails for a single video"""
        try:
            video_file = Path(video_path)

            if not video_file.exists():
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": f"File not found: {video_path}",
                }

            logger.debug(
                f"Creating thumbnails for video {video_number}/{total_videos}: {video_file.name}"
            )

            # Create video-specific output directory
            video_output_dir = output_dir / video_file.stem
            video_output_dir.mkdir(parents=True, exist_ok=True)

            # Get video metadata for duration and optimal timestamps
            metadata = await ffmpeg_stream_manager.extract_metadata_async(video_file)
            duration = metadata.get("duration", 0)

            if duration <= 0:
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": "Could not determine video duration",
                }

            # Calculate optimal timestamps (avoid first/last 10%)
            start_time = duration * 0.1
            end_time = duration * 0.9

            if timestamps_per_video == 1:
                timestamps = [duration / 2]
            else:
                step = (end_time - start_time) / (timestamps_per_video - 1)
                timestamps = [
                    start_time + (i * step) for i in range(timestamps_per_video)
                ]

            # Generate thumbnails for each timestamp and size
            thumbnails = []
            for timestamp in timestamps:
                for width, height in thumbnail_sizes:
                    thumbnail_result = await self._generate_single_thumbnail(
                        video_file, video_output_dir, timestamp, width, height
                    )
                    thumbnails.append(thumbnail_result)

            successful_thumbs = [t for t in thumbnails if t["success"]]

            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": len(successful_thumbs) > 0,
                "thumbnails": thumbnails,
                "successful_count": len(successful_thumbs),
                "total_count": len(thumbnails),
                "video_duration": duration,
                "output_directory": str(video_output_dir),
            }

        except Exception as e:
            logger.error(f"Error creating thumbnails for {video_path}: {e}")
            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": False,
                "error": str(e),
            }

    async def _generate_single_thumbnail(
        self,
        video_file: Path,
        output_dir: Path,
        timestamp: float,
        width: int,
        height: int,
    ) -> Dict:
        """Generate a single thumbnail with specific parameters"""
        try:
            thumbnail_name = f"thumb_{timestamp:.1f}s_{width}x{height}.jpg"
            thumbnail_path = output_dir / thumbnail_name

            # Use FFmpeg stream manager for thumbnail generation
            result = await ffmpeg_stream_manager.generate_thumbnail_async(
                video_file,
                thumbnail_path,
                timestamp=str(timestamp),
                size=f"{width}x{height}",
                job_id=f"{self.task_id}_thumb",
            )

            return {
                "timestamp": timestamp,
                "size": f"{width}x{height}",
                "path": str(thumbnail_path),
                "success": result["success"],
                "file_size": result.get("file_size", 0) if result["success"] else 0,
                "generation_time": result.get("generation_time", 0),
            }

        except Exception as e:
            logger.warning(
                f"Failed to generate thumbnail at {timestamp}s, {width}x{height}: {e}"
            )
            return {
                "timestamp": timestamp,
                "size": f"{width}x{height}",
                "success": False,
                "error": str(e),
            }

    def _generate_thumbnail_summary(
        self, thumbnail_results: List[Dict], thumbnail_sizes: List[Tuple[int, int]]
    ) -> Dict:
        """Generate summary statistics for thumbnail creation"""
        successful_videos = [r for r in thumbnail_results if r["success"]]
        total_successful_thumbs = sum(r["successful_count"] for r in successful_videos)
        total_thumbs_attempted = sum(
            r["total_count"] for r in thumbnail_results if "total_count" in r
        )

        # Size distribution
        size_stats = {}
        for width, height in thumbnail_sizes:
            size_key = f"{width}x{height}"
            size_count = 0
            for result in successful_videos:
                size_count += len(
                    [
                        t
                        for t in result["thumbnails"]
                        if t["size"] == size_key and t["success"]
                    ]
                )
            size_stats[size_key] = size_count

        return {
            "videos_processed": len(thumbnail_results),
            "videos_successful": len(successful_videos),
            "thumbnails_created": total_successful_thumbs,
            "thumbnails_attempted": total_thumbs_attempted,
            "success_rate": (
                (total_successful_thumbs / total_thumbs_attempted * 100)
                if total_thumbs_attempted > 0
                else 0
            ),
            "size_distribution": size_stats,
            "thumbnail_sizes": [f"{w}x{h}" for w, h in thumbnail_sizes],
        }


# Celery task for bulk thumbnail creation
@celery_app.task(bind=True, name="ffmpeg.bulk_thumbnails")
def bulk_thumbnail_creation(
    self,
    video_paths: List[str],
    output_directory: str,
    thumbnail_sizes: List[Tuple[int, int]] = None,
    timestamps_per_video: int = 3,
    batch_size: int = 5,
    priority: str = "normal",
    user_id: Optional[str] = None,
):
    """
    Generate thumbnails for multiple videos with progress tracking
    """
    import asyncio
    from pathlib import Path

    from src.jobs.redis_manager import redis_manager
    from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager

    if thumbnail_sizes is None:
        thumbnail_sizes = [(640, 480)]  # Standard thumbnail size

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_videos = len(video_paths)
    processed_videos = 0
    successful_thumbnails = 0
    errors = []

    # Update initial progress
    redis_manager.set_job_progress(
        self.request.id,
        {
            "percent": 0,
            "message": f"Starting thumbnail generation for {total_videos} videos",
            "status": "STARTED",
        },
    )

    try:
        for i, video_path in enumerate(video_paths):
            try:
                video_file = Path(video_path)

                # Update progress
                progress = int((i / total_videos) * 100)
                redis_manager.set_job_progress(
                    self.request.id,
                    {
                        "percent": progress,
                        "message": f"Processing video {i+1} of {total_videos}: {video_file.name}",
                        "status": "PROGRESS",
                        "current_step": f"Generating thumbnail for {video_file.name}",
                    },
                )

                # Generate thumbnail filename
                thumbnail_filename = f"{video_file.stem}_thumb.jpg"
                thumbnail_path = output_dir / thumbnail_filename

                # Generate thumbnail synchronously (since we're in a Celery worker)
                result = asyncio.run(
                    ffmpeg_stream_manager.generate_thumbnail_async(
                        video_path=video_file,
                        output_path=thumbnail_path,
                        timestamp=None,  # Auto-detect middle of video
                        size="640x480",
                    )
                )

                if result.get("success"):
                    successful_thumbnails += 1
                    logger.info(f"Generated thumbnail for video: {thumbnail_path}")

                    # Update database with thumbnail path
                    try:
                        from src.database.connection import get_db
                        from src.database.models import Video

                        with get_db() as db_session:
                            # Find the video by matching the file path
                            video_record = (
                                db_session.query(Video)
                                .filter(Video.local_path.like(f"%{video_file.name}"))
                                .first()
                            )

                            if video_record:
                                video_record.thumbnail_path = str(thumbnail_path)
                                db_session.commit()
                                logger.info(
                                    f"Updated database thumbnail_path for video ID {video_record.id}: {thumbnail_path}"
                                )
                            else:
                                logger.warning(
                                    f"Could not find video record for {video_file.name}"
                                )

                    except Exception as db_error:
                        logger.error(
                            f"Failed to update database for {video_file.name}: {db_error}"
                        )

                else:
                    error_msg = result.get("error", "Unknown error")
                    errors.append(f"{video_file.name}: {error_msg}")
                    logger.warning(
                        f"Failed to generate thumbnail for {video_file.name}: {error_msg}"
                    )

                processed_videos += 1

            except Exception as e:
                errors.append(f"{video_path}: {str(e)}")
                logger.error(f"Error generating thumbnail for {video_path}: {e}")

        # Final progress update
        redis_manager.set_job_progress(
            self.request.id,
            {
                "percent": 100,
                "message": f"Completed thumbnail generation: {successful_thumbnails} successful, {len(errors)} errors",
                "status": "SUCCESS",
            },
        )

        return {
            "success": True,
            "processed_videos": processed_videos,
            "successful_thumbnails": successful_thumbnails,
            "total_videos": total_videos,
            "errors": errors,
        }

    except Exception as e:
        redis_manager.set_job_progress(
            self.request.id,
            {"percent": 0, "message": f"Task failed: {str(e)}", "status": "FAILURE"},
        )
        raise


# Convenience function for task submission
def submit_bulk_thumbnail_creation_task(
    video_paths: List[str],
    output_directory: str,
    thumbnail_sizes: List[Tuple[int, int]] = None,
    timestamps_per_video: int = 3,
    batch_size: int = 5,
    priority: str = "normal",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit bulk thumbnail creation task

    Args:
        video_paths: List of video file paths
        output_directory: Directory to save thumbnails
        thumbnail_sizes: List of (width, height) tuples
        timestamps_per_video: Number of thumbnails per video
        batch_size: Number of videos to process concurrently
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = bulk_thumbnail_creation.delay(
        video_paths=video_paths,
        output_directory=output_directory,
        thumbnail_sizes=thumbnail_sizes,
        timestamps_per_video=timestamps_per_video,
        batch_size=batch_size,
        priority=priority,
        user_id=user_id,
    )
    logger.info(
        f"Submitted bulk thumbnail creation job {task.id} for {len(video_paths)} videos"
    )
    return task.id
