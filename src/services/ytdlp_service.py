"""
Enhanced yt-dlp CLI Service for MVidarr - Refactored
Direct video downloading using yt-dlp with progress tracking

Refactored from monolithic 1,524-line file into modular architecture:
- ytdlp_cookie_manager: Cookie/authentication management
- ytdlp_file_cleanup: Post-download file cleanup operations
- ytdlp_database_sync: Database synchronization layer
- ytdlp_history: Download history and resume functionality
- ytdlp_download_manager: Core download operations
- ytdlp_service: Main service orchestrator (this file)

Original file: 1,524 lines with 15+ methods
Refactored into: 6 specialized modules for better maintainability
"""

import os
import shutil
import subprocess
from typing import Any, Dict, Optional

from src.services.ytdlp_cookie_manager import YtDlpCookieManager
from src.services.ytdlp_download_manager import (
    add_music_video_download,
    clear_stuck_downloads,
    get_queue,
    process_pending_downloads,
    retry_download,
    stop_download,
)
from src.services.ytdlp_history import (
    clear_history,
    get_history,
    resume_pending_downloads,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.ytdlp_service")


class YtDlpService:
    """Service for downloading videos using yt-dlp CLI directly"""

    def __init__(self):
        """Initialize the yt-dlp service with state management"""
        # Find yt-dlp executable dynamically - prefer pipx version
        self.yt_dlp_path = (
            "/root/.local/bin/yt-dlp"  # pipx installed (latest)
            if os.path.exists("/root/.local/bin/yt-dlp")
            else shutil.which("yt-dlp")
            or shutil.which("yt-dlp.exe")
            or "/usr/local/bin/yt-dlp"
        )

        # Download state management
        self.active_downloads = {}
        self.download_queue = []
        self.download_history = []
        self._next_id = 1

        # Cookie manager
        self.cookie_manager = YtDlpCookieManager()
        self.cookie_manager.load_existing_cookie_file()

        # Resume pending downloads from database
        resume_pending_downloads(
            self.download_queue,
            self.active_downloads,
            self._get_next_id,
            self._download_video,
        )

    def _get_next_id(self) -> int:
        """Get next unique download ID

        Returns:
            Unique integer ID for the download
        """
        download_id = self._next_id
        self._next_id += 1
        return download_id

    def _get_service_state(self) -> Dict:
        """Get current service state for passing to module functions

        Returns:
            Dictionary containing service state
        """
        return {
            "yt_dlp_path": self.yt_dlp_path,
            "active_downloads": self.active_downloads,
            "download_queue": self.download_queue,
            "download_history": self.download_history,
            "_next_id": self._next_id,
            "custom_cookie_file": self.cookie_manager.get_cookie_file_path(),
        }

    def _download_video(self, download_entry: Dict):
        """Private method wrapper for download execution

        This method is passed to the download manager for execution.

        Args:
            download_entry: Dictionary containing download information
        """
        from src.services.ytdlp_download_manager import _download_video

        _download_video(self._get_service_state(), download_entry)

    # ============================================================================
    # DOWNLOAD MANAGEMENT METHODS (delegated to ytdlp_download_manager module)
    # ============================================================================

    def add_music_video_download(
        self,
        artist: str,
        title: str,
        url: str,
        quality: str = "best",
        video_id: int = None,
        download_subtitles: bool = False,
        subtitle_languages: str = "en,en-US",
        artist_folder_path: str = None,
        user_id: int = None,
        format_string: str = None,
        upgrade_mode: bool = False,
    ) -> Dict:
        """Add a music video download using yt-dlp CLI

        Args:
            artist: Artist name
            title: Video title
            url: Video URL
            quality: Video quality preference (deprecated - use quality service)
            video_id: Optional video ID for database tracking
            download_subtitles: Whether to download closed captions/subtitles
            subtitle_languages: Language codes for subtitles (e.g., "en,en-US,fr")
            artist_folder_path: Optional custom folder path for the artist
            user_id: Optional user ID for quality preferences
            format_string: Optional format string override
            upgrade_mode: Whether this is a quality upgrade

        Returns:
            Dictionary with download submission result
        """
        return add_music_video_download(
            self._get_service_state(),
            artist,
            title,
            url,
            quality,
            video_id,
            download_subtitles,
            subtitle_languages,
            artist_folder_path,
            user_id,
            format_string,
            upgrade_mode,
        )

    def get_queue(self) -> Dict:
        """Get current download queue status

        Returns:
            Dictionary containing queue information
        """
        return get_queue(self._get_service_state())

    def stop_download(self, download_id: int) -> Dict:
        """Stop an active download

        Args:
            download_id: ID of the download to stop

        Returns:
            Dictionary with success status
        """
        return stop_download(self._get_service_state(), download_id)

    def retry_download(self, download_id: int) -> Dict:
        """Retry a failed or stopped download

        Args:
            download_id: ID of the download to retry

        Returns:
            Dictionary with retry status
        """
        return retry_download(self._get_service_state(), download_id)

    def process_pending_downloads(self) -> Dict:
        """Process pending downloads from database with rate limiting

        Returns:
            Dictionary with processing status
        """
        return process_pending_downloads(self._get_service_state())

    def clear_stuck_downloads(self) -> Dict:
        """Clear downloads stuck at 0% progress

        Returns:
            Dictionary with cleared download count
        """
        return clear_stuck_downloads(self._get_service_state())

    # ============================================================================
    # HISTORY MANAGEMENT METHODS (delegated to ytdlp_history module)
    # ============================================================================

    def get_history(self, limit: int = 50) -> Dict:
        """Get download history from both in-memory and database sources

        Args:
            limit: Maximum number of history entries to return

        Returns:
            Dictionary containing history entries and counts
        """
        return get_history(self.download_history, limit)

    def clear_history(self) -> Dict:
        """Clear download history from both memory and database

        Returns:
            Dictionary with success status and deletion counts
        """
        return clear_history(self.download_history, self.download_queue)

    # ============================================================================
    # COOKIE MANAGEMENT METHODS (delegated to ytdlp_cookie_manager module)
    # ============================================================================

    def set_cookie_file(self, cookie_file_path: str):
        """Set custom cookie file for age-restricted videos

        Args:
            cookie_file_path: Path to the cookie file
        """
        self.cookie_manager.set_cookie_file(cookie_file_path)

    def clear_cookie_file(self):
        """Clear custom cookie file"""
        self.cookie_manager.clear_cookie_file()

    def get_cookie_status(self) -> Dict:
        """Get status of custom cookie file

        Returns:
            Dictionary containing cookie availability status and file info
        """
        return self.cookie_manager.get_cookie_status()

    # ============================================================================
    # HEALTH CHECK
    # ============================================================================

    def health_check(self) -> Dict:
        """Check if yt-dlp is available and working

        Returns:
            Dictionary with service health status
        """
        try:
            result = subprocess.run(
                [self.yt_dlp_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                cookie_status = self.get_cookie_status()
                return {
                    "status": "healthy",
                    "version": result.stdout.strip(),
                    "active_downloads": len(self.active_downloads),
                    "queued_downloads": len(self.download_queue),
                    "cookie_status": cookie_status,
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "yt-dlp command failed",
                    "stderr": result.stderr,
                }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global instance
ytdlp_service = YtDlpService()
