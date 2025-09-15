"""
YouTube Quality Check Service

Checks YouTube for available video qualities and stores results in the database.
This helps determine which videos are truly upgradeable.
"""

import re
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_

from src.database.connection import get_db
from src.database.models import Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.youtube_quality_check")


class YouTubeQualityCheckService:
    """Service for checking available YouTube video qualities"""

    def __init__(self):
        self.rate_limit_delay = 2.0  # Seconds between requests to avoid throttling
        self.last_request_time = 0

    def _rate_limit(self):
        """Implement rate limiting for YouTube requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def check_video_quality(self, video: Video) -> Dict:
        """
        Check available qualities for a single video

        Args:
            video: Video database object

        Returns:
            Dictionary with quality check results
        """
        result = {
            "success": False,
            "available_qualities": [],
            "max_available_quality": None,
            "error": None,
            "check_date": datetime.utcnow(),
        }

        try:
            # Get video URL
            video_url = video.youtube_url or video.url
            if not video_url:
                result["error"] = "No video URL available"
                return result

            # Rate limit requests
            self._rate_limit()

            # Run yt-dlp to get available formats
            logger.info(
                f"Checking available qualities for video {video.id}: {video.title}"
            )

            cmd = ["yt-dlp", "--list-formats", "--no-warnings", video_url]

            process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if process.returncode != 0:
                result["error"] = f"yt-dlp failed: {process.stderr.strip()}"
                return result

            # Parse the output to extract available qualities
            qualities = self._parse_formats_output(process.stdout)

            result["available_qualities"] = qualities
            result["max_available_quality"] = self._get_max_quality(qualities)
            result["success"] = True

            logger.info(
                f"Video {video.id} qualities: {qualities}, max: {result['max_available_quality']}"
            )

        except subprocess.TimeoutExpired:
            result["error"] = "yt-dlp request timed out"
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error checking quality for video {video.id}: {e}")

        return result

    def _parse_formats_output(self, output: str) -> List[Dict]:
        """
        Parse yt-dlp format list output to extract quality information

        Args:
            output: Raw yt-dlp output

        Returns:
            List of quality dictionaries
        """
        qualities = []

        # Look for format lines (skip headers and storyboards)
        lines = output.split("\n")
        for line in lines:
            line = line.strip()

            # Skip headers, empty lines, and storyboard formats
            if (
                not line
                or line.startswith("ID")
                or line.startswith("-")
                or "storyboard" in line
                or "images" in line
            ):
                continue

            # Skip audio-only formats
            if "audio only" in line:
                continue

            # Parse format line using regex to be more flexible
            # Look for resolution pattern like "256x144", "426x240", "1920x1080"
            resolution_match = re.search(r"(\d+)x(\d+)", line)
            if not resolution_match:
                continue

            try:
                width = int(resolution_match.group(1))
                height = int(resolution_match.group(2))
                resolution = f"{width}x{height}"

                # Extract format ID (first field)
                parts = line.split()
                if len(parts) < 1:
                    continue

                format_id = parts[0]

                # Try to extract extension (second field, but be flexible)
                extension = "mp4"  # default
                if len(parts) > 1 and parts[1] in ["mp4", "webm", "mkv", "3gp", "flv"]:
                    extension = parts[1]

                quality_dict = {
                    "format_id": format_id,
                    "extension": extension,
                    "resolution": resolution,
                    "width": width,
                    "height": height,
                    "quality_label": f"{height}p",
                }
                qualities.append(quality_dict)

            except (IndexError, ValueError) as e:
                # Skip malformed lines
                logger.debug(f"Skipping malformed format line: {line}")
                continue

        # Sort by height (highest first) and deduplicate by height
        qualities.sort(key=lambda x: x["height"], reverse=True)

        # Remove duplicates by height, keeping the first (highest quality) of each resolution
        seen_heights = set()
        unique_qualities = []
        for quality in qualities:
            if quality["height"] not in seen_heights:
                seen_heights.add(quality["height"])
                unique_qualities.append(quality)

        return unique_qualities

    def _get_max_quality(self, qualities: List[Dict]) -> Optional[str]:
        """
        Get the maximum available quality from the qualities list

        Args:
            qualities: List of quality dictionaries

        Returns:
            String representation of max quality (e.g., "1080p") or None
        """
        if not qualities:
            return None

        # Already sorted by height (highest first)
        return qualities[0]["quality_label"]

    def update_video_quality_info(self, video: Video, check_result: Dict):
        """
        Update video record with quality check results

        Args:
            video: Video database object
            check_result: Result from check_video_quality
        """
        try:
            video.available_qualities = check_result["available_qualities"]
            video.quality_check_date = check_result["check_date"]
            video.max_available_quality = check_result["max_available_quality"]

            if check_result["success"]:
                video.quality_check_status = "success"
            else:
                video.quality_check_status = "failed"
                logger.warning(
                    f"Quality check failed for video {video.id}: {check_result['error']}"
                )

        except Exception as e:
            logger.error(f"Error updating video {video.id} quality info: {e}")
            video.quality_check_status = "failed"

    def check_all_videos(
        self, limit: Optional[int] = None, only_unchecked: bool = True
    ) -> Dict:
        """
        Check qualities for multiple videos

        Args:
            limit: Maximum number of videos to check
            only_unchecked: Only check videos not checked recently

        Returns:
            Summary of check results
        """
        summary = {
            "total_checked": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "skipped": 0,
            "errors": [],
        }

        try:
            with get_db() as session:
                # Build query for videos to check
                query = session.query(Video).filter(
                    Video.status == VideoStatus.DOWNLOADED,
                    Video.youtube_url.isnot(None),
                )

                # Only check videos not checked in the last 7 days
                if only_unchecked:
                    week_ago = datetime.utcnow() - timedelta(days=7)
                    query = query.filter(
                        (Video.quality_check_date.is_(None))
                        | (Video.quality_check_date < week_ago)
                    )

                if limit:
                    query = query.limit(limit)

                videos = query.all()
                total_videos = len(videos)

                logger.info(f"Starting quality check for {total_videos} videos")

                # Process videos with progress logging
                processed_count = 0
                for video in videos:
                    processed_count += 1

                    # Log progress every 10 videos
                    if processed_count % 10 == 0 or processed_count == total_videos:
                        logger.info(
                            f"Quality check progress: {processed_count}/{total_videos} videos processed"
                        )

                    try:
                        # Check this video's quality
                        check_result = self.check_video_quality(video)

                        # Update the database
                        self.update_video_quality_info(video, check_result)
                        session.commit()

                        summary["total_checked"] += 1
                        if check_result["success"]:
                            summary["successful_checks"] += 1
                            logger.debug(
                                f"Video {video.id} ({video.title[:30]}...): Found max quality {check_result.get('max_available_quality')}"
                            )
                        else:
                            summary["failed_checks"] += 1
                            summary["errors"].append(
                                f"Video {video.id}: {check_result['error']}"
                            )

                    except Exception as e:
                        summary["failed_checks"] += 1
                        summary["errors"].append(f"Video {video.id}: {str(e)}")
                        logger.error(f"Error processing video {video.id}: {e}")

                logger.info(f"Quality check complete: {summary}")

        except Exception as e:
            logger.error(f"Error in check_all_videos: {e}")
            summary["errors"].append(str(e))

        return summary

    def is_video_upgradeable(self, video: Video) -> bool:
        """
        Check if a video is truly upgradeable based on quality check data

        Args:
            video: Video database object

        Returns:
            True if video can be upgraded to better quality
        """
        # If no quality check has been performed yet, allow upgrade attempts
        # This maintains backward compatibility and doesn't block existing functionality
        if not video.quality_check_date:
            return True

        # If quality check failed, still allow upgrade attempts (fallback behavior)
        if video.quality_check_status != "success":
            return True

        # Must have current quality
        current_quality = video.quality
        if not current_quality:
            return True  # Allow upgrade attempt if current quality unknown

        # Must have max available quality
        max_available = video.max_available_quality
        if not max_available:
            return True  # Allow upgrade attempt if max quality unknown

        # Compare qualities (extract numeric height)
        try:
            current_height = int(re.sub(r"[^\d]", "", current_quality))
            max_height = int(re.sub(r"[^\d]", "", max_available))

            # Only block upgrade if we're certain current quality is >= max available
            return max_height > current_height

        except (ValueError, TypeError):
            return True  # Allow upgrade attempt if quality parsing fails


# Global service instance
youtube_quality_check_service = YouTubeQualityCheckService()
