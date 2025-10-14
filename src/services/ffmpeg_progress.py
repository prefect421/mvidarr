"""
FFmpeg Progress Monitoring and Job Updates

Handles real-time progress tracking for FFmpeg operations with WebSocket integration
and Redis-based job progress updates.
"""

import asyncio
import re
import time
from typing import Callable, Dict, Optional

from src.jobs.redis_manager import redis_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_progress")


class FFmpegProgressMonitor:
    """Monitors and tracks FFmpeg operation progress"""

    async def monitor_ffmpeg_progress(
        self,
        stderr_stream: asyncio.StreamReader,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        operation: str = "ffmpeg_processing",
    ):
        """
        Monitor FFmpeg progress from stderr stream

        Args:
            stderr_stream: FFmpeg stderr stream
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates
            operation: Type of operation being monitored
        """
        try:
            duration_pattern = re.compile(
                r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})"
            )
            time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")

            total_duration = None

            async for line in stderr_stream:
                try:
                    line_str = line.decode("utf-8", errors="ignore").strip()

                    # Parse duration from initial output
                    if total_duration is None:
                        duration_match = duration_pattern.search(line_str)
                        if duration_match:
                            hours, minutes, seconds, centiseconds = map(
                                int, duration_match.groups()
                            )
                            total_duration = (
                                hours * 3600
                                + minutes * 60
                                + seconds
                                + centiseconds / 100
                            )
                            logger.debug(f"Detected video duration: {total_duration}s")

                    # Parse current time progress
                    time_match = time_pattern.search(line_str)
                    if time_match and total_duration:
                        hours, minutes, seconds, centiseconds = map(
                            int, time_match.groups()
                        )
                        current_time = (
                            hours * 3600 + minutes * 60 + seconds + centiseconds / 100
                        )

                        progress_percent = min(
                            100, int((current_time / total_duration) * 100)
                        )

                        progress_data = {
                            "stage": operation,
                            "progress": progress_percent,
                            "status": "running",
                            "message": f"Processing: {progress_percent}% complete",
                            "current_time": current_time,
                            "total_duration": total_duration,
                        }

                        # Send progress update
                        if progress_callback:
                            progress_callback(progress_data)

                        if job_id:
                            await self.update_job_progress(job_id, progress_data)

                        # Throttle progress updates (every 5%)
                        if progress_percent % 5 == 0:
                            logger.debug(
                                f"FFmpeg progress: {progress_percent}% ({current_time:.1f}s / {total_duration:.1f}s)"
                            )

                except Exception as e:
                    logger.debug(f"Error parsing FFmpeg progress line: {e}")
                    continue

        except asyncio.CancelledError:
            logger.debug("FFmpeg progress monitoring cancelled")
        except Exception as e:
            logger.error(f"Error monitoring FFmpeg progress: {e}")

    async def update_job_progress(self, job_id: str, progress_data: Dict):
        """
        Update job progress in Redis and publish to WebSocket

        Args:
            job_id: Job ID to update
            progress_data: Progress information dictionary
        """
        try:
            # Update job progress in Redis
            job_key = f"job_progress:{job_id}"
            progress_update = {
                "timestamp": time.time(),
                "job_id": job_id,
                **progress_data,
            }

            await redis_manager.set_json(job_key, progress_update, ttl=3600)

            # Publish progress update to WebSocket channel
            await redis_manager.publish_json(f"job_updates:{job_id}", progress_update)

            # Also publish to general job updates channel
            await redis_manager.publish_json("job_updates", progress_update)

        except Exception as e:
            logger.error(f"Error updating job progress for {job_id}: {e}")


# Shared instance
ffmpeg_progress_monitor = FFmpegProgressMonitor()
