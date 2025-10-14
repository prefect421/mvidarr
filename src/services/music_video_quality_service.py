"""
Music Video Quality Assessment Service - Phase 3 Week 26
Enhanced video quality analysis specifically designed for music video content
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.music_video_quality")


class VideoType(Enum):
    """Types of music video content"""

    OFFICIAL_MUSIC_VIDEO = "official_music_video"
    LIVE_PERFORMANCE = "live_performance"
    LYRIC_VIDEO = "lyric_video"
    ACOUSTIC_VERSION = "acoustic_version"
    REMIX_VERSION = "remix_version"
    COVER_VERSION = "cover_version"
    CONCERT_RECORDING = "concert_recording"
    INTERVIEW = "interview"
    BEHIND_SCENES = "behind_scenes"
    UNKNOWN = "unknown"


class QualityRating(Enum):
    """Quality ratings for music videos"""

    EXCELLENT = "excellent"  # 90-100%
    GOOD = "good"  # 70-89%
    ACCEPTABLE = "acceptable"  # 50-69%
    POOR = "poor"  # 30-49%
    UNACCEPTABLE = "unacceptable"  # 0-29%


@dataclass
class VideoQualityMetrics:
    """Comprehensive video quality metrics"""

    video_path: str
    resolution: str
    bitrate: int
    fps: float
    duration: float
    video_codec: str
    audio_codec: str
    file_size: int

    # Quality scores (0-100)
    video_quality_score: float = 0.0
    audio_quality_score: float = 0.0
    technical_quality_score: float = 0.0
    content_quality_score: float = 0.0
    overall_quality_score: float = 0.0

    # Specific assessments
    has_intro_outro: bool = False
    has_watermark: bool = False
    audio_video_sync: bool = True
    video_type: VideoType = VideoType.UNKNOWN
    quality_rating: QualityRating = QualityRating.UNACCEPTABLE

    # Technical details
    color_depth: int = 8
    aspect_ratio: str = "16:9"
    audio_channels: int = 2
    audio_sample_rate: int = 44100

    # Issues detected
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_path": self.video_path,
            "resolution": self.resolution,
            "bitrate": self.bitrate,
            "fps": self.fps,
            "duration": self.duration,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "file_size": self.file_size,
            "video_quality_score": self.video_quality_score,
            "audio_quality_score": self.audio_quality_score,
            "technical_quality_score": self.technical_quality_score,
            "content_quality_score": self.content_quality_score,
            "overall_quality_score": self.overall_quality_score,
            "has_intro_outro": self.has_intro_outro,
            "has_watermark": self.has_watermark,
            "audio_video_sync": self.audio_video_sync,
            "video_type": self.video_type.value,
            "quality_rating": self.quality_rating.value,
            "color_depth": self.color_depth,
            "aspect_ratio": self.aspect_ratio,
            "audio_channels": self.audio_channels,
            "audio_sample_rate": self.audio_sample_rate,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }


class MusicVideoQualityService:
    """Advanced quality assessment service for music videos"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize music video quality service"""
        self.config = config or {
            "min_resolution_width": 1280,  # Minimum HD width
            "min_bitrate": 2000,  # kbps
            "min_fps": 24,
            "max_fps": 60,
            "preferred_codecs": ["h264", "h265", "vp9"],
            "preferred_audio_codecs": ["aac", "mp3"],
            "cache_ttl": 7200,  # 2 hours
            "analyze_audio_quality": True,
            "detect_video_type": True,
            "check_sync": True,
        }

        # Quality assessment weights
        self.quality_weights = {
            "video_quality": 0.3,
            "audio_quality": 0.25,
            "technical_quality": 0.25,
            "content_quality": 0.2,
        }

        # Performance tracking
        self.stats = {
            "assessments_completed": 0,
            "total_processing_time": 0.0,
            "average_score": 0.0,
            "quality_distribution": {
                "excellent": 0,
                "good": 0,
                "acceptable": 0,
                "poor": 0,
                "unacceptable": 0,
            },
        }

        logger.info("📊 Music video quality service initialized")

    async def analyze_music_video_quality(
        self, video_path: str, artist: Optional[str] = None, title: Optional[str] = None
    ) -> Optional[VideoQualityMetrics]:
        """
        Perform comprehensive quality analysis of a music video

        Args:
            video_path: Path to video file
            artist: Optional artist name for context
            title: Optional song title for context

        Returns:
            VideoQualityMetrics with comprehensive assessment
        """
        start_time = time.time()

        try:
            video_path_obj = Path(video_path)
            if not video_path_obj.exists():
                logger.error(f"Video file not found: {video_path}")
                return None

            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"video_quality_{video_path_obj.stat().st_mtime}_{video_path_obj.stat().st_size}"

            cached_result = await cache_manager.get(CacheType.MEDIA_METADATA, cache_key)
            if cached_result:
                return VideoQualityMetrics(**cached_result)

            logger.info(f"📊 Analyzing quality of music video: {video_path_obj.name}")

            # Extract basic metadata using FFprobe
            metadata = await self._extract_detailed_metadata(video_path)
            if not metadata:
                logger.error(f"Failed to extract metadata from: {video_path}")
                return None

            # Initialize quality metrics
            metrics = VideoQualityMetrics(
                video_path=video_path,
                resolution=metadata.get("resolution", "unknown"),
                bitrate=metadata.get("bitrate", 0),
                fps=metadata.get("fps", 0.0),
                duration=metadata.get("duration", 0.0),
                video_codec=metadata.get("video_codec", "unknown"),
                audio_codec=metadata.get("audio_codec", "unknown"),
                file_size=video_path_obj.stat().st_size,
                color_depth=metadata.get("color_depth", 8),
                aspect_ratio=metadata.get("aspect_ratio", "unknown"),
                audio_channels=metadata.get("audio_channels", 2),
                audio_sample_rate=metadata.get("audio_sample_rate", 44100),
            )

            # Perform various quality assessments
            metrics.video_quality_score = await self._assess_video_quality(metadata)
            metrics.audio_quality_score = await self._assess_audio_quality(
                metadata, video_path
            )
            metrics.technical_quality_score = await self._assess_technical_quality(
                metadata
            )

            # Detect video type and content quality
            metrics.video_type = await self._detect_video_type(
                video_path, artist, title
            )
            metrics.content_quality_score = await self._assess_content_quality(
                video_path, metrics.video_type
            )

            # Check for specific music video issues
            await self._check_music_video_issues(video_path, metrics)

            # Calculate overall quality score
            metrics.overall_quality_score = self._calculate_overall_score(metrics)
            metrics.quality_rating = self._determine_quality_rating(
                metrics.overall_quality_score
            )

            # Generate recommendations
            metrics.recommendations = await self._generate_recommendations(metrics)

            # Cache results
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                cache_key,
                metrics.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            # Update statistics
            self.stats["assessments_completed"] += 1
            processing_time = time.time() - start_time
            self.stats["total_processing_time"] += processing_time
            self.stats["average_score"] = (
                self.stats["average_score"] * (self.stats["assessments_completed"] - 1)
                + metrics.overall_quality_score
            ) / self.stats["assessments_completed"]
            self.stats["quality_distribution"][metrics.quality_rating.value] += 1

            # Track performance
            await track_media_processing_time(
                "music_video_quality_analysis", processing_time
            )

            logger.info(
                f"✅ Quality analysis completed for {video_path_obj.name}: "
                f"{metrics.quality_rating.value.upper()} ({metrics.overall_quality_score:.1f}%) "
                f"in {processing_time:.2f}s"
            )

            return metrics

        except Exception as e:
            logger.error(f"❌ Quality analysis failed for {video_path}: {e}")
            return None

    async def _extract_detailed_metadata(
        self, video_path: str
    ) -> Optional[Dict[str, Any]]:
        """Extract detailed video metadata using FFprobe"""
        try:
            import json
            import subprocess

            # Enhanced FFprobe command for detailed analysis
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_programs",
                "-show_chapters",
                "-count_frames",
                "-select_streams",
                "v:0,a:0",
                video_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"FFprobe failed: {stderr.decode()}")
                return None

            probe_data = json.loads(stdout.decode())

            # Extract video and audio streams
            video_stream = None
            audio_stream = None

            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream

            if not video_stream:
                logger.error("No video stream found")
                return None

            # Calculate aspect ratio
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            aspect_ratio = f"{width}:{height}"
            if width and height:
                ratio = width / height
                if abs(ratio - 16 / 9) < 0.1:
                    aspect_ratio = "16:9"
                elif abs(ratio - 4 / 3) < 0.1:
                    aspect_ratio = "4:3"
                elif abs(ratio - 21 / 9) < 0.1:
                    aspect_ratio = "21:9"

            # Build comprehensive metadata
            metadata = {
                "duration": float(probe_data.get("format", {}).get("duration", 0)),
                "bitrate": int(probe_data.get("format", {}).get("bit_rate", 0)),
                "resolution": f"{width}x{height}",
                "width": width,
                "height": height,
                "fps": eval(video_stream.get("r_frame_rate", "0/1")),
                "video_codec": video_stream.get("codec_name", "unknown"),
                "pixel_format": video_stream.get("pix_fmt", "unknown"),
                "color_depth": self._get_color_depth(video_stream.get("pix_fmt", "")),
                "aspect_ratio": aspect_ratio,
                "video_bitrate": int(video_stream.get("bit_rate", 0)),
                "frame_count": int(video_stream.get("nb_frames", 0)),
            }

            # Add audio information if available
            if audio_stream:
                metadata.update(
                    {
                        "has_audio": True,
                        "audio_codec": audio_stream.get("codec_name", "unknown"),
                        "audio_bitrate": int(audio_stream.get("bit_rate", 0)),
                        "sample_rate": int(audio_stream.get("sample_rate", 0)),
                        "audio_channels": int(audio_stream.get("channels", 0)),
                        "channel_layout": audio_stream.get("channel_layout", "unknown"),
                    }
                )
            else:
                metadata["has_audio"] = False

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract detailed metadata: {e}")
            return None

    def _get_color_depth(self, pixel_format: str) -> int:
        """Determine color depth from pixel format"""
        if "10le" in pixel_format or "10be" in pixel_format:
            return 10
        elif "12le" in pixel_format or "12be" in pixel_format:
            return 12
        else:
            return 8

    async def _assess_video_quality(self, metadata: Dict[str, Any]) -> float:
        """Assess video quality based on technical specifications"""
        score = 0.0
        max_score = 100.0

        try:
            # Resolution scoring (40 points)
            width = metadata.get("width", 0)
            height = metadata.get("height", 0)

            if width >= 3840 and height >= 2160:  # 4K
                score += 40
            elif width >= 1920 and height >= 1080:  # 1080p
                score += 35
            elif width >= 1280 and height >= 720:  # 720p
                score += 25
            elif width >= 854 and height >= 480:  # 480p
                score += 15
            else:  # Below 480p
                score += 5

            # Bitrate scoring (25 points)
            bitrate = metadata.get("video_bitrate", 0) / 1000  # Convert to kbps

            if bitrate >= 8000:  # High quality
                score += 25
            elif bitrate >= 4000:  # Good quality
                score += 20
            elif bitrate >= 2000:  # Acceptable
                score += 15
            elif bitrate >= 1000:  # Low quality
                score += 10
            else:  # Very low quality
                score += 5

            # Frame rate scoring (20 points)
            fps = metadata.get("fps", 0)

            if 23 <= fps <= 30 or 50 <= fps <= 60:  # Standard rates
                score += 20
            elif 20 <= fps < 23 or 30 < fps < 50:  # Acceptable rates
                score += 15
            else:  # Non-standard rates
                score += 10

            # Codec scoring (15 points)
            codec = metadata.get("video_codec", "").lower()

            if codec in ["h265", "hevc", "vp9"]:  # Modern codecs
                score += 15
            elif codec in ["h264", "avc"]:  # Standard codecs
                score += 12
            elif codec in ["vp8", "mpeg4"]:  # Older but acceptable
                score += 8
            else:  # Very old codecs
                score += 3

            return min(score, max_score)

        except Exception as e:
            logger.error(f"Video quality assessment failed: {e}")
            return 0.0

    async def _assess_audio_quality(
        self, metadata: Dict[str, Any], video_path: str
    ) -> float:
        """Assess audio quality based on technical specifications and analysis"""
        score = 0.0
        max_score = 100.0

        try:
            if not metadata.get("has_audio", False):
                return 0.0

            # Codec scoring (30 points)
            codec = metadata.get("audio_codec", "").lower()

            if codec in ["aac", "flac", "alac"]:  # High quality codecs
                score += 30
            elif codec in ["mp3", "ogg", "opus"]:  # Good codecs
                score += 25
            elif codec in ["ac3", "dts"]:  # Acceptable codecs
                score += 20
            else:  # Lower quality codecs
                score += 10

            # Bitrate scoring (25 points)
            audio_bitrate = metadata.get("audio_bitrate", 0) / 1000  # Convert to kbps

            if audio_bitrate >= 320:  # Very high quality
                score += 25
            elif audio_bitrate >= 256:  # High quality
                score += 22
            elif audio_bitrate >= 192:  # Good quality
                score += 18
            elif audio_bitrate >= 128:  # Acceptable quality
                score += 15
            else:  # Low quality
                score += 8

            # Sample rate scoring (25 points)
            sample_rate = metadata.get("sample_rate", 0)

            if sample_rate >= 48000:  # High sample rate
                score += 25
            elif sample_rate >= 44100:  # CD quality
                score += 22
            elif sample_rate >= 32000:  # Acceptable
                score += 18
            else:  # Low sample rate
                score += 10

            # Channel configuration scoring (20 points)
            channels = metadata.get("audio_channels", 0)

            if channels >= 6:  # Surround sound
                score += 20
            elif channels == 2:  # Stereo
                score += 18
            elif channels == 1:  # Mono
                score += 10
            else:  # Unknown/problematic
                score += 5

            return min(score, max_score)

        except Exception as e:
            logger.error(f"Audio quality assessment failed: {e}")
            return 0.0

    async def _assess_technical_quality(self, metadata: Dict[str, Any]) -> float:
        """Assess technical quality aspects"""
        score = 0.0
        max_score = 100.0

        try:
            # Aspect ratio appropriateness (25 points)
            aspect_ratio = metadata.get("aspect_ratio", "")

            if aspect_ratio in ["16:9", "21:9"]:  # Standard widescreen
                score += 25
            elif aspect_ratio == "4:3":  # Older standard
                score += 20
            else:  # Non-standard
                score += 15

            # Color depth scoring (25 points)
            color_depth = metadata.get("color_depth", 8)

            if color_depth >= 10:  # HDR capable
                score += 25
            elif color_depth == 8:  # Standard
                score += 20
            else:  # Sub-standard
                score += 10

            # Duration appropriateness for music video (25 points)
            duration = metadata.get("duration", 0)

            if 120 <= duration <= 600:  # 2-10 minutes (typical music video)
                score += 25
            elif 60 <= duration < 120 or 600 < duration <= 900:  # Acceptable range
                score += 20
            elif 30 <= duration < 60 or 900 < duration <= 1800:  # Unusual but OK
                score += 15
            else:  # Too short/long for music video
                score += 5

            # File size efficiency (25 points)
            file_size_mb = metadata.get("file_size", 0) / (1024 * 1024)
            bitrate_mbps = metadata.get("bitrate", 0) / (1024 * 1024)

            if duration > 0:
                expected_size = (bitrate_mbps * duration) / 8  # Expected file size
                actual_size = file_size_mb

                if expected_size > 0:
                    efficiency = min(2.0, actual_size / expected_size)
                    if 0.8 <= efficiency <= 1.2:  # Good efficiency
                        score += 25
                    elif 0.6 <= efficiency <= 1.5:  # Acceptable
                        score += 20
                    else:  # Poor efficiency
                        score += 10
                else:
                    score += 15  # Default if can't calculate
            else:
                score += 15  # Default if duration unknown

            return min(score, max_score)

        except Exception as e:
            logger.error(f"Technical quality assessment failed: {e}")
            return 0.0

    async def _detect_video_type(
        self, video_path: str, artist: Optional[str] = None, title: Optional[str] = None
    ) -> VideoType:
        """Detect the type of music video content"""
        try:
            filename = Path(video_path).name.lower()

            # Check filename for type indicators
            if any(
                keyword in filename for keyword in ["live", "concert", "performance"]
            ):
                return VideoType.LIVE_PERFORMANCE
            elif any(keyword in filename for keyword in ["lyric", "lyrics"]):
                return VideoType.LYRIC_VIDEO
            elif any(keyword in filename for keyword in ["acoustic"]):
                return VideoType.ACOUSTIC_VERSION
            elif any(keyword in filename for keyword in ["remix", "mix"]):
                return VideoType.REMIX_VERSION
            elif any(keyword in filename for keyword in ["cover"]):
                return VideoType.COVER_VERSION
            elif any(
                keyword in filename for keyword in ["interview", "behind", "making"]
            ):
                return VideoType.BEHIND_SCENES
            elif any(keyword in filename for keyword in ["official", "video"]):
                return VideoType.OFFICIAL_MUSIC_VIDEO

            # Additional analysis could be added here using video content analysis

            return VideoType.OFFICIAL_MUSIC_VIDEO  # Default assumption

        except Exception as e:
            logger.error(f"Video type detection failed: {e}")
            return VideoType.UNKNOWN

    async def _assess_content_quality(
        self, video_path: str, video_type: VideoType
    ) -> float:
        """Assess content-specific quality based on video type"""
        score = 70.0  # Base score

        try:
            # Adjust score based on video type
            if video_type == VideoType.OFFICIAL_MUSIC_VIDEO:
                score += 20  # Official videos get bonus points
            elif video_type == VideoType.LIVE_PERFORMANCE:
                score += 15  # Live performances are valuable
            elif video_type == VideoType.ACOUSTIC_VERSION:
                score += 10  # Acoustic versions are good
            elif video_type == VideoType.LYRIC_VIDEO:
                score += 5  # Lyric videos are acceptable
            elif video_type == VideoType.COVER_VERSION:
                score -= 10  # Cover versions are less valuable

            # Additional content analysis could be added here

            return min(score, 100.0)

        except Exception as e:
            logger.error(f"Content quality assessment failed: {e}")
            return 50.0

    async def _check_music_video_issues(
        self, video_path: str, metrics: VideoQualityMetrics
    ):
        """Check for specific music video issues"""
        try:
            # Check for common issues
            issues = []

            # Low resolution
            if metrics.resolution.startswith(("480x", "360x", "240x")):
                issues.append("Low resolution - not suitable for modern displays")

            # Low bitrate
            if metrics.bitrate < 1000000:  # Less than 1 Mbps
                issues.append("Low bitrate may cause visible compression artifacts")

            # Unusual frame rate
            if metrics.fps < 20 or metrics.fps > 60:
                issues.append(f"Unusual frame rate ({metrics.fps} fps)")

            # No audio
            if metrics.audio_codec == "unknown":
                issues.append("No audio track detected")

            # Very short or very long
            if metrics.duration < 30:
                issues.append("Video is unusually short for a music video")
            elif metrics.duration > 900:  # 15 minutes
                issues.append("Video is unusually long for a music video")

            # Old codecs
            if metrics.video_codec in ["mpeg2", "mpeg1", "wmv"]:
                issues.append("Outdated video codec - consider reencoding")

            metrics.issues = issues

        except Exception as e:
            logger.error(f"Issue detection failed: {e}")

    def _calculate_overall_score(self, metrics: VideoQualityMetrics) -> float:
        """Calculate overall quality score from individual components"""
        try:
            total_score = (
                metrics.video_quality_score * self.quality_weights["video_quality"]
                + metrics.audio_quality_score * self.quality_weights["audio_quality"]
                + metrics.technical_quality_score
                * self.quality_weights["technical_quality"]
                + metrics.content_quality_score
                * self.quality_weights["content_quality"]
            )

            # Apply penalties for issues
            penalty = len(metrics.issues) * 5  # 5 points per issue
            total_score = max(0, total_score - penalty)

            return round(total_score, 1)

        except Exception as e:
            logger.error(f"Overall score calculation failed: {e}")
            return 0.0

    def _determine_quality_rating(self, score: float) -> QualityRating:
        """Determine quality rating from numerical score"""
        if score >= 90:
            return QualityRating.EXCELLENT
        elif score >= 70:
            return QualityRating.GOOD
        elif score >= 50:
            return QualityRating.ACCEPTABLE
        elif score >= 30:
            return QualityRating.POOR
        else:
            return QualityRating.UNACCEPTABLE

    async def _generate_recommendations(
        self, metrics: VideoQualityMetrics
    ) -> List[str]:
        """Generate recommendations for improving video quality"""
        recommendations = []

        try:
            # Resolution recommendations
            if metrics.video_quality_score < 60:
                if "x" in metrics.resolution:
                    width = int(metrics.resolution.split("x")[0])
                    if width < 1280:
                        recommendations.append(
                            "Consider finding a higher resolution version (at least 720p)"
                        )

            # Audio recommendations
            if metrics.audio_quality_score < 60:
                recommendations.append(
                    "Audio quality could be improved - look for higher bitrate version"
                )

            # Codec recommendations
            if metrics.video_codec in ["mpeg2", "mpeg1", "wmv"]:
                recommendations.append(
                    "Video uses outdated codec - modern H.264/H.265 would be better"
                )

            # Duration recommendations
            if metrics.duration < 60:
                recommendations.append(
                    "Video seems too short - verify this is the complete music video"
                )
            elif metrics.duration > 600:
                recommendations.append(
                    "Video is quite long - consider if this is the official video or extended version"
                )

            # File size recommendations
            file_size_mb = metrics.file_size / (1024 * 1024)
            if file_size_mb > 500:  # Very large file
                recommendations.append(
                    "File size is quite large - consider compression if storage is limited"
                )
            elif (
                file_size_mb < 10 and metrics.duration > 120
            ):  # Very small file for duration
                recommendations.append(
                    "File size seems small for duration - may indicate low quality encoding"
                )

            return recommendations

        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return ["Unable to generate specific recommendations"]

    async def get_quality_statistics(self) -> Dict[str, Any]:
        """Get music video quality service statistics"""
        try:
            avg_processing_time = self.stats["total_processing_time"] / max(
                1, self.stats["assessments_completed"]
            )

            return {
                "service": "Music Video Quality Assessment",
                "assessments_completed": self.stats["assessments_completed"],
                "average_quality_score": round(self.stats["average_score"], 1),
                "average_processing_time_seconds": round(avg_processing_time, 2),
                "quality_distribution": self.stats["quality_distribution"],
                "config": self.config,
                "quality_weights": self.quality_weights,
                "capabilities": {
                    "video_quality_analysis": True,
                    "audio_quality_analysis": self.config["analyze_audio_quality"],
                    "video_type_detection": self.config["detect_video_type"],
                    "sync_checking": self.config["check_sync"],
                    "recommendation_generation": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ Failed to get quality statistics: {e}")
            return {"service": "Music Video Quality Assessment", "error": str(e)}


# Global music video quality service instance
_music_video_quality_service: Optional[MusicVideoQualityService] = None


async def get_music_video_quality_service(
    config: Optional[Dict[str, Any]] = None
) -> MusicVideoQualityService:
    """Get or create global music video quality service instance"""
    global _music_video_quality_service

    if _music_video_quality_service is None:
        _music_video_quality_service = MusicVideoQualityService(config)

    return _music_video_quality_service
