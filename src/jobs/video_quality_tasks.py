"""
Advanced video quality analysis and optimization tasks

Provides Celery tasks for comprehensive video quality analysis, optimization,
and batch processing with real-time progress tracking.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.database.connection import get_db
from src.database.models import Video
from src.jobs.base_task import BaseTask
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.video_quality")


class VideoQualityAnalysisTask(BaseTask):
    """Advanced video quality analysis with comprehensive metrics"""

    name = "video_quality.analyze"
    description = "Analyze video quality with comprehensive metrics and recommendations"

    async def execute_async(self, video_id: int, **kwargs) -> Dict:
        """
        Perform comprehensive video quality analysis

        Args:
            video_id: Database ID of video to analyze
            **kwargs: Additional task arguments

        Returns:
            Dict: Comprehensive quality analysis results
        """
        try:
            await self.update_progress(
                5, "starting", f"Starting quality analysis for video {video_id}"
            )

            # Get video from database
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    raise ValueError(f"Video with ID {video_id} not found")

                if not video.local_path or not Path(video.local_path).exists():
                    raise FileNotFoundError(f"Video file not found: {video.local_path}")

                video_path = Path(video.local_path)

                await self.update_progress(
                    10, "running", f"Analyzing {video_path.name}"
                )

                # Extract comprehensive metadata
                metadata = await ffmpeg_stream_manager.extract_metadata_async(
                    video_path,
                    job_id=self.task_id,
                    progress_callback=self._progress_callback,
                )

                # Perform quality analysis
                quality_analysis = await self._analyze_video_quality(
                    metadata, video_path
                )

                # Generate recommendations
                recommendations = await self._generate_quality_recommendations(
                    quality_analysis, metadata, video
                )

                # Update video metadata in database
                await self._update_video_quality_data(
                    video, quality_analysis, metadata, session
                )

                await self.update_progress(
                    100,
                    "completed",
                    f"Quality analysis complete: {quality_analysis['overall_score']}/100 score",
                )

                return {
                    "success": True,
                    "video_id": video_id,
                    "video_path": str(video_path),
                    "metadata": metadata,
                    "quality_analysis": quality_analysis,
                    "recommendations": recommendations,
                    "updated_database": True,
                }

        except Exception as e:
            error_msg = f"Quality analysis failed for video {video_id}: {e}"
            logger.error(error_msg)
            await self.update_progress(0, "error", error_msg)
            return {"success": False, "error": error_msg, "video_id": video_id}

    async def _analyze_video_quality(self, metadata: Dict, video_path: Path) -> Dict:
        """Perform comprehensive quality analysis"""
        quality_metrics = {
            "resolution_score": 0,
            "bitrate_score": 0,
            "codec_score": 0,
            "file_size_efficiency": 0,
            "audio_quality_score": 0,
            "overall_score": 0,
        }

        # Resolution quality analysis
        height = metadata.get("height", 0)
        if height >= 2160:  # 4K
            quality_metrics["resolution_score"] = 100
        elif height >= 1440:  # 1440p
            quality_metrics["resolution_score"] = 90
        elif height >= 1080:  # 1080p
            quality_metrics["resolution_score"] = 80
        elif height >= 720:  # 720p
            quality_metrics["resolution_score"] = 60
        elif height >= 480:  # 480p
            quality_metrics["resolution_score"] = 40
        else:
            quality_metrics["resolution_score"] = 20

        # Bitrate quality analysis
        bitrate = metadata.get("bitrate", 0)
        duration = metadata.get("duration", 1)
        if bitrate and duration:
            # Calculate bitrate per pixel for quality assessment
            pixels_per_second = (
                metadata.get("width", 1) * height * metadata.get("fps", 25)
            )
            if pixels_per_second > 0:
                bitrate_per_pixel = bitrate / pixels_per_second

                # Scoring based on bitrate efficiency
                if bitrate_per_pixel >= 0.1:
                    quality_metrics["bitrate_score"] = 100
                elif bitrate_per_pixel >= 0.05:
                    quality_metrics["bitrate_score"] = 80
                elif bitrate_per_pixel >= 0.02:
                    quality_metrics["bitrate_score"] = 60
                else:
                    quality_metrics["bitrate_score"] = 30

        # Codec quality scoring
        video_codec = metadata.get("video_codec", "").lower()
        if "h265" in video_codec or "hevc" in video_codec:
            quality_metrics["codec_score"] = 100
        elif "h264" in video_codec or "avc" in video_codec:
            quality_metrics["codec_score"] = 80
        elif "vp9" in video_codec:
            quality_metrics["codec_score"] = 85
        elif "vp8" in video_codec:
            quality_metrics["codec_score"] = 60
        else:
            quality_metrics["codec_score"] = 40

        # File size efficiency
        file_size = metadata.get("file_size", 0)
        if file_size and duration:
            file_size_mb = file_size / (1024 * 1024)
            size_per_minute = file_size_mb / (duration / 60)

            # Efficiency scoring based on size per minute for quality
            if height >= 1080:
                # High resolution expectations
                if size_per_minute <= 50:  # Highly efficient
                    quality_metrics["file_size_efficiency"] = 100
                elif size_per_minute <= 100:
                    quality_metrics["file_size_efficiency"] = 80
                elif size_per_minute <= 200:
                    quality_metrics["file_size_efficiency"] = 60
                else:
                    quality_metrics["file_size_efficiency"] = 40
            else:
                # Lower resolution expectations
                if size_per_minute <= 20:
                    quality_metrics["file_size_efficiency"] = 100
                elif size_per_minute <= 40:
                    quality_metrics["file_size_efficiency"] = 80
                elif size_per_minute <= 80:
                    quality_metrics["file_size_efficiency"] = 60
                else:
                    quality_metrics["file_size_efficiency"] = 40

        # Audio quality scoring
        audio_codec = metadata.get("audio_codec", "").lower()
        if "flac" in audio_codec or "alac" in audio_codec:
            quality_metrics["audio_quality_score"] = 100
        elif "aac" in audio_codec:
            quality_metrics["audio_quality_score"] = 80
        elif "mp3" in audio_codec:
            quality_metrics["audio_quality_score"] = 60
        else:
            quality_metrics["audio_quality_score"] = 40

        # Calculate overall score (weighted average)
        weights = {
            "resolution_score": 0.35,
            "bitrate_score": 0.25,
            "codec_score": 0.20,
            "file_size_efficiency": 0.15,
            "audio_quality_score": 0.05,
        }

        overall_score = sum(
            quality_metrics[metric] * weight for metric, weight in weights.items()
        )
        quality_metrics["overall_score"] = int(overall_score)

        # Additional analysis details
        analysis_details = {
            "quality_category": self._categorize_quality(overall_score),
            "resolution_category": metadata.get("quality", "unknown"),
            "estimated_upgrade_potential": max(0, 90 - overall_score),
            "file_size_mb": file_size / (1024 * 1024) if file_size else 0,
            "duration_minutes": duration / 60 if duration else 0,
            "technical_details": {
                "video_codec": metadata.get("video_codec"),
                "audio_codec": metadata.get("audio_codec"),
                "fps": metadata.get("fps"),
                "bitrate_kbps": bitrate // 1000 if bitrate else 0,
            },
        }

        return {**quality_metrics, **analysis_details}

    async def _generate_quality_recommendations(
        self, quality_analysis: Dict, metadata: Dict, video: Video
    ) -> Dict:
        """Generate quality improvement recommendations"""
        recommendations = {
            "upgrade_recommended": False,
            "priority": "low",
            "recommended_actions": [],
            "estimated_improvement": 0,
            "technical_recommendations": {},
        }

        overall_score = quality_analysis["overall_score"]

        # Determine if upgrade is recommended
        if overall_score < 70:
            recommendations["upgrade_recommended"] = True
            recommendations["priority"] = "high" if overall_score < 50 else "medium"

        # Resolution recommendations
        height = metadata.get("height", 0)
        if height < 720:
            recommendations["recommended_actions"].append(
                "Upgrade to HD (720p) or higher resolution"
            )
            recommendations["technical_recommendations"]["target_resolution"] = "720p"
        elif height < 1080:
            recommendations["recommended_actions"].append(
                "Consider upgrading to Full HD (1080p)"
            )
            recommendations["technical_recommendations"]["target_resolution"] = "1080p"

        # Codec recommendations
        video_codec = metadata.get("video_codec", "").lower()
        if "h265" not in video_codec and "hevc" not in video_codec:
            if quality_analysis["codec_score"] < 80:
                recommendations["recommended_actions"].append(
                    "Convert to H.265/HEVC for better compression"
                )
                recommendations["technical_recommendations"]["target_codec"] = "libx265"

        # Bitrate optimization
        if quality_analysis["bitrate_score"] < 60:
            recommendations["recommended_actions"].append(
                "Optimize bitrate for better quality-to-size ratio"
            )

        # Audio quality recommendations
        if quality_analysis["audio_quality_score"] < 70:
            recommendations["recommended_actions"].append(
                "Upgrade audio codec for better sound quality"
            )
            recommendations["technical_recommendations"]["target_audio_codec"] = "aac"

        # Estimate potential improvement
        potential_score = min(
            90,
            overall_score
            + (30 if height < 720 else 15)
            + (15 if quality_analysis["codec_score"] < 80 else 5),
        )
        recommendations["estimated_improvement"] = potential_score - overall_score

        return recommendations

    async def _update_video_quality_data(
        self, video: Video, quality_analysis: Dict, metadata: Dict, session
    ):
        """Update video database record with quality analysis results"""
        try:
            # Update basic video metadata
            video.duration = metadata.get("duration") or video.duration
            video.quality = metadata.get("quality") or video.quality

            # Create or update video_metadata with quality analysis
            video_metadata = video.video_metadata or {}
            video_metadata.update(
                {
                    "quality_analysis": quality_analysis,
                    "last_analyzed": asyncio.get_event_loop().time(),
                    "ffmpeg_metadata": {
                        "width": metadata.get("width"),
                        "height": metadata.get("height"),
                        "video_codec": metadata.get("video_codec"),
                        "audio_codec": metadata.get("audio_codec"),
                        "fps": metadata.get("fps"),
                        "bitrate": metadata.get("bitrate"),
                        "file_size": metadata.get("file_size"),
                    },
                }
            )

            video.video_metadata = video_metadata
            session.commit()

        except Exception as e:
            logger.error(f"Error updating video quality data: {e}")
            session.rollback()

    def _categorize_quality(self, score: float) -> str:
        """Categorize quality score into human-readable category"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "very_good"
        elif score >= 60:
            return "good"
        elif score >= 45:
            return "fair"
        else:
            return "poor"

    def _progress_callback(self, progress_data: Dict):
        """Handle progress updates from FFmpeg stream manager"""
        try:
            stage = progress_data.get("stage", "analysis")
            status = progress_data.get("status", "running")
            message = progress_data.get("message", "Analyzing video quality")
            progress = progress_data.get("progress", 0)

            # Scale progress for quality analysis portion (50-90%)
            scaled_progress = 50 + int(progress * 0.4)

            asyncio.create_task(
                self.update_progress(
                    scaled_progress, status, f"Quality analysis: {message}"
                )
            )

        except Exception as e:
            logger.warning(f"Error in quality analysis progress callback: {e}")


