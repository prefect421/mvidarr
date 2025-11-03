"""
FFmpeg Video Conversion Operations

Provides video format conversion with predefined profiles and custom options.
Supports both basic and advanced conversion scenarios with progress tracking.
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from src.services.ffmpeg_metadata import ffmpeg_metadata_extractor
from src.services.ffmpeg_progress import ffmpeg_progress_monitor
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_conversion")


class FFmpegConverter:
    """Handles video format conversion operations"""

    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def convert_video_async(
        self,
        input_path: Path,
        output_path: Path,
        format_options: Dict,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> bool:
        """
        Async video format conversion with progress tracking

        Args:
            input_path: Input video file path
            output_path: Output video file path
            format_options: FFmpeg format conversion options
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            bool: True if conversion successful
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input video file not found: {input_path}")

        # Build FFmpeg conversion command
        cmd = ["ffmpeg", "-i", str(input_path)]

        # Add format options
        for key, value in format_options.items():
            if isinstance(value, list):
                cmd.extend(value)
            else:
                cmd.extend([key, str(value)])

        # Add progress output and output file
        cmd.extend(["-progress", "pipe:2", str(output_path)])

        logger.info(f"Starting async video conversion: {input_path} -> {output_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            if job_id:
                self.active_processes[job_id] = process

            # Monitor progress
            progress_task = asyncio.create_task(
                ffmpeg_progress_monitor.monitor_ffmpeg_progress(
                    process.stderr,
                    job_id,
                    progress_callback,
                    operation="video_conversion",
                )
            )

            # Wait for completion
            return_code = await process.wait()

            # Cancel progress monitoring
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

            success = return_code == 0

            if success:
                logger.info(f"Video conversion completed: {output_path}")
                if progress_callback:
                    progress_callback(
                        {
                            "stage": "video_conversion",
                            "status": "completed",
                            "message": f"Conversion complete: {output_path.name}",
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "video_conversion",
                            "progress": 100,
                            "status": "completed",
                            "message": f"Conversion complete: {output_path.name}",
                            "output_file": str(output_path),
                        },
                    )
            else:
                error_msg = f"Video conversion failed with return code: {return_code}"
                logger.error(error_msg)

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "video_conversion",
                            "status": "error",
                            "message": error_msg,
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "video_conversion",
                            "progress": 0,
                            "status": "error",
                            "message": error_msg,
                        },
                    )

            return success

        except Exception as e:
            error_msg = f"Video conversion error: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "video_conversion",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "video_conversion",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

            return False

        finally:
            if job_id and job_id in self.active_processes:
                del self.active_processes[job_id]

    async def convert_video_advanced_async(
        self,
        input_path: Path,
        output_path: Path,
        conversion_profile: str,
        custom_options: Optional[Dict] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Advanced video format conversion with predefined profiles and custom options

        Args:
            input_path: Input video file path
            output_path: Output video file path
            conversion_profile: Predefined conversion profile name
            custom_options: Additional custom FFmpeg options
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            Dict: Conversion results with metadata
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input video file not found: {input_path}")

        # Get conversion profile
        profile_options = self._get_conversion_profile(conversion_profile)
        if not profile_options:
            raise ValueError(f"Unknown conversion profile: {conversion_profile}")

        # Merge custom options if provided
        if custom_options:
            profile_options.update(custom_options)

        # Get input metadata first
        input_metadata = await ffmpeg_metadata_extractor.extract_metadata_async(
            input_path, job_id
        )

        # Build advanced FFmpeg command
        cmd = ["ffmpeg", "-i", str(input_path)]

        # Add profile options
        for key, value in profile_options.items():
            if isinstance(value, list):
                cmd.extend(value)
            else:
                cmd.extend([key, str(value)])

        # Add progress output and output file
        cmd.extend(["-progress", "pipe:2", "-y", str(output_path)])

        logger.info(
            f"Starting advanced video conversion: {input_path.name} -> {output_path.name}"
        )
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            if job_id:
                self.active_processes[job_id] = process

            # Monitor progress
            progress_task = asyncio.create_task(
                ffmpeg_progress_monitor.monitor_ffmpeg_progress(
                    process.stderr,
                    job_id,
                    progress_callback,
                    operation="advanced_video_conversion",
                )
            )

            # Wait for completion
            return_code = await process.wait()

            # Cancel progress monitoring
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

            conversion_time = time.time() - start_time
            success = return_code == 0 and output_path.exists()

            if success:
                # Get output metadata
                output_metadata = (
                    await ffmpeg_metadata_extractor.extract_metadata_async(
                        output_path, job_id
                    )
                )
                file_size = output_path.stat().st_size

                logger.info(
                    f"Advanced video conversion completed in {conversion_time:.2f}s: {output_path.name}"
                )

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "advanced_video_conversion",
                            "status": "completed",
                            "message": f"Advanced conversion complete: {output_path.name}",
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "advanced_video_conversion",
                            "progress": 100,
                            "status": "completed",
                            "message": f"Advanced conversion complete: {output_path.name}",
                            "output_file": str(output_path),
                            "conversion_time": conversion_time,
                        },
                    )

                return {
                    "success": True,
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "conversion_profile": conversion_profile,
                    "input_metadata": input_metadata,
                    "output_metadata": output_metadata,
                    "file_size": file_size,
                    "conversion_time": conversion_time,
                    "size_reduction": (
                        (
                            (input_metadata.get("file_size", 0) - file_size)
                            / input_metadata.get("file_size", 1)
                        )
                        * 100
                        if input_metadata.get("file_size")
                        else 0
                    ),
                }
            else:
                error_msg = (
                    f"Advanced video conversion failed with return code: {return_code}"
                )
                logger.error(error_msg)

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "advanced_video_conversion",
                            "status": "error",
                            "message": error_msg,
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "advanced_video_conversion",
                            "progress": 0,
                            "status": "error",
                            "message": error_msg,
                        },
                    )

                return {
                    "success": False,
                    "error": error_msg,
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "conversion_time": conversion_time,
                }

        except Exception as e:
            error_msg = f"Advanced video conversion error: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "advanced_video_conversion",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "advanced_video_conversion",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

            return {
                "success": False,
                "error": error_msg,
                "input_path": str(input_path),
                "output_path": str(output_path),
            }

        finally:
            if job_id and job_id in self.active_processes:
                del self.active_processes[job_id]

    def _get_conversion_profile(self, profile_name: str) -> Optional[Dict]:
        """Get predefined conversion profile options"""
        profiles = {
            # Web streaming optimized
            "web_optimized": {
                "-c:v": "libx264",
                "-preset": "medium",
                "-crf": "23",
                "-maxrate": "2M",
                "-bufsize": "4M",
                "-c:a": "aac",
                "-b:a": "128k",
                "-f": "mp4",
                "-movflags": "faststart",
            },
            # High quality archival
            "high_quality": {
                "-c:v": "libx264",
                "-preset": "slow",
                "-crf": "18",
                "-c:a": "aac",
                "-b:a": "192k",
                "-f": "mp4",
            },
            # Mobile optimized
            "mobile_optimized": {
                "-c:v": "libx264",
                "-preset": "fast",
                "-crf": "28",
                "-vf": "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease",
                "-maxrate": "1M",
                "-bufsize": "2M",
                "-c:a": "aac",
                "-b:a": "96k",
                "-f": "mp4",
                "-movflags": "faststart",
            },
            # Ultra compression
            "ultra_compress": {
                "-c:v": "libx265",
                "-preset": "medium",
                "-crf": "32",
                "-c:a": "aac",
                "-b:a": "64k",
                "-f": "mp4",
            },
            # WebM for web
            "webm_web": {
                "-c:v": "libvpx-vp9",
                "-crf": "30",
                "-b:v": "0",
                "-maxrate": "2M",
                "-bufsize": "4M",
                "-c:a": "libopus",
                "-b:a": "128k",
                "-f": "webm",
            },
            # Audio extraction
            "audio_only": {"-vn": "", "-c:a": "mp3", "-b:a": "192k", "-f": "mp3"},
            # Thumbnail extraction
            "thumbnail": {
                "-vf": "thumbnail,scale=320:240:force_original_aspect_ratio=decrease",
                "-frames:v": "1",
                "-f": "image2",
                "-q:v": "2",
            },
        }

        return profiles.get(profile_name)


# Shared instance
ffmpeg_converter = FFmpegConverter()
