"""
Download Manager Module for YtDlp Service

This module contains the core download management functionality extracted from ytdlp_service.py.
It provides standalone functions for managing downloads, processing queues, and handling download operations.

All functions accept service state as parameters to maintain separation of concerns while
allowing the main orchestrator to manage state.
"""

import os
import threading
from datetime import datetime
from typing import Dict

from src.database.connection import get_db
from src.database.models import Artist as ArtistModel
from src.database.models import Download, Video
from src.services.settings_service import settings
from src.services.youtube_download_engine import youtube_download_engine
from src.services.ytdlp_file_detection import YtDlpFileDetection
from src.services.ytdlp_metadata import YtDlpMetadata
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.ytdlp_download_manager")


def add_music_video_download(
    service_state: Dict,
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
    """
    Add a music video download to the queue

    Args:
        service_state: Dictionary containing service state:
            - active_downloads: Dict of active download entries
            - download_queue: List of queued downloads
            - download_history: List of completed downloads
            - _next_id: Counter for download IDs
        artist: Artist name
        title: Video title
        url: Video URL
        quality: Video quality preference (deprecated - use quality service)
        video_id: Optional video ID for database tracking
        download_subtitles: Whether to download closed captions/subtitles
        subtitle_languages: Language codes for subtitles (e.g., "en,en-US,fr")
        artist_folder_path: Optional custom folder path for the artist
        user_id: Optional user ID for quality preferences
        format_string: Optional quality format string (for upgrades)
        upgrade_mode: Whether this is a quality upgrade (replaces existing file)

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
        logger.info(f"Music videos path exists: {os.path.exists(music_videos_path)}")
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

        # Get quality format string - use provided format_string if available (for upgrades)
        if format_string:
            quality_format_string = format_string
            logger.info(
                f"Using provided format string: {quality_format_string[:100]}..."
            )
        else:
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
                logger.info(
                    f"Using generated quality format string: {quality_format_string[:100]}..."
                )
            except Exception as quality_error:
                logger.warning(
                    f"Failed to get quality format string, using default: {quality_error}"
                )
                quality_format_string = "bv*[height<=1080]+ba/best[height<=1080]/18/worst"  # Restore quality preference with fallback

        # Check for existing active downloads for this video
        if video_id:
            existing_active = None
            for existing_id, existing_entry in service_state[
                "active_downloads"
            ].items():
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
        download_id = service_state["_next_id"]
        service_state["_next_id"] += 1

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
            "upgrade_mode": upgrade_mode,  # Track if this is a quality upgrade
        }

        # Create database record for persistent history
        try:
            with get_db() as session:
                # Find or create artist
                artist_obj = session.query(ArtistModel).filter_by(name=artist).first()
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
        service_state["download_queue"].append(download_entry)
        service_state["active_downloads"][download_id] = download_entry

        # Start download in background thread
        thread = threading.Thread(
            target=_download_video, args=(service_state, download_entry)
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


def _download_video(service_state: Dict, download_entry: Dict):
    """
    Download video using the complete YouTube Download Engine

    Args:
        service_state: Service state dictionary
        download_entry: Download entry dictionary
    """
    download_id = download_entry["id"]
    video_id = download_entry.get("video_id")

    try:
        download_entry["status"] = "downloading"
        download_entry["started_at"] = datetime.utcnow().isoformat()

        # Update database status to downloading
        _update_database_download_status(download_entry, "downloading")

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

            # Clean up old quality versions if this is an upgrade
            if download_entry.get("upgrade_mode"):
                _cleanup_old_quality_versions(result.file_path, result.file_size)

            # Update database with success
            _update_video_status_in_database(
                video_id,
                "DOWNLOADED",
                result.file_path,
                result.file_size,
            )
            _update_database_download_status(
                download_entry,
                "completed",
                result.file_path,
                result.file_size,
            )

            # EMERGENCY VALIDATION: Ensure video was properly linked
            if video_id:
                YtDlpMetadata.emergency_validate_video_linking(
                    video_id,
                    download_entry,
                    YtDlpFileDetection.find_downloaded_file,
                )

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
                    metadata_thread = threading.Thread(target=run_metadata_enrichment)
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
                _update_database_download_status(
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
                _update_video_status_in_database(video_id, "FAILED")
                _update_database_download_status(
                    download_entry, "failed", None, None, error_message
                )

    except Exception as e:
        download_entry["status"] = "failed"
        download_entry["completed_at"] = datetime.utcnow().isoformat()
        download_entry["error_message"] = f"Download engine error: {str(e)}"

        logger.error(f"Download {download_id} engine exception: {e}")

        _update_video_status_in_database(video_id, "FAILED")
        _update_database_download_status(download_entry, "failed", None, None, str(e))

    finally:
        # Move from active to history
        if download_id in service_state["active_downloads"]:
            service_state["download_history"].append(
                service_state["active_downloads"][download_id]
            )
            del service_state["active_downloads"][download_id]

        # Remove from queue
        service_state["download_queue"] = [
            d for d in service_state["download_queue"] if d["id"] != download_id
        ]


def _update_video_status_in_database(
    video_id: int, status: str, file_path: str = None, file_size: int = None
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
                            _handle_quality_upgrade_cleanup(
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
                logger.info(f"Updated video {video_id} status to {status} in database")
            else:
                logger.warning(f"Video {video_id} not found in database")
    except Exception as e:
        logger.error(f"Failed to update video {video_id} status in database: {e}")


def _update_database_download_status(
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
        with get_db() as session:
            db_download = (
                session.query(Download).filter(Download.id == db_download_id).first()
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


def _handle_quality_upgrade_cleanup(video, original_file_path: str, new_file_path: str):
    """Handle cleanup of original files during quality upgrades"""
    try:
        # Check if this is a quality upgrade (indicated by metadata or title)
        is_upgrade = False

        # Check video metadata for upgrade flag
        if hasattr(video, "video_metadata") and video.video_metadata:
            is_upgrade = video.video_metadata.get("upgrade_requested", False)
            logger.info(f"Video {video.id} upgrade_requested flag: {is_upgrade}")

        # Also check if this looks like an upgrade based on file paths
        # (new file in same directory, different filename)
        if not is_upgrade and original_file_path and new_file_path:
            original_dir = os.path.dirname(original_file_path)
            new_dir = os.path.dirname(new_file_path)
            original_basename = os.path.basename(original_file_path)
            new_basename = os.path.basename(new_file_path)

            # Same directory but different files suggests upgrade
            is_upgrade = original_dir == new_dir and original_basename != new_basename

            if is_upgrade:
                logger.info(
                    f"Video {video.id} detected as upgrade based on file paths: "
                    f"{original_basename} -> {new_basename}"
                )

        if not is_upgrade:
            logger.debug(
                f"Not a quality upgrade for video {video.id}, skipping cleanup"
            )
            return  # Not a quality upgrade, don't delete anything

        # Check user preference for auto-deletion
        auto_delete = settings.get("auto_delete_original_on_upgrade", True)
        if not auto_delete:
            logger.info(f"Original file cleanup disabled for video {video.id}")
            return

        # Verify the original file exists and new file is different
        if not os.path.exists(original_file_path):
            logger.debug(f"Original file already doesn't exist: {original_file_path}")
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
        logger.error(f"Error during quality upgrade cleanup for video {video.id}: {e}")
        # Don't raise the exception - cleanup failure shouldn't break the download


def _cleanup_old_quality_versions(new_file_path: str, new_file_size: int):
    """
    Clean up old lower-quality versions after successful quality upgrade
    Keeps only the newest/largest version to save disk space
    """
    try:
        import re

        if not new_file_path or not os.path.exists(new_file_path):
            logger.warning(f"Cannot cleanup: new file doesn't exist: {new_file_path}")
            return

        # Get directory and base filename
        directory = os.path.dirname(new_file_path)
        new_filename = os.path.basename(new_file_path)
        new_basename = os.path.splitext(new_filename)[0]

        # Remove "(Quality Upgrade)" suffix if present for matching
        base_pattern = re.sub(r"\s*\(Quality Upgrade\)", "", new_basename)

        logger.info(f"Cleaning up old quality versions for: {base_pattern}")

        # Find all related files (same base name, different quality)
        related_files = []
        for file in os.listdir(directory):
            if file == new_filename:
                continue  # Skip the new file itself

            # Match files with same base pattern
            file_basename = os.path.splitext(file)[0]
            file_pattern = re.sub(r"\s*\(Quality Upgrade\)", "", file_basename)

            if file_pattern == base_pattern or base_pattern in file_pattern:
                full_path = os.path.join(directory, file)
                if os.path.isfile(full_path):
                    file_size = os.path.getsize(full_path)
                    # Only consider video files smaller than the new file
                    if (
                        file.endswith((".mp4", ".webm", ".mkv", ".avi", ".mov"))
                        and file_size < new_file_size
                    ):
                        related_files.append((full_path, file, file_size))

        if not related_files:
            logger.info("No old quality versions found to clean up")
            return

        # Delete old quality versions
        deleted_count = 0
        space_freed = 0
        for file_path, filename, file_size in related_files:
            try:
                os.remove(file_path)
                deleted_count += 1
                space_freed += file_size
                logger.info(
                    f"Deleted old quality version: {filename} ({file_size/(1024*1024):.1f}MB)"
                )

                # Also delete associated files (.info.json, .vtt, etc.)
                base_path = os.path.splitext(file_path)[0]
                for ext in [".info.json", ".vtt", ".srt", ".webp", ".jpg", ".meta"]:
                    assoc_file = base_path + ext
                    if os.path.exists(assoc_file):
                        try:
                            os.remove(assoc_file)
                            logger.debug(
                                f"Deleted associated file: {os.path.basename(assoc_file)}"
                            )
                        except:
                            pass

            except Exception as e:
                logger.warning(f"Failed to delete old version {filename}: {e}")

        if deleted_count > 0:
            logger.info(
                f"Cleanup complete: Deleted {deleted_count} old versions, freed {space_freed/(1024*1024):.1f}MB"
            )

    except Exception as e:
        logger.error(f"Error during old quality cleanup: {e}")


def get_queue(service_state: Dict) -> Dict:
    """
    Get current download queue status

    Args:
        service_state: Service state dictionary

    Returns:
        Dictionary with queue information
    """
    queue_items = list(service_state["active_downloads"].values())
    return {"queue": queue_items, "count": len(queue_items)}


def stop_download(service_state: Dict, download_id: int) -> Dict:
    """
    Stop a download

    Args:
        service_state: Service state dictionary
        download_id: ID of download to stop

    Returns:
        Dictionary with operation result
    """
    # Check in-memory active downloads first
    if download_id in service_state["active_downloads"]:
        download_entry = service_state["active_downloads"][download_id]
        download_entry["status"] = "stopped"
        download_entry["completed_at"] = datetime.utcnow().isoformat()
        download_entry["error_message"] = "Download stopped by user"

        # Move to history
        service_state["download_history"].append(download_entry)
        del service_state["active_downloads"][download_id]

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


def retry_download(service_state: Dict, download_id: int) -> Dict:
    """
    Retry a failed download

    Args:
        service_state: Service state dictionary
        download_id: ID of download to retry

    Returns:
        Dictionary with operation result
    """
    # Find in history first
    for entry in service_state["download_history"]:
        if entry["id"] == download_id and entry["status"] in ["failed", "stopped"]:
            # Create new download with same parameters
            return add_music_video_download(
                service_state,
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
                    music_videos_path = settings.get(
                        "music_videos_path", "data/musicvideos"
                    )
                    if not music_videos_path or music_videos_path.strip() == "":
                        music_videos_path = "data/musicvideos"

                    folder_name = FilenameCleanup.sanitize_folder_name(artist_name)
                    output_dir = os.path.join(music_videos_path, folder_name)

                    download_entry = {
                        "id": service_state["_next_id"],
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

                    service_state["_next_id"] += 1
                    service_state["download_queue"].append(download_entry)
                    service_state["active_downloads"][
                        download_entry["id"]
                    ] = download_entry

                    # Start download thread
                    thread = threading.Thread(
                        target=_download_video, args=(service_state, download_entry)
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


def process_pending_downloads(service_state: Dict) -> Dict:
    """
    Process pending downloads from database with rate limiting (max 1 every 30 seconds)

    Args:
        service_state: Service state dictionary

    Returns:
        Dictionary with processing results
    """
    processed_count = 0
    errors = []

    try:
        with get_db() as session:
            # Check if there are already active downloads to avoid overwhelming YouTube
            active_download_count = len(service_state["active_downloads"])

            # Also check for downloads in 'downloading' status in database
            downloading_in_db = (
                session.query(Download).filter(Download.status == "downloading").count()
            )
            total_active = active_download_count + downloading_in_db

            logger.info(
                f"Active downloads - In memory: {active_download_count}, In DB: {downloading_in_db}, Total: {total_active}"
            )

            if total_active >= 1:  # AGGRESSIVE RATE LIMITING: Max 1 concurrent download
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

            logger.info(f"Found {len(pending_downloads)} pending downloads in database")

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
                    if download_data["id"] in service_state["active_downloads"]:
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
                        video_data["artist_name"] if video_data else "Unknown Artist"
                    )

                    # Create artist folder and get output directory
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
                    service_state["download_queue"].append(download_entry)
                    service_state["active_downloads"][
                        f"db_{download_data['id']}"
                    ] = download_entry

                    # Update database status to 'downloading' (still within session)
                    download.status = "downloading"
                    download.updated_at = datetime.utcnow()

                    # Start download in background thread
                    thread = threading.Thread(
                        target=_download_video, args=(service_state, download_entry)
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
                    error_msg = f"Failed to process download {download_id}: {str(e)}"
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


def clear_stuck_downloads(service_state: Dict, minutes: int = 10) -> Dict:
    """
    Clear downloads stuck at 0% for more than specified minutes

    Args:
        service_state: Service state dictionary
        minutes: Number of minutes after which a stuck download should be cleared

    Returns:
        Dictionary with operation result
    """
    current_time = datetime.utcnow()
    cleared_count = 0

    stuck_ids = []
    for download_id, entry in service_state["active_downloads"].items():
        if entry["status"] == "downloading" and entry["progress"] == 0:
            started_at = (
                datetime.fromisoformat(entry["started_at"])
                if entry["started_at"]
                else current_time
            )
            if (current_time - started_at).total_seconds() > (minutes * 60):
                stuck_ids.append(download_id)

    for download_id in stuck_ids:
        stop_download(service_state, download_id)
        cleared_count += 1

    return {"success": True, "cleared_count": cleared_count}