class BulkVideoQualityAnalysisTask(BaseTask):
    """Bulk video quality analysis for multiple videos"""

    name = "video_quality.bulk_analyze"
    description = "Analyze quality for multiple videos with batch processing"

    async def execute_async(
        self, video_ids: List[int], batch_size: int = 5, **kwargs
    ) -> Dict:
        """
        Analyze quality for multiple videos

        Args:
            video_ids: List of video IDs to analyze
            batch_size: Number of videos to process concurrently
            **kwargs: Additional task arguments

        Returns:
            Dict: Bulk analysis results
        """
        total_videos = len(video_ids)
        processed = 0
        successful = 0
        failed = 0
        results = []

        try:
            await self.update_progress(
                5,
                "starting",
                f"Starting bulk quality analysis for {total_videos} videos",
            )

            # Process videos in batches
            for i in range(0, total_videos, batch_size):
                batch = video_ids[i : i + batch_size]

                # Process batch concurrently
                batch_results = await asyncio.gather(
                    *[
                        self._analyze_single_video(
                            video_id, processed + j + 1, total_videos
                        )
                        for j, video_id in enumerate(batch)
                    ],
                    return_exceptions=True,
                )

                # Process batch results
                for j, result in enumerate(batch_results):
                    processed += 1

                    if isinstance(result, Exception):
                        failed += 1
                        results.append(
                            {
                                "video_id": batch[j],
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        if result["success"]:
                            successful += 1
                        else:
                            failed += 1
                        results.append(result)

                    # Update progress
                    progress = int((processed / total_videos) * 90) + 5
                    await self.update_progress(
                        progress,
                        "running",
                        f"Analyzed {processed}/{total_videos} videos "
                        f"({successful} successful, {failed} failed)",
                    )

            await self.update_progress(
                100,
                "completed",
                f"Bulk analysis complete: {successful} successful, {failed} failed",
            )

            return {
                "success": True,
                "total_videos": total_videos,
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "results": results,
            }

        except Exception as e:
            error_msg = f"Bulk quality analysis failed: {e}"
            logger.error(error_msg)
            await self.update_progress(0, "error", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "total_videos": total_videos,
                "processed": processed,
                "results": results,
            }

    async def _analyze_single_video(
        self, video_id: int, video_number: int, total_videos: int
    ) -> Dict:
        """Analyze a single video as part of bulk processing"""
        try:
            logger.debug(f"Analyzing video {video_id} ({video_number}/{total_videos})")

            # Create and execute individual analysis task
            analysis_task = VideoQualityAnalysisTask()
            analysis_task.task_id = f"{self.task_id}_video_{video_id}"

            result = await analysis_task.execute_async(video_id)

            return {"video_id": video_id, "video_number": video_number, **result}

        except Exception as e:
            logger.error(f"Error analyzing video {video_id}: {e}")
            return {
                "video_id": video_id,
                "video_number": video_number,
                "success": False,
                "error": str(e),
            }


class VideoThumbnailGenerationTask(BaseTask):
    """Generate thumbnails for videos with multiple sizes and timestamps"""

    name = "video_quality.generate_thumbnails"
    description = "Generate multiple thumbnail sizes at various timestamps"

    async def execute_async(
        self,
        video_id: int,
        thumbnail_count: int = 3,
        thumbnail_sizes: List[Tuple[int, int]] = None,
        **kwargs,
    ) -> Dict:
        """
        Generate thumbnails for a video

        Args:
            video_id: Database ID of video
            thumbnail_count: Number of thumbnails to generate
            thumbnail_sizes: List of (width, height) tuples for thumbnail sizes
            **kwargs: Additional task arguments

        Returns:
            Dict: Thumbnail generation results
        """
        if thumbnail_sizes is None:
            thumbnail_sizes = [(320, 240), (640, 480), (960, 720)]

        try:
            await self.update_progress(
                5, "starting", f"Starting thumbnail generation for video {video_id}"
            )

            # Get video from database
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    raise ValueError(f"Video with ID {video_id} not found")

                if not video.local_path or not Path(video.local_path).exists():
                    raise FileNotFoundError(f"Video file not found: {video.local_path}")

                video_path = Path(video.local_path)

                # Get video metadata for duration
                metadata = await ffmpeg_stream_manager.extract_metadata_async(
                    video_path
                )
                duration = metadata.get("duration", 0)

                if duration <= 0:
                    raise ValueError("Could not determine video duration")

                await self.update_progress(
                    15, "running", "Generating thumbnails at multiple timestamps"
                )

                # Calculate timestamps for thumbnails (avoid first/last 10%)
                start_time = duration * 0.1
                end_time = duration * 0.9

                if thumbnail_count == 1:
                    timestamps = [duration / 2]
                else:
                    step = (end_time - start_time) / (thumbnail_count - 1)
                    timestamps = [
                        start_time + (i * step) for i in range(thumbnail_count)
                    ]

                thumbnail_results = []
                total_operations = len(timestamps) * len(thumbnail_sizes)
                completed_operations = 0

                # Generate thumbnails for each timestamp and size
                for timestamp in timestamps:
                    for width, height in thumbnail_sizes:
                        try:
                            thumbnail_path = await self._generate_single_thumbnail(
                                video_path, timestamp, width, height, video_id
                            )

                            thumbnail_results.append(
                                {
                                    "timestamp": timestamp,
                                    "size": f"{width}x{height}",
                                    "path": str(thumbnail_path),
                                    "success": True,
                                }
                            )

                        except Exception as e:
                            logger.warning(
                                f"Failed to generate thumbnail at {timestamp}s, {width}x{height}: {e}"
                            )
                            thumbnail_results.append(
                                {
                                    "timestamp": timestamp,
                                    "size": f"{width}x{height}",
                                    "success": False,
                                    "error": str(e),
                                }
                            )

                        completed_operations += 1
                        progress = 15 + int(
                            (completed_operations / total_operations) * 80
                        )
                        await self.update_progress(
                            progress,
                            "running",
                            f"Generated {completed_operations}/{total_operations} thumbnails",
                        )

                successful_thumbnails = [r for r in thumbnail_results if r["success"]]

                # Update video record with thumbnail paths
                if successful_thumbnails:
                    await self._update_video_thumbnails(
                        video, successful_thumbnails, session
                    )

                await self.update_progress(
                    100,
                    "completed",
                    f"Generated {len(successful_thumbnails)}/{total_operations} thumbnails successfully",
                )

                return {
                    "success": True,
                    "video_id": video_id,
                    "total_thumbnails": len(successful_thumbnails),
                    "thumbnails": thumbnail_results,
                    "video_duration": duration,
                }

        except Exception as e:
            error_msg = f"Thumbnail generation failed for video {video_id}: {e}"
            logger.error(error_msg)
            await self.update_progress(0, "error", error_msg)
            return {"success": False, "error": error_msg, "video_id": video_id}

    async def _generate_single_thumbnail(
        self, video_path: Path, timestamp: float, width: int, height: int, video_id: int
    ) -> Path:
        """Generate a single thumbnail at specific timestamp and size"""

        # Create thumbnail directory
        thumbnail_dir = video_path.parent / "thumbnails" / str(video_id)
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Generate thumbnail filename
        thumbnail_name = f"thumb_{timestamp:.1f}s_{width}x{height}.jpg"
        thumbnail_path = thumbnail_dir / thumbnail_name

        # FFmpeg command for thumbnail generation
        format_options = {
            "-ss": str(timestamp),
            "-vf": f"thumbnail,scale={width}:{height}",
            "-frames:v": "1",
            "-f": "image2",
            "-y": "",  # Overwrite existing files
        }

        # Use FFmpeg stream manager for thumbnail generation
        success = await ffmpeg_stream_manager.convert_video_async(
            video_path,
            thumbnail_path,
            format_options,
            job_id=f"{self.task_id}_thumb_{timestamp}_{width}x{height}",
        )

        if not success or not thumbnail_path.exists():
            raise RuntimeError(f"Thumbnail generation failed: {thumbnail_path}")

        return thumbnail_path

    async def _update_video_thumbnails(
        self, video: Video, thumbnails: List[Dict], session
    ):
        """Update video record with generated thumbnail information"""
        try:
            video_metadata = video.video_metadata or {}

            # Find the best quality thumbnail for main thumbnail
            best_thumbnail = max(
                (t for t in thumbnails if t["success"]),
                key=lambda x: int(x["size"].split("x")[0]),
                default=None,
            )

            if best_thumbnail:
                video.thumbnail_path = best_thumbnail["path"]

            # Store all thumbnail information
            video_metadata["generated_thumbnails"] = thumbnails
            video_metadata[
                "thumbnail_generation_date"
            ] = asyncio.get_event_loop().time()

            video.video_metadata = video_metadata
            session.commit()

        except Exception as e:
            logger.error(f"Error updating video thumbnail data: {e}")
            session.rollback()


# Task registration
VIDEO_QUALITY_TASKS = [
    VideoQualityAnalysisTask,
    BulkVideoQualityAnalysisTask,
    VideoThumbnailGenerationTask,
]


# Convenience functions for task submission
async def submit_video_quality_analysis_task(
    video_id: int, priority: str = "normal", user_id: Optional[str] = None
) -> str:
    """Submit video quality analysis task"""
    task = VideoQualityAnalysisTask()
    return await task.submit(video_id=video_id, priority=priority, user_id=user_id)


async def submit_bulk_quality_analysis_task(
    video_ids: List[int],
    batch_size: int = 5,
    priority: str = "low",
    user_id: Optional[str] = None,
) -> str:
    """Submit bulk video quality analysis task"""
    task = BulkVideoQualityAnalysisTask()
    return await task.submit(
        video_ids=video_ids, batch_size=batch_size, priority=priority, user_id=user_id
    )


async def submit_thumbnail_generation_task(
    video_id: int,
    thumbnail_count: int = 3,
    thumbnail_sizes: List[Tuple[int, int]] = None,
    priority: str = "normal",
    user_id: Optional[str] = None,
) -> str:
    """Submit thumbnail generation task"""
    task = VideoThumbnailGenerationTask()
    return await task.submit(
        video_id=video_id,
        thumbnail_count=thumbnail_count,
        thumbnail_sizes=thumbnail_sizes,
        priority=priority,
        user_id=user_id,
    )
