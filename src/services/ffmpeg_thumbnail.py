"""
FFmpeg Thumbnail Generation

Provides single and bulk thumbnail generation from video files with concurrent
batch processing support.
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.services.ffmpeg_metadata import ffmpeg_metadata_extractor
from src.services.ffmpeg_progress import ffmpeg_progress_monitor
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_thumbnail")


class FFmpegThumbnailGenerator:
    """Generates thumbnails from video files"""

    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def generate_thumbnail_async(
        self,
        video_path: Path,
        output_path: Path,
        timestamp: Optional[str] = None,
        size: Optional[str] = "320x240",
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Generate thumbnail from video at specified timestamp

        Args:
            video_path: Path to video file
            output_path: Path for output thumbnail
            timestamp: Timestamp in format "HH:MM:SS" or seconds
            size: Thumbnail size in format "WIDTHxHEIGHT"
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            Dict: Thumbnail generation results
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Default to middle of video if no timestamp specified
        if not timestamp:
            metadata = await ffmpeg_metadata_extractor.extract_metadata_async(
                video_path, job_id
            )
            duration = metadata.get("duration", 10)
            timestamp = str(int(duration / 2))  # Middle of video

        logger.info(f"Generating thumbnail: {video_path.name} -> {output_path.name}")

        try:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "thumbnail_generation",
                        "status": "starting",
                        "message": f"Generating thumbnail for {video_path.name}",
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "thumbnail_generation",
                        "progress": 20,
                        "status": "running",
                        "message": f"Generating thumbnail for {video_path.name}",
                    },
                )

            # Build FFmpeg command for thumbnail
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-ss",
                timestamp,
                "-vframes",
                "1",
                "-vf",
                f"scale={size}:force_original_aspect_ratio=decrease",
                "-q:v",
                "2",
                "-y",  # Overwrite output
                str(output_path),
            ]

            logger.debug(f"Thumbnail command: {' '.join(cmd)}")

            start_time = time.time()

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            if job_id:
                self.active_processes[job_id] = process

            # Wait for completion
            return_code = await process.wait()

            generation_time = time.time() - start_time
            success = return_code == 0 and output_path.exists()

            if success:
                file_size = output_path.stat().st_size

                logger.info(
                    f"Thumbnail generated in {generation_time:.2f}s: {output_path.name}"
                )

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "thumbnail_generation",
                            "status": "completed",
                            "message": f"Thumbnail generated: {output_path.name}",
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "thumbnail_generation",
                            "progress": 100,
                            "status": "completed",
                            "message": f"Thumbnail generated: {output_path.name}",
                            "output_file": str(output_path),
                        },
                    )

                return {
                    "success": True,
                    "video_path": str(video_path),
                    "output_path": str(output_path),
                    "timestamp": timestamp,
                    "size": size,
                    "file_size": file_size,
                    "generation_time": generation_time,
                }
            else:
                error_msg = (
                    f"Thumbnail generation failed with return code: {return_code}"
                )
                logger.error(error_msg)

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "thumbnail_generation",
                            "status": "error",
                            "message": error_msg,
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "thumbnail_generation",
                            "progress": 0,
                            "status": "error",
                            "message": error_msg,
                        },
                    )

                return {
                    "success": False,
                    "error": error_msg,
                    "video_path": str(video_path),
                    "generation_time": generation_time,
                }

        except Exception as e:
            error_msg = f"Thumbnail generation error: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "thumbnail_generation",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "thumbnail_generation",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

            return {"success": False, "error": error_msg, "video_path": str(video_path)}

        finally:
            if job_id and job_id in self.active_processes:
                del self.active_processes[job_id]

    async def generate_bulk_thumbnails_async(
        self,
        video_paths: List[Path],
        output_dir: Path,
        size: str = "320x240",
        batch_size: int = 5,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Generate thumbnails for multiple videos concurrently

        Args:
            video_paths: List of video file paths
            output_dir: Directory for output thumbnails
            size: Thumbnail size in format "WIDTHxHEIGHT"
            batch_size: Number of thumbnails to generate concurrently
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            Dict: Bulk thumbnail generation results
        """
        total_videos = len(video_paths)
        processed_videos = 0
        successful_thumbnails = 0
        failed_thumbnails = 0
        results = []

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting bulk thumbnail generation for {total_videos} videos")

        try:
            if progress_callback:
                progress_callback(
                    {
                        "stage": "bulk_thumbnail_generation",
                        "status": "starting",
                        "message": f"Starting bulk thumbnail generation for {total_videos} videos",
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "bulk_thumbnail_generation",
                        "progress": 5,
                        "status": "running",
                        "message": f"Starting bulk thumbnail generation for {total_videos} videos",
                    },
                )

            # Process videos in batches
            for i in range(0, total_videos, batch_size):
                batch = video_paths[i : i + batch_size]
                batch_results = await asyncio.gather(
                    *[
                        self._generate_single_thumbnail_batch(
                            video_path, output_dir, size, i + j + 1, total_videos
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
                        results.append(
                            {
                                "video_path": str(batch[j]),
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        if result["success"]:
                            successful_thumbnails += 1
                        else:
                            failed_thumbnails += 1
                        results.append(result)

                    # Update progress
                    progress = int((processed_videos / total_videos) * 90) + 5

                    if progress_callback:
                        progress_callback(
                            {
                                "stage": "bulk_thumbnail_generation",
                                "status": "running",
                                "message": f"Generated {processed_videos}/{total_videos} thumbnails",
                            }
                        )

                    if job_id:
                        await ffmpeg_progress_monitor.update_job_progress(
                            job_id,
                            {
                                "stage": "bulk_thumbnail_generation",
                                "progress": progress,
                                "status": "running",
                                "message": f"Generated {processed_videos}/{total_videos} thumbnails",
                            },
                        )

            # Final progress update
            if progress_callback:
                progress_callback(
                    {
                        "stage": "bulk_thumbnail_generation",
                        "status": "completed",
                        "message": f"Bulk thumbnail generation completed: {successful_thumbnails} successful, {failed_thumbnails} failed",
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "bulk_thumbnail_generation",
                        "progress": 100,
                        "status": "completed",
                        "message": f"Bulk thumbnail generation completed: {successful_thumbnails} successful, {failed_thumbnails} failed",
                    },
                )

            return {
                "success": True,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
                "successful_thumbnails": successful_thumbnails,
                "failed_thumbnails": failed_thumbnails,
                "results": results,
            }

        except Exception as e:
            error_msg = f"Bulk thumbnail generation failed: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "bulk_thumbnail_generation",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "bulk_thumbnail_generation",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

            return {
                "success": False,
                "error": error_msg,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
                "results": results,
            }

    async def _generate_single_thumbnail_batch(
        self,
        video_path: Path,
        output_dir: Path,
        size: str,
        video_number: int,
        total_videos: int,
    ) -> Dict:
        """Generate thumbnail for a single video in batch processing"""
        try:
            if not video_path.exists():
                return {
                    "video_path": str(video_path),
                    "success": False,
                    "error": f"File not found: {video_path}",
                }

            # Generate output path
            output_filename = f"{video_path.stem}_thumb.jpg"
            output_path = output_dir / output_filename

            logger.debug(
                f"Generating thumbnail {video_number}/{total_videos}: {video_path.name}"
            )

            # Generate thumbnail
            result = await self.generate_thumbnail_async(
                video_path, output_path, size=size
            )

            result["video_number"] = video_number
            result["total_videos"] = total_videos

            return result

        except Exception as e:
            logger.error(f"Error generating thumbnail for {video_path}: {e}")
            return {"video_path": str(video_path), "success": False, "error": str(e)}


# Shared instance
ffmpeg_thumbnail_generator = FFmpegThumbnailGenerator()
