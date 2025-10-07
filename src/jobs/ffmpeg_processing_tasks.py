"""
FFmpeg processing background tasks for video operations

Provides Celery tasks for async video processing, metadata extraction,
and format conversion with real-time progress tracking.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.jobs.base_task import BaseTask
from src.jobs.celery_app import celery_app
from src.jobs.redis_manager import redis_manager
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.ffmpeg_processing")


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


class FFmpegConcurrentQualityAnalysisTask(BaseTask):
    """Concurrent video quality analysis and optimization recommendations"""

    name = "ffmpeg.concurrent_quality_analysis"
    description = "Analyze video quality with concurrent processing and optimization recommendations"

    async def execute_async(
        self,
        video_paths: List[str],
        batch_size: int = 10,
        generate_upgrade_plan: bool = True,
        **kwargs,
    ) -> Dict:
        """
        Perform concurrent quality analysis on multiple videos

        Args:
            video_paths: List of video file paths to analyze
            batch_size: Number of videos to process concurrently
            generate_upgrade_plan: Whether to generate quality upgrade recommendations
            **kwargs: Additional task arguments

        Returns:
            Dict: Concurrent quality analysis results with upgrade recommendations
        """
        total_videos = len(video_paths)
        processed_videos = 0
        analysis_results = []
        upgrade_candidates = []

        try:
            await self.update_progress(
                5, f"Starting concurrent quality analysis for {total_videos} videos"
            )

            # Process videos in batches for concurrent analysis
            for i in range(0, total_videos, batch_size):
                batch = video_paths[i : i + batch_size]

                # Execute batch concurrently
                batch_results = await asyncio.gather(
                    *[
                        self._analyze_single_video_quality(
                            video_path, processed_videos + j + 1, total_videos
                        )
                        for j, video_path in enumerate(batch)
                    ],
                    return_exceptions=True,
                )

                # Process batch results
                for j, result in enumerate(batch_results):
                    processed_videos += 1

                    if isinstance(result, Exception):
                        analysis_results.append(
                            {
                                "video_path": batch[j],
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        analysis_results.append(result)

                        # Identify upgrade candidates
                        if result["success"] and generate_upgrade_plan:
                            quality_score = (
                                result.get("quality_analysis", {})
                                .get("quality_metrics", {})
                                .get("overall_score", 100)
                            )
                            if (
                                quality_score < 70
                            ):  # Videos with quality score < 70 are upgrade candidates
                                upgrade_candidates.append(
                                    {
                                        "video_path": batch[j],
                                        "current_quality_score": quality_score,
                                        "improvement_potential": min(
                                            90 - quality_score, 30
                                        ),
                                        "recommended_profile": self._recommend_conversion_profile(
                                            result
                                        ),
                                    }
                                )

                    # Update progress
                    progress = int((processed_videos / total_videos) * 85) + 10
                    await self.update_progress(
                        progress, f"Analyzed {processed_videos}/{total_videos} videos"
                    )

            # Generate comprehensive quality report
            quality_summary = self._generate_quality_summary(
                analysis_results, upgrade_candidates
            )

            await self.update_progress(
                100,
                f"Quality analysis complete: {len(upgrade_candidates)} videos recommended for upgrade",
            )

            return {
                "success": True,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
                "analysis_results": analysis_results,
                "upgrade_candidates": upgrade_candidates,
                "quality_summary": quality_summary,
                "batch_processing_stats": {
                    "batch_size": batch_size,
                    "total_batches": (total_videos + batch_size - 1) // batch_size,
                    "concurrent_processing": True,
                },
            }

        except Exception as e:
            error_msg = f"Concurrent quality analysis failed: {e}"
            logger.error(error_msg)
            await self.update_progress(0, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
            }

    async def _analyze_single_video_quality(
        self, video_path: str, video_number: int, total_videos: int
    ) -> Dict:
        """Analyze quality for a single video as part of concurrent processing"""
        try:
            video_file = Path(video_path)

            if not video_file.exists():
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": f"File not found: {video_path}",
                }

            logger.debug(
                f"Analyzing video quality {video_number}/{total_videos}: {video_file.name}"
            )

            # Perform quality analysis
            quality_analysis = await ffmpeg_stream_manager.analyze_video_quality_async(
                video_file, job_id=f"{self.task_id}_video_{video_number}"
            )

            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": True,
                **quality_analysis,
            }

        except Exception as e:
            logger.error(f"Error analyzing video quality for {video_path}: {e}")
            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": False,
                "error": str(e),
            }

    def _recommend_conversion_profile(self, analysis_result: Dict) -> str:
        """Recommend optimal conversion profile based on quality analysis"""
        if not analysis_result["success"]:
            return "web_optimized"  # Default fallback

        quality_metrics = analysis_result.get("quality_analysis", {}).get(
            "quality_metrics", {}
        )
        metadata = analysis_result.get("metadata", {})

        resolution_score = quality_metrics.get("resolution_score", 0)
        codec_score = quality_metrics.get("codec_score", 0)
        height = metadata.get("height", 0)

        # Recommend profile based on current quality and resolution
        if height >= 1080 and codec_score < 80:
            return "high_quality"  # High resolution but poor codec
        elif height < 720:
            return "mobile_optimized"  # Low resolution, optimize for mobile
        elif codec_score < 60:
            return "web_optimized"  # Poor codec, optimize for web
        else:
            return "ultra_compress"  # Good quality, focus on size reduction

    def _generate_quality_summary(
        self, analysis_results: List[Dict], upgrade_candidates: List[Dict]
    ) -> Dict:
        """Generate comprehensive quality summary statistics"""
        successful_analyses = [r for r in analysis_results if r["success"]]

        if not successful_analyses:
            return {
                "total_analyzed": 0,
                "average_quality_score": 0,
                "quality_distribution": {},
                "upgrade_potential": 0,
            }

        quality_scores = [
            r.get("quality_analysis", {})
            .get("quality_metrics", {})
            .get("overall_score", 0)
            for r in successful_analyses
        ]

        # Quality distribution
        quality_distribution = {
            "excellent (90-100)": len([s for s in quality_scores if s >= 90]),
            "very_good (75-89)": len([s for s in quality_scores if 75 <= s < 90]),
            "good (60-74)": len([s for s in quality_scores if 60 <= s < 75]),
            "fair (45-59)": len([s for s in quality_scores if 45 <= s < 60]),
            "poor (0-44)": len([s for s in quality_scores if s < 45]),
        }

        return {
            "total_analyzed": len(successful_analyses),
            "average_quality_score": (
                sum(quality_scores) / len(quality_scores) if quality_scores else 0
            ),
            "quality_distribution": quality_distribution,
            "upgrade_candidates": len(upgrade_candidates),
            "upgrade_potential": sum(
                [c["improvement_potential"] for c in upgrade_candidates]
            ),
            "analysis_coverage": (
                (len(successful_analyses) / len(analysis_results)) * 100
                if analysis_results
                else 0
            ),
        }


class FFmpegBulkThumbnailCreationTask(BaseTask):
    """Bulk thumbnail creation with progress tracking and multiple size options"""

    name = "ffmpeg.bulk_thumbnails"
    description = (
        "Create thumbnails for multiple videos with progress tracking and size options"
    )

    async def execute_async(
        self,
        video_paths: List[str],
        output_directory: str,
        thumbnail_sizes: List[Tuple[int, int]] = None,
        timestamps_per_video: int = 3,
        batch_size: int = 5,
        **kwargs,
    ) -> Dict:
        """
        Generate thumbnails for multiple videos with progress tracking

        Args:
            video_paths: List of video file paths
            output_directory: Directory to save thumbnails
            thumbnail_sizes: List of (width, height) tuples for thumbnail sizes
            timestamps_per_video: Number of thumbnails per video
            batch_size: Number of videos to process concurrently
            **kwargs: Additional task arguments

        Returns:
            Dict: Bulk thumbnail creation results
        """
        if thumbnail_sizes is None:
            thumbnail_sizes = [
                (320, 240),
                (640, 480),
                (1280, 720),
            ]  # Small, medium, large

        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        total_videos = len(video_paths)
        processed_videos = 0
        successful_thumbnails = 0
        failed_thumbnails = 0
        thumbnail_results = []

        try:
            await self.update_progress(
                5, f"Starting bulk thumbnail creation for {total_videos} videos"
            )

            # Process videos in batches
            for i in range(0, total_videos, batch_size):
                batch = video_paths[i : i + batch_size]

                # Execute batch concurrently
                batch_results = await asyncio.gather(
                    *[
                        self._create_video_thumbnails(
                            video_path,
                            output_dir,
                            thumbnail_sizes,
                            timestamps_per_video,
                            processed_videos + j + 1,
                            total_videos,
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
                        thumbnail_results.append(
                            {
                                "video_path": batch[j],
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        if result["success"]:
                            successful_thumbnails += len(result["thumbnails"])
                        else:
                            failed_thumbnails += 1
                        thumbnail_results.append(result)

                    # Update progress
                    progress = int((processed_videos / total_videos) * 90) + 5
                    await self.update_progress(
                        progress,
                        f"Created thumbnails for {processed_videos}/{total_videos} videos",
                    )

            # Generate thumbnail summary
            thumbnail_summary = self._generate_thumbnail_summary(
                thumbnail_results, thumbnail_sizes
            )

            await self.update_progress(
                100,
                f"Bulk thumbnail creation complete: {successful_thumbnails} thumbnails created",
            )

            return {
                "success": True,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
                "successful_thumbnails": successful_thumbnails,
                "failed_thumbnails": failed_thumbnails,
                "thumbnail_results": thumbnail_results,
                "thumbnail_summary": thumbnail_summary,
                "output_directory": str(output_dir),
            }

        except Exception as e:
            error_msg = f"Bulk thumbnail creation failed: {e}"
            logger.error(error_msg)
            await self.update_progress(0, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "total_videos": total_videos,
                "processed_videos": processed_videos,
            }

    async def _create_video_thumbnails(
        self,
        video_path: str,
        output_dir: Path,
        thumbnail_sizes: List[Tuple[int, int]],
        timestamps_per_video: int,
        video_number: int,
        total_videos: int,
    ) -> Dict:
        """Create thumbnails for a single video"""
        try:
            video_file = Path(video_path)

            if not video_file.exists():
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": f"File not found: {video_path}",
                }

            logger.debug(
                f"Creating thumbnails for video {video_number}/{total_videos}: {video_file.name}"
            )

            # Create video-specific output directory
            video_output_dir = output_dir / video_file.stem
            video_output_dir.mkdir(parents=True, exist_ok=True)

            # Get video metadata for duration and optimal timestamps
            metadata = await ffmpeg_stream_manager.extract_metadata_async(video_file)
            duration = metadata.get("duration", 0)

            if duration <= 0:
                return {
                    "video_path": video_path,
                    "success": False,
                    "error": "Could not determine video duration",
                }

            # Calculate optimal timestamps (avoid first/last 10%)
            start_time = duration * 0.1
            end_time = duration * 0.9

            if timestamps_per_video == 1:
                timestamps = [duration / 2]
            else:
                step = (end_time - start_time) / (timestamps_per_video - 1)
                timestamps = [
                    start_time + (i * step) for i in range(timestamps_per_video)
                ]

            # Generate thumbnails for each timestamp and size
            thumbnails = []
            for timestamp in timestamps:
                for width, height in thumbnail_sizes:
                    thumbnail_result = await self._generate_single_thumbnail(
                        video_file, video_output_dir, timestamp, width, height
                    )
                    thumbnails.append(thumbnail_result)

            successful_thumbs = [t for t in thumbnails if t["success"]]

            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": len(successful_thumbs) > 0,
                "thumbnails": thumbnails,
                "successful_count": len(successful_thumbs),
                "total_count": len(thumbnails),
                "video_duration": duration,
                "output_directory": str(video_output_dir),
            }

        except Exception as e:
            logger.error(f"Error creating thumbnails for {video_path}: {e}")
            return {
                "video_path": video_path,
                "video_number": video_number,
                "success": False,
                "error": str(e),
            }

    async def _generate_single_thumbnail(
        self,
        video_file: Path,
        output_dir: Path,
        timestamp: float,
        width: int,
        height: int,
    ) -> Dict:
        """Generate a single thumbnail with specific parameters"""
        try:
            thumbnail_name = f"thumb_{timestamp:.1f}s_{width}x{height}.jpg"
            thumbnail_path = output_dir / thumbnail_name

            # Use FFmpeg stream manager for thumbnail generation
            result = await ffmpeg_stream_manager.generate_thumbnail_async(
                video_file,
                thumbnail_path,
                timestamp=str(timestamp),
                size=f"{width}x{height}",
                job_id=f"{self.task_id}_thumb",
            )

            return {
                "timestamp": timestamp,
                "size": f"{width}x{height}",
                "path": str(thumbnail_path),
                "success": result["success"],
                "file_size": result.get("file_size", 0) if result["success"] else 0,
                "generation_time": result.get("generation_time", 0),
            }

        except Exception as e:
            logger.warning(
                f"Failed to generate thumbnail at {timestamp}s, {width}x{height}: {e}"
            )
            return {
                "timestamp": timestamp,
                "size": f"{width}x{height}",
                "success": False,
                "error": str(e),
            }

    def _generate_thumbnail_summary(
        self, thumbnail_results: List[Dict], thumbnail_sizes: List[Tuple[int, int]]
    ) -> Dict:
        """Generate summary statistics for thumbnail creation"""
        successful_videos = [r for r in thumbnail_results if r["success"]]
        total_successful_thumbs = sum(r["successful_count"] for r in successful_videos)
        total_thumbs_attempted = sum(
            r["total_count"] for r in thumbnail_results if "total_count" in r
        )

        # Size distribution
        size_stats = {}
        for width, height in thumbnail_sizes:
            size_key = f"{width}x{height}"
            size_count = 0
            for result in successful_videos:
                size_count += len(
                    [
                        t
                        for t in result["thumbnails"]
                        if t["size"] == size_key and t["success"]
                    ]
                )
            size_stats[size_key] = size_count

        return {
            "videos_processed": len(thumbnail_results),
            "videos_successful": len(successful_videos),
            "thumbnails_created": total_successful_thumbs,
            "thumbnails_attempted": total_thumbs_attempted,
            "success_rate": (
                (total_successful_thumbs / total_thumbs_attempted * 100)
                if total_thumbs_attempted > 0
                else 0
            ),
            "size_distribution": size_stats,
            "thumbnail_sizes": [f"{w}x{h}" for w, h in thumbnail_sizes],
        }


class FFmpegVideoValidationTask(BaseTask):
    """Enhanced video file integrity validation with comprehensive checks"""

    name = "ffmpeg.validate_video"
    description = "Comprehensive video file integrity validation with detailed analysis"

    async def execute_async(
        self, video_path: str, comprehensive_check: bool = True, **kwargs
    ) -> Dict:
        """
        Enhanced video file integrity validation

        Args:
            video_path: Path to video file to validate
            comprehensive_check: Whether to perform comprehensive validation
            **kwargs: Additional task arguments

        Returns:
            Dict: Enhanced validation results with detailed analysis
        """
        video_file = Path(video_path)

        if not video_file.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        try:
            await self.update_progress(
                10, f"Starting enhanced validation for {video_file.name}"
            )

            # Basic metadata extraction and validation
            metadata = await ffmpeg_stream_manager.extract_metadata_async(
                video_file,
                job_id=self.task_id,
                progress_callback=self._progress_callback,
            )

            await self.update_progress(
                30, "Metadata validation complete, analyzing video integrity"
            )

            # Enhanced validation checks
            validation_results = {
                "file_exists": video_file.exists(),
                "file_readable": video_file.is_file(),
                "has_video_stream": metadata.get("video_codec") is not None,
                "has_audio_stream": metadata.get("audio_codec") is not None,
                "has_duration": metadata.get("duration") is not None
                and metadata["duration"] > 0,
                "has_resolution": metadata.get("width") is not None
                and metadata.get("height") is not None,
                "file_size_valid": video_file.stat().st_size > 1024,  # At least 1KB
                "codec_recognized": self._validate_codec_support(metadata),
                "aspect_ratio_valid": self._validate_aspect_ratio(metadata),
                "frame_rate_valid": self._validate_frame_rate(metadata),
            }

            # Perform comprehensive integrity check if requested
            if comprehensive_check:
                await self.update_progress(
                    60, "Performing comprehensive integrity analysis"
                )

                # Quality analysis for integrity assessment
                quality_analysis = (
                    await ffmpeg_stream_manager.analyze_video_quality_async(
                        video_file,
                        job_id=self.task_id,
                        progress_callback=self._progress_callback,
                    )
                )

                # Additional integrity checks
                integrity_checks = {
                    "quality_score_reasonable": quality_analysis["quality_metrics"][
                        "overall_score"
                    ]
                    > 10,
                    "bitrate_reasonable": self._validate_bitrate(metadata),
                    "duration_matches_filesize": self._validate_duration_filesize_ratio(
                        metadata, video_file
                    ),
                    "no_corruption_indicators": quality_analysis["quality_metrics"][
                        "overall_score"
                    ]
                    > 30,
                }

                validation_results.update(integrity_checks)

            # Calculate comprehensive validation score
            validation_score = (
                sum(validation_results.values()) / len(validation_results) * 100
            )
            is_valid = validation_score >= 80  # 80% or more checks must pass

            # Generate detailed validation report
            validation_report = self._generate_validation_report(
                validation_results, metadata, video_file
            )

            await self.update_progress(
                100,
                f"Enhanced validation complete: {'PASS' if is_valid else 'FAIL'} ({validation_score:.0f}% score)",
            )

            return {
                "success": True,
                "valid": is_valid,
                "validation_score": validation_score,
                "validation_results": validation_results,
                "validation_report": validation_report,
                "metadata": metadata,
                "video_path": str(video_file),
                "video_name": video_file.name,
                "file_size": video_file.stat().st_size,
                "comprehensive_check": comprehensive_check,
            }

        except Exception as e:
            error_msg = f"Enhanced video validation failed for {video_file.name}: {e}"
            logger.error(error_msg)
            await self.update_progress(0, error_msg)
            return {
                "success": False,
                "valid": False,
                "error": error_msg,
                "video_path": str(video_file),
            }

    def _validate_codec_support(self, metadata: Dict) -> bool:
        """Validate that video and audio codecs are recognized and supported"""
        video_codec = metadata.get("video_codec", "").lower()
        audio_codec = metadata.get("audio_codec", "").lower()

        supported_video_codecs = {
            "h264",
            "h265",
            "hevc",
            "vp8",
            "vp9",
            "av1",
            "mpeg4",
            "xvid",
            "divx",
        }
        supported_audio_codecs = {"aac", "mp3", "opus", "vorbis", "flac", "ac3", "dts"}

        video_supported = (
            any(codec in video_codec for codec in supported_video_codecs)
            if video_codec
            else False
        )
        audio_supported = (
            any(codec in audio_codec for codec in supported_audio_codecs)
            if audio_codec
            else True
        )  # Audio optional

        return video_supported and audio_supported

    def _validate_aspect_ratio(self, metadata: Dict) -> bool:
        """Validate that aspect ratio is reasonable"""
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not width or not height:
            return False

        aspect_ratio = width / height
        # Reasonable aspect ratios between 0.5 (portrait) and 3.0 (ultra-wide)
        return 0.5 <= aspect_ratio <= 3.0

    def _validate_frame_rate(self, metadata: Dict) -> bool:
        """Validate that frame rate is reasonable"""
        fps = metadata.get("fps", 0)

        if not fps:
            return False

        # Reasonable frame rates between 1 and 120 fps
        return 1.0 <= fps <= 120.0

    def _validate_bitrate(self, metadata: Dict) -> bool:
        """Validate that bitrate is reasonable for the video"""
        bitrate = metadata.get("bitrate", 0)
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not bitrate or not width or not height:
            return True  # Can't validate without data

        total_pixels = width * height
        bitrate_mbps = bitrate / 1000000

        # Very loose bounds - extremely low or high bitrates might indicate corruption
        min_bitrate = 0.01  # 10 kbps minimum
        max_bitrate = 100  # 100 Mbps maximum for normal videos

        return min_bitrate <= bitrate_mbps <= max_bitrate

    def _validate_duration_filesize_ratio(
        self, metadata: Dict, video_file: Path
    ) -> bool:
        """Validate that duration and file size are reasonably correlated"""
        duration = metadata.get("duration", 0)
        file_size = video_file.stat().st_size

        if not duration or duration <= 0:
            return False

        # Very loose bounds - looking for obvious corruption indicators
        size_per_second = file_size / duration

        # Minimum: ~1KB per second (very low quality)
        # Maximum: ~10MB per second (very high quality)
        return 1024 <= size_per_second <= 10 * 1024 * 1024

    def _generate_validation_report(
        self, validation_results: Dict, metadata: Dict, video_file: Path
    ) -> Dict:
        """Generate detailed validation report"""
        failed_checks = [
            check for check, passed in validation_results.items() if not passed
        ]
        passed_checks = [
            check for check, passed in validation_results.items() if passed
        ]

        # Categorize issues by severity
        critical_issues = []
        warnings = []

        for failed_check in failed_checks:
            if failed_check in ["file_exists", "has_video_stream", "file_size_valid"]:
                critical_issues.append(failed_check.replace("_", " ").title())
            else:
                warnings.append(failed_check.replace("_", " ").title())

        # Generate recommendations
        recommendations = []
        if not validation_results.get("has_audio_stream"):
            recommendations.append(
                "Consider adding audio track for better compatibility"
            )
        if not validation_results.get("codec_recognized"):
            recommendations.append("Convert to widely supported codec (H.264/AAC)")
        if not validation_results.get("quality_score_reasonable", True):
            recommendations.append(
                "Video quality appears very low - consider re-encoding"
            )

        return {
            "total_checks": len(validation_results),
            "passed_checks": len(passed_checks),
            "failed_checks": len(failed_checks),
            "critical_issues": critical_issues,
            "warnings": warnings,
            "recommendations": recommendations,
            "file_info": {
                "format": video_file.suffix,
                "size_mb": round(video_file.stat().st_size / 1024 / 1024, 2),
                "duration_minutes": round(metadata.get("duration", 0) / 60, 2),
                "resolution": f"{metadata.get('width', 0)}x{metadata.get('height', 0)}",
                "video_codec": metadata.get("video_codec", "unknown"),
                "audio_codec": metadata.get("audio_codec", "none"),
            },
        }

    def _progress_callback(self, progress_data: Dict):
        """Handle progress updates from FFmpeg stream manager"""
        try:
            stage = progress_data.get("stage", "validation")
            status = progress_data.get("status", "running")
            message = progress_data.get("message", "Validating video integrity")
            progress = progress_data.get("progress", 0)

            # Scale progress for validation portion (30-90%)
            scaled_progress = 30 + int(progress * 0.6)

            asyncio.create_task(
                self.update_progress(scaled_progress, status, f"Validation: {message}")
            )

        except Exception as e:
            logger.warning(f"Error in validation progress callback: {e}")


# Celery task for bulk thumbnail creation
@celery_app.task(bind=True, name="ffmpeg.bulk_thumbnails")
def bulk_thumbnail_creation(
    self,
    video_paths: List[str],
    output_directory: str,
    thumbnail_sizes: List[Tuple[int, int]] = None,
    timestamps_per_video: int = 3,
    batch_size: int = 5,
    priority: str = "normal",
    user_id: Optional[str] = None,
):
    """
    Generate thumbnails for multiple videos with progress tracking
    """
    import asyncio
    from pathlib import Path

    from src.jobs.redis_manager import redis_manager
    from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager

    if thumbnail_sizes is None:
        thumbnail_sizes = [(640, 480)]  # Standard thumbnail size

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_videos = len(video_paths)
    processed_videos = 0
    successful_thumbnails = 0
    errors = []

    # Update initial progress
    redis_manager.set_job_progress(
        self.request.id,
        {
            "percent": 0,
            "message": f"Starting thumbnail generation for {total_videos} videos",
            "status": "STARTED",
        },
    )

    try:
        for i, video_path in enumerate(video_paths):
            try:
                video_file = Path(video_path)

                # Update progress
                progress = int((i / total_videos) * 100)
                redis_manager.set_job_progress(
                    self.request.id,
                    {
                        "percent": progress,
                        "message": f"Processing video {i+1} of {total_videos}: {video_file.name}",
                        "status": "PROGRESS",
                        "current_step": f"Generating thumbnail for {video_file.name}",
                    },
                )

                # Generate thumbnail filename
                thumbnail_filename = f"{video_file.stem}_thumb.jpg"
                thumbnail_path = output_dir / thumbnail_filename

                # Generate thumbnail synchronously (since we're in a Celery worker)
                result = asyncio.run(
                    ffmpeg_stream_manager.generate_thumbnail_async(
                        video_path=video_file,
                        output_path=thumbnail_path,
                        timestamp=None,  # Auto-detect middle of video
                        size="640x480",
                    )
                )

                if result.get("success"):
                    successful_thumbnails += 1
                    logger.info(f"Generated thumbnail for video: {thumbnail_path}")

                    # Update database with thumbnail path
                    try:
                        from src.database.connection import get_db
                        from src.database.models import Video

                        with get_db() as db_session:
                            # Find the video by matching the file path
                            video_record = (
                                db_session.query(Video)
                                .filter(Video.local_path.like(f"%{video_file.name}"))
                                .first()
                            )

                            if video_record:
                                video_record.thumbnail_path = str(thumbnail_path)
                                db_session.commit()
                                logger.info(
                                    f"Updated database thumbnail_path for video ID {video_record.id}: {thumbnail_path}"
                                )
                            else:
                                logger.warning(
                                    f"Could not find video record for {video_file.name}"
                                )

                    except Exception as db_error:
                        logger.error(
                            f"Failed to update database for {video_file.name}: {db_error}"
                        )

                else:
                    error_msg = result.get("error", "Unknown error")
                    errors.append(f"{video_file.name}: {error_msg}")
                    logger.warning(
                        f"Failed to generate thumbnail for {video_file.name}: {error_msg}"
                    )

                processed_videos += 1

            except Exception as e:
                errors.append(f"{video_path}: {str(e)}")
                logger.error(f"Error generating thumbnail for {video_path}: {e}")

        # Final progress update
        redis_manager.set_job_progress(
            self.request.id,
            {
                "percent": 100,
                "message": f"Completed thumbnail generation: {successful_thumbnails} successful, {len(errors)} errors",
                "status": "SUCCESS",
            },
        )

        return {
            "success": True,
            "processed_videos": processed_videos,
            "successful_thumbnails": successful_thumbnails,
            "total_videos": total_videos,
            "errors": errors,
        }

    except Exception as e:
        redis_manager.set_job_progress(
            self.request.id,
            {"percent": 0, "message": f"Task failed: {str(e)}", "status": "FAILURE"},
        )
        raise


# Task registration
FFMPEG_TASKS = [
    FFmpegMetadataExtractionTask,
    FFmpegVideoConversionTask,
    FFmpegBulkMetadataTask,
    FFmpegAdvancedFormatConversionTask,
    FFmpegConcurrentQualityAnalysisTask,
    FFmpegBulkThumbnailCreationTask,
    FFmpegVideoValidationTask,
]


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


async def submit_video_validation_task(
    video_path: str, priority: str = "normal", user_id: Optional[str] = None
) -> str:
    """
    Submit video validation task

    Args:
        video_path: Path to video file to validate
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegVideoValidationTask()
    return await task.submit(video_path=video_path, priority=priority, user_id=user_id)


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


