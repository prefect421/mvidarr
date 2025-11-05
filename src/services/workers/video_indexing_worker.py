"""
Video Indexing Worker
Handles background jobs for video indexing operations.
"""

import logging
from typing import Any, Dict

from src.services.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class VideoIndexingWorker(BaseWorker):
    """Worker for video indexing background jobs"""

    async def process(self):
        """Process video indexing job based on type"""
        job_type = self.job.type.value
        payload = self.job.payload

        try:
            if job_type == "video_index_all":
                return await self._handle_index_all_videos(payload)
            elif job_type == "video_index_single":
                return await self._handle_index_single_video(payload)
            else:
                raise ValueError(f"Unknown video indexing job type: {job_type}")

        except Exception as e:
            logger.error(f"Video indexing job {self.job.id} failed: {e}")
            raise

    async def _handle_index_all_videos(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Index all videos in the music videos directory"""
        fetch_metadata = payload.get("fetch_metadata", True)
        max_files = payload.get("max_files")

        await self.update_progress(5, f"Starting video indexing process...")

        # Import the video indexing service
        from src.services.video_indexing_service import video_indexing_service

        # Run indexing through thread pool
        result = await self.run_async_service(
            lambda: video_indexing_service.index_all_videos(
                fetch_metadata=fetch_metadata, max_files=max_files
            )
        )

        successful = result.get("successful", 0)
        total = result.get("total_files", 0)

        await self.update_progress(
            100, f"Video indexing completed: {successful}/{total} files processed"
        )

        return {
            "fetch_metadata": fetch_metadata,
            "max_files": max_files,
            "result": result,
            "message": f"Video indexing completed: {successful}/{total} files processed successfully",
        }

    async def _handle_index_single_video(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Index a specific video file"""
        from pathlib import Path

        file_path = payload.get("file_path")
        fetch_metadata = payload.get("fetch_metadata", True)

        if not file_path:
            raise ValueError("file_path is required for single video indexing")

        await self.update_progress(10, f"Indexing video: {file_path}")

        # Import the video indexing service
        from src.services.video_indexing_service import video_indexing_service

        # Run single video indexing through thread pool
        # Note: index_single_file expects a Path object
        result = await self.run_async_service(
            lambda: video_indexing_service.index_single_file(
                file_path=Path(file_path), fetch_metadata=fetch_metadata
            )
        )

        await self.update_progress(100, f"Video indexing completed for: {file_path}")

        return {
            "file_path": file_path,
            "fetch_metadata": fetch_metadata,
            "result": result,
            "message": f"Video indexing completed for: {file_path}",
        }
