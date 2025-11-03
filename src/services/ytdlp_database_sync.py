"""
Database Synchronization for yt-dlp Service
Handles video status updates, download tracking, and quality upgrade cleanup

Extracted from ytdlp_service.py as part of code cleanup.
"""

import os
from datetime import datetime

from src.database.connection import get_db
from src.database.models import Download, Video
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ytdlp_database_sync")


def update_video_status_in_database(
    video_id: int, status: str, file_path: str = None, file_size: int = None
):
    """Update video status in database

    Args:
        video_id: ID of the video to update
        status: New status (e.g., "DOWNLOADED", "DOWNLOADING", "FAILED")
        file_path: Optional path to the downloaded video file
        file_size: Optional size of the downloaded file in bytes
    """
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
                            handle_quality_upgrade_cleanup(
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


def update_database_download_status(
    download_entry: dict,
    status: str,
    file_path: str = None,
    file_size: int = None,
    error_message: str = None,
):
    """Update download status in database

    Args:
        download_entry: Dictionary containing download information
        status: New status for the download
        file_path: Optional path to the downloaded file
        file_size: Optional size of the file in bytes
        error_message: Optional error message if download failed
    """
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


def handle_quality_upgrade_cleanup(video, original_file_path: str, new_file_path: str):
    """Handle cleanup of original files during quality upgrades

    Args:
        video: Video database model instance
        original_file_path: Path to the original lower-quality file
        new_file_path: Path to the new higher-quality file
    """
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
