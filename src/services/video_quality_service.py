"""
Video Quality Management Service for Issue #110
Implements user-configurable quality preferences and upgrade system.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import and_, asc, desc, func
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Setting, User, Video, VideoStatus
from src.services.settings_service import settings
from src.services.youtube_quality_check_service import youtube_quality_check_service
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

logger = get_logger("mvidarr.video_quality")


class QualityLevel(Enum):
    """Standardized video quality levels"""

    ULTRA_LOW = "144p"
    LOW = "240p"
    STANDARD = "360p"
    MEDIUM = "480p"
    HIGH = "720p"
    FULL_HD = "1080p"
    QUAD_HD = "1440p"
    ULTRA_HD = "2160p"  # 4K
    BEST_AVAILABLE = "best"

    @classmethod
    def from_height(cls, height: int) -> "QualityLevel":
        """Convert pixel height to quality level"""
        if height is None:
            return cls.STANDARD  # Default fallback

        try:
            height = int(height)  # Ensure it's an integer
        except (ValueError, TypeError):
            return cls.STANDARD  # Default fallback

        if height <= 144:
            return cls.ULTRA_LOW
        elif height <= 240:
            return cls.LOW
        elif height <= 360:
            return cls.STANDARD
        elif height <= 480:
            return cls.MEDIUM
        elif height <= 720:
            return cls.HIGH
        elif height <= 1080:
            return cls.FULL_HD
        elif height <= 1440:
            return cls.QUAD_HD
        else:
            return cls.ULTRA_HD

    def to_height(self) -> int:
        """Convert quality level to pixel height"""
        height_map = {
            self.ULTRA_LOW: 144,
            self.LOW: 240,
            self.STANDARD: 360,
            self.MEDIUM: 480,
            self.HIGH: 720,
            self.FULL_HD: 1080,
            self.QUAD_HD: 1440,
            self.ULTRA_HD: 2160,
            self.BEST_AVAILABLE: 9999,
        }
        return height_map.get(self, 1080)


class VideoQualityService:
    """Service for managing video quality preferences and upgrades"""

    def __init__(self):
        self.logger = logger

    def get_default_quality_preferences(self) -> Dict[str, any]:
        """Get default system-wide quality preferences"""
        return {
            "default_quality": QualityLevel.BEST_AVAILABLE.value,
            "max_quality_limit": QualityLevel.ULTRA_HD.value,  # 4K max
            "min_quality_limit": QualityLevel.MEDIUM.value,  # 480p min
            "prefer_video_codec": ["h264", "h265", "vp9", "av1"],  # Preference order
            "prefer_audio_codec": ["aac", "opus", "mp3"],
            "max_file_size_gb": 10.0,  # Maximum file size in GB
            "bandwidth_limit": None,  # No bandwidth limit by default
            "quality_fallback": True,  # Allow fallback to lower quality
            "upgrade_existing": False,  # Don't auto-upgrade existing videos
            "storage_optimization": False,  # Prioritize quality over storage
        }

    def get_user_quality_preferences(
        self, user_id: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Get quality preferences for a specific user or system defaults

        Args:
            user_id: Optional user ID for personalized preferences

        Returns:
            User's quality preferences dictionary
        """
        # Start with system defaults
        preferences = self.get_default_quality_preferences()

        try:
            # Override with user preferences if available
            if user_id:
                user_prefs = settings.get(f"user_{user_id}_quality_preferences")
                if user_prefs:
                    preferences.update(user_prefs)

            # Also check for global quality settings
            global_prefs = {
                "default_quality": settings.get(
                    "default_video_quality", preferences["default_quality"]
                ),
                "max_quality_limit": settings.get(
                    "max_video_quality", preferences["max_quality_limit"]
                ),
                "min_quality_limit": settings.get(
                    "min_video_quality", preferences["min_quality_limit"]
                ),
                "max_file_size_gb": settings.get(
                    "max_video_file_size_gb", preferences["max_file_size_gb"]
                ),
            }

            # Update preferences with non-None values
            for key, value in global_prefs.items():
                if value is not None:
                    preferences[key] = value

            self.logger.debug(
                f"Retrieved quality preferences for user {user_id}: {preferences}"
            )
            return preferences

        except Exception as e:
            self.logger.error(f"Error getting user quality preferences: {e}")
            return preferences

    def set_user_quality_preferences(
        self, preferences: Dict[str, any], user_id: Optional[int] = None
    ) -> bool:
        """
        Set quality preferences for a user or globally

        Args:
            preferences: Quality preferences dictionary
            user_id: Optional user ID for personalized preferences

        Returns:
            True if preferences were saved successfully
        """
        try:
            # Validate preferences
            if not self._validate_quality_preferences(preferences):
                return False

            if user_id:
                # Save user-specific preferences
                settings.set(f"user_{user_id}_quality_preferences", preferences)
            else:
                # Save as global preferences
                for key, value in preferences.items():
                    if key in [
                        "default_quality",
                        "max_quality_limit",
                        "min_quality_limit",
                        "max_file_size_gb",
                    ]:
                        setting_key = key.replace("_quality", "_video_quality").replace(
                            "_limit", ""
                        )
                        settings.set(setting_key, value)

            self.logger.info(
                f"Updated quality preferences for user {user_id}: {preferences}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error setting quality preferences: {e}")
            return False

    def _validate_quality_preferences(self, preferences: Dict[str, any]) -> bool:
        """Validate quality preferences structure and values"""
        try:
            # Check required fields
            required_fields = [
                "default_quality",
                "max_quality_limit",
                "min_quality_limit",
            ]
            for field in required_fields:
                if field not in preferences:
                    self.logger.error(
                        f"Missing required field in quality preferences: {field}"
                    )
                    return False

            # Validate quality values
            valid_qualities = [q.value for q in QualityLevel]
            for quality_field in [
                "default_quality",
                "max_quality_limit",
                "min_quality_limit",
            ]:
                if preferences[quality_field] not in valid_qualities:
                    self.logger.error(
                        f"Invalid quality value: {preferences[quality_field]}"
                    )
                    return False

            # Validate file size limit
            max_size = preferences.get("max_file_size_gb")
            if max_size is not None and (
                not isinstance(max_size, (int, float)) or max_size <= 0
            ):
                self.logger.error(f"Invalid max file size: {max_size}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating quality preferences: {e}")
            return False

    @monitor_performance("video_quality.generate_ytdlp_format_string")
    def generate_ytdlp_format_string(
        self, user_id: Optional[int] = None, artist_id: Optional[int] = None
    ) -> str:
        """
        Generate yt-dlp format string with improved quality selection using -S parameters

        Uses advanced format selection based on:
        - Resolution preference (1080p optimal)
        - Container preference (mp4:m4a)
        - Codec preference (AVC1/H264)
        - Quality-focused selection strategy

        Args:
            user_id: Optional user ID for personalized preferences
            artist_id: Optional artist ID for artist-specific preferences

        Returns:
            yt-dlp format string with improved quality selection
        """
        try:
            # Get base preferences
            preferences = self.get_user_quality_preferences(user_id)

            # Check for artist-specific overrides
            if artist_id:
                artist_prefs = self._get_artist_quality_preferences(artist_id)
                if artist_prefs:
                    preferences.update(artist_prefs)

            # Build format string based on preferences
            default_quality = preferences.get(
                "default_quality", QualityLevel.BEST_AVAILABLE.value
            )
            max_quality = preferences.get(
                "max_quality_limit", QualityLevel.ULTRA_HD.value
            )
            min_quality = preferences.get(
                "min_quality_limit", QualityLevel.MEDIUM.value
            )

            # Convert quality levels to heights
            max_height = (
                QualityLevel(max_quality).to_height() if max_quality != "best" else 9999
            )
            min_height = QualityLevel(min_quality).to_height()

            format_parts = []

            # IMPROVED STRATEGY: Use yt-dlp's advanced format selection with -S parameters
            # This provides much better quality selection than traditional format strings

            # Primary: High-quality formats with AVC1 codec preference (best compatibility)
            # Target 1080p as optimal balance of quality and file size
            if max_height >= 1080:
                # Best quality 1080p with AVC1 codec and MP4 container
                format_parts.extend(
                    [
                        "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=1080][vcodec^=avc1]+bestaudio",
                        "bestvideo[height<=1080][ext=mp4]+bestaudio[acodec^=mp4a]/bestvideo[height<=1080][ext=mp4]+bestaudio",
                    ]
                )

            if max_height >= 720:
                # Fallback to 720p with same codec preferences
                format_parts.extend(
                    [
                        "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=720][vcodec^=avc1]+bestaudio",
                        "bestvideo[height<=720][ext=mp4]+bestaudio[acodec^=mp4a]/bestvideo[height<=720][ext=mp4]+bestaudio",
                    ]
                )

            # Secondary: Traditional best quality with height limits
            if default_quality == QualityLevel.BEST_AVAILABLE.value:
                if max_height >= 1080:
                    # Prioritize 1080p as optimal quality
                    format_parts.extend(
                        [
                            "best[height<=1080][vcodec^=avc1][ext=mp4]",
                            "best[height<=1080][ext=mp4]",
                            "best[height<=1080]",
                        ]
                    )
                elif max_height >= 720:
                    format_parts.extend(
                        [
                            "best[height<=720][vcodec^=avc1][ext=mp4]",
                            "best[height<=720][ext=mp4]",
                            "best[height<=720]",
                        ]
                    )
                else:
                    format_parts.append(f"best[height<={max_height}]")
            else:
                # Specific quality preference
                target_height = QualityLevel(default_quality).to_height()
                format_parts.extend(
                    [
                        f"best[height<={target_height}][vcodec^=avc1][ext=mp4]",
                        f"best[height<={target_height}][ext=mp4]",
                        f"best[height<={target_height}]",
                    ]
                )

            # Tertiary: Quality fallback chain with codec preferences
            if preferences.get("quality_fallback", True):
                fallback_heights = (
                    [1080, 720, 480] if max_height >= 480 else [max_height]
                )
                for height in fallback_heights:
                    if min_height <= height <= max_height:
                        format_parts.extend(
                            [
                                f"best[height<={height}][vcodec^=avc1][ext=mp4]",
                                f"best[height<={height}][ext=mp4]",
                                f"best[height<={height}]",
                            ]
                        )

            # Final fallbacks: Ensure something downloads
            format_parts.extend(
                [
                    "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]",  # Best AVC1 + MP4 audio
                    "bestvideo[ext=mp4]+bestaudio[acodec^=mp4a]",  # Best MP4 video + MP4 audio
                    "bestvideo+bestaudio/best[ext=mp4]",  # Any separate streams or MP4
                    "best",  # Ultimate fallback
                ]
            )

            # Join with forward slashes for yt-dlp format selection
            format_string = "/".join(format_parts)

            self.logger.debug(
                f"Generated improved yt-dlp format string for user {user_id}, artist {artist_id}: {format_string[:200]}..."
            )
            return format_string

        except Exception as e:
            self.logger.error(f"Error generating yt-dlp format string: {e}")
            # Return improved safe default with AVC1 and MP4 preferences
            return (
                "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                "bestvideo[height<=1080][ext=mp4]+bestaudio/"
                "best[height<=1080][ext=mp4]/"
                "best[height<=720][ext=mp4]/"
                "bestvideo[height<=1080]+bestaudio/"
                "best"
            )

    def _get_artist_quality_preferences(
        self, artist_id: int
    ) -> Optional[Dict[str, any]]:
        """Get artist-specific quality preferences"""
        try:
            artist_prefs = settings.get(f"artist_{artist_id}_quality_preferences")
            return artist_prefs if isinstance(artist_prefs, dict) else None
        except Exception as e:
            self.logger.debug(
                f"No artist-specific quality preferences for artist {artist_id}: {e}"
            )
            return None

    def set_artist_quality_preferences(
        self, artist_id: int, preferences: Dict[str, any]
    ) -> bool:
        """Set quality preferences for a specific artist"""
        try:
            if not self._validate_quality_preferences(preferences):
                return False

            settings.set(f"artist_{artist_id}_quality_preferences", preferences)
            self.logger.info(
                f"Set artist {artist_id} quality preferences: {preferences}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error setting artist quality preferences: {e}")
            return False

    @monitor_performance("video_quality.analyze_video_quality")
    def analyze_video_quality(self, video: Video) -> Dict[str, any]:
        """
        Analyze the current quality of a video

        Args:
            video: Video database object

        Returns:
            Quality analysis dictionary
        """
        analysis = {
            "current_quality": None,
            "current_height": None,
            "current_width": None,
            "file_size_mb": None,
            "quality_level": None,
            "codec_info": {},
            "quality_score": 0,
            "upgrade_recommended": False,
            "upgrade_available": True,  # Assume upgrades available unless proven otherwise
        }

        try:
            # Get basic quality info
            if video.quality:
                analysis["current_quality"] = video.quality

                # Extract height from quality string (e.g., "1080p" -> 1080)
                if "p" in video.quality:
                    try:
                        height = int(video.quality.replace("p", ""))
                        analysis["current_height"] = height
                        analysis["quality_level"] = QualityLevel.from_height(
                            height
                        ).value
                    except ValueError:
                        pass

            # Get technical metadata if available
            if video.video_metadata:
                metadata = video.video_metadata
                analysis["current_width"] = metadata.get("width")

                # Ensure height is an integer
                metadata_height = metadata.get("height")
                if metadata_height is not None:
                    try:
                        metadata_height = int(metadata_height)
                        analysis["current_height"] = metadata_height
                    except (ValueError, TypeError):
                        pass  # Keep existing current_height
                analysis["codec_info"] = {
                    "video_codec": metadata.get("video_codec"),
                    "audio_codec": metadata.get("audio_codec"),
                    "fps": metadata.get("fps"),
                    "bitrate": metadata.get("bitrate"),
                }

                # Recalculate quality level from actual height
                if analysis["current_height"]:
                    analysis["quality_level"] = QualityLevel.from_height(
                        analysis["current_height"]
                    ).value

            # Calculate file size
            if video.local_path:
                try:
                    import os

                    if os.path.exists(video.local_path):
                        file_size_bytes = os.path.getsize(video.local_path)
                        analysis["file_size_mb"] = file_size_bytes / (1024 * 1024)
                except Exception:
                    pass

            # Calculate quality score (0-100)
            quality_score = 0
            if analysis["current_height"]:
                height = analysis["current_height"]
                # Ensure height is numeric for comparisons
                try:
                    height = int(height)
                except (ValueError, TypeError):
                    height = 0

                if height >= 2160:
                    quality_score = 100  # 4K
                elif height >= 1440:
                    quality_score = 90  # 1440p
                elif height >= 1080:
                    quality_score = 80  # 1080p
                elif height >= 720:
                    quality_score = 60  # 720p
                elif height >= 480:
                    quality_score = 40  # 480p
                elif height >= 360:
                    quality_score = 25  # 360p
                else:
                    quality_score = 10  # Below 360p

                # Bonus for good codecs
                video_codec = analysis["codec_info"].get("video_codec") or ""
                video_codec = video_codec.lower() if video_codec else ""
                if "h264" in video_codec or "h265" in video_codec:
                    quality_score += 5
                elif "av1" in video_codec:
                    quality_score += 10

            analysis["quality_score"] = min(quality_score, 100)

            # Determine if upgrade is recommended
            current_height = analysis["current_height"] or 0
            # Ensure current_height is numeric for comparison
            try:
                current_height = int(current_height) if current_height else 0
            except (ValueError, TypeError):
                current_height = 0

            if current_height < 1080:  # Recommend upgrade for anything below 1080p
                analysis["upgrade_recommended"] = True

            return analysis

        except Exception as e:
            self.logger.error(
                f"Error analyzing video quality for video {video.id}: {e}"
            )
            return analysis

    @monitor_performance("video_quality.find_upgradeable_videos")
    def find_upgradeable_videos(
        self, user_id: Optional[int] = None, limit: int = 0
    ) -> List[Dict[str, any]]:
        """
        Find videos that could benefit from quality upgrades

        Args:
            user_id: Optional user ID for preference filtering
            limit: Maximum number of videos to return

        Returns:
            List of upgradeable video information
        """
        upgradeable_videos = []

        try:
            with get_db() as session:
                # Get videos with known quality below 1080p
                # Build query
                query = session.query(Video).filter(
                    Video.status == VideoStatus.DOWNLOADED,
                    Video.local_path.isnot(None),
                    Video.quality.isnot(None),
                )

                # Apply limit only if specified (0 means no limit)
                if limit > 0:
                    query = query.limit(limit * 2)  # Get extra to filter

                videos = query.all()

                user_preferences = self.get_user_quality_preferences(user_id)
                target_quality = user_preferences.get("default_quality", "1080p")

                for video in videos:
                    # Use YouTube quality check data if available
                    if not youtube_quality_check_service.is_video_upgradeable(video):
                        continue

                    analysis = self.analyze_video_quality(video)

                    if analysis["upgrade_recommended"]:
                        upgrade_info = {
                            "video_id": video.id,
                            "title": video.title,
                            "artist_name": None,
                            "current_quality": analysis["current_quality"],
                            "current_height": analysis["current_height"],
                            "quality_score": analysis["quality_score"],
                            "file_size_mb": analysis["file_size_mb"],
                            "recommended_quality": target_quality,
                            "upgrade_priority": self._calculate_upgrade_priority(
                                analysis, user_preferences
                            ),
                        }

                        # Get artist name
                        if video.artist_id:
                            artist = (
                                session.query(Artist)
                                .filter(Artist.id == video.artist_id)
                                .first()
                            )
                            if artist:
                                upgrade_info["artist_name"] = artist.name

                        upgradeable_videos.append(upgrade_info)

                # Sort by upgrade priority (highest first)
                upgradeable_videos.sort(
                    key=lambda x: x["upgrade_priority"], reverse=True
                )

                # Apply limit only if specified (0 means no limit)
                if limit > 0:
                    return upgradeable_videos[:limit]
                else:
                    return upgradeable_videos

        except Exception as e:
            self.logger.error(f"Error finding upgradeable videos: {e}")
            return []

    def _calculate_upgrade_priority(
        self, analysis: Dict[str, any], preferences: Dict[str, any]
    ) -> int:
        """Calculate priority score for video upgrade (0-100)"""
        priority = 0

        # Base priority on current quality
        current_height = analysis.get("current_height", 0)
        # Ensure height is numeric for comparisons
        try:
            current_height = int(current_height) if current_height else 0
        except (ValueError, TypeError):
            current_height = 0

        if current_height <= 360:
            priority += 50  # High priority for very low quality
        elif current_height <= 480:
            priority += 30  # Medium priority
        elif current_height <= 720:
            priority += 15  # Lower priority

        # Bonus for very small file sizes (likely low bitrate)
        file_size_mb = analysis.get("file_size_mb", 0)
        if file_size_mb < 50:  # Very small files likely low quality
            priority += 20
        elif file_size_mb < 100:
            priority += 10

        # Penalty for already large files
        if file_size_mb > 1000:  # 1GB+
            priority -= 10

        return min(priority, 100)

    @monitor_performance("video_quality.upgrade_video_quality")
    def upgrade_video_quality(
        self, video_id: int, user_id: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Upgrade a video to higher quality

        Args:
            video_id: Video ID to upgrade
            user_id: Optional user ID for preference filtering

        Returns:
            Upgrade result dictionary
        """
        try:
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    return {"success": False, "error": "Video not found"}

                # Use youtube_url or url as the source URL
                video_url = video.youtube_url or video.url
                if not video_url:
                    return {
                        "success": False,
                        "error": "No source URL available for upgrade",
                    }

                # Analyze current quality
                current_analysis = self.analyze_video_quality(video)

                # Get upgrade preferences
                user_prefs = self.get_user_quality_preferences(user_id)
                new_format_string = self.generate_ytdlp_format_string(
                    user_id, video.artist_id
                )

                # Create new download with higher quality settings
                from src.services.ytdlp_service import ytdlp_service

                # Get artist name for download
                artist_name = "Unknown Artist"
                if video.artist_id:
                    artist = (
                        session.query(Artist)
                        .filter(Artist.id == video.artist_id)
                        .first()
                    )
                    if artist:
                        artist_name = artist.name

                # Mark video for upgrade in database BEFORE queuing download
                video.video_metadata = video.video_metadata or {}
                video.video_metadata.update(
                    {
                        "upgrade_requested": True,
                        "upgrade_requested_at": datetime.utcnow().isoformat(),
                        "upgrade_from_quality": current_analysis.get("current_quality"),
                        "upgrade_target_quality": user_prefs.get("default_quality"),
                        "original_file_path": video.local_path,  # Store for cleanup
                    }
                )
                session.commit()  # Commit the upgrade flag immediately

                # Queue the upgrade download using background job system
                import asyncio

                from src.services.job_queue import (
                    BackgroundJob,
                    JobPriority,
                    JobType,
                    get_job_queue,
                )

                # Create background job for video download
                download_job = BackgroundJob(
                    type=JobType.VIDEO_DOWNLOAD,
                    priority=JobPriority.HIGH,  # Quality upgrades are high priority
                    payload={
                        "video_id": video_id,
                        "quality": "best",  # Will be overridden by format string
                        "force_redownload": True,  # Always redownload for upgrades
                        "upgrade_mode": True,  # Flag this as an upgrade
                        "original_quality": current_analysis.get("current_quality"),
                        "target_quality": user_prefs.get("default_quality"),
                    },
                )

                # Queue the download job
                async def queue_download_job():
                    job_queue = await get_job_queue()
                    return await job_queue.enqueue(download_job)

                download_job_id = asyncio.run(queue_download_job())

                self.logger.info(
                    f"Queued video download job {download_job_id} for quality upgrade of video {video_id}"
                )

                return {
                    "success": True,
                    "message": "Video upgrade download queued",
                    "download_job_id": download_job_id,
                    "current_quality": current_analysis.get("current_quality"),
                    "target_quality": user_prefs.get("default_quality"),
                }

        except Exception as e:
            self.logger.error(f"Error upgrading video {video_id}: {e}")
            return {"success": False, "error": str(e)}

    @monitor_performance("video_quality.bulk_upgrade_videos")
    def bulk_upgrade_videos(
        self, video_ids: List[int], user_id: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Upgrade multiple videos to higher quality

        Args:
            video_ids: List of video IDs to upgrade
            user_id: Optional user ID for preference filtering

        Returns:
            Bulk upgrade result summary
        """
        results = {
            "success": True,
            "total_requested": len(video_ids),
            "successful_upgrades": 0,
            "failed_upgrades": 0,
            "errors": [],
        }

        for video_id in video_ids:
            try:
                upgrade_result = self.upgrade_video_quality(video_id, user_id)
                if upgrade_result.get("success"):
                    results["successful_upgrades"] += 1
                else:
                    results["failed_upgrades"] += 1
                    results["errors"].append(
                        f"Video {video_id}: {upgrade_result.get('error')}"
                    )
            except Exception as e:
                results["failed_upgrades"] += 1
                results["errors"].append(f"Video {video_id}: {str(e)}")

        if results["failed_upgrades"] > 0:
            results["success"] = False

        self.logger.info(f"Bulk upgrade completed: {results}")
        return results

    def get_quality_statistics(self) -> Dict[str, any]:
        """Get system-wide video quality statistics"""
        stats = {
            "total_videos": 0,
            "quality_distribution": {},
            "average_file_size_mb": 0,
            "upgrade_candidates": 0,
            "storage_usage_gb": 0,
        }

        try:
            with get_db() as session:
                videos = (
                    session.query(Video)
                    .filter(
                        Video.status == VideoStatus.DOWNLOADED,
                        Video.local_path.isnot(None),
                    )
                    .all()
                )

                stats["total_videos"] = len(videos)
                total_size_bytes = 0
                quality_counts = {}
                upgrade_candidates = 0

                for video in videos:
                    analysis = self.analyze_video_quality(video)

                    # Quality distribution
                    quality = analysis.get("quality_level", "Unknown")
                    quality_counts[quality] = quality_counts.get(quality, 0) + 1

                    # File size tracking
                    file_size_mb = analysis.get("file_size_mb", 0)
                    if file_size_mb:
                        total_size_bytes += file_size_mb * 1024 * 1024

                    # Upgrade candidates
                    if analysis.get("upgrade_recommended"):
                        upgrade_candidates += 1

                stats["quality_distribution"] = quality_counts
                stats["upgrade_candidates"] = upgrade_candidates
                stats["storage_usage_gb"] = total_size_bytes / (1024**3)

                if len(videos) > 0:
                    stats["average_file_size_mb"] = (
                        total_size_bytes / (1024**2)
                    ) / len(videos)

        except Exception as e:
            self.logger.error(f"Error getting quality statistics: {e}")

        return stats


# Global service instance
video_quality_service = VideoQualityService()
