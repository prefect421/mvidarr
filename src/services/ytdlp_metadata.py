"""
Utility module for emergency video metadata extraction and file recovery.

This module provides fallback mechanisms for validating video downloads,
searching for files when expected paths don't exist, and extracting basic
metadata using ffprobe when yt-dlp metadata is unavailable.
"""

import glob
import json
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Optional

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services.settings_service import settings
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.ytdlp_metadata")


class YtDlpMetadata:
    """Utility class for emergency metadata extraction and file recovery."""

    @staticmethod
    def emergency_validate_video_linking(
        video_id: int, download_entry: dict, find_downloaded_file_func
    ):
        """
        Emergency validation and recovery system for video file linking.

        Implements comprehensive defensive measures for download validation.
        If a video's local_path is None after download, attempts to recover
        the file using multiple search strategies.

        Args:
            video_id: Database ID of the video to validate
            download_entry: Download metadata dictionary
            find_downloaded_file_func: Function to find downloaded files
                                      (from YtDlpFileDetection.find_downloaded_file)
        """
        try:
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if not video:
                    logger.error(
                        f"❌ Video {video_id} not found for emergency validation"
                    )
                    return

                if video.local_path is None:
                    logger.warning(
                        f"⚠️  Video {video_id} was not properly linked after download completion"
                    )
                    logger.warning(f"   Attempting emergency file linking recovery...")

                    # First try improved file detection on the original template
                    recovered_file_path = None
                    if "output_dir" in download_entry:
                        output_template = os.path.join(
                            download_entry["output_dir"],
                            f"{FilenameCleanup.sanitize_folder_name(download_entry.get('title', 'Unknown'))}.%(ext)s",
                        )
                        recovered_file_path = find_downloaded_file_func(
                            output_template, download_entry
                        )
                        if recovered_file_path:
                            logger.info(
                                f"   ✅ Found file using improved template detection: {recovered_file_path}"
                            )

                    # If that fails, try comprehensive file search
                    if not recovered_file_path:
                        recovered_file_path = YtDlpMetadata.emergency_file_search(
                            video, download_entry, session
                        )

                    if recovered_file_path:
                        video.local_path = recovered_file_path
                        session.commit()
                        logger.info(
                            f"✅ Emergency linking recovery successful: {recovered_file_path}"
                        )

                        # Extract basic metadata from recovered file
                        YtDlpMetadata.extract_basic_metadata_emergency(
                            video, recovered_file_path, session
                        )
                    else:
                        logger.error(
                            f"❌ Emergency linking recovery FAILED for video {video_id}"
                        )
                        logger.error(
                            f"   Manual intervention required - check fix_unlinked_videos.py"
                        )
                else:
                    logger.info(
                        f"✅ Video {video_id} successfully linked to {video.local_path}"
                    )

        except Exception as e:
            logger.error(f"Emergency validation failed for video {video_id}: {e}")

    @staticmethod
    def emergency_file_search(video, download_entry: dict, session) -> Optional[str]:
        """
        Emergency file search using multiple patterns and fallback locations.

        Searches for downloaded video files in common locations when the
        expected file path is not found. Uses various patterns including:
        - Organized location (data/musicvideos/Artist/Title)
        - YouTube download location (data/musicvideos/YouTube/...)
        - Direct download location

        Args:
            video: Video database model instance
            download_entry: Download metadata dictionary
            session: Database session

        Returns:
            Path to found file if successful, None otherwise
        """
        try:
            music_videos_path = settings.get("music_videos_path", "data/musicvideos")

            # Get artist name for file location
            artist_name = "Unknown Artist"
            if video.artist_id:
                artist = (
                    session.query(Artist).filter(Artist.id == video.artist_id).first()
                )
                if artist:
                    artist_name = artist.name

            # Clean video title for filename matching
            video_title = video.title or f"Video_{video.id}"
            clean_title = YtDlpMetadata.sanitize_filename_for_search(video_title)

            # Search patterns for downloaded files
            search_patterns = [
                # Organized location: data/musicvideos/Artist/Title.ext
                os.path.join(
                    music_videos_path,
                    YtDlpMetadata.sanitize_filename_for_search(artist_name),
                    f"*{clean_title[:20]}*",
                ),
                # YouTube download location: data/musicvideos/YouTube/Date-Title/file
                os.path.join(
                    music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.mp4"
                ),
                os.path.join(
                    music_videos_path, "YouTube", f"*{clean_title[:20]}*", "*.webm"
                ),
                # Direct download location
                os.path.join(music_videos_path, "*", f"*{clean_title[:20]}*"),
                # Also search in download entry output dir if available
                (
                    os.path.join(
                        download_entry.get("output_dir", ""), f"*{clean_title[:20]}*"
                    )
                    if download_entry.get("output_dir")
                    else None
                ),
            ]

            # Remove None patterns
            search_patterns = [p for p in search_patterns if p]

            # Search for video files
            video_exts = [".mp4", ".webm", ".mkv", ".avi"]
            for pattern in search_patterns:
                logger.info(f"🔍 Emergency search pattern: {pattern}")
                potential_files = glob.glob(pattern)
                for file_path in potential_files:
                    if any(file_path.endswith(ext) for ext in video_exts):
                        # Check if this file was recently created (within last 30 minutes)
                        if os.path.exists(file_path):
                            file_time = os.path.getmtime(file_path)
                            if time.time() - file_time < 1800:  # 30 minutes
                                logger.info(
                                    f"✅ Emergency recovery found recent file: {file_path}"
                                )
                                return file_path

            logger.warning(f"❌ Emergency file search failed for video {video.id}")
            return None

        except Exception as e:
            logger.error(f"Emergency file search failed: {e}")
            return None

    @staticmethod
    def extract_basic_metadata_emergency(video, file_path: str, session):
        """
        Emergency metadata extraction with graceful fallbacks.

        Uses ffprobe to extract basic video information (duration, quality,
        resolution, codec) when yt-dlp metadata is not available.

        Args:
            video: Video database model instance to update
            file_path: Path to the video file
            session: Database session
        """
        try:
            # Use ffprobe to get video information
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                probe_data = json.loads(result.stdout)

                # Extract duration from format
                format_info = probe_data.get("format", {})
                duration = float(format_info.get("duration", 0))

                # Extract video stream info
                video_stream = next(
                    (
                        s
                        for s in probe_data.get("streams", [])
                        if s.get("codec_type") == "video"
                    ),
                    None,
                )
                if video_stream:
                    width = video_stream.get("width", 0)
                    height = video_stream.get("height", 0)
                    codec = video_stream.get("codec_name", "unknown")

                    # Determine quality based on height
                    if height >= 2160:
                        quality = "4K"
                    elif height >= 1440:
                        quality = "1440p"
                    elif height >= 1080:
                        quality = "1080p"
                    elif height >= 720:
                        quality = "720p"
                    elif height >= 480:
                        quality = "480p"
                    else:
                        quality = "SD"

                    # Update video record with emergency metadata
                    video.duration = duration
                    video.quality = quality

                    # Update video_metadata
                    existing_metadata = video.video_metadata or {}
                    existing_metadata.update(
                        {
                            "width": width,
                            "height": height,
                            "video_codec": codec,
                            "file_size": (
                                os.path.getsize(file_path)
                                if os.path.exists(file_path)
                                else None
                            ),
                            "emergency_recovery": True,
                            "extraction_date": datetime.utcnow().isoformat(),
                        }
                    )
                    video.video_metadata = existing_metadata

                    session.commit()
                    logger.info(
                        f"✅ Emergency metadata extraction successful for video {video.id}"
                    )

        except Exception as e:
            logger.warning(
                f"Emergency metadata extraction failed for video {video.id}: {e}"
            )
            # Don't fail - at least we have the file path

    @staticmethod
    def sanitize_filename_for_search(filename: str) -> str:
        """
        Sanitize filename for search patterns and filesystem compatibility.

        Removes problematic characters and truncates to reasonable length.

        Args:
            filename: Original filename to sanitize

        Returns:
            Sanitized filename safe for filesystem operations
        """
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", filename)
        sanitized = re.sub(r"[^\w\s-]", "", sanitized).strip()
        return sanitized[:100] if sanitized else "Unknown"
