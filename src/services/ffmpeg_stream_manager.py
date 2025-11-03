"""
FFmpeg Stream Manager for async video processing operations

REFACTORED: This is now an aggregator module that combines functionality from:
- ffmpeg_metadata: Metadata extraction and quality analysis
- ffmpeg_conversion: Video format conversion
- ffmpeg_thumbnail: Thumbnail generation
- ffmpeg_streaming: Video streaming and process management
- ffmpeg_progress: Progress monitoring and job updates

This module maintains backward compatibility with existing code while providing
a modular architecture for better maintainability.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional

from src.services.ffmpeg_conversion import ffmpeg_converter
from src.services.ffmpeg_metadata import ffmpeg_metadata_extractor
from src.services.ffmpeg_progress import ffmpeg_progress_monitor
from src.services.ffmpeg_streaming import ffmpeg_streamer
from src.services.ffmpeg_thumbnail import ffmpeg_thumbnail_generator
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_stream_manager")


class FFmpegStreamManager:
    """
    Aggregator class for FFmpeg operations with backward compatibility

    This class delegates to specialized modules while maintaining the original API
    """

    def __init__(self):
        # Initialize component managers
        self.metadata_extractor = ffmpeg_metadata_extractor
        self.converter = ffmpeg_converter
        self.thumbnail_generator = ffmpeg_thumbnail_generator
        self.streamer = ffmpeg_streamer
        self.progress_monitor = ffmpeg_progress_monitor

        # Maintain active_processes for backward compatibility
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}

    # ==================== Streaming Operations ====================

    async def stream_video_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Delegate to FFmpegStreamer"""
        async for chunk in self.streamer.stream_video_async(
            video_path, job_id, progress_callback
        ):
            yield chunk

    async def cancel_operation(self, job_id: str) -> bool:
        """Delegate to FFmpegStreamer"""
        return await self.streamer.cancel_operation(job_id)

    # ==================== Metadata Operations ====================

    async def extract_metadata_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Delegate to FFmpegMetadataExtractor"""
        return await self.metadata_extractor.extract_metadata_async(
            video_path, job_id, progress_callback
        )

    async def analyze_video_quality_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Delegate to FFmpegMetadataExtractor"""
        return await self.metadata_extractor.analyze_video_quality_async(
            video_path, job_id, progress_callback
        )

    # ==================== Conversion Operations ====================

    async def convert_video_async(
        self,
        input_path: Path,
        output_path: Path,
        format_options: Dict,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> bool:
        """Delegate to FFmpegConverter"""
        return await self.converter.convert_video_async(
            input_path, output_path, format_options, job_id, progress_callback
        )

    async def convert_video_advanced_async(
        self,
        input_path: Path,
        output_path: Path,
        conversion_profile: str,
        custom_options: Optional[Dict] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Delegate to FFmpegConverter"""
        return await self.converter.convert_video_advanced_async(
            input_path,
            output_path,
            conversion_profile,
            custom_options,
            job_id,
            progress_callback,
        )

    # ==================== Thumbnail Operations ====================

    async def generate_thumbnail_async(
        self,
        video_path: Path,
        output_path: Path,
        timestamp: Optional[str] = None,
        size: Optional[str] = "320x240",
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Delegate to FFmpegThumbnailGenerator"""
        return await self.thumbnail_generator.generate_thumbnail_async(
            video_path, output_path, timestamp, size, job_id, progress_callback
        )

    async def generate_bulk_thumbnails_async(
        self,
        video_paths: List[Path],
        output_dir: Path,
        size: str = "320x240",
        batch_size: int = 5,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Delegate to FFmpegThumbnailGenerator"""
        return await self.thumbnail_generator.generate_bulk_thumbnails_async(
            video_paths, output_dir, size, batch_size, job_id, progress_callback
        )

    # ==================== Progress Monitoring ====================

    async def _monitor_ffmpeg_progress(
        self,
        stderr_stream: asyncio.StreamReader,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        operation: str = "ffmpeg_processing",
    ):
        """Delegate to FFmpegProgressMonitor"""
        await self.progress_monitor.monitor_ffmpeg_progress(
            stderr_stream, job_id, progress_callback, operation
        )

    async def _update_job_progress(self, job_id: str, progress_data: Dict):
        """Delegate to FFmpegProgressMonitor"""
        await self.progress_monitor.update_job_progress(job_id, progress_data)

    # ==================== Helper Methods ====================

    def _get_conversion_profile(self, profile_name: str) -> Optional[Dict]:
        """Delegate to FFmpegConverter"""
        return self.converter._get_conversion_profile(profile_name)


# Global instance for backward compatibility
ffmpeg_stream_manager = FFmpegStreamManager()
