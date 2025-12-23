"""
Video Batch Operations Service

Handles batch video operations including wanted video downloads and bulk processing.
Extracted from Flask API layer to provide framework-agnostic service functionality.
"""

import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.video_batch")


def get_ytdlp_path() -> str:
    """Get the best available yt-dlp executable path"""
    ytdlp_paths = [
        "/root/.local/bin/yt-dlp",  # pipx installed (latest)
        "/usr/local/bin/yt-dlp",  # system installed
    ]

    for path in ytdlp_paths:
        if os.path.exists(path):
            return path

    # Fallback to system PATH
    found_path = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found_path:
        return found_path

    # Last resort fallback
    return "/usr/local/bin/yt-dlp"


def resolve_video_url(video, session) -> Optional[str]:
    """
    Helper function to resolve video URL using yt-dlp search

    Args:
        video: Video object from database
        session: Database session

    Returns:
        str: Resolved URL or None
    """
    if video.url:
        return video.url

    # Also check youtube_url field as fallback (but ensure it's complete)
    if (
        video.youtube_url and len(video.youtube_url.strip()) > 30
    ):  # Valid YouTube URLs are longer than 30 chars
        # Additional check: ensure URL has a video ID (not just ending with "?v=")
        if not video.youtube_url.endswith("?v="):
            return video.youtube_url

    try:
        artist_name = video.artist.name if video.artist else "Unknown Artist"
        # Ensure title is a string (fix for integer title issue)
        video_title = str(video.title) if video.title is not None else "Unknown"
        search_query = f"{artist_name} {video_title}"
        logger.info(f"Searching for video URL: {search_query}")

        # Use yt-dlp to search YouTube
        cmd = [
            get_ytdlp_path(),  # Use the best available version
            "--dump-json",
            "--no-download",
            "--playlist-items",
            "1",
            f"ytsearch1:{search_query}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and result.stdout:
            video_info = json.loads(result.stdout.strip())
            resolved_url = video_info.get("webpage_url") or video_info.get("url")

            if resolved_url:
                # Update video with resolved URL
                video.url = resolved_url
                if "id" in video_info:
                    video.youtube_id = video_info["id"]
                session.commit()
                logger.info(f"Resolved video URL for '{video.title}': {resolved_url}")
                return resolved_url
            else:
                logger.warning(f"No URL found in video info for '{video.title}'")
        else:
            logger.error(f"yt-dlp search failed for '{search_query}': {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp search timed out for '{search_query}'")
    except Exception as e:
        logger.error(f"Error resolving video URL for '{video.title}': {e}")

    return None


def download_all_wanted_videos_internal(limit: int = 50) -> Dict:
    """
    Internal function to download all videos with WANTED status

    Args:
        limit: Maximum number of wanted videos to process (default: 50)

    Returns:
        dict: Results containing success status, counts, and individual results
    """
    try:
        results = []
        success_count = 0
        failed_count = 0
        wanted_video_ids = []

        # Import settings service for subtitle configuration
        from src.services.settings_service import settings

        # Read subtitle settings from database once for all downloads
        download_subtitles = settings.get_bool("download_subtitles", False)
        subtitle_languages = settings.get("subtitle_languages", "en,en-US")

        # First, get all wanted video IDs
        with get_db() as session:
            wanted_videos = (
                session.query(Video.id, Video.title, Artist.name)
                .join(Artist)
                .filter(Video.status == VideoStatus.WANTED)
                .limit(limit)
                .all()
            )

            if not wanted_videos:
                return {
                    "success": True,
                    "message": "No wanted videos found",
                    "success_count": 0,
                    "failed_count": 0,
                    "results": [],
                }

            wanted_video_ids = [(v.id, v.title, v.name) for v in wanted_videos]

        logger.info(f"Found {len(wanted_video_ids)} wanted videos to download")

        # Process each video individually to avoid session issues
        for video_id, video_title, artist_name in wanted_video_ids:
            try:
                with get_db() as session:
                    # Get fresh video object for each download
                    video = session.query(Video).filter(Video.id == video_id).first()

                    if not video:
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": "Video not found",
                            }
                        )
                        failed_count += 1
                        continue

                    # Resolve video URL using helper function
                    video_url = resolve_video_url(video, session)

                    if not video_url:
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": "No URL available for download",
                            }
                        )
                        failed_count += 1
                        continue

                    # Import yt-dlp service
                    from src.services.download_service_adapter import ytdlp_service

                    # Queue download
                    result = ytdlp_service.add_music_video_download(
                        artist=artist_name,
                        title=video_title,
                        url=video_url,
                        quality="best",
                        video_id=video_id,
                        download_subtitles=download_subtitles,
                        subtitle_languages=subtitle_languages,
                    )

                    if result and result.get("success"):
                        # Update the video status in a separate transaction
                        video.status = VideoStatus.DOWNLOADING
                        session.commit()

                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": True,
                                "download_id": result.get("id"),
                                "message": "Queued for download",
                            }
                        )
                        success_count += 1
                    else:
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": result.get("error", "Unknown error"),
                            }
                        )
                        failed_count += 1

            except Exception as e:
                logger.error(f"Failed to process video {video_id} ({video_title}): {e}")
                results.append(
                    {
                        "video_id": video_id,
                        "title": video_title,
                        "artist": artist_name,
                        "success": False,
                        "error": str(e),
                    }
                )
                failed_count += 1

        return {
            "success": True,
            "message": f"Processed {len(wanted_video_ids)} videos: {success_count} succeeded, {failed_count} failed",
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Failed to download wanted videos: {e}")
        return {
            "success": False,
            "error": str(e),
            "success_count": 0,
            "failed_count": 0,
            "results": [],
        }


def get_wanted_videos_for_download(limit: int = 50) -> List[Dict]:
    """
    Get videos that are marked as WANTED for downloading

    Scheduler V2 enhancement (v0.10.1): Priority-based ordering
    - Orders by artist schedule_priority (high > medium > low)
    - Then by video priority (if available)
    - Then by created date (oldest first for fairness)
    - Respects artist download_enabled flag

    Args:
        limit: Maximum number of videos to return (default: 50)

    Returns:
        list: Videos with WANTED status ready for download, as dict objects
    """
    try:
        with get_db() as session:
            from sqlalchemy import case

            # Build query with priority ordering (Scheduler V2)
            query = (
                session.query(Video)
                .join(Artist)
                .filter(Video.status == VideoStatus.WANTED)
            )

            # Filter by artist download_enabled if field exists (Scheduler V2)
            if hasattr(Artist, "download_enabled"):
                query = query.filter(Artist.download_enabled == True)

            # Order by priority (Scheduler V2 enhancement)
            if hasattr(Artist, "schedule_priority"):
                # Priority mapping: high=1, medium=2, low=3 for sorting
                priority_order = case(
                    (Artist.schedule_priority == "high", 1),
                    (Artist.schedule_priority == "medium", 2),
                    (Artist.schedule_priority == "low", 3),
                    else_=2,  # Default to medium priority
                )
                query = query.order_by(
                    priority_order,
                    Artist.priority.desc().nullslast(),  # Higher priority artists first
                    Video.created_at.asc(),  # Oldest videos first (fairness)
                )
            else:
                # Fallback to original ordering if no priority field
                query = query.order_by(Video.created_at.desc())

            wanted_videos = query.limit(limit).all()

            # Convert to dict format for scheduler
            video_list = []
            for video in wanted_videos:
                video_dict = {
                    "id": video.id,
                    "title": video.title,
                    "artist_name": video.artist.name if video.artist else "Unknown",
                    "youtube_url": video.youtube_url,
                    "status": (
                        video.status.value
                        if hasattr(video.status, "value")
                        else video.status
                    ),
                }
                video_list.append(video_dict)

            return video_list

    except Exception as e:
        logger.error(f"Error getting wanted videos for download: {e}")
        return []
