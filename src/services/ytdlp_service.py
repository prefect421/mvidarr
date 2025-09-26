"""
yt-dlp CLI service for downloading videos directly
"""

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.database.connection import get_db
from src.database.models import Video
from src.services.settings_service import settings
from src.services.youtube_download_engine import youtube_download_engine
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.ytdlp_service")


class YtDlpService:
    """Service for downloading videos using yt-dlp CLI directly"""

    def __init__(self):
        # Find yt-dlp executable dynamically - prefer pipx version
        self.yt_dlp_path = (
            "/root/.local/bin/yt-dlp"  # pipx installed (latest)
            if os.path.exists("/root/.local/bin/yt-dlp")
            else shutil.which("yt-dlp")
            or shutil.which("yt-dlp.exe")
            or "/usr/local/bin/yt-dlp"
        )
        self.active_downloads = {}
        self.download_queue = []
        self.download_history = []
        self._next_id = 1
        self.custom_cookie_file = None

        # Auto-load existing cookie file at startup
        self._load_existing_cookie_file()

        # Resume pending downloads from database
        self._resume_pending_downloads()

    def _get_next_id(self) -> int:
        """Get next unique download ID"""
        download_id = self._next_id
        self._next_id += 1
        return download_id

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
    ) -> Dict:
        """
        Add a music video download using yt-dlp CLI directly

        Args:
            artist: Artist name
            title: Video title
            url: Video URL
            quality: Video quality preference (deprecated - use quality service)
            video_id: Optional video ID for database tracking
            download_subtitles: Whether to download closed captions/subtitles
            subtitle_languages: Language codes for subtitles (e.g., "en,en-US,fr")
            artist_folder_path: Optional custom folder path for the artist (overrides artist name)
            user_id: Optional user ID for quality preferences

        Returns:
            Dictionary with download submission result
        """
        try:
            # Get music videos path from settings
            music_videos_path = settings.get("music_videos_path", "data/musicvideos")

            # If setting exists but is empty, use default
            if not music_videos_path or music_videos_path.strip() == "":
                music_videos_path = "data/musicvideos"

            # Ensure base music videos directory exists first
            try:
                os.makedirs(music_videos_path, exist_ok=True, mode=0o755)
                logger.info(f"Ensured base directory exists: {music_videos_path}")
            except Exception as base_e:
                logger.error(
                    f"Failed to create base directory {music_videos_path}: {base_e}"
                )
                return {
                    "success": False,
                    "error": f"Cannot create base directory: {str(base_e)}",
                }

            # Determine folder name: use artist_folder_path if provided, otherwise sanitized artist name
            if artist_folder_path and artist_folder_path.strip():
                folder_name = FilenameCleanup.sanitize_folder_name(
                    artist_folder_path.strip()
                )
                logger.info(f"Using custom folder path: {folder_name}")
            else:
                folder_name = FilenameCleanup.sanitize_folder_name(artist)
                logger.info(f"Using auto-generated folder name: {folder_name}")

            clean_title = FilenameCleanup.sanitize_folder_name(title)

            # Create output path: music_videos_path/folder_name/
            output_dir = os.path.join(music_videos_path, folder_name)

            # Debug logging for permission issues
            logger.info(f"Attempting to create directory: {output_dir}")
            logger.info(f"Current working directory: {os.getcwd()}")
            logger.info(
                f"Music videos path exists: {os.path.exists(music_videos_path)}"
            )
            logger.info(
                f"Music videos path writable: {os.access(music_videos_path, os.W_OK)}"
            )

            try:
                os.makedirs(output_dir, exist_ok=True, mode=0o755)
                logger.info(f"Successfully created directory: {output_dir}")
            except PermissionError as e:
                logger.error(f"Permission denied creating {output_dir}: {e}")
                if os.path.exists(music_videos_path):
                    logger.error(
                        f"Parent directory permissions: {oct(os.stat(music_videos_path).st_mode)}"
                    )
                    logger.error(
                        f"Parent directory owner: {os.stat(music_videos_path).st_uid}:{os.stat(music_videos_path).st_gid}"
                    )

                # Try alternative approach: create without specifying mode
                try:
                    logger.info(
                        "Attempting fallback directory creation without mode specification"
                    )
                    os.makedirs(output_dir, exist_ok=True)
                    logger.info(f"Fallback successful for directory: {output_dir}")
                except Exception as fallback_e:
                    logger.error(f"Fallback also failed: {fallback_e}")
                    return {
                        "success": False,
                        "error": f"Cannot create artist directory: {str(e)}",
                    }
            except Exception as e:
                logger.error(f"Unexpected error creating {output_dir}: {e}")
                return {
                    "success": False,
                    "error": f"Directory creation failed: {str(e)}",
                }

            # Get quality format string from quality service
            try:
                from src.services.video_quality_service import video_quality_service

                # Find artist ID if video_id is provided
                artist_id = None
                if video_id:
                    with get_db() as temp_session:
                        from src.database.models import Video as VideoModel

                        video_obj = (
                            temp_session.query(VideoModel)
                            .filter(VideoModel.id == video_id)
                            .first()
                        )
                        if video_obj:
                            artist_id = video_obj.artist_id

                quality_format_string = (
                    video_quality_service.generate_ytdlp_format_string(
                        user_id, artist_id
                    )
                )
                logger.info(f"Using quality format string: {quality_format_string}")
            except Exception as quality_error:
                logger.warning(
                    f"Failed to get quality format string, using default: {quality_error}"
                )
                quality_format_string = "bv*[height<=1080]+ba/best[height<=1080]/18/worst"  # Restore quality preference with fallback

            # Check for existing active downloads for this video
            if video_id:
                existing_active = None
                for existing_id, existing_entry in self.active_downloads.items():
                    if existing_entry.get("video_id") == video_id:
                        existing_active = existing_entry
                        break

                if existing_active:
                    return {
                        "success": True,
                        "id": existing_active["id"],
                        "message": f"Download already in progress: {artist} - {title}",
                        "status": "already_active",
                    }

            # Create download entry
            download_id = self._get_next_id()
            download_entry = {
                "id": download_id,
                "artist": artist,
                "artist_folder_path": artist_folder_path,
                "title": title,
                "url": url,
                "quality": quality,
                "quality_format_string": quality_format_string,
                "video_id": video_id,
                "user_id": user_id,
                "download_subtitles": download_subtitles,
                "subtitle_languages": subtitle_languages,
                "status": "pending",
                "progress": 0,
                "output_dir": output_dir,
                "created_at": datetime.utcnow().isoformat(),
                "started_at": None,
                "completed_at": None,
                "error_message": None,
                "file_path": None,
                "file_size": None,
                "db_download_id": None,  # Track corresponding database ID
            }

            # Create database record for persistent history
            try:
                from src.database.models import Artist as ArtistModel
                from src.database.models import Download

                with get_db() as session:
                    # Find or create artist
                    artist_obj = (
                        session.query(ArtistModel).filter_by(name=artist).first()
                    )
                    if not artist_obj:
                        artist_obj = ArtistModel(name=artist)
                        session.add(artist_obj)
                        session.flush()  # Get the ID

                    # Create database download record
                    db_download = Download(
                        artist_id=artist_obj.id,
                        video_id=video_id,
                        title=title,
                        original_url=url,
                        quality=quality,
                        status="pending",
                        progress=0,
                    )
                    session.add(db_download)
                    session.commit()

                    # Store the database ID in the download entry
                    download_entry["db_download_id"] = db_download.id
                    logger.info(
                        f"Created database download record with ID {db_download.id}"
                    )

            except Exception as db_error:
                logger.warning(f"Failed to create database download record: {db_error}")
                # Continue with in-memory tracking even if database fails

            # Add to queue
            self.download_queue.append(download_entry)
            self.active_downloads[download_id] = download_entry

            # Start download in background thread
            thread = threading.Thread(
                target=self._download_video, args=(download_entry,)
            )
            thread.daemon = True
            thread.start()

            logger.info(f"Queued download: {artist} - {title}")

            return {
                "success": True,
                "id": download_id,
                "message": f"Download queued: {artist} - {title}",
            }

        except Exception as e:
            logger.error(f"Failed to queue download: {e}")
            return {"success": False, "error": str(e)}

    def _download_video(self, download_entry: Dict):
        """
        Download video using the complete YouTube Download Engine
        This replaces the old fragmented approach with a unified production solution
        """
        download_id = download_entry["id"]
        video_id = download_entry.get("video_id")

        try:
            download_entry["status"] = "downloading"
            download_entry["started_at"] = datetime.utcnow().isoformat()

            # Update database status to downloading
            self._update_database_download_status(download_entry, "downloading")

            # Use quality format string from video quality service
            quality_format = download_entry.get("quality_format_string", "best")

            logger.info(f"Download {download_id}: Using YouTube Download Engine")
            logger.info(f"Download {download_id}: Quality format: {quality_format}")

            # Use the complete YouTube download engine
            result = youtube_download_engine.download_video(
                url=download_entry["url"],
                output_path=download_entry["output_dir"],
                title=download_entry["title"],
                quality=quality_format,
                download_subtitles=download_entry.get("download_subtitles", False),
                subtitle_languages=download_entry.get("subtitle_languages", "en,en-US"),
            )

            if result.success:
                # Download successful
                download_entry["status"] = "completed"
                download_entry["completed_at"] = datetime.utcnow().isoformat()
                download_entry["progress"] = 100
                download_entry["file_path"] = result.file_path
                download_entry["file_size"] = result.file_size

                logger.info(f"Download {download_id} completed successfully!")
                logger.info(
                    f"Download {download_id}: Strategy used: {result.strategy_used.value}"
                )
                logger.info(f"Download {download_id}: File: {result.file_path}")
                logger.info(f"Download {download_id}: Duration: {result.duration:.1f}s")

                # Update database with success
                self._update_video_status_in_database(
                    video_id,
                    "DOWNLOADED",
                    result.file_path,
                    result.file_size,
                )
                self._update_database_download_status(
                    download_entry,
                    "completed",
                    result.file_path,
                    result.file_size,
                )

                # EMERGENCY VALIDATION: Ensure video was properly linked
                if video_id:
                    self._emergency_validate_video_linking(video_id, download_entry)

                # Enhanced metadata enrichment after successful download
                if video_id:
                    try:
                        logger.info(
                            f"Starting enhanced metadata enrichment for video {video_id}"
                        )
                        from src.services.metadata_enrichment_service import (
                            metadata_enrichment_service,
                        )

                        # Run async metadata enrichment in a new thread to avoid blocking
                        def run_metadata_enrichment():
                            import asyncio

                            try:
                                # Create new event loop in this thread
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                result = loop.run_until_complete(
                                    metadata_enrichment_service.enrich_video_metadata(
                                        video_id, force_refresh=False
                                    )
                                )
                                if result.success:
                                    logger.info(
                                        f"Enhanced metadata enrichment completed for video {video_id}"
                                    )
                                else:
                                    logger.warning(
                                        f"Enhanced metadata enrichment failed for video {video_id}: {result.errors}"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Error during enhanced metadata enrichment for video {video_id}: {e}"
                                )
                            finally:
                                loop.close()

                        # Start enrichment in background thread
                        metadata_thread = threading.Thread(
                            target=run_metadata_enrichment
                        )
                        metadata_thread.daemon = True
                        metadata_thread.start()

                    except Exception as e:
                        logger.error(
                            f"Failed to start enhanced metadata enrichment for video {video_id}: {e}"
                        )

            else:
                # Download failed - check if it's rate limiting
                error_message = result.error_message or "Unknown download error"

                # Check if failure is due to rate limiting (HTTP 429 or similar)
                is_rate_limited = any(
                    keyword in error_message.lower()
                    for keyword in [
                        "429",
                        "too many requests",
                        "rate limit",
                        "temporarily unavailable",
                    ]
                )

                if is_rate_limited:
                    # Rate limited - reschedule for retry instead of permanent failure
                    logger.warning(
                        f"Download {download_id} rate limited, will retry later: {error_message}"
                    )
                    download_entry["status"] = "pending"
                    download_entry["error_message"] = (
                        f"Rate limited - will retry: {error_message}"
                    )

                    # Update database to pending for retry (don't mark video as FAILED)
                    self._update_database_download_status(
                        download_entry,
                        "pending",
                        None,
                        None,
                        f"Rate limited - will retry: {error_message}",
                    )
                else:
                    # Permanent failure
                    download_entry["status"] = "failed"
                    download_entry["completed_at"] = datetime.utcnow().isoformat()
                    download_entry["error_message"] = error_message

                    logger.error(
                        f"Download {download_id} failed permanently: {error_message}"
                    )
                    if result.duration:
                        logger.info(
                            f"Download {download_id}: Duration: {result.duration:.1f}s"
                        )

                    # Update database with permanent failure
                    self._update_video_status_in_database(video_id, "FAILED")
                    self._update_database_download_status(
                        download_entry, "failed", None, None, error_message
                    )

        except Exception as e:
            download_entry["status"] = "failed"
            download_entry["completed_at"] = datetime.utcnow().isoformat()
            download_entry["error_message"] = f"Download engine error: {str(e)}"

            logger.error(f"Download {download_id} engine exception: {e}")

            self._update_video_status_in_database(video_id, "FAILED")
            self._update_database_download_status(
                download_entry, "failed", None, None, str(e)
            )

        finally:
            # Move from active to history
            if download_id in self.active_downloads:
                self.download_history.append(self.active_downloads[download_id])
                del self.active_downloads[download_id]

            # Remove from queue
            self.download_queue = [
                d for d in self.download_queue if d["id"] != download_id
            ]

    def _update_video_status_in_database(
        self, video_id: int, status: str, file_path: str = None, file_size: int = None
    ):
        """Update video status in database"""
        if not video_id:
            return

        try:
            with get_db() as session:
                video = session.query(Video).filter(Video.id == video_id).first()
                if video:
                    # Store original file path for potential cleanup
                    original_file_path = video.local_path

                    video.status = status
                    if file_path:
                        video.local_path = file_path
                    if status == "DOWNLOADED":
                        # Ensure we have the file info
                        if file_path and os.path.exists(file_path):
                            video.local_path = file_path
                            if not file_size:
                                file_size = os.path.getsize(file_path)

                            # Handle quality upgrade file cleanup
                            if original_file_path and original_file_path != file_path:
                                self._handle_quality_upgrade_cleanup(
                                    video, original_file_path, file_path
                                )

                            # DEFENSIVE: Ensure local_path is set BEFORE attempting FFmpeg
                            # This prevents loss of file path if FFmpeg extraction fails
                            if not video.local_path and file_path:
                                video.local_path = file_path
                                session.commit()
                                logger.info(
                                    f"✅ DEFENSIVE: Pre-set local_path for video {video_id}: {file_path}"
                                )

                            # ARCHITECTURAL CHANGE: Sequential processing instead of immediate FFmpeg
                            # This eliminates race conditions between download and enhancement services
                            logger.info(
                                f"✅ Video {video_id} download completed and linked successfully."
                            )
                            logger.info(f"📋 File: {file_path} ({file_size} bytes)")
                            logger.info(
                                f"🔄 Video queued for enhancement processing by metadata service"
                            )

                    session.commit()
                    logger.info(
                        f"Updated video {video_id} status to {status} in database"
                    )
                else:
                    logger.warning(f"Video {video_id} not found in database")
        except Exception as e:
            logger.error(f"Failed to update video {video_id} status in database: {e}")

    def _update_database_download_status(
        self,
        download_entry: dict,
        status: str,
        file_path: str = None,
        file_size: int = None,
        error_message: str = None,
    ):
        """Update download status in database"""
        db_download_id = download_entry.get("db_download_id")
        if not db_download_id:
            logger.warning(
                f"No db_download_id found in download_entry for {download_entry.get('id')}"
            )
            return

        try:
            from src.database.models import Download

            with get_db() as session:
                db_download = (
                    session.query(Download)
                    .filter(Download.id == db_download_id)
                    .first()
                )
                if db_download:
                    db_download.status = status
                    db_download.progress = download_entry.get("progress", 0)
                    db_download.updated_at = datetime.utcnow()

                    if file_path:
                        db_download.file_path = file_path
                    if file_size:
                        db_download.file_size = file_size
                    if error_message:
                        db_download.error_message = error_message

                    session.commit()
                    logger.info(
                        f"Updated database download {db_download_id} status to {status}"
                    )
                else:
                    logger.warning(f"Database download {db_download_id} not found")
        except Exception as e:
            logger.error(f"Failed to update database download {db_download_id}: {e}")

    def _handle_quality_upgrade_cleanup(
        self, video, original_file_path: str, new_file_path: str
    ):
        """Handle cleanup of original files during quality upgrades"""
        try:
            # Check if this is a quality upgrade (indicated by metadata or title)
            is_upgrade = False

            # Check video metadata for upgrade flag
            if hasattr(video, "video_metadata") and video.video_metadata:
                is_upgrade = video.video_metadata.get("upgrade_requested", False)

            # Also check if this looks like an upgrade based on file paths
            # (new file in same directory, different filename)
            if not is_upgrade and original_file_path and new_file_path:
                original_dir = os.path.dirname(original_file_path)
                new_dir = os.path.dirname(new_file_path)
                # Same directory but different files suggests upgrade
                is_upgrade = original_dir == new_dir and os.path.basename(
                    original_file_path
                ) != os.path.basename(new_file_path)

            if not is_upgrade:
                return  # Not a quality upgrade, don't delete anything

            # Check user preference for auto-deletion
            auto_delete = settings.get("auto_delete_original_on_upgrade", True)
            if not auto_delete:
                logger.info(f"Original file cleanup disabled for video {video.id}")
                return

            # Verify the original file exists and new file is different
            if not os.path.exists(original_file_path):
                logger.debug(
                    f"Original file already doesn't exist: {original_file_path}"
                )
                return

            if not os.path.exists(new_file_path):
                logger.warning(
                    f"New file doesn't exist yet, skipping cleanup: {new_file_path}"
                )
                return

            if os.path.samefile(original_file_path, new_file_path):
                logger.debug(f"Original and new files are the same, no cleanup needed")
                return

            # Compare file sizes to ensure new file is reasonable
            original_size = os.path.getsize(original_file_path)
            new_size = os.path.getsize(new_file_path)

            # Basic sanity check - new file shouldn't be much smaller (might indicate failed download)
            if new_size < original_size * 0.5:  # New file is less than 50% of original
                logger.warning(
                    f"New file ({new_size} bytes) is much smaller than original ({original_size} bytes), "
                    f"skipping cleanup for safety. Video {video.id}"
                )
                return

            # Safe to delete original file
            logger.info(
                f"Quality upgrade cleanup: Deleting original file {original_file_path} "
                f"({original_size} bytes) for video {video.id}"
            )

            # Create backup info before deletion
            backup_info = {
                "deleted_file_path": original_file_path,
                "deleted_file_size": original_size,
                "deleted_at": datetime.utcnow().isoformat(),
                "replaced_by": new_file_path,
                "replaced_by_size": new_size,
            }

            # Delete the original file
            os.remove(original_file_path)

            # Update video metadata with cleanup info
            if not hasattr(video, "video_metadata") or not video.video_metadata:
                video.video_metadata = {}
            video.video_metadata["quality_upgrade_cleanup"] = backup_info

            logger.info(
                f"Successfully deleted original file and updated metadata for video {video.id}. "
                f"Saved {original_size} bytes of disk space."
            )

        except Exception as e:
            logger.error(
                f"Error during quality upgrade cleanup for video {video.id}: {e}"
            )
            # Don't raise the exception - cleanup failure shouldn't break the download

    def get_queue(self) -> Dict:
        """Get current download queue status"""
        queue_items = list(self.active_downloads.values())
        return {"queue": queue_items, "count": len(queue_items)}

    def get_history(self, limit: int = 50) -> Dict:
        """Get download history from both in-memory and database sources"""
        try:
            # Get in-memory history
            memory_history = list(self.download_history)

            # Get database history
            database_history = []
            try:
                from src.database.models import Artist, Download, Video

                with get_db() as session:
                    # Query database downloads with artist and video info
                    db_downloads = (
                        session.query(Download, Artist.name, Video.title)
                        .join(Artist, Download.artist_id == Artist.id)
                        .outerjoin(Video, Download.video_id == Video.id)
                        .order_by(Download.created_at.desc())
                        .limit(limit * 2)  # Get more to account for merging
                        .all()
                    )

                    for download, artist_name, video_title in db_downloads:
                        # Convert database download to ytdlp_service format
                        db_entry = {
                            "id": f"db_{download.id}",  # Prefix to avoid ID conflicts
                            "artist": artist_name,
                            "title": video_title or download.title,
                            "url": download.original_url,
                            "quality": download.quality or "best",
                            "video_id": download.video_id,
                            "download_subtitles": False,
                            "status": download.status,
                            "progress": download.progress,
                            "output_dir": (
                                os.path.dirname(download.file_path)
                                if download.file_path
                                else None
                            ),
                            "created_at": download.created_at.isoformat(),
                            "started_at": download.created_at.isoformat(),
                            "completed_at": (
                                download.updated_at.isoformat()
                                if download.status in ["completed", "failed"]
                                else None
                            ),
                            "error_message": download.error_message,
                            "file_path": download.file_path,
                            "file_size": download.file_size,
                        }
                        database_history.append(db_entry)

            except Exception as db_error:
                logger.warning(f"Failed to get database download history: {db_error}")
                # Continue with just in-memory history if database fails

            # Combine and deduplicate histories
            all_history = memory_history + database_history

            # Deduplicate based on URL and creation time (keep most recent)
            seen_downloads = {}
            deduplicated_history = []

            for entry in all_history:
                # Create a unique key based on URL and title
                key = f"{entry.get('url', '')}_{entry.get('title', '')}"
                created_at = entry.get("created_at", "")

                # Keep the entry with the latest created_at for each unique download
                if (
                    key not in seen_downloads
                    or created_at > seen_downloads[key]["created_at"]
                ):
                    seen_downloads[key] = entry

            # Convert back to list and sort by creation time (most recent first)
            deduplicated_history = list(seen_downloads.values())
            deduplicated_history.sort(
                key=lambda x: x.get("created_at", ""), reverse=True
            )

            # Apply limit
            recent_history = (
                deduplicated_history[:limit] if limit > 0 else deduplicated_history
            )

            return {
                "history": recent_history,
                "count": len(recent_history),
                "memory_count": len(memory_history),
                "database_count": len(database_history),
            }

        except Exception as e:
            logger.error(f"Error getting download history: {e}")
            # Fallback to original in-memory only behavior
            recent_history = (
                self.download_history[-limit:] if limit > 0 else self.download_history
            )
            return {
                "history": list(reversed(recent_history)),
                "count": len(recent_history),
            }

    def stop_download(self, download_id: int) -> Dict:
        """Stop a download (not easily implemented with subprocess, return success for UI)"""
        from ..database.connection import get_db
        from ..database.models import Download

        # Check in-memory active downloads first
        if download_id in self.active_downloads:
            download_entry = self.active_downloads[download_id]
            download_entry["status"] = "stopped"
            download_entry["completed_at"] = datetime.utcnow().isoformat()
            download_entry["error_message"] = "Download stopped by user"

            # Move to history
            self.download_history.append(download_entry)
            del self.active_downloads[download_id]

            return {"success": True, "message": f"Download {download_id} stopped"}

        # Check database for download record
        try:
            with get_db() as session:
                download = (
                    session.query(Download).filter(Download.id == download_id).first()
                )
                if download:
                    # Update status in database
                    download.status = "stopped"
                    download.error_message = "Download stopped by user"
                    download.updated_at = datetime.utcnow()
                    session.commit()

                    return {
                        "success": True,
                        "message": f"Download {download_id} stopped",
                    }

        except Exception as e:
            logger.error(f"Error stopping download {download_id}: {e}")
            return {"success": False, "error": f"Database error: {str(e)}"}

        return {"success": False, "error": "Download not found"}

    def retry_download(self, download_id: int) -> Dict:
        """Retry a failed download"""
        from ..database.connection import get_db
        from ..database.models import Download, Video

        # Find in history first
        for entry in self.download_history:
            if entry["id"] == download_id and entry["status"] in ["failed", "stopped"]:
                # Create new download with same parameters
                return self.add_music_video_download(
                    artist=entry["artist"],
                    title=entry["title"],
                    url=entry["url"],
                    quality=entry["quality"],
                    video_id=entry.get("video_id"),
                    download_subtitles=entry.get("download_subtitles", False),
                    subtitle_languages=entry.get("subtitle_languages", "en,en-US"),
                    artist_folder_path=entry.get("artist_folder_path"),
                )

        # Check database for download record
        try:
            with get_db() as session:
                download = (
                    session.query(Download).filter(Download.id == download_id).first()
                )
                if download and download.status in ["failed", "stopped"]:
                    # Get video info for retry
                    video = None
                    if download.video_id:
                        video = (
                            session.query(Video)
                            .filter(Video.id == download.video_id)
                            .first()
                        )

                    # Update status to pending and reset progress
                    download.status = "pending"
                    download.progress = 0
                    download.error_message = None
                    download.updated_at = datetime.utcnow()
                    session.commit()

                    # Actually add the download back to the queue
                    if video and video.youtube_url:
                        # Extract data from session to avoid lazy loading issues
                        video_id = video.id
                        video_title = video.title
                        video_url = video.youtube_url
                        artist_name = (
                            video.artist.name if video.artist else "Unknown Artist"
                        )
                        download_db_id = download.id

                        # Add to queue using the same logic as _resume_pending_downloads
                        from src.services.settings_service import settings

                        music_videos_path = settings.get(
                            "music_videos_path", "data/musicvideos"
                        )
                        if not music_videos_path or music_videos_path.strip() == "":
                            music_videos_path = "data/musicvideos"

                        folder_name = FilenameCleanup.sanitize_folder_name(artist_name)
                        output_dir = os.path.join(music_videos_path, folder_name)

                        download_entry = {
                            "id": self._get_next_id(),
                            "download_id": download_db_id,
                            "artist": artist_name,
                            "title": video_title,
                            "url": video_url,
                            "quality": "best",
                            "download_subtitles": False,
                            "status": "queued",
                            "progress": 0,
                            "video_id": video_id,
                            "output_dir": output_dir,
                            "quality_format_string": "bv*[height<=1080]+ba/best[height<=1080]/18/worst",
                        }

                        self.download_queue.append(download_entry)
                        self.active_downloads[download_entry["id"]] = download_entry

                        # Start download thread
                        thread = threading.Thread(
                            target=self._download_video, args=(download_entry,)
                        )
                        thread.daemon = True
                        thread.start()

                        logger.info(f"Requeued download: {artist_name} - {video_title}")

                    return {
                        "success": True,
                        "message": f"Download {download_id} queued for retry",
                    }
                elif download:
                    return {
                        "success": False,
                        "error": f"Download is in '{download.status}' status and cannot be retried",
                    }

        except Exception as e:
            logger.error(f"Error retrying download {download_id}: {e}")
            return {"success": False, "error": f"Database error: {str(e)}"}

        return {"success": False, "error": "Download not found or not retryable"}

    def process_pending_downloads(self) -> Dict:
        """Process pending downloads from database with rate limiting (max 1 every 30 seconds)"""
        from ..database.connection import get_db
        from ..database.models import Download, Video

        processed_count = 0
        errors = []

        try:
            with get_db() as session:
                # Check if there are already active downloads to avoid overwhelming YouTube
                active_download_count = len(self.active_downloads)

                # Also check for downloads in 'downloading' status in database
                downloading_in_db = (
                    session.query(Download)
                    .filter(Download.status == "downloading")
                    .count()
                )
                total_active = active_download_count + downloading_in_db

                logger.info(
                    f"Active downloads - In memory: {active_download_count}, In DB: {downloading_in_db}, Total: {total_active}"
                )

                if (
                    total_active >= 1
                ):  # AGGRESSIVE RATE LIMITING: Max 1 concurrent download
                    logger.info(
                        f"Rate limiting: {total_active} downloads already active, skipping new starts"
                    )
                    return {
                        "success": True,
                        "processed_count": 0,
                        "found_pending": 0,
                        "errors": [],
                        "message": f"Rate limiting: {total_active} downloads already active",
                    }

                # Get pending/queued downloads from database - only start 1 at a time
                pending_downloads = (
                    session.query(Download)
                    .filter(Download.status.in_(["pending", "queued"]))
                    .order_by(Download.created_at.asc())
                    .limit(1)  # RATE LIMITING: Only process 1 download at a time
                    .all()
                )

                logger.info(
                    f"Found {len(pending_downloads)} pending downloads in database"
                )

                for download in pending_downloads:
                    try:
                        # EXTRACT ALL DATA WITHIN SESSION to avoid DetachedInstanceError
                        download_data = {
                            "id": download.id,
                            "video_id": download.video_id,
                            "title": download.title,
                            "original_url": download.original_url,
                            "quality": download.quality,
                            "created_at": download.created_at,
                        }

                        # Skip if already active in ytdlp_service
                        if download_data["id"] in self.active_downloads:
                            logger.debug(
                                f"Download {download_data['id']} already active, skipping"
                            )
                            continue

                        # Get video info if available (with eager loading)
                        video_data = None
                        if download_data["video_id"]:
                            from sqlalchemy.orm import joinedload

                            video = (
                                session.query(Video)
                                .options(joinedload(Video.artist))
                                .filter(Video.id == download_data["video_id"])
                                .first()
                            )

                            if video:
                                video_data = {
                                    "youtube_url": video.youtube_url,
                                    "url": video.url,
                                    "artist_name": (
                                        video.artist.name
                                        if video.artist
                                        else "Unknown Artist"
                                    ),
                                }

                        # Determine URL to use
                        download_url = download_data["original_url"]
                        if video_data and video_data["youtube_url"]:
                            download_url = video_data["youtube_url"]
                        elif video_data and video_data["url"]:
                            download_url = video_data["url"]

                        if not download_url or download_url == "Unknown URL":
                            logger.warning(
                                f"Download {download_data['id']} has no valid URL, skipping"
                            )
                            continue

                        # Get artist name
                        artist_name = (
                            video_data["artist_name"]
                            if video_data
                            else "Unknown Artist"
                        )

                        # Create artist folder and get output directory
                        from src.services.settings_service import settings

                        music_videos_path = settings.get(
                            "music_videos_path", "data/musicvideos"
                        )
                        if not music_videos_path or music_videos_path.strip() == "":
                            music_videos_path = "data/musicvideos"

                        # Create artist folder
                        folder_name = FilenameCleanup.sanitize_folder_name(artist_name)
                        output_dir = os.path.join(music_videos_path, folder_name)
                        os.makedirs(output_dir, exist_ok=True)

                        # Add to ytdlp_service queue with mapping to database ID
                        logger.info(
                            f"Processing download {download_data['id']}: {artist_name} - {download_data['title']}"
                        )

                        # Create download entry for ytdlp_service using EXTRACTED DATA
                        download_entry = {
                            "id": f"db_{download_data['id']}",  # Map to database ID
                            "db_download_id": download_data[
                                "id"
                            ],  # Store original database ID for status updates
                            "artist": artist_name,
                            "title": download_data["title"],
                            "url": download_url,
                            "quality": download_data["quality"] or "best",
                            "video_id": download_data["video_id"],
                            "download_subtitles": True,  # Enable subtitles by default
                            "subtitle_languages": "en,en-US,ja",
                            "status": "queued",
                            "progress": 0,
                            "created_at": datetime.utcnow().isoformat(),
                            "started_at": None,
                            "completed_at": None,
                            "error_message": None,
                            "file_path": None,
                            "file_size": None,
                            "artist_folder_path": folder_name,
                            "output_dir": output_dir,
                        }

                        # Add to queue and active downloads
                        self.download_queue.append(download_entry)
                        self.active_downloads[f"db_{download_data['id']}"] = (
                            download_entry
                        )

                        # Update database status to 'downloading' (still within session)
                        download.status = "downloading"
                        download.updated_at = datetime.utcnow()

                        # Start download in background thread
                        thread = threading.Thread(
                            target=self._download_video, args=(download_entry,)
                        )
                        thread.daemon = True
                        thread.start()

                        processed_count += 1
                        logger.info(
                            f"Started download {download_data['id']} in background thread"
                        )

                    except Exception as e:
                        # Use extracted data to avoid session issues in error handling
                        download_id = getattr(download, "id", "unknown")
                        error_msg = (
                            f"Failed to process download {download_id}: {str(e)}"
                        )
                        logger.error(error_msg)
                        errors.append(error_msg)

                        # Update download status to failed (still within session)
                        try:
                            download.status = "failed"
                            download.error_message = str(e)
                            download.updated_at = datetime.utcnow()
                        except:
                            pass  # Don't fail the whole operation if we can't update one record

                # Commit all changes
                session.commit()

                return {
                    "success": True,
                    "processed_count": processed_count,
                    "found_pending": len(pending_downloads),
                    "errors": errors,
                    "message": f"Processed {processed_count} pending downloads",
                }

        except Exception as e:
            logger.error(f"Error processing pending downloads: {e}")
            return {
                "success": False,
                "error": str(e),
                "processed_count": processed_count,
                "errors": errors,
            }

    def clear_history(self) -> Dict:
        """Clear download history from both memory and database"""
        memory_count = len(self.download_history)
        self.download_history.clear()

        # Also clear database records
        db_count = 0
        try:
            from src.database.models import Download

            with get_db() as session:
                db_count = session.query(Download).count()
                session.query(Download).delete()
                session.commit()
                logger.info(f"Cleared {db_count} download records from database")
        except Exception as e:
            logger.error(f"Failed to clear download history from database: {e}")
            # Still return success for memory clearing even if DB fails

        # Also clear download queue to prevent re-adding completed downloads
        cleared_queue_count = len(self.download_queue)
        self.download_queue.clear()

        total_count = memory_count + db_count
        logger.info(
            f"Clear history summary - Memory: {memory_count}, Database: {db_count}, Queue: {cleared_queue_count}"
        )

        return {
            "success": True,
            "deleted_count": total_count,
            "details": {
                "memory": memory_count,
                "database": db_count,
                "queue_cleared": cleared_queue_count,
            },
        }

    def clear_stuck_downloads(self, minutes: int = 10) -> Dict:
        """Clear downloads stuck at 0% for more than specified minutes"""
        current_time = datetime.utcnow()
        cleared_count = 0

        stuck_ids = []
        for download_id, entry in self.active_downloads.items():
            if entry["status"] == "downloading" and entry["progress"] == 0:
                started_at = (
                    datetime.fromisoformat(entry["started_at"])
                    if entry["started_at"]
                    else current_time
                )
                if (current_time - started_at).total_seconds() > (minutes * 60):
                    stuck_ids.append(download_id)

        for download_id in stuck_ids:
            self.stop_download(download_id)
            cleared_count += 1

        return {"success": True, "cleared_count": cleared_count}

    def set_cookie_file(self, cookie_file_path: str):
        """Set custom cookie file for age-restricted videos"""
        self.custom_cookie_file = cookie_file_path
        logger.info(f"Custom cookie file set: {cookie_file_path}")

    def clear_cookie_file(self):
        """Clear custom cookie file"""
        self.custom_cookie_file = None
        logger.info("Custom cookie file cleared")

    def get_cookie_status(self) -> Dict:
        """Get status of custom cookie file"""
        if self.custom_cookie_file and os.path.exists(self.custom_cookie_file):
            try:
                stat = os.stat(self.custom_cookie_file)
                return {
                    "cookies_available": True,
                    "file_path": self.custom_cookie_file,
                    "file_size": stat.st_size,
                    "modified_time": stat.st_mtime,
                }
            except Exception as e:
                return {"cookies_available": False, "error": str(e)}
        else:
            return {"cookies_available": False}

    def _load_existing_cookie_file(self):
        """Auto-load existing cookie file at startup if available"""
        import os

        # Check standard cookie locations
        cookie_paths = [
            "data/cookies/youtube_cookies.txt",
            "cookies.txt",
            "youtube_cookies.txt",
        ]

        for path in cookie_paths:
            full_path = os.path.join(os.getcwd(), path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                logger.info(f"Auto-loading existing cookie file: {full_path}")
                self.custom_cookie_file = full_path
                break

        if not self.custom_cookie_file:
            logger.debug("No existing cookie file found to auto-load")

    def health_check(self) -> Dict:
        """Check if yt-dlp is available and working"""
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

    def _emergency_validate_video_linking(self, video_id: int, download_entry: dict):
        """
        Emergency validation and recovery system for video file linking
        Implements comprehensive defensive measures for download validation
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

                    # First try our improved file detection on the original template
                    recovered_file_path = None
                    if "output_dir" in download_entry:
                        output_template = os.path.join(
                            download_entry["output_dir"],
                            f"{FilenameCleanup.sanitize_folder_name(download_entry.get('title', 'Unknown'))}.%(ext)s",
                        )
                        recovered_file_path = self._find_downloaded_file(
                            output_template, download_entry
                        )
                        if recovered_file_path:
                            logger.info(
                                f"   ✅ Found file using improved template detection: {recovered_file_path}"
                            )

                    # If that fails, try comprehensive file search
                    if not recovered_file_path:
                        recovered_file_path = self._emergency_file_search(
                            video, download_entry, session
                        )

                    if recovered_file_path:
                        video.local_path = recovered_file_path
                        session.commit()
                        logger.info(
                            f"✅ Emergency linking recovery successful: {recovered_file_path}"
                        )

                        # Extract basic metadata from recovered file
                        self._extract_basic_metadata_emergency(
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

    def _find_downloaded_file(
        self, output_template: str, download_entry: dict
    ) -> Optional[str]:
        """
        Robust file detection that handles yt-dlp filename variations
        """
        import glob
        import re
        from html import unescape

        # Extract directory and base filename from template
        output_dir = os.path.dirname(output_template)
        template_basename = os.path.basename(output_template).replace("%(ext)s", "")

        logger.debug(
            f"Looking for files in {output_dir} matching pattern based on: {template_basename}"
        )

        # Strategy 1: Exact template match (original logic)
        for ext in ["mp4", "mkv", "webm", "avi", "mov", "flv"]:
            exact_file = output_template.replace("%(ext)s", ext)
            if os.path.exists(exact_file):
                logger.debug(f"Found exact template match: {exact_file}")
                return exact_file

        # Strategy 2: Pattern-based search with HTML entity decoding
        # Clean the template basename by handling common yt-dlp transformations
        search_patterns = []

        # Create search pattern by:
        # 1. HTML decode common entities
        decoded_basename = unescape(template_basename)
        # 2. Handle yt-dlp's common filename transformations
        alt_basename1 = template_basename.replace("'", "39").replace("&#39;", "39")
        alt_basename2 = template_basename.replace(" - '", " - 39").replace(
            " - &#39;", " - 39"
        )
        alt_basename3 = (
            template_basename.replace("'", "39")
            .replace("&#39;", "39")
            .replace(" - ", " - 39")
        )
        # Handle parentheses removal (common yt-dlp transformation)
        no_parens = re.sub(r"[()]", "", template_basename)
        no_parens_spaces = re.sub(r"[()]", " ", template_basename).replace("  ", " ")
        # Handle period removal after abbreviations
        no_periods = template_basename.replace("ft.", "ft").replace("feat.", "feat")
        # Combined transformations
        combined = (
            re.sub(r"[()]", "", template_basename)
            .replace("ft.", "ft")
            .replace("feat.", "feat")
        )

        # 3. Create flexible pattern that allows for minor variations
        flexible_pattern = re.escape(template_basename[:15])  # First 15 chars

        # More comprehensive search patterns
        search_patterns.extend(
            [
                f"{template_basename}.*",  # Original template
                f"{decoded_basename}.*",  # HTML decoded
                f"{alt_basename1}.*",  # Quote variations
                f"{alt_basename2}.*",  # Quote variations with context
                f"{alt_basename3}.*",  # Quote variations with separator
                f"{no_parens}.*",  # Parentheses removed
                f"{no_parens_spaces}.*",  # Parentheses replaced with spaces
                f"{no_periods}.*",  # Periods removed from abbreviations
                f"{combined}.*",  # Combined transformations
                f"*{template_basename[:10]}*",  # Partial start match
                f"*{flexible_pattern[:10]}*",  # Flexible partial match
                f"*{template_basename.split(' - ')[0]}*{template_basename.split(' - ')[-1][:10]}*",  # Artist + partial title
            ]
        )

        # Search for files using glob patterns
        for pattern in search_patterns:
            glob_pattern = os.path.join(output_dir, pattern)
            matches = glob.glob(glob_pattern)

            # Filter for video files
            video_matches = [
                m
                for m in matches
                if any(
                    m.lower().endswith(f".{ext}")
                    for ext in ["mp4", "mkv", "webm", "avi", "mov", "flv"]
                )
            ]

            if video_matches:
                # Filter matches by title similarity to avoid wrong files
                title_keywords = [
                    word.lower() for word in template_basename.split() if len(word) > 3
                ]

                if len(video_matches) > 1 and title_keywords:
                    # Score each match by how many title keywords it contains
                    def score_match(file_path):
                        filename = os.path.basename(file_path).lower()
                        score = sum(
                            1 for keyword in title_keywords if keyword in filename
                        )
                        return score

                    # Get matches with the highest keyword score
                    scored_matches = [(score_match(f), f) for f in video_matches]
                    max_score = max(scored_matches, key=lambda x: x[0])[0]

                    if max_score > 0:  # At least one keyword match
                        best_matches = [
                            f for score, f in scored_matches if score == max_score
                        ]
                        # Among the best keyword matches, pick the largest file
                        best_file = max(
                            best_matches,
                            key=lambda f: (
                                os.path.getsize(f) if os.path.exists(f) else 0
                            ),
                        )
                    else:
                        # No keyword matches, fall back to largest file
                        best_file = max(
                            video_matches,
                            key=lambda f: (
                                os.path.getsize(f) if os.path.exists(f) else 0
                            ),
                        )
                else:
                    # Single match or no keywords, take first/largest
                    best_file = (
                        video_matches[0]
                        if len(video_matches) == 1
                        else max(
                            video_matches,
                            key=lambda f: (
                                os.path.getsize(f) if os.path.exists(f) else 0
                            ),
                        )
                    )

                logger.debug(
                    f"Found pattern match: {best_file} using pattern: {pattern}"
                )
                return best_file

        # Strategy 3: Fallback - look for any recent video files in the directory
        try:
            import time

            current_time = time.time()
            recent_threshold = 300  # 5 minutes

            for file_path in glob.glob(os.path.join(output_dir, "*.mp4")):
                if os.path.exists(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age < recent_threshold:
                        # Check if filename has any similarity to expected title
                        if any(
                            word.lower() in os.path.basename(file_path).lower()
                            for word in template_basename.split()
                            if len(word) > 3
                        ):
                            logger.debug(f"Found recent similar file: {file_path}")
                            return file_path
        except Exception as e:
            logger.debug(f"Fallback search failed: {e}")

        logger.warning(f"No downloaded file found for template: {output_template}")
        return None

    def _emergency_file_search(
        self, video, download_entry: dict, session
    ) -> Optional[str]:
        """
        Emergency file search using multiple patterns and fallback locations
        """
        try:
            import glob
            import time

            from src.services.settings_service import settings

            music_videos_path = settings.get("music_videos_path", "data/musicvideos")

            # Get artist name for file location
            artist_name = "Unknown Artist"
            if video.artist_id:
                from src.database.models import Artist

                artist = (
                    session.query(Artist).filter(Artist.id == video.artist_id).first()
                )
                if artist:
                    artist_name = artist.name

            # Clean video title for filename matching
            video_title = video.title or f"Video_{video.id}"
            clean_title = self._sanitize_filename_for_search(video_title)

            # Search patterns for downloaded files
            search_patterns = [
                # Organized location: data/musicvideos/Artist/Title.ext
                os.path.join(
                    music_videos_path,
                    self._sanitize_filename_for_search(artist_name),
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

    def _extract_basic_metadata_emergency(self, video, file_path: str, session):
        """
        Emergency metadata extraction with graceful fallbacks
        """
        try:
            import json
            import subprocess

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

    def _sanitize_filename_for_search(self, filename: str) -> str:
        """Sanitize filename for search patterns and filesystem compatibility"""
        import re

        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", filename)
        sanitized = re.sub(r"[^\w\s-]", "", sanitized).strip()
        return sanitized[:100] if sanitized else "Unknown"

    def _resume_pending_downloads(self):
        """Resume downloads that were queued but not processed during restart"""
        try:
            from src.database.connection import get_db
            from src.database.models import Download, Video

            with get_db() as session:
                # Get pending/queued downloads with explicit loading
                pending_downloads = (
                    session.query(Download)
                    .filter(Download.status.in_(["queued", "pending"]))
                    .order_by(Download.created_at)
                    .all()
                )

                logger.info(
                    f"Found {len(pending_downloads)} pending downloads to resume"
                )

                for download in pending_downloads:
                    try:
                        # Extract all required data within the session to avoid lazy loading
                        download_db_id = download.id
                        video_id_fk = download.video_id

                        # Get video data with explicit loading
                        from sqlalchemy.orm import joinedload

                        video = (
                            session.query(Video)
                            .options(joinedload(Video.artist))
                            .filter_by(id=video_id_fk)
                            .first()
                        )
                        if not video or not video.youtube_url:
                            logger.warning(
                                f"Skipping download {download_db_id} - no video or URL"
                            )
                            continue

                        # Get all data while in session to avoid lazy loading issues
                        artist_name = (
                            video.artist.name if video.artist else "Unknown Artist"
                        )
                        video_title = video.title
                        video_url = video.youtube_url
                        video_id = video.id

                        # Calculate output directory
                        from src.services.settings_service import settings

                        music_videos_path = settings.get(
                            "music_videos_path", "data/musicvideos"
                        )
                        if not music_videos_path or music_videos_path.strip() == "":
                            music_videos_path = "data/musicvideos"

                        folder_name = FilenameCleanup.sanitize_folder_name(artist_name)
                        output_dir = os.path.join(music_videos_path, folder_name)

                        # Add to queue with existing download record (use local vars to avoid session issues)
                        download_entry = {
                            "id": self._get_next_id(),  # Internal download ID
                            "db_download_id": download_db_id,  # Reference to existing DB record (fixed field name)
                            "artist": artist_name,
                            "title": video_title,
                            "url": video_url,
                            "quality": "best",
                            "download_subtitles": False,
                            "status": "queued",
                            "progress": 0,
                            "video_id": video_id,
                            "output_dir": output_dir,
                            "quality_format_string": "bv*[height<=1080]+ba/best[height<=1080]/18/worst",  # Quality preference with safe fallback
                        }

                        self.download_queue.append(download_entry)
                        self.active_downloads[download_entry["id"]] = download_entry

                        # Start download thread immediately (like add_music_video_download does)
                        thread = threading.Thread(
                            target=self._download_video, args=(download_entry,)
                        )
                        thread.daemon = True
                        thread.start()

                        logger.info(f"Resumed download: {artist_name} - {video_title}")

                    except Exception as e:
                        logger.error(
                            f"Failed to resume download {download_db_id or 'unknown'}: {e}"
                        )
                        # If it's a session binding issue, skip and continue
                        if "not bound to a Session" in str(e):
                            logger.warning(
                                f"Skipping download {download_db_id} due to session binding issue"
                            )
                        continue

        except Exception as e:
            logger.error(f"Failed to resume pending downloads: {e}")


# Global instance
ytdlp_service = YtDlpService()
