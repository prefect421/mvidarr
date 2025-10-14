"""
FFmpeg Video Streaming and Process Management

Provides async video streaming with FFmpeg transcoding and process lifecycle management
including cancellation support.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, Optional

from src.services.ffmpeg_progress import ffmpeg_progress_monitor
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_streaming")


class FFmpegStreamer:
    """Manages FFmpeg streaming operations and process lifecycle"""

    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def stream_video_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Async video streaming with FFmpeg transcoding

        Args:
            video_path: Path to video file
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Yields:
            bytes: Video data chunks
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # FFmpeg command for streaming with progress output
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "mp4",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-progress",
            "pipe:2",  # Progress to stderr
            "-",  # Output to stdout
        ]

        logger.info(f"Starting async FFmpeg streaming: {video_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            if job_id:
                self.active_processes[job_id] = process

            # Start progress monitoring task
            progress_task = None
            if job_id or progress_callback:
                progress_task = asyncio.create_task(
                    ffmpeg_progress_monitor.monitor_ffmpeg_progress(
                        process.stderr, job_id, progress_callback
                    )
                )

            # Stream video data
            chunk_size = 8192
            while True:
                chunk = await process.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk

            # Wait for process completion
            await process.wait()

            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"FFmpeg streaming error for {video_path}: {e}")
            if job_id and job_id in self.active_processes:
                del self.active_processes[job_id]
            raise
        finally:
            if job_id and job_id in self.active_processes:
                del self.active_processes[job_id]

    async def cancel_operation(self, job_id: str) -> bool:
        """
        Cancel an active FFmpeg operation

        Args:
            job_id: Job ID to cancel

        Returns:
            bool: True if cancellation successful
        """
        if job_id not in self.active_processes:
            logger.warning(f"No active process found for job_id: {job_id}")
            return False

        try:
            process = self.active_processes[job_id]
            process.terminate()

            # Wait for termination with timeout
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                process.kill()
                await process.wait()

            del self.active_processes[job_id]

            logger.info(f"Successfully cancelled FFmpeg operation: {job_id}")

            # Update job status
            await ffmpeg_progress_monitor.update_job_progress(
                job_id,
                {
                    "stage": "cancelled",
                    "progress": 0,
                    "status": "cancelled",
                    "message": "Operation cancelled by user",
                },
            )

            return True

        except Exception as e:
            logger.error(f"Error cancelling FFmpeg operation {job_id}: {e}")
            return False


# Shared instance
ffmpeg_streamer = FFmpegStreamer()
