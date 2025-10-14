"""
History Management for yt-dlp Service
Handles download history tracking, retrieval, and resume functionality

Extracted from ytdlp_service.py as part of code cleanup.
"""

import os
import threading
from typing import Dict, List

from sqlalchemy.orm import joinedload

from src.database.connection import get_db
from src.database.models import Artist, Download, Video
from src.services.settings_service import settings
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.ytdlp_history")


def get_history(download_history: List[Dict], limit: int = 50) -> Dict:
    """Get download history from both in-memory and database sources

    Args:
        download_history: In-memory download history list
        limit: Maximum number of history entries to return

    Returns:
        Dictionary containing history entries and counts
    """
    try:
        # Get in-memory history
        memory_history = list(download_history)

        # Get database history
        database_history = []
        try:
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
            if key not in seen_downloads or created_at > seen_downloads[key].get(
                "created_at", ""
            ):
                seen_downloads[key] = entry

        # Convert back to list and sort by creation time (most recent first)
        deduplicated_history = list(seen_downloads.values())
        deduplicated_history.sort(key=lambda x: x.get("created_at", ""), reverse=True)

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
        recent_history = download_history[-limit:] if limit > 0 else download_history
        return {
            "history": list(reversed(recent_history)),
            "count": len(recent_history),
        }


def clear_history(download_history: List[Dict], download_queue: List[Dict]) -> Dict:
    """Clear download history from both memory and database

    Args:
        download_history: In-memory download history list
        download_queue: In-memory download queue list

    Returns:
        Dictionary with success status and deletion counts
    """
    memory_count = len(download_history)
    download_history.clear()

    # Also clear database records
    db_count = 0
    try:
        with get_db() as session:
            db_count = session.query(Download).count()
            session.query(Download).delete()
            session.commit()
            logger.info(f"Cleared {db_count} download records from database")
    except Exception as e:
        logger.error(f"Failed to clear download history from database: {e}")
        # Still return success for memory clearing even if DB fails

    # Also clear download queue to prevent re-adding completed downloads
    cleared_queue_count = len(download_queue)
    download_queue.clear()

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


def resume_pending_downloads(
    download_queue: List[Dict],
    active_downloads: Dict,
    get_next_id_func,
    download_video_func,
):
    """Resume downloads that were queued but not processed during restart

    Args:
        download_queue: In-memory download queue list
        active_downloads: Dictionary of active downloads
        get_next_id_func: Function to get next unique download ID
        download_video_func: Function to execute download
    """
    try:
        with get_db() as session:
            # Get pending/queued downloads with explicit loading
            pending_downloads = (
                session.query(Download)
                .filter(Download.status.in_(["queued", "pending"]))
                .order_by(Download.created_at)
                .all()
            )

            logger.info(f"Found {len(pending_downloads)} pending downloads to resume")

            for download in pending_downloads:
                try:
                    # Extract all required data within the session to avoid lazy loading
                    download_db_id = download.id
                    video_id_fk = download.video_id

                    # Get video data with explicit loading
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
                    music_videos_path = settings.get(
                        "music_videos_path", "data/musicvideos"
                    )
                    if not music_videos_path or music_videos_path.strip() == "":
                        music_videos_path = "data/musicvideos"

                    folder_name = FilenameCleanup.sanitize_folder_name(artist_name)
                    output_dir = os.path.join(music_videos_path, folder_name)

                    # Add to queue with existing download record (use local vars to avoid session issues)
                    download_entry = {
                        "id": get_next_id_func(),  # Internal download ID
                        "db_download_id": download_db_id,  # Reference to existing DB record
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

                    download_queue.append(download_entry)
                    active_downloads[download_entry["id"]] = download_entry

                    # Start download thread immediately
                    thread = threading.Thread(
                        target=download_video_func, args=(download_entry,)
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
