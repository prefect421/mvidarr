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

        # Restore cookies from database if they exist
        self._restore_cookies_from_database()

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

    def _restore_cookies_from_database(self):
        """Restore YouTube cookies from database to filesystem on startup"""
        try:
            import base64

            from src.services.settings_service import SettingsService

            # Check if cookies exist in database
            cookie_content_b64 = SettingsService.get(
                "youtube_cookies_content", default=None
            )

            if cookie_content_b64:
                # Decode and write to file
                cookie_content = base64.b64decode(cookie_content_b64)

                # Ensure cookies directory exists
                cookie_dir = os.path.dirname(self.cookies_path)
                if not os.path.exists(cookie_dir):
                    os.makedirs(cookie_dir, exist_ok=True)

                # Write cookie file
                with open(self.cookies_path, "wb") as f:
                    f.write(cookie_content)

                logger.info(
                    f"Restored YouTube cookies from database to {self.cookies_path}"
                )
            else:
                logger.debug("No YouTube cookies found in database to restore")

        except Exception as e:
            logger.error(f"Failed to restore cookies from database: {e}")

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
        # settings.get() returns strings from DB; 'False' is truthy in Python
        enable_aggressive_anti_detection = settings.get_bool(
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
        """
        Get download queue status (backwards compatible)

        Delegates to unified download service for single source of truth
        """
        logger.info("Adapter get_queue: Delegating to unified download service")
        return self.unified_service.get_download_queue()

    def get_history(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get download history (backwards compatible)

        Delegates to unified download service for single source of truth
        """
        logger.info(
            f"Adapter get_history: Delegating to unified download service (limit={limit})"
        )
        return self.unified_service.get_download_history(limit=limit)

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
        """
        Get cookie status (backwards compatible)

        Checks both filesystem and database for cookie availability
        Returns status from database if file doesn't exist (which is normal,
        as cookies are now stored in database and restored to file on demand)
        """
        # First check if file exists (fast path)
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
                logger.warning(f"Failed to stat cookie file: {e}")
                # Fall through to database check

        # If file doesn't exist, check database (where cookies are actually stored)
        try:
            import base64

            from src.services.settings_service import SettingsService

            cookie_content_b64 = SettingsService.get(
                "youtube_cookies_content", default=None
            )

            if cookie_content_b64:
                # Cookies exist in database
                cookie_content = base64.b64decode(cookie_content_b64)
                file_size = len(cookie_content)

                # Get upload timestamp
                upload_timestamp = SettingsService.get(
                    "youtube_cookies_uploaded_at", default=None
                )

                if upload_timestamp:
                    modified_time = float(upload_timestamp)
                else:
                    modified_time = 0

                return {
                    "cookies_available": True,
                    "file_path": "database (persistent storage)",
                    "file_size": file_size,
                    "modified_time": modified_time,
                }
            else:
                return {
                    "cookies_available": False,
                    "error": "No cookies found in database or filesystem",
                }
        except Exception as e:
            logger.error(f"Failed to check cookie status in database: {e}")
            return {"cookies_available": False, "error": str(e)}

    def process_pending_downloads(self) -> Dict[str, Any]:
        """
        Process pending downloads - backwards compatible method

        Queries database for pending/queued downloads and starts them
        via the unified download service.

        Returns:
            Dict with success status, processed count, and any errors
        """
        try:
            from src.database.connection import get_db
            from src.database.models import Download, Video

            processed_count = 0
            errors = []

            with get_db() as session:
                # Find pending/queued downloads
                pending_downloads = (
                    session.query(Download)
                    .filter(Download.status.in_(["pending", "queued"]))
                    .limit(10)  # Process in batches to avoid overwhelming the system
                    .all()
                )

                logger.info(
                    f"Found {len(pending_downloads)} pending downloads to process"
                )

                for download in pending_downloads:
                    try:
                        # Get associated video
                        video = (
                            session.query(Video)
                            .filter(Video.id == download.video_id)
                            .first()
                        )

                        if not video:
                            logger.warning(
                                f"Download {download.id} references non-existent video {download.video_id}"
                            )
                            download.status = "failed"
                            download.error_message = "Video not found in database"
                            session.commit()
                            errors.append(
                                f"Download {download.id}: Video {download.video_id} not found"
                            )
                            continue

                        # Start download via unified service
                        logger.info(
                            f"Starting download {download.id}: {video.artist} - {video.title}"
                        )

                        # Use add_music_video_download to start the download
                        result = self.add_music_video_download(
                            artist=video.artist,
                            title=video.title,
                            url=video.url,
                            quality=download.quality or "best",
                            video_id=video.id,
                            download_id=download.id,
                        )

                        if result.get("success"):
                            processed_count += 1
                            # Update download status to downloading
                            download.status = "downloading"
                            session.commit()
                        else:
                            error_msg = result.get("error", "Unknown error")
                            logger.error(
                                f"Failed to start download {download.id}: {error_msg}"
                            )
                            download.status = "failed"
                            download.error_message = error_msg
                            session.commit()
                            errors.append(f"Download {download.id}: {error_msg}")

                    except Exception as e:
                        logger.error(
                            f"Error processing download {download.id}: {e}",
                            exc_info=True,
                        )
                        errors.append(f"Download {download.id}: {str(e)}")
                        try:
                            download.status = "failed"
                            download.error_message = str(e)
                            session.commit()
                        except:
                            pass

            return {
                "success": True,
                "processed_count": processed_count,
                "found_pending": len(pending_downloads),
                "errors": errors,
                "message": f"Processed {processed_count} pending downloads",
            }

        except Exception as e:
            logger.error(f"Error in process_pending_downloads: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to process pending downloads: {str(e)}",
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

    def stop_download(self, download_id: int) -> Dict[str, Any]:
        """Stop/cancel download (API compatibility method)"""
        success = self.cancel_download(download_id)

        if success:
            return {
                "success": True,
                "message": f"Download {download_id} stopped",
                "download_id": download_id,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "Download not found or already completed",
                "download_id": download_id,
                "error": "Download not found",
            }

    def stop_video_download(self, video_id: int) -> Dict[str, Any]:
        """Stop a video stuck in the queue (video-sourced queue entry)"""
        success = self.unified_service.reset_stuck_video(video_id)

        if success:
            return {
                "success": True,
                "message": f"Video {video_id} download stopped",
                "download_id": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "Video not found",
                "download_id": None,
                "error": "Video not found",
            }

    def retry_video_download(self, video_id: int) -> Dict[str, Any]:
        """Reset a stuck video back to WANTED so it can be redownloaded"""
        success = self.unified_service.reset_stuck_video(video_id)

        if success:
            return {
                "success": True,
                "message": f"Video {video_id} reset to WANTED for retry",
                "download_id": None,
                "error": None,
            }
        else:
            return {
                "success": False,
                "message": "Video not found",
                "download_id": None,
                "error": "Video not found",
            }

    def retry_download(self, download_id: int) -> Dict[str, Any]:
        """Retry a failed/stopped download (API compatibility method)"""
        try:
            from src.database.connection import get_db
            from src.database.models import Download, Video

            with get_db() as session:
                download = (
                    session.query(Download).filter(Download.id == download_id).first()
                )

                if not download:
                    return {
                        "success": False,
                        "message": "Download not found",
                        "download_id": download_id,
                        "error": "Download not found",
                    }

                if download.status not in ["failed", "stopped", "cancelled"]:
                    return {
                        "success": False,
                        "message": f"Download is in '{download.status}' status and cannot be retried",
                        "download_id": download_id,
                        "error": f"Invalid status: {download.status}",
                    }

                # Reset download status to pending for retry
                download.status = "pending"
                download.progress = 0
                download.error_message = None
                download.updated_at = datetime.utcnow()
                session.commit()

                logger.info(f"Download {download_id} queued for retry")

                return {
                    "success": True,
                    "message": f"Download {download_id} queued for retry",
                    "download_id": download_id,
                    "error": None,
                }

        except Exception as e:
            logger.error(f"Error retrying download {download_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Failed to retry download: {str(e)}",
                "download_id": download_id,
                "error": str(e),
            }

    def clear_history(self, session=None) -> Dict[str, Any]:
        """
        Clear download history (backwards compatible)

        Clears both in-memory history and database records

        Args:
            session: Optional SQLAlchemy session to use (if None, creates its own)

        Returns:
            Dict with success status and deletion counts
        """
        try:
            # Clear in-memory history
            memory_count = len(self.download_history)
            self.download_history.clear()

            # Clear database records
            db_count = 0
            try:
                from src.database.models import Download

                # Use provided session or create a new one
                if session:
                    # Use existing session (FastAPI dependency injection)
                    db_count = session.query(Download).count()
                    session.query(Download).delete()
                    session.commit()
                    logger.info(f"Cleared {db_count} download records from database")
                else:
                    # Create own session (backward compatibility)
                    from src.database.connection import get_db

                    with get_db() as db_session:
                        db_count = db_session.query(Download).count()
                        db_session.query(Download).delete()
                        db_session.commit()
                        logger.info(
                            f"Cleared {db_count} download records from database"
                        )
            except Exception as db_error:
                logger.error(
                    f"Failed to clear download history from database: {db_error}",
                    exc_info=True,
                )
                # Continue even if DB fails - at least clear memory

            # Also clear download queue to prevent re-adding completed downloads
            cleared_queue_count = len(self.download_queue)
            self.download_queue.clear()

            total_count = memory_count + db_count
            logger.info(
                f"Cleared download history: {memory_count} from memory, "
                f"{db_count} from database, {cleared_queue_count} from queue"
            )

            return {
                "success": True,
                "message": f"Cleared {total_count} download records",
                "deleted_count": total_count,  # For frontend compatibility
                "memory_count": memory_count,
                "database_count": db_count,
                "queue_count": cleared_queue_count,
                "total_count": total_count,
            }

        except Exception as e:
            logger.error(f"Failed to clear download history: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to clear history: {str(e)}",
            }

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
