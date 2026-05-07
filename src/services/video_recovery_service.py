"""
Video Recovery Service - Handles missing video detection and file recovery
"""

import os
from typing import Optional

from sqlalchemy import and_

from src.database.connection import get_db
from src.database.models import Video, VideoStatus
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.video_recovery")


class VideoRecoveryService:
    """Service for recovering missing videos and fixing broken file paths"""

    def __init__(self):
        self.downloads_dir = None
        self._init_downloads_dir()

    def _init_downloads_dir(self):
        """Initialize downloads directory path"""
        try:
            self.downloads_dir = settings.get("downloads_directory", "data/downloads")
            if not os.path.isabs(self.downloads_dir):
                self.downloads_dir = os.path.join(os.getcwd(), self.downloads_dir)

            # Ensure downloads directory exists
            os.makedirs(self.downloads_dir, exist_ok=True)
            logger.info(f"Initialized downloads directory: {self.downloads_dir}")

        except Exception as e:
            logger.error(f"Failed to initialize downloads directory: {e}")
            self.downloads_dir = os.path.join(os.getcwd(), "data/downloads")

    def fix_missing_downloaded_videos(self) -> dict:
        """
        Specifically find all videos marked as DOWNLOADED but with missing files
        and set them to WANTED status

        Returns:
            dict: Statistics about the operation
        """
        stats = {
            "total_downloaded": 0,
            "missing_files": 0,
            "recovered_videos": 0,
            "marked_wanted": 0,
            "artists_monitored": 0,
        }

        try:
            with get_db() as session:
                # Get all videos marked as DOWNLOADED
                downloaded_videos = (
                    session.query(Video)
                    .filter(Video.status == VideoStatus.DOWNLOADED)
                    .all()
                )

                stats["total_downloaded"] = len(downloaded_videos)
                logger.info(
                    f"Checking {stats['total_downloaded']} videos marked as downloaded"
                )

                for video in downloaded_videos:
                    # Check if file is actually missing
                    if self._is_video_missing(video):
                        stats["missing_files"] += 1
                        logger.warning(
                            f"Missing file for downloaded video: {video.title}"
                        )

                        # Try to recover the video first
                        if self._attempt_recovery(video, session):
                            stats["recovered_videos"] += 1
                            logger.info(f"Recovered video: {video.title}")
                        else:
                            # Mark as wanted and ensure artist is monitored
                            video.status = VideoStatus.WANTED
                            video.local_path = None
                            stats["marked_wanted"] += 1
                            logger.info(f"Marked as wanted: {video.title}")

                            # Ensure artist is being tracked
                            if video.artist and not video.artist.monitored:
                                video.artist.monitored = True
                                stats["artists_monitored"] += 1
                                logger.info(
                                    f"Enabled monitoring for artist: {video.artist.name}"
                                )

                session.commit()

                logger.info(f"Missing downloaded videos fix complete: {stats}")
                return stats

        except Exception as e:
            logger.error(f"Error fixing missing downloaded videos: {e}")
            return stats

    def scan_missing_videos(self) -> dict:
        """
        Scan all videos and identify missing files

        Returns:
            dict: Recovery statistics
        """
        stats = {
            "total_videos": 0,
            "missing_videos": 0,
            "recovered_videos": 0,
            "marked_wanted": 0,
            "artists_monitored": 0,
        }

        try:
            with get_db() as session:
                # Get all videos that should have local files
                videos = (
                    session.query(Video)
                    .filter(
                        and_(
                            Video.local_path.isnot(None),
                            Video.status.in_(
                                [VideoStatus.DOWNLOADED, VideoStatus.DOWNLOADING]
                            ),
                        )
                    )
                    .all()
                )

                stats["total_videos"] = len(videos)
                logger.info(
                    f"Scanning {stats['total_videos']} videos for missing files"
                )

                for video in videos:
                    if self._is_video_missing(video):
                        stats["missing_videos"] += 1

                        # Try to recover the video
                        if self._attempt_recovery(video, session):
                            stats["recovered_videos"] += 1
                        else:
                            # Mark as wanted and ensure artist is monitored
                            if self._mark_as_wanted(video, session):
                                stats["marked_wanted"] += 1

                            if self._ensure_artist_monitored(video, session):
                                stats["artists_monitored"] += 1

                session.commit()

                logger.info(f"Video recovery scan complete: {stats}")
                return stats

        except Exception as e:
            logger.error(f"Error during video recovery scan: {e}")
            return stats

    def _is_video_missing(self, video: Video) -> bool:
        """Check if a video file is missing from its stored path"""
        if not video.local_path:
            return False

        # Construct absolute path
        if os.path.isabs(video.local_path):
            full_path = video.local_path
        else:
            full_path = os.path.join(os.getcwd(), video.local_path)

        return not os.path.exists(full_path)

    def _attempt_recovery(self, video: Video, session) -> bool:
        """
        Attempt to recover a missing video by finding it in artist folders

        Args:
            video: Video object to recover
            session: Database session

        Returns:
            bool: True if recovery successful
        """
        if not video.artist:
            return False

        try:
            recovered_path = self._find_video_in_artist_folders(video)
            if recovered_path:
                # Update video with recovered path
                video.local_path = recovered_path
                video.status = VideoStatus.DOWNLOADED

                logger.info(f"Recovered video '{video.title}' at: {recovered_path}")
                return True

        except Exception as e:
            logger.error(
                f"Error during recovery attempt for video '{video.title}': {e}"
            )

        return False

    def _find_video_in_artist_folders(self, video: Video) -> Optional[str]:
        """
        Search for video file in expected artist folder locations

        Args:
            video: Video object to search for

        Returns:
            str: Path to found video file or None
        """
        if not video.artist:
            return None

        # Possible artist folder names
        artist_names = [video.artist.name, self._sanitize_filename(video.artist.name)]

        for artist_name in artist_names:
            artist_folder = os.path.join(self.downloads_dir, artist_name)

            if os.path.exists(artist_folder):
                found_path = self._search_folder_for_video(artist_folder, video)
                if found_path:
                    return found_path

        return None

    def _search_folder_for_video(self, folder_path: str, video: Video) -> Optional[str]:
        """
        Search within a folder for a specific video file

        Args:
            folder_path: Path to search in
            video: Video object to find

        Returns:
            str: Path to video file or None
        """
        video_extensions = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v")
        video_title_clean = self._clean_title_for_matching(video.title)

        try:
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(video_extensions):
                    full_path = os.path.join(folder_path, filename)

                    # Various matching strategies
                    if self._is_filename_match(filename, video, video_title_clean):
                        return full_path

        except Exception as e:
            logger.error(f"Error searching folder {folder_path}: {e}")

        return None

    def _is_filename_match(
        self, filename: str, video: Video, video_title_clean: str
    ) -> bool:
        """
        Check if a filename matches a video using multiple strategies

        Args:
            filename: Filename to check
            video: Video object
            video_title_clean: Cleaned video title for matching

        Returns:
            bool: True if filename matches video
        """
        filename_clean = self._clean_title_for_matching(filename)

        # Strategy 1: Clean title substring match
        if video_title_clean in filename_clean or filename_clean.startswith(
            video_title_clean[:10]
        ):
            return True

        # Strategy 2: Word-based matching (require at least 3 significant words)
        video_words = [word for word in video_title_clean.split() if len(word) > 3]
        if len(video_words) >= 2:  # Only if we have meaningful words
            word_matches = sum(1 for word in video_words if word in filename_clean)
            if word_matches >= min(2, len(video_words)):
                return True

        # Strategy 3: YouTube ID match (most reliable)
        if video.youtube_id and video.youtube_id in filename:
            return True

        # Strategy 4: Exact title match (case insensitive)
        if video.title.lower() in filename.lower():
            return True

        return False

    def _clean_title_for_matching(self, title: str) -> str:
        """Clean title for fuzzy matching"""
        import re

        # Remove special characters and extra spaces
        cleaned = re.sub(r"[^\w\s]", " ", title.lower())
        # Replace multiple spaces with single space
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Remove common words that don't help with matching
        stop_words = {
            "the",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "a",
            "an",
        }
        words = [
            word for word in cleaned.split() if word not in stop_words and len(word) > 2
        ]
        return " ".join(words)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize name for use as folder name"""
        import re

        return re.sub(r'[<>:"/\\|?*]', "_", name)

    def _mark_as_wanted(self, video: Video, session) -> bool:
        """
        Mark video as wanted if it was previously downloaded

        Args:
            video: Video object to mark
            session: Database session

        Returns:
            bool: True if marked as wanted
        """
        try:
            if video.status == VideoStatus.DOWNLOADED:
                video.status = VideoStatus.WANTED
                video.local_path = None
                logger.info(f"Marked missing video as wanted: {video.title}")
                return True
        except Exception as e:
            logger.error(f"Error marking video as wanted: {e}")

        return False

    def _ensure_artist_monitored(self, video: Video, session) -> bool:
        """
        Ensure artist is being monitored for new videos

        Args:
            video: Video object whose artist should be monitored
            session: Database session

        Returns:
            bool: True if artist monitoring was enabled
        """
        try:
            if video.artist and not video.artist.monitored:
                video.artist.monitored = True
                logger.info(f"Enabled monitoring for artist: {video.artist.name}")
                return True
        except Exception as e:
            logger.error(f"Error enabling artist monitoring: {e}")

        return False

    def scan_orphaned_files(self) -> dict:
        """
        Scan downloads directory for orphaned video files (files without database records)

        Returns:
            dict: Statistics about orphaned files found
        """
        stats = {
            "total_files": 0,
            "orphaned_files": 0,
            "matched_files": 0,
            "artist_folders": 0,
        }

        try:
            if not os.path.exists(self.downloads_dir):
                logger.warning(
                    f"Downloads directory does not exist: {self.downloads_dir}"
                )
                return stats

            video_extensions = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v")
            orphaned_files = []

            # Scan each artist folder
            for item in os.listdir(self.downloads_dir):
                item_path = os.path.join(self.downloads_dir, item)

                if os.path.isdir(item_path):
                    stats["artist_folders"] += 1

                    # Scan files in artist folder
                    for filename in os.listdir(item_path):
                        if filename.lower().endswith(video_extensions):
                            file_path = os.path.join(item_path, filename)
                            stats["total_files"] += 1

                            # Check if file has corresponding database record
                            if not self._has_database_record(file_path):
                                stats["orphaned_files"] += 1
                                orphaned_files.append(file_path)
                            else:
                                stats["matched_files"] += 1

            logger.info(f"Orphaned files scan complete: {stats}")

            # Log some orphaned files for debugging
            if orphaned_files:
                logger.warning(f"Found {len(orphaned_files)} orphaned files. Examples:")
                for file_path in orphaned_files[:5]:  # Show first 5 examples
                    logger.warning(f"  Orphaned: {file_path}")

            return stats

        except Exception as e:
            logger.error(f"Error during orphaned files scan: {e}")
            return stats

    def _has_database_record(self, file_path: str) -> bool:
        """
        Check if a file path has a corresponding database record

        Args:
            file_path: Path to check

        Returns:
            bool: True if database record exists
        """
        try:
            with get_db() as session:
                # Check for exact path match
                video = (
                    session.query(Video).filter(Video.local_path == file_path).first()
                )
                if video:
                    return True

                # Check for relative path match
                relative_path = os.path.relpath(file_path, os.getcwd())
                video = (
                    session.query(Video)
                    .filter(Video.local_path == relative_path)
                    .first()
                )
                if video:
                    return True

                return False

        except Exception as e:
            logger.error(f"Error checking database record for {file_path}: {e}")
            return False


# Global service instance
video_recovery_service = VideoRecoveryService()
