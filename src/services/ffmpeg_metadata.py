"""
FFmpeg Metadata Extraction and Quality Analysis

Provides video metadata extraction using FFprobe and comprehensive quality analysis
including resolution, bitrate, and codec efficiency scoring.
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.services.ffmpeg_progress import ffmpeg_progress_monitor
from src.utils.async_subprocess import AsyncSubprocessManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_metadata")


class FFmpegMetadataExtractor:
    """Extracts and analyzes video metadata using FFprobe"""

    def __init__(self):
        self.subprocess_manager = AsyncSubprocessManager()

    async def extract_metadata_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Async metadata extraction using FFprobe

        Args:
            video_path: Path to video file
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            Dict: Video metadata
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        metadata = {
            "duration": None,
            "quality": None,
            "width": None,
            "height": None,
            "video_codec": None,
            "audio_codec": None,
            "fps": None,
            "bitrate": None,
            "file_size": None,
        }

        # FFprobe command for metadata extraction
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        try:
            logger.debug(f"Running async FFprobe on: {video_path}")

            if progress_callback:
                progress_callback(
                    {
                        "stage": "metadata_extraction",
                        "status": "starting",
                        "message": f"Analyzing {video_path.name}",
                    }
                )

            # Update job progress if job_id provided
            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "metadata_extraction",
                        "progress": 10,
                        "status": "running",
                        "message": f"Analyzing {video_path.name}",
                    },
                )

            result = await self.subprocess_manager.run_command_async(cmd, timeout=30)

            if result["success"]:
                data = json.loads(result["stdout"])

                # Extract format information
                if "format" in data:
                    format_info = data["format"]

                    # Duration in seconds
                    if "duration" in format_info:
                        try:
                            metadata["duration"] = int(float(format_info["duration"]))
                        except (ValueError, TypeError):
                            pass

                    # Bitrate
                    if "bit_rate" in format_info:
                        try:
                            metadata["bitrate"] = int(format_info["bit_rate"])
                        except (ValueError, TypeError):
                            pass

                    # File size
                    if "size" in format_info:
                        try:
                            metadata["file_size"] = int(format_info["size"])
                        except (ValueError, TypeError):
                            pass

                # Extract stream information
                if "streams" in data:
                    for stream in data["streams"]:
                        if stream.get("codec_type") == "video":
                            # Video stream information
                            metadata["width"] = stream.get("width")
                            metadata["height"] = stream.get("height")
                            metadata["video_codec"] = stream.get("codec_name")

                            # Frame rate
                            if "r_frame_rate" in stream:
                                try:
                                    fps_str = stream["r_frame_rate"]
                                    if "/" in fps_str:
                                        num, den = fps_str.split("/")
                                        metadata["fps"] = round(
                                            float(num) / float(den), 2
                                        )
                                    else:
                                        metadata["fps"] = float(fps_str)
                                except (ValueError, TypeError, ZeroDivisionError):
                                    pass

                        elif stream.get("codec_type") == "audio":
                            # Audio stream information
                            if not metadata["audio_codec"]:
                                metadata["audio_codec"] = stream.get("codec_name")

                # Determine quality based on height
                if metadata["height"]:
                    height = metadata["height"]
                    if height >= 2160:
                        metadata["quality"] = "4K"
                    elif height >= 1440:
                        metadata["quality"] = "1440p"
                    elif height >= 1080:
                        metadata["quality"] = "1080p"
                    elif height >= 720:
                        metadata["quality"] = "720p"
                    elif height >= 480:
                        metadata["quality"] = "480p"
                    else:
                        metadata["quality"] = f"{height}p"

                logger.debug(
                    f"Extracted metadata for {video_path}: "
                    f"duration={metadata['duration']}s, quality={metadata['quality']}"
                )

                # Update progress
                if progress_callback:
                    progress_callback(
                        {
                            "stage": "metadata_extraction",
                            "status": "completed",
                            "message": f"Analysis complete: {metadata['quality']}, {metadata['duration']}s",
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "metadata_extraction",
                            "progress": 100,
                            "status": "completed",
                            "message": f"Analysis complete: {metadata['quality']}, {metadata['duration']}s",
                            "metadata": metadata,
                        },
                    )

            else:
                error_msg = f"FFprobe failed for {video_path}: {result.get('stderr', 'Unknown error')}"
                logger.warning(error_msg)

                if progress_callback:
                    progress_callback(
                        {
                            "stage": "metadata_extraction",
                            "status": "error",
                            "message": error_msg,
                        }
                    )

                if job_id:
                    await ffmpeg_progress_monitor.update_job_progress(
                        job_id,
                        {
                            "stage": "metadata_extraction",
                            "progress": 0,
                            "status": "error",
                            "message": error_msg,
                        },
                    )

        except Exception as e:
            error_msg = f"Error extracting FFmpeg metadata for {video_path}: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "metadata_extraction",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "metadata_extraction",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

        return metadata

    async def analyze_video_quality_async(
        self,
        video_path: Path,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Analyze video quality using FFmpeg and FFprobe

        Args:
            video_path: Path to video file
            job_id: Optional job ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            Dict: Quality analysis results
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Starting video quality analysis: {video_path.name}")

        try:
            # Get basic metadata first
            if progress_callback:
                progress_callback(
                    {
                        "stage": "quality_analysis",
                        "status": "starting",
                        "message": f"Analyzing {video_path.name}",
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "quality_analysis",
                        "progress": 10,
                        "status": "running",
                        "message": f"Extracting metadata for {video_path.name}",
                    },
                )

            metadata = await self.extract_metadata_async(video_path, job_id)

            # Analyze video quality metrics
            quality_metrics = {
                "resolution_quality": self._analyze_resolution_quality(metadata),
                "bitrate_quality": self._analyze_bitrate_quality(metadata),
                "codec_efficiency": self._analyze_codec_efficiency(metadata),
                "overall_score": 0,
                "recommendations": [],
            }

            # Calculate overall quality score
            quality_metrics["overall_score"] = self._calculate_quality_score(
                quality_metrics, metadata
            )

            # Generate recommendations
            quality_metrics["recommendations"] = self._generate_quality_recommendations(
                quality_metrics, metadata
            )

            if progress_callback:
                progress_callback(
                    {
                        "stage": "quality_analysis",
                        "status": "completed",
                        "message": f"Quality analysis complete: {quality_metrics['overall_score']:.1f}/100",
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "quality_analysis",
                        "progress": 100,
                        "status": "completed",
                        "message": f"Quality analysis complete: {quality_metrics['overall_score']:.1f}/100",
                        "quality_score": quality_metrics["overall_score"],
                    },
                )

            return {
                "success": True,
                "video_path": str(video_path),
                "metadata": metadata,
                "quality_metrics": quality_metrics,
            }

        except Exception as e:
            error_msg = f"Video quality analysis failed for {video_path.name}: {e}"
            logger.error(error_msg)

            if progress_callback:
                progress_callback(
                    {
                        "stage": "quality_analysis",
                        "status": "error",
                        "message": error_msg,
                    }
                )

            if job_id:
                await ffmpeg_progress_monitor.update_job_progress(
                    job_id,
                    {
                        "stage": "quality_analysis",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

            return {"success": False, "error": error_msg, "video_path": str(video_path)}

    def _analyze_resolution_quality(self, metadata: Dict) -> Dict:
        """Analyze video resolution quality"""
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not width or not height:
            return {"score": 0, "grade": "Unknown", "reason": "No resolution data"}

        total_pixels = width * height
        aspect_ratio = width / height if height > 0 else 0

        # Resolution quality scoring
        if total_pixels >= 3840 * 2160:  # 4K
            score = 100
            grade = "Excellent"
        elif total_pixels >= 1920 * 1080:  # 1080p
            score = 90
            grade = "Very Good"
        elif total_pixels >= 1280 * 720:  # 720p
            score = 75
            grade = "Good"
        elif total_pixels >= 854 * 480:  # 480p
            score = 60
            grade = "Fair"
        elif total_pixels >= 640 * 360:  # 360p
            score = 40
            grade = "Poor"
        else:
            score = 20
            grade = "Very Poor"

        return {
            "score": score,
            "grade": grade,
            "width": width,
            "height": height,
            "total_pixels": total_pixels,
            "aspect_ratio": round(aspect_ratio, 2),
        }

    def _analyze_bitrate_quality(self, metadata: Dict) -> Dict:
        """Analyze video bitrate quality"""
        bitrate = metadata.get("bitrate")
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)

        if not bitrate:
            return {"score": 0, "grade": "Unknown", "reason": "No bitrate data"}

        bitrate_mbps = bitrate / 1000000  # Convert to Mbps
        total_pixels = width * height

        # Calculate bitrate per pixel
        bitrate_per_pixel = (
            bitrate_mbps / (total_pixels / 1000000) if total_pixels > 0 else 0
        )

        # Bitrate quality scoring based on resolution
        if total_pixels >= 1920 * 1080:  # 1080p+
            if bitrate_mbps >= 8:
                score = 100
                grade = "Excellent"
            elif bitrate_mbps >= 5:
                score = 85
                grade = "Very Good"
            elif bitrate_mbps >= 3:
                score = 70
                grade = "Good"
            elif bitrate_mbps >= 1.5:
                score = 55
                grade = "Fair"
            else:
                score = 30
                grade = "Poor"
        else:  # Lower resolutions
            if bitrate_mbps >= 4:
                score = 100
                grade = "Excellent"
            elif bitrate_mbps >= 2:
                score = 85
                grade = "Very Good"
            elif bitrate_mbps >= 1:
                score = 70
                grade = "Good"
            elif bitrate_mbps >= 0.5:
                score = 55
                grade = "Fair"
            else:
                score = 30
                grade = "Poor"

        return {
            "score": score,
            "grade": grade,
            "bitrate_mbps": round(bitrate_mbps, 2),
            "bitrate_per_pixel": round(bitrate_per_pixel, 4),
        }

    def _analyze_codec_efficiency(self, metadata: Dict) -> Dict:
        """Analyze codec efficiency"""
        video_codec = metadata.get("video_codec", "").lower()

        # Codec efficiency scoring
        codec_scores = {
            "h265": {"score": 100, "grade": "Excellent", "efficiency": "Very High"},
            "hevc": {"score": 100, "grade": "Excellent", "efficiency": "Very High"},
            "av1": {"score": 100, "grade": "Excellent", "efficiency": "Very High"},
            "vp9": {"score": 90, "grade": "Very Good", "efficiency": "High"},
            "h264": {"score": 80, "grade": "Good", "efficiency": "Good"},
            "avc": {"score": 80, "grade": "Good", "efficiency": "Good"},
            "vp8": {"score": 70, "grade": "Fair", "efficiency": "Moderate"},
            "xvid": {"score": 60, "grade": "Poor", "efficiency": "Low"},
            "divx": {"score": 60, "grade": "Poor", "efficiency": "Low"},
            "mpeg4": {"score": 50, "grade": "Poor", "efficiency": "Low"},
            "mpeg2": {"score": 40, "grade": "Very Poor", "efficiency": "Very Low"},
        }

        result = codec_scores.get(
            video_codec, {"score": 30, "grade": "Unknown", "efficiency": "Unknown"}
        )

        result["codec"] = video_codec
        return result

    def _calculate_quality_score(self, quality_metrics: Dict, metadata: Dict) -> float:
        """Calculate overall quality score"""
        resolution_score = quality_metrics["resolution_quality"].get("score", 0)
        bitrate_score = quality_metrics["bitrate_quality"].get("score", 0)
        codec_score = quality_metrics["codec_efficiency"].get("score", 0)

        # Weighted average (resolution 40%, bitrate 35%, codec 25%)
        overall_score = (
            (resolution_score * 0.4) + (bitrate_score * 0.35) + (codec_score * 0.25)
        )

        return round(overall_score, 1)

    def _generate_quality_recommendations(
        self, quality_metrics: Dict, metadata: Dict
    ) -> List[str]:
        """Generate quality improvement recommendations"""
        recommendations = []

        resolution_score = quality_metrics["resolution_quality"].get("score", 0)
        bitrate_score = quality_metrics["bitrate_quality"].get("score", 0)
        codec_score = quality_metrics["codec_efficiency"].get("score", 0)

        # Resolution recommendations
        if resolution_score < 60:
            recommendations.append(
                "Consider upscaling to at least 720p for better quality"
            )

        # Bitrate recommendations
        if bitrate_score < 70:
            recommendations.append("Increase bitrate for better visual quality")

        # Codec recommendations
        if codec_score < 80:
            codec = metadata.get("video_codec", "").lower()
            if codec in ["xvid", "divx", "mpeg4", "mpeg2"]:
                recommendations.append(
                    "Convert to H.264 or H.265 for better compression efficiency"
                )
            elif codec == "h264":
                recommendations.append(
                    "Consider upgrading to H.265 for better compression"
                )

        # Overall recommendations
        overall_score = quality_metrics.get("overall_score", 0)
        if overall_score < 60:
            recommendations.append(
                "Overall video quality is poor - consider re-encoding"
            )
        elif overall_score < 80:
            recommendations.append("Video quality could be improved with optimization")

        return recommendations


# Shared instance
ffmpeg_metadata_extractor = FFmpegMetadataExtractor()
