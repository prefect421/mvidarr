"""
FFmpeg Stream Manager for async video processing operations

Provides async subprocess management for FFmpeg operations with real-time progress tracking
and WebSocket integration for background job processing.
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional, Tuple

from src.jobs.redis_manager import redis_manager
from src.utils.async_subprocess import AsyncSubprocessManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ffmpeg_stream_manager")


class FFmpegStreamManager:
    """Manages async FFmpeg operations with progress tracking and WebSocket integration"""

    def __init__(self):
        self.subprocess_manager = AsyncSubprocessManager()
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
                    self._monitor_ffmpeg_progress(
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
                await self._update_job_progress(
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
                    await self._update_job_progress(
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
                    await self._update_job_progress(
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
                await self._update_job_progress(
                    job_id,
                    {
                        "stage": "metadata_extraction",
                        "progress": 0,
                        "status": "error",
                        "message": error_msg,
                    },
                )

        return metadata

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
        input_metadata = await self.extract_metadata_async(input_path, job_id)

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
                self._monitor_ffmpeg_progress(
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
                output_metadata = await self.extract_metadata_async(output_path, job_id)
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
                    await self._update_job_progress(
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
                    await self._update_job_progress(
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
                await self._update_job_progress(
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
                await self._update_job_progress(
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
                await self._update_job_progress(
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
                await self._update_job_progress(
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
            metadata = await self.extract_metadata_async(video_path, job_id)
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
                await self._update_job_progress(
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
                    await self._update_job_progress(
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
                    await self._update_job_progress(
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
                await self._update_job_progress(
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
                await self._update_job_progress(
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
                        await self._update_job_progress(
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
                await self._update_job_progress(
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
                await self._update_job_progress(
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
                self._monitor_ffmpeg_progress(
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
                    await self._update_job_progress(
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
                    await self._update_job_progress(
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
                await self._update_job_progress(
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
            await self._update_job_progress(
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

    async def _monitor_ffmpeg_progress(
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
                            await self._update_job_progress(job_id, progress_data)

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

    async def _update_job_progress(self, job_id: str, progress_data: Dict):
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


# Global instance
ffmpeg_stream_manager = FFmpegStreamManager()
