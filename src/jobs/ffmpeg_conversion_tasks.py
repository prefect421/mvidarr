"""
FFmpeg video format conversion background tasks

Provides Celery tasks for async video format conversion with quality optimization,
multiple profiles, and real-time progress tracking.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional

from src.jobs.base_task import BaseTask
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.ffmpeg_conversion")


class FFmpegVideoConversionTask(BaseTask):
    """Background task for video format conversion"""

    name = "ffmpeg.convert_video"
    description = "Convert video files to different formats"

    async def execute_async(
        self, input_path: str, output_path: str, format_options: Dict, **kwargs
    ) -> Dict:
        """
        Convert video to different format

        Args:
            input_path: Input video file path
            output_path: Output video file path
            format_options: FFmpeg conversion options
            **kwargs: Additional task arguments

        Returns:
            Dict: Conversion results
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input video file not found: {input_path}")

        try:
            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Update task progress
            await self.update_progress(
                5, f"Starting video conversion: {input_file.name} -> {output_file.name}"
            )

            # Perform video conversion
            success = await ffmpeg_stream_manager.convert_video_async(
                input_file,
                output_file,
                format_options,
                job_id=self.task_id,
                progress_callback=self._progress_callback,
            )

            if success and output_file.exists():
                file_size = output_file.stat().st_size

                await self.update_progress(
                    100,
                    f"Video conversion completed: {output_file.name} ({file_size // 1024 // 1024}MB)",
                )

                return {
                    "success": True,
                    "input_path": str(input_file),
                    "output_path": str(output_file),
                    "output_size": file_size,
                    "format_options": format_options,
                }
            else:
                error_msg = f"Video conversion failed: output file not created"
                logger.error(error_msg)

                await self.update_progress(0, error_msg)

                return {
                    "success": False,
                    "error": error_msg,
                    "input_path": str(input_file),
                    "output_path": str(output_file),
                }

        except Exception as e:
            error_msg = f"Video conversion failed for {input_file.name}: {e}"
            logger.error(error_msg)

            await self.update_progress(0, error_msg)

            return {
                "success": False,
                "error": error_msg,
                "input_path": str(input_file),
                "output_path": str(output_path),
            }

    def _progress_callback(self, progress_data: Dict):
        """Handle progress updates from FFmpeg stream manager"""
        try:
            # Convert progress data to task progress format
            stage = progress_data.get("stage", "processing")
            status = progress_data.get("status", "running")
            message = progress_data.get("message", "Converting video")
            progress = progress_data.get("progress", 0)

            # Update task progress asynchronously
            asyncio.create_task(self.update_progress(progress, status, message))

        except Exception as e:
            logger.warning(f"Error in progress callback: {e}")


