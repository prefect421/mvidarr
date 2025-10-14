"""
FFmpeg metadata extraction background tasks

Provides Celery tasks for async video metadata extraction and bulk metadata operations
with real-time progress tracking.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional

from src.jobs.base_task import BaseTask
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.ffmpeg_metadata")


class FFmpegMetadataExtractionTask(BaseTask):
    """Background task for extracting video metadata using FFprobe"""

    name = "ffmpeg.extract_metadata"
    description = "Extract technical metadata from video files"

    async def execute_async(self, video_path: str, **kwargs) -> Dict:
        """
        Extract metadata from video file

        Args:
            video_path: Path to video file
            **kwargs: Additional task arguments

        Returns:
            Dict: Extracted metadata and task results
        """
        video_file = Path(video_path)

        if not video_file.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        try:
            # Update task progress
            await self.update_progress(
                10, f"Starting metadata extraction for {video_file.name}"
            )

            # Extract metadata using async stream manager
            metadata = await ffmpeg_stream_manager.extract_metadata_async(
                video_file,
                job_id=self.task_id,
                progress_callback=self._progress_callback,
            )

            # Update final progress
            await self.update_progress(
                100,
                f"Metadata extracted: {metadata.get('quality', 'unknown')} quality, "
                f"{metadata.get('duration', 'unknown')} seconds",
            )

            return {
                "success": True,
                "metadata": metadata,
                "video_path": str(video_file),
                "video_name": video_file.name,
                "file_size": video_file.stat().st_size if video_file.exists() else None,
            }

        except Exception as e:
            error_msg = f"Metadata extraction failed for {video_file.name}: {e}"
            logger.error(error_msg)

            await self.update_progress(0, error_msg)

            return {"success": False, "error": error_msg, "video_path": str(video_file)}

    def _progress_callback(self, progress_data: Dict):
        """Handle progress updates from FFmpeg stream manager"""
        try:
            # Convert progress data to task progress format
            stage = progress_data.get("stage", "processing")
            status = progress_data.get("status", "running")
            message = progress_data.get("message", "Processing video")
            progress = progress_data.get("progress", 0)

            # Update task progress asynchronously
            asyncio.create_task(self.update_progress(progress, status, message))

        except Exception as e:
            logger.warning(f"Error in progress callback: {e}")


class FFmpegBulkMetadataTask(BaseTask):
    """Background task for bulk video metadata extraction"""

    name = "ffmpeg.bulk_metadata"
    description = "Extract metadata from multiple video files"

    async def execute_async(
        self, video_paths: list, batch_size: int = 10, **kwargs
    ) -> Dict:
        """
        Extract metadata from multiple video files

        Args:
            video_paths: List of video file paths
            batch_size: Number of files to process concurrently
            **kwargs: Additional task arguments

        Returns:
            Dict: Bulk processing results
        """
        total_files = len(video_paths)
        processed_files = 0
        successful_extractions = 0
        failed_extractions = 0
        results = []

        try:
            await self.update_progress(
                5, f"Starting bulk metadata extraction for {total_files} videos"
            )

            # Process files in batches
            for i in range(0, total_files, batch_size):
                batch = video_paths[i : i + batch_size]
                batch_results = await asyncio.gather(
                    *[
                        self._extract_single_metadata(
                            video_path, i + j + 1, total_files
                        )
                        for j, video_path in enumerate(batch)
                    ],
                    return_exceptions=True,
                )

                # Process batch results
                for j, result in enumerate(batch_results):
                    processed_files += 1

                    if isinstance(result, Exception):
                        failed_extractions += 1
                        results.append(
                            {
                                "video_path": batch[j],
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        if result["success"]:
                            successful_extractions += 1
                        else:
                            failed_extractions += 1
                        results.append(result)

                    # Update progress
                    progress = int((processed_files / total_files) * 90) + 5
                    await self.update_progress(
                        progress,
                        f"Processed {processed_files}/{total_files} videos "
                        f"({successful_extractions} successful, {failed_extractions} failed)",
                    )

            # Final progress update
            await self.update_progress(
                100,
                f"Bulk metadata extraction completed: {successful_extractions} successful, "
                f"{failed_extractions} failed out of {total_files} total",
            )

            return {
                "success": True,
                "total_files": total_files,
                "processed_files": processed_files,
                "successful_extractions": successful_extractions,
                "failed_extractions": failed_extractions,
                "results": results,
            }

        except Exception as e:
            error_msg = f"Bulk metadata extraction failed: {e}"
            logger.error(error_msg)

            await self.update_progress(0, error_msg)

            return {
                "success": False,
                "error": error_msg,
                "total_files": total_files,
                "processed_files": processed_files,
                "results": results,
            }

    async def _extract_single_metadata(
        self, video_path: str, file_number: int, total_files: int
    ) -> Dict:
        """Extract metadata from a single video file"""
        try:
            video_file = Path(video_path)

            if not video_file.exists():
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": f"File not found: {video_path}",
                }

            logger.debug(
                f"Extracting metadata from {video_file.name} ({file_number}/{total_files})"
            )

            metadata = await ffmpeg_stream_manager.extract_metadata_async(video_file)

            return {
                "video_path": video_path,
                "success": True,
                "metadata": metadata,
                "video_name": video_file.name,
                "file_size": video_file.stat().st_size,
            }

        except Exception as e:
            logger.error(f"Error extracting metadata from {video_path}: {e}")
            return {"video_path": video_path, "success": False, "error": str(e)}


# Convenience functions for task submission
async def submit_metadata_extraction_task(
    video_path: str, priority: str = "normal", user_id: Optional[str] = None
) -> str:
    """
    Submit metadata extraction task

    Args:
        video_path: Path to video file
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegMetadataExtractionTask()
    return await task.submit(video_path=video_path, priority=priority, user_id=user_id)


async def submit_bulk_metadata_task(
    video_paths: list,
    batch_size: int = 10,
    priority: str = "low",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit bulk metadata extraction task

    Args:
        video_paths: List of video file paths
        batch_size: Number of files to process concurrently
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegBulkMetadataTask()
    return await task.submit(
        video_paths=video_paths,
        batch_size=batch_size,
        priority=priority,
        user_id=user_id,
    )
