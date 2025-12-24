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
                title=FilenameCleanup.sanitize_folder_name(title),
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
        # Query database for currently downloading videos + recently completed (last 5 min)
        # This provides visibility into rapid downloads that complete in seconds
        try:
            from datetime import datetime, timedelta

            from src.database.connection import get_db
            from src.database.models import Artist, Video, VideoStatus

            queue_items = []
            active_from_unified = self.unified_service.get_active_downloads()

            with get_db() as session:
                recent_cutoff = datetime.utcnow() - timedelta(hours=2)
                very_recent_cutoff = datetime.utcnow() - timedelta(minutes=5)

                # Get DOWNLOADING videos
                downloading_videos = (
                    session.query(Video, Artist.name)
                    .join(Artist, Video.artist_id == Artist.id)
                    .filter(
                        Video.status == VideoStatus.DOWNLOADING,
                        Video.updated_at >= recent_cutoff,
                    )
                    .order_by(Video.updated_at.desc())
                    .limit(50)
                    .all()
                )

                for video, artist_name in downloading_videos:
                    queue_items.append(
                        {
                            "id": video.id,
                            "artist": artist_name,
                            "title": video.title,
                            "url": video.url or video.youtube_url,
                            "status": "downloading",
                            "created_at": (
                                video.created_at.isoformat()
                                if video.created_at
                                else None
                            ),
                            "video_id": video.id,
                        }
                    )

                # Also include recently DOWNLOADED videos (last 5 minutes) for visibility
                # Since downloads complete in 10-25 seconds, this shows recent activity
                if len(queue_items) == 0:
                    recently_completed = (
                        session.query(Video, Artist.name)
                        .join(Artist, Video.artist_id == Artist.id)
                        .filter(
                            Video.status == VideoStatus.DOWNLOADED,
                            Video.updated_at >= very_recent_cutoff,
                        )
                        .order_by(Video.updated_at.desc())
                        .limit(20)
                        .all()
                    )

                    for video, artist_name in recently_completed:
                        queue_items.append(
                            {
                                "id": video.id,
                                "artist": artist_name,
                                "title": video.title,
                                "url": video.url or video.youtube_url,
                                "status": "completed_recently",
                                "created_at": (
                                    video.created_at.isoformat()
                                    if video.created_at
                                    else None
                                ),
                                "completed_at": (
                                    video.updated_at.isoformat()
                                    if video.updated_at
                                    else None
                                ),
                                "video_id": video.id,
                            }
                        )

            return {
                "queue": queue_items,
                "total": len(queue_items),
                "active_downloads": len(active_from_unified),
            }
        except Exception as e:
            logger.error(f"Error getting queue from database: {e}")
            # Fallback to in-memory tracking
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
        # Query database for completed/failed downloads instead of relying on in-memory state
        logger.info(f"DEBUG get_history: Called with limit={limit}")
        try:
            from datetime import datetime, timedelta

            from src.database.connection import get_db
            from src.database.models import Artist, Video, VideoStatus

            history_items = []

            logger.info("DEBUG get_history: About to open database session")
            with get_db() as session:
                # Get recently completed or failed videos (last 30 days)
                recent_cutoff = datetime.utcnow() - timedelta(days=30)
                logger.info(f"DEBUG get_history: Querying videos since {recent_cutoff}")

                completed_videos = (
                    session.query(Video, Artist.name)
                    .join(Artist, Video.artist_id == Artist.id)
                    .filter(
                        Video.status.in_([VideoStatus.DOWNLOADED, VideoStatus.FAILED]),
                        Video.updated_at >= recent_cutoff,
                    )
                    .order_by(Video.updated_at.desc())
                    .limit(limit)
                    .all()
                )

                logger.info(
                    f"DEBUG get_history: Query returned {len(completed_videos)} videos"
                )

                for video, artist_name in completed_videos:
                    history_items.append(
                        {
                            "id": video.id,
                            "artist": artist_name,
                            "title": video.title,
                            "url": video.url or video.youtube_url,
                            "status": (
                                "completed"
                                if video.status == VideoStatus.DOWNLOADED
                                else "failed"
                            ),
                            "file_path": video.local_path,
                            "completed_at": (
                                video.updated_at.isoformat()
                                if video.updated_at
                                else None
                            ),
                            "created_at": (
                                video.created_at.isoformat()
                                if video.created_at
                                else None
                            ),
                            "video_id": video.id,
                        }
                    )

                logger.info(
                    f"DEBUG get_history: Built {len(history_items)} history items"
                )

            logger.info(f"DEBUG get_history: Returning {len(history_items)} items")
            return {"history": history_items, "total": len(history_items)}
        except Exception as e:
            logger.error(f"Error getting history from database: {e}", exc_info=True)
            # Fallback to in-memory tracking
            limited_history = (
                self.download_history[-limit:] if limit > 0 else self.download_history
            )
            logger.info(
                f"DEBUG get_history: Exception occurred, falling back to in-memory ({len(limited_history)} items)"
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

    def process_pending_downloads(self) -> Dict[str, Any]:
        """
        Process pending downloads - backwards compatible method

        The unified download service handles pending downloads automatically,
        so this method simply returns success for compatibility with existing
        Celery tasks and scheduler code.

        Returns:
            Dict with success status and message
        """
        logger.info(
            "process_pending_downloads() called - unified service handles this automatically"
        )
        return {
            "success": True,
            "message": "Unified download service processes downloads automatically",
            "processed_count": 0,  # Not tracked separately in unified service
        }

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