class FFmpegAdvancedFormatConversionTask(BaseTask):
    """Advanced video format conversion with multiple profile options and quality optimization"""

    name = "ffmpeg.advanced_convert"
    description = "Advanced video format conversion with quality optimization and multiple profiles"

    async def execute_async(
        self,
        input_path: str,
        output_path: str,
        conversion_profile: str,
        custom_options: Optional[Dict] = None,
        quality_target: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """
        Perform advanced video format conversion with quality optimization

        Args:
            input_path: Input video file path
            output_path: Output video file path
            conversion_profile: Target conversion profile (web_optimized, high_quality, mobile_optimized, etc.)
            custom_options: Additional custom FFmpeg options
            quality_target: Target quality level (maintain, improve, compress)
            **kwargs: Additional task arguments

        Returns:
            Dict: Advanced conversion results with quality analysis
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input video file not found: {input_path}")

        try:
            await self.update_progress(
                5,
                f"Starting advanced conversion: {input_file.name} -> {conversion_profile}",
            )

            # Analyze input video quality first
            input_metadata = await ffmpeg_stream_manager.extract_metadata_async(
                input_file,
                job_id=self.task_id,
                progress_callback=self._progress_callback,
            )

            await self.update_progress(
                15,
                f"Input analysis complete: {input_metadata.get('quality', 'unknown')} quality",
            )

            # Perform quality analysis to optimize conversion
            input_quality = await ffmpeg_stream_manager.analyze_video_quality_async(
                input_file,
                job_id=self.task_id,
                progress_callback=self._progress_callback,
            )

            await self.update_progress(
                25,
                f"Quality analysis complete: {input_quality['quality_metrics']['overall_score']}/100 score",
            )

            # Execute advanced conversion
            conversion_result = (
                await ffmpeg_stream_manager.convert_video_advanced_async(
                    input_file,
                    output_file,
                    conversion_profile,
                    custom_options,
                    job_id=self.task_id,
                    progress_callback=self._progress_callback,
                )
            )

            if conversion_result["success"]:
                await self.update_progress(
                    95,
                    f"Conversion complete: {output_file.name} ({conversion_result.get('file_size', 0) // 1024 // 1024}MB)",
                )

                # Analyze output quality for comparison
                output_quality = (
                    await ffmpeg_stream_manager.analyze_video_quality_async(
                        output_file, job_id=self.task_id
                    )
                )

                await self.update_progress(
                    100,
                    f"Advanced conversion completed with {conversion_result.get('size_reduction', 0):.1f}% size optimization",
                )

                return {
                    "success": True,
                    "input_path": str(input_file),
                    "output_path": str(output_file),
                    "conversion_profile": conversion_profile,
                    "input_quality": input_quality,
                    "output_quality": output_quality,
                    "conversion_metrics": {
                        "size_reduction_percent": conversion_result.get(
                            "size_reduction", 0
                        ),
                        "conversion_time": conversion_result.get("conversion_time", 0),
                        "quality_improvement": output_quality["quality_metrics"][
                            "overall_score"
                        ]
                        - input_quality["quality_metrics"]["overall_score"],
                        "output_file_size": conversion_result.get("file_size", 0),
                    },
                    "recommendations": self._generate_conversion_recommendations(
                        input_quality, output_quality
                    ),
                }
            else:
                error_msg = conversion_result.get("error", "Advanced conversion failed")
                await self.update_progress(0, error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "input_path": str(input_file),
                    "output_path": str(output_file),
                }

        except Exception as e:
            error_msg = f"Advanced format conversion failed for {input_file.name}: {e}"
            logger.error(error_msg)
            await self.update_progress(0, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "input_path": str(input_file),
                "output_path": str(output_file),
            }

    def _generate_conversion_recommendations(
        self, input_quality: Dict, output_quality: Dict
    ) -> List[str]:
        """Generate recommendations based on conversion results"""
        recommendations = []

        input_score = input_quality["quality_metrics"]["overall_score"]
        output_score = output_quality["quality_metrics"]["overall_score"]

        if output_score > input_score:
            recommendations.append(
                f"Quality improved by {output_score - input_score} points"
            )
        elif output_score < input_score - 10:
            recommendations.append(
                "Consider using higher quality settings to maintain quality"
            )

        output_codec = output_quality["metadata"].get("video_codec", "").lower()
        if "h265" in output_codec or "hevc" in output_codec:
            recommendations.append(
                "H.265 codec provides excellent compression efficiency"
            )

        return recommendations

    def _progress_callback(self, progress_data: Dict):
        """Handle progress updates from FFmpeg stream manager"""
        try:
            stage = progress_data.get("stage", "processing")
            status = progress_data.get("status", "running")
            message = progress_data.get("message", "Advanced conversion processing")
            progress = progress_data.get("progress", 0)

            # Scale progress for advanced conversion (25-95%)
            scaled_progress = 25 + int(progress * 0.7)

            asyncio.create_task(
                self.update_progress(
                    scaled_progress, status, f"Advanced conversion: {message}"
                )
            )

        except Exception as e:
            logger.warning(f"Error in advanced conversion progress callback: {e}")


# Convenience functions for task submission
async def submit_video_conversion_task(
    input_path: str,
    output_path: str,
    format_options: Dict,
    priority: str = "normal",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit video conversion task

    Args:
        input_path: Input video file path
        output_path: Output video file path
        format_options: FFmpeg conversion options
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegVideoConversionTask()
    return await task.submit(
        input_path=input_path,
        output_path=output_path,
        format_options=format_options,
        priority=priority,
        user_id=user_id,
    )


async def submit_advanced_format_conversion_task(
    input_path: str,
    output_path: str,
    conversion_profile: str,
    custom_options: Optional[Dict] = None,
    quality_target: Optional[str] = None,
    priority: str = "normal",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit advanced video format conversion task

    Args:
        input_path: Input video file path
        output_path: Output video file path
        conversion_profile: Target conversion profile
        custom_options: Additional custom FFmpeg options
        quality_target: Target quality level
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegAdvancedFormatConversionTask()
    return await task.submit(
        input_path=input_path,
        output_path=output_path,
        conversion_profile=conversion_profile,
        custom_options=custom_options,
        quality_target=quality_target,
        priority=priority,
        user_id=user_id,
    )
