"""
Video Organization Worker
Handles background jobs for video organization operations.
"""

import logging
from typing import Any, Dict

from src.services.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class VideoOrganizationWorker(BaseWorker):
    """Worker for video organization background jobs"""

    async def process(self):
        """Process video organization job based on type"""
        job_type = self.job.type.value
        payload = self.job.payload

        try:
            if job_type == "video_organize_all":
                result = await self._handle_organize_all_videos(payload)
                await self.complete(result)
            elif job_type == "video_organize_single":
                result = await self._handle_organize_single_video(payload)
                await self.complete(result)
            elif job_type == "video_reorganize_existing":
                result = await self._handle_reorganize_existing_videos(payload)
                await self.complete(result)
            else:
                raise ValueError(f"Unknown video organization job type: {job_type}")

        except Exception as e:
            logger.error(f"Video organization job {self.job.id} failed: {e}")
            await self.fail(f"Video organization failed: {str(e)}")
            raise

    async def _handle_organize_all_videos(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Organize all videos in downloads directory"""
        await self.update_progress(
            5, "Starting video organization for all downloads..."
        )

        # Import the video organization service
        from src.services.video_organization_service import video_organizer

        # Run organization through thread pool
        result = await self.run_async_service(
            lambda: video_organizer.organize_all_downloads()
        )

        successful = result.get("successful", 0)
        total = result.get("total_files", 0)

        await self.update_progress(
            100, f"Video organization completed: {successful}/{total} files processed"
        )

        return {
            "result": result,
            "message": f"Organized {successful} of {total} videos successfully",
        }

    async def _handle_organize_single_video(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Organize a specific video file"""
        filename = payload.get("filename")

        if not filename:
            raise ValueError("filename is required for single video organization")

        await self.update_progress(10, f"Organizing video: {filename}")

        # Import the video organization service
        from src.services.video_organization_service import video_organizer

        # Run single video organization through thread pool
        result = await self.run_async_service(
            lambda: video_organizer.organize_single_file(filename)
        )

        success = result.get("success", False)
        message = result.get("message", "Unknown result")

        await self.update_progress(100, f"Video organization completed for: {filename}")

        return {
            "filename": filename,
            "result": result,
            "message": f"Organization {'succeeded' if success else 'failed'} for {filename}: {message}",
        }

    async def _handle_reorganize_existing_videos(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reorganize existing videos in the music videos directory"""
        await self.update_progress(5, "Starting reorganization of existing videos...")

        # Import the video organization service
        from src.services.video_organization_service import video_organizer

        # Run reorganization through thread pool
        result = await self.run_async_service(
            lambda: video_organizer.reorganize_existing_videos()
        )

        successful = result.get("successful", 0)
        total = result.get("total_files", 0)

        await self.update_progress(
            100, f"Video reorganization completed: {successful}/{total} files processed"
        )

        return {
            "result": result,
            "message": f"Reorganized {successful} of {total} videos successfully",
        }
