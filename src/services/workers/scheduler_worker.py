"""
Scheduler Worker
Handles background jobs for scheduled downloads and discovery operations.
"""

import logging
from typing import Any, Dict

from src.services.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class SchedulerWorker(BaseWorker):
    """Worker for scheduled background jobs"""

    async def process(self):
        """Process scheduler job based on type"""
        job_type = self.job.type.value
        payload = self.job.payload

        try:
            if job_type == "scheduled_download":
                return await self._handle_scheduled_download(payload)
            elif job_type == "scheduled_discovery":
                return await self._handle_scheduled_discovery(payload)
            else:
                raise ValueError(f"Unknown scheduler job type: {job_type}")

        except Exception as e:
            logger.error(f"Scheduler job {self.job.id} failed: {e}")
            raise

    async def _handle_scheduled_download(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle scheduled download job"""
        max_downloads = payload.get("max_downloads", 10)

        await self.update_progress(10, "Getting videos for scheduled download...")

        # Import here to avoid circular dependencies
        from src.api.videos import get_wanted_videos_for_download

        # Get wanted videos
        wanted_videos = await self.run_async_service(
            lambda: get_wanted_videos_for_download(limit=max_downloads)
        )

        if not wanted_videos:
            await self.update_progress(100, "No videos found for download")
            return {
                "status": "success",
                "downloaded": 0,
                "message": "No videos to download",
            }

        total_videos = len(wanted_videos)
        downloaded_count = 0
        failed_count = 0

        await self.update_progress(20, f"Found {total_videos} videos to download")

        # Process each video download by creating individual download jobs
        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        job_queue = await get_job_queue()

        for i, video in enumerate(wanted_videos):
            try:
                # Create individual video download job
                download_job = BackgroundJob(
                    type=JobType.VIDEO_DOWNLOAD,
                    priority=JobPriority.NORMAL,
                    payload={
                        "video_id": video["id"],
                        "quality": "best",
                        "scheduled": True,  # Mark as scheduled download
                    },
                    created_by=self.job.created_by,
                )

                # Enqueue download job
                job_id = await job_queue.enqueue(download_job)
                downloaded_count += 1

                progress = 20 + int((i + 1) / total_videos * 70)  # 20-90% range
                await self.update_progress(
                    progress,
                    f"Queued download {i + 1}/{total_videos}: {video.get('title', 'Unknown Title')}",
                )

                logger.info(
                    f"✅ Successfully queued download job {job_id} for video ID {video['id']}"
                )

            except Exception as e:
                failed_count += 1
                logger.error(
                    f"❌ Failed to queue download for video ID {video['id']}: {e}"
                )

        await self.update_progress(
            100,
            f"Scheduled downloads completed: {downloaded_count} queued, {failed_count} failed",
        )

        return {
            "status": "success",
            "downloaded": downloaded_count,
            "failed": failed_count,
            "total": total_videos,
            "message": f"Scheduled download completed: {downloaded_count} videos queued for download",
        }

    async def _handle_scheduled_discovery(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle scheduled discovery job"""
        max_artists = payload.get("max_artists", 5)
        max_videos_per_artist = payload.get("max_videos_per_artist", 3)

        await self.update_progress(10, "Starting scheduled video discovery...")

        # Import here to avoid circular dependencies
        from src.api.video_discovery import discover_videos_for_artists

        # Run discovery through thread pool
        result = await self.run_async_service(
            lambda: discover_videos_for_artists(
                max_artists=max_artists,
                max_videos_per_artist=max_videos_per_artist,
                scheduled=True,  # Mark as scheduled discovery
            )
        )

        await self.update_progress(100, "Scheduled video discovery completed")

        return {
            "status": "success",
            "artists_processed": result.get("artists_processed", 0),
            "videos_discovered": result.get("videos_discovered", 0),
            "result": result,
            "message": f"Discovery completed: {result.get('videos_discovered', 0)} videos found for {result.get('artists_processed', 0)} artists",
        }
