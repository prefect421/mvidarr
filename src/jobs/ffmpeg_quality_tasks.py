"""
FFmpeg video quality analysis and validation background tasks

Provides Celery tasks for concurrent video quality analysis, validation,
and upgrade recommendations with real-time progress tracking.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional

from src.jobs.base_task import BaseTask
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.ffmpeg_quality")


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


# Convenience functions for task submission
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
