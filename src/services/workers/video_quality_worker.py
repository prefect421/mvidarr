"""
Video Quality Worker
Handles background jobs for video quality analysis, upgrades, and bulk operations.
"""

import logging
from typing import Any, Dict

from src.services.video_quality_service import video_quality_service
from src.services.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class VideoQualityWorker(BaseWorker):
    """Worker for video quality-related background jobs"""

    async def process(self):
        """Process video quality job based on type"""
        job_type = self.job.type.value
        payload = self.job.payload

        try:
            if job_type == "video_quality_analyze":
                result = await self._handle_analyze_video(payload)
                await self.complete(result)
            elif job_type == "video_quality_upgrade":
                result = await self._handle_upgrade_video(payload)
                await self.complete(result)
            elif job_type == "video_quality_bulk_upgrade":
                result = await self._handle_bulk_upgrade_videos(payload)
                await self.complete(result)
            elif job_type == "video_quality_check_all":
                result = await self._handle_check_all_qualities(payload)
                await self.complete(result)
            else:
                raise ValueError(f"Unknown video quality job type: {job_type}")

        except Exception as e:
            logger.error(f"Video quality job {self.job.id} failed: {e}")
            await self.fail(f"Video quality operation failed: {str(e)}")
            raise

    async def _handle_analyze_video(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze quality of a specific video"""
        video_id = payload.get("video_id")
        if not video_id:
            raise ValueError("video_id is required for video quality analysis")

        await self.update_progress(10, f"Analyzing video {video_id} quality...")

        # Get video from database
        from src.database.connection import get_db
        from src.database.models import Video

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            if not video:
                raise ValueError(f"Video {video_id} not found")

            await self.update_progress(30, "Running quality analysis...")

            # Run quality analysis through thread pool
            analysis = await self.run_async_service(
                lambda: video_quality_service.analyze_video_quality(video)
            )

            await self.update_progress(100, "Quality analysis completed")

            return {
                "video_id": video_id,
                "analysis": analysis,
                "message": f"Quality analysis completed for video {video_id}",
            }

    async def _handle_upgrade_video(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upgrade quality of a specific video"""
        video_id = payload.get("video_id")
        user_id = payload.get("user_id")

        if not video_id:
            raise ValueError("video_id is required for video quality upgrade")

        await self.update_progress(
            10, f"Starting quality upgrade for video {video_id}..."
        )

        # Run quality upgrade through thread pool
        result = await self.run_async_service(
            lambda: video_quality_service.upgrade_video_quality(video_id, user_id)
        )

        await self.update_progress(100, "Quality upgrade completed")

        return {
            "video_id": video_id,
            "upgrade_result": result,
            "message": f"Quality upgrade completed for video {video_id}",
        }

    async def _handle_bulk_upgrade_videos(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upgrade quality of multiple videos"""
        video_ids = payload.get("video_ids", [])
        user_id = payload.get("user_id")

        if not video_ids:
            raise ValueError("video_ids array is required for bulk quality upgrade")

        total_videos = len(video_ids)
        await self.update_progress(
            5, f"Starting bulk quality upgrade for {total_videos} videos..."
        )

        # Run bulk upgrade through thread pool with progress tracking
        async def progress_callback(current, total, message):
            progress = int(10 + (current / total * 80))  # 10-90% range
            await self.update_progress(
                progress, f"Processing video {current}/{total}: {message}"
            )

        # Since video_quality_service.bulk_upgrade_videos doesn't support async callbacks,
        # we'll run it through thread pool and estimate progress
        result = await self.run_async_service(
            lambda: video_quality_service.bulk_upgrade_videos(video_ids, user_id)
        )

        await self.update_progress(
            100, f"Bulk quality upgrade completed for {total_videos} videos"
        )

        return {
            "video_ids": video_ids,
            "total_processed": total_videos,
            "upgrade_result": result,
            "message": f"Bulk quality upgrade completed for {total_videos} videos",
        }

    async def _handle_check_all_qualities(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check qualities for all videos in the system"""
        limit = payload.get("limit")
        only_unchecked = payload.get("only_unchecked", True)

        await self.update_progress(5, "Starting quality check for all videos...")

        # Import the quality check service
        from src.services.youtube_quality_check_service import (
            youtube_quality_check_service,
        )

        # Run quality check through thread pool
        summary = await self.run_async_service(
            lambda: youtube_quality_check_service.check_all_videos(
                limit=limit, only_unchecked=only_unchecked
            )
        )

        await self.update_progress(
            100,
            f"Quality check completed: {summary.get('successful_checks', 0)} videos processed",
        )

        return {
            "summary": summary,
            "limit": limit,
            "only_unchecked": only_unchecked,
            "message": f"Quality check completed: {summary.get('successful_checks', 0)}/{summary.get('total_checked', 0)} videos checked successfully",
        }
