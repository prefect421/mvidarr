"""
Download Service Adapter - Backwards Compatibility Layer
Provides seamless integration with existing MVidarr code while using the new unified service
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

from src.services.settings_service import settings
from src.services.unified_download_service import (
    AntiDetectionLevel,
    DownloadContext,
    unified_download_service,
)
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.download_adapter")


class DownloadServiceAdapter:
    """
    Adapter that provides the old ytdlp_service interface while using the new unified service
    This allows gradual migration without breaking existing code
    """

    def __init__(self):
        self.unified_service = unified_download_service
        self.active_downloads = {}  # For backwards compatibility
        self.download_queue = []  # For backwards compatibility
        self.download_history = []  # For backwards compatibility

        # Initialize with existing settings
        self._load_settings()

        logger.info(
            "Download Service Adapter initialized - providing backwards compatibility"
        )

    def _load_settings(self):
        """Load settings that affect download behavior"""
        self.music_videos_path = settings.get("music_videos_path", "data/musicvideos")
        self.cookies_path = settings.get(
            "youtube_cookies_path", "data/cookies/youtube_cookies.txt"
        )

        # Ensure paths exist
        if not os.path.exists(self.music_videos_path):
            os.makedirs(self.music_videos_path, exist_ok=True)

    def add_music_video_download(
        self,
        artist: str,
        title: str,
        url: str,
        quality: str = "best",
        download_subtitles: bool = False,
        video_id: Optional[int] = None,
        download_id: Optional[int] = None,
        format_string: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Backwards compatible interface for adding downloads
        Maps to the new unified service while maintaining the same API
        """
        try:
            # Create output directory
            folder_name = FilenameCleanup.sanitize_folder_name(artist)
            output_path = os.path.join(self.music_videos_path, folder_name)
            os.makedirs(output_path, exist_ok=True)

            # Determine anti-detection level based on settings
            anti_detection_level = self._get_anti_detection_level()

            # Create download context
            # Use custom format string if provided (for quality upgrades), otherwise use quality
            context = DownloadContext(
                video_id=video_id or 0,
                url=url,
                title=FilenameCleanup.sanitize_filename(title),
                artist=artist,
                quality=format_string
                or quality,  # Pass format_string as quality if provided
                output_path=output_path,
                cookies_path=(
                    self.cookies_path if os.path.exists(self.cookies_path) else None
                ),
                anti_detection=anti_detection_level,
            )

            # Start download using unified service
            unified_download_id = self.unified_service.download_video(
                context, completion_callback=self._download_completion_callback
            )

            # Create backwards compatible response
            download_entry = {
                "id": unified_download_id,
                "artist": artist,
                "title": title,
                "url": url,
                "quality": quality,
                "status": "queued",
                "created_at": datetime.utcnow().isoformat(),
                "video_id": video_id,
                "download_id": download_id,
            }

            # Add to backwards compatibility structures
            self.active_downloads[unified_download_id] = download_entry
            self.download_queue.append(download_entry)

            logger.info(f"Queued download via adapter: {artist} - {title}")

            return {
                "success": True,
                "id": unified_download_id,
                "message": f"Download queued: {artist} - {title}",
            }

        except Exception as e:
            logger.error(f"Failed to queue download: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to queue download: {str(e)}",
            }

    def _get_anti_detection_level(self) -> AntiDetectionLevel:
        """Determine anti-detection level based on system settings and history"""
        # Check if we've had recent detection issues
        enable_aggressive_anti_detection = settings.get(
            "enable_aggressive_anti_detection", False
        )

        if enable_aggressive_anti_detection:
            return AntiDetectionLevel.AGGRESSIVE

        # Default to moderate for good balance
        return AntiDetectionLevel.MODERATE

    def _download_completion_callback(self, download_id: int, result):
        """Handle download completion for backwards compatibility"""
        if download_id in self.active_downloads:
            download_entry = self.active_downloads[download_id]

            # Update status
            if result.success:
                download_entry["status"] = "completed"
                download_entry["file_path"] = result.file_path
                download_entry["file_size"] = result.file_size
                logger.info(f"Download {download_id} completed: {result.file_path}")
            else:
                download_entry["status"] = "failed"
                download_entry["error_message"] = result.error_message
                logger.error(f"Download {download_id} failed: {result.error_message}")

            download_entry["completed_at"] = datetime.utcnow().isoformat()

            # Move to history
            self.download_history.append(download_entry)
            del self.active_downloads[download_id]

            # Remove from queue
            self.download_queue = [
                d for d in self.download_queue if d["id"] != download_id
            ]

    def get_queue(self) -> Dict[str, Any]:
        """Get download queue status (backwards compatible)"""
        active_from_unified = self.unified_service.get_active_downloads()

        # Merge with our backwards compatibility tracking
        queue_items = []
        for download_id, entry in self.active_downloads.items():
            queue_items.append(
                {
                    **entry,
                    "status": (
                        "downloading"
                        if download_id in active_from_unified
                        else entry.get("status", "queued")
                    ),
                }
            )

        return {
            "queue": queue_items,
            "total": len(queue_items),
            "active_downloads": len(active_from_unified),
        }

    def get_history(self, limit: int = 50) -> Dict[str, Any]:
        """Get download history (backwards compatible)"""
        limited_history = (
            self.download_history[-limit:] if limit > 0 else self.download_history
        )

        return {"history": limited_history, "total": len(limited_history)}

    def health_check(self) -> Dict[str, Any]:
        """Health check for backwards compatibility"""
        try:
            version = self.unified_service.ytdlp_manager.get_version()
            return {
                "status": "healthy",
                "version": version,
                "message": "Unified download service operational",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "message": "Service health check failed",
            }

    def get_cookie_status(self) -> Dict[str, Any]:
        """Get cookie file status (backwards compatible)"""

        if os.path.exists(self.cookies_path):
            try:
                stat = os.stat(self.cookies_path)
                return {
                    "cookies_available": True,
                    "file_path": self.cookies_path,
                    "file_size": stat.st_size,
                    "modified_time": stat.st_mtime,
                }
            except Exception as e:
                return {"cookies_available": False, "error": str(e)}
        else:
            return {"cookies_available": False, "error": "Cookie file not found"}

    def cancel_download(self, download_id: int) -> bool:
        """Cancel download (backwards compatible)"""
        success = self.unified_service.cancel_download(download_id)

        if success and download_id in self.active_downloads:
            download_entry = self.active_downloads[download_id]
            download_entry["status"] = "cancelled"
            download_entry["completed_at"] = datetime.utcnow().isoformat()

            self.download_history.append(download_entry)
            del self.active_downloads[download_id]

            self.download_queue = [
                d for d in self.download_queue if d["id"] != download_id
            ]

        return success

    # Additional methods for full backwards compatibility
    def _resume_pending_downloads(self):
        """Resume pending downloads - now handled by unified service automatically"""
        logger.info("Resume pending downloads called - handled by unified service")
        pass

    def _update_database_download_status(
        self, download_entry, status, file_path=None, file_size=None, error=None
    ):
        """Database updates are now handled internally by unified service"""
        pass


# Global adapter instance for backwards compatibility
ytdlp_service = DownloadServiceAdapter()

# Also make it available under the old import path
import sys

sys.modules["src.services.ytdlp_service"] = sys.modules[__name__]