async def submit_concurrent_quality_analysis_task(
    video_paths: List[str],
    batch_size: int = 10,
    generate_upgrade_plan: bool = True,
    priority: str = "low",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit concurrent video quality analysis task

    Args:
        video_paths: List of video file paths to analyze
        batch_size: Number of videos to process concurrently
        generate_upgrade_plan: Whether to generate upgrade recommendations
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = FFmpegConcurrentQualityAnalysisTask()
    return await task.submit(
        video_paths=video_paths,
        batch_size=batch_size,
        generate_upgrade_plan=generate_upgrade_plan,
        priority=priority,
        user_id=user_id,
    )


def submit_bulk_thumbnail_creation_task(
    video_paths: List[str],
    output_directory: str,
    thumbnail_sizes: List[Tuple[int, int]] = None,
    timestamps_per_video: int = 3,
    batch_size: int = 5,
    priority: str = "normal",
    user_id: Optional[str] = None,
) -> str:
    """
    Submit bulk thumbnail creation task

    Args:
        video_paths: List of video file paths
        output_directory: Directory to save thumbnails
        thumbnail_sizes: List of (width, height) tuples
        timestamps_per_video: Number of thumbnails per video
        batch_size: Number of videos to process concurrently
        priority: Task priority (low, normal, high)
        user_id: Optional user ID for tracking

    Returns:
        str: Task ID
    """
    task = bulk_thumbnail_creation.delay(
        video_paths=video_paths,
        output_directory=output_directory,
        thumbnail_sizes=thumbnail_sizes,
        timestamps_per_video=timestamps_per_video,
        batch_size=batch_size,
        priority=priority,
        user_id=user_id,
    )
    logger.info(
        f"Submitted bulk thumbnail creation job {task.id} for {len(video_paths)} videos"
    )
    return task.id
