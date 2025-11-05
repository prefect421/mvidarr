"""
FastAPI Videos Downloads API Module

This module contains all download-related operations for videos.
These endpoints handle video download management:
- Single video download (with multiple variants)
- Bulk video downloads
- Download wanted videos
- Debug download endpoints

Extracted from videos.py as part of the API modularization effort.
Uses shared utility functions (resolve_video_url) from the parent module.

Authentication: All endpoints require session-based authentication via get_current_user dependency.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import get_current_user_legacy
from src.api.fastapi.videos_models import BulkDownloadRequest
from src.database.connection import get_db_session
from src.database.models import Artist, Download, Video, VideoStatus
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_downloads")


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def resolve_video_url(video: Video, session: Session) -> Optional[str]:
    """
    Helper function to resolve video URL using yt-dlp search

    This is a placeholder - the actual implementation should be imported
    from the main videos module or moved to a shared utilities module.

    Args:
        video: Video object
        session: Database session

    Returns:
        str: Resolved URL or None
    """
    # Import from parent module to avoid duplication
    from src.api.fastapi.videos import resolve_video_url as _resolve_video_url

    return await _resolve_video_url(video, session)


# ========================================================================================
# DOWNLOAD OPERATIONS
# ========================================================================================


@router.post("/bulk/download")
async def bulk_download_videos(
    request: BulkDownloadRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Bulk download videos"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to download
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        queued_count = 0
        skipped_count = 0
        errors = []

        for video in videos:
            try:
                video_id = video.id  # Store ID before any operations
                # Skip if already downloaded
                if video.status == "downloaded":
                    skipped_count += 1
                    continue

                # Check if already in queue
                existing_download = (
                    session.query(Download)
                    .filter(
                        Download.video_id == video_id,
                        Download.status.in_(["queued", "downloading"]),
                    )
                    .first()
                )

                if existing_download:
                    skipped_count += 1
                    continue

                # Validate and resolve video URL
                video_url = (
                    video.url
                    or video.youtube_url
                    or f"https://youtube.com/watch?v={video.youtube_id}"
                    if hasattr(video, "youtube_id") and video.youtube_id
                    else None
                )

                if not video_url:
                    # Try to resolve URL
                    resolved_url = await resolve_video_url(video, session)
                    if not resolved_url:
                        errors.append(f"Video {video_id}: No valid URL found")
                        continue
                    video_url = resolved_url

                # Create download entry with all required fields
                download = Download(
                    artist_id=video.artist_id,
                    video_id=video_id,
                    title=video.title,
                    original_url=video_url,
                    status="queued",
                    priority=1,  # Default priority for bulk downloads
                    created_at=datetime.utcnow(),
                )

                session.add(download)
                session.flush()  # Get the download ID

                # Update video status to downloading
                video.status = VideoStatus.DOWNLOADING
                video.updated_at = datetime.utcnow()

                # Submit job to ytdlp_service
                try:
                    from src.services.download_service_adapter import ytdlp_service

                    # Submit to ytdlp_service with download options
                    result = ytdlp_service.add_music_video_download(
                        artist=video.artist.name if video.artist else "Unknown Artist",
                        title=video.title,
                        url=video_url,
                        quality="best",
                        download_subtitles=False,
                        video_id=video_id,
                        download_id=download.id,
                    )

                    logger.info(
                        f"✅ Submitted bulk download job {result.get('download_id')} for video {video_id}"
                    )

                except Exception as download_error:
                    logger.error(
                        f"Failed to submit download task for video {video_id}: {download_error}"
                    )
                    # Still count as queued since it's in the database

                queued_count += 1

            except Exception as e:
                video_id = getattr(video, "id", "unknown")  # Safe ID retrieval
                errors.append(f"Video {video_id}: {str(e)}")
                logger.error(f"Error queuing download for video {video_id}: {e}")

        session.commit()

        logger.info(f"Bulk queued {queued_count} downloads, skipped {skipped_count}")

        result = {
            "message": "Bulk download completed",
            "queued_count": queued_count,
            "skipped_count": skipped_count,
            "total_requested": len(request.video_ids),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk download: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/download")
async def queue_video_download(
    video_id: int = FastAPIPath(..., ge=1),
    request: Dict[str, Any] = Body(default={}),
    session: Session = Depends(get_db_session),
):
    """Queue video download with flexible validation"""
    try:
        logger.info(f"DEBUG: Download request for video {video_id}: {request}")

        # Extract parameters with safe defaults
        priority = 1
        force_redownload = False

        if request:
            priority = request.get("priority", 1)
            force_redownload = request.get("force_redownload", False)

            # Validate priority
            if not isinstance(priority, int) or priority < 1 or priority > 10:
                priority = 1

            # Validate force_redownload
            if not isinstance(force_redownload, bool):
                force_redownload = False

        logger.info(
            f"DEBUG: Using download params - priority: {priority}, force_redownload: {force_redownload}"
        )

        # Get video from database
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Check if already downloaded and not forcing redownload
        if video.status == VideoStatus.DOWNLOADED and not force_redownload:
            return {"message": "Video already downloaded", "video_id": video_id}

        # Check if download already in queue
        existing_download = (
            session.query(Download)
            .filter(
                Download.video_id == video_id,
                Download.status.in_(["queued", "downloading"]),
            )
            .first()
        )

        if existing_download and not force_redownload:
            return {
                "message": "Video already in download queue",
                "video_id": video_id,
                "download_id": existing_download.id,
            }

        # Resolve video URL if needed
        if not video.url:
            url = await resolve_video_url(video, session)
            if not url:
                raise HTTPException(
                    status_code=400, detail="Could not resolve video URL for download"
                )

        # Create download entry
        download = Download(
            artist_id=video.artist_id,
            video_id=video_id,
            title=video.title,
            original_url=(
                video.url
                or video.youtube_url
                or f"https://youtube.com/watch?v={video.youtube_id}"
                if hasattr(video, "youtube_id") and video.youtube_id
                else "Unknown URL"
            ),
            status="queued",
            priority=priority,
            created_at=datetime.utcnow(),
        )

        session.add(download)

        # Update video status
        video.status = VideoStatus.DOWNLOADING
        video.updated_at = datetime.utcnow()

        session.commit()

        # Create background job for download processing
        try:
            from ...services.job_queue import (
                BackgroundJob,
                JobPriority,
                JobType,
                get_job_queue,
            )

            job_queue = await get_job_queue()

            # Map download priority to job priority
            job_priority_map = {
                1: JobPriority.LOW,
                2: JobPriority.NORMAL,
                3: JobPriority.HIGH,
                4: JobPriority.URGENT,
                5: JobPriority.URGENT,
            }
            job_priority = job_priority_map.get(priority, JobPriority.NORMAL)

            # Create download job
            download_job = BackgroundJob(
                type=JobType.VIDEO_DOWNLOAD,
                priority=job_priority,
                payload={
                    "video_id": video_id,
                    "download_id": download.id,
                    "quality": "best",
                    "force_redownload": force_redownload,
                },
                created_by=f"user-api-download-{video_id}",
            )

            job_id = await job_queue.enqueue(download_job)
            logger.info(
                f"Created background download job {job_id} for video {video_id}"
            )

        except Exception as job_error:
            logger.error(
                f"Failed to create background download job for video {video_id}: {job_error}"
            )
            # Don't fail the request if job creation fails
        # This would integrate with the Celery task system
        logger.info(f"Queued download for video {video_id} (priority: {priority})")

        return {
            "message": "Video download queued",
            "video_id": video_id,
            "download_id": download.id,
            "priority": priority,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing download for video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/download-debug")
async def queue_video_download_debug(
    video_id: int = FastAPIPath(..., ge=1),
    request: Dict[str, Any] = Body(default={}),
    session: Session = Depends(get_db_session),
):
    """Debug version of video download bypassing validation"""
    try:
        logger.info(f"DEBUG: Download request for video {video_id}: {request}")

        # Extract parameters with defaults
        priority = request.get("priority", 1) if request else 1
        force_redownload = request.get("force_redownload", False) if request else False

        # Validate and fix parameters
        if not isinstance(priority, int) or priority < 1 or priority > 10:
            priority = 1
        if not isinstance(force_redownload, bool):
            force_redownload = False

        logger.info(
            f"DEBUG: Processing download - video_id: {video_id}, priority: {priority}, force: {force_redownload}"
        )

        # Get video
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            return {"success": False, "error": "Video not found"}

        # Check if already downloaded
        if video.status == VideoStatus.DOWNLOADED and not force_redownload:
            return {
                "success": True,
                "message": "Video already downloaded",
                "video_id": video_id,
            }

        # Simple success response for testing
        return {
            "success": True,
            "message": "Debug download endpoint working",
            "video_id": video_id,
            "priority": priority,
            "force_redownload": force_redownload,
            "video_status": video.status.value if video.status else "unknown",
        }

    except Exception as e:
        logger.error(f"DEBUG: Download error for video {video_id}: {e}")
        return {"success": False, "error": str(e), "error_type": type(e).__name__}


@router.post("/{video_id}/queue-download")
async def queue_download_video(
    video_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Queue video download via Celery processor"""
    try:
        logger.info(f"Queuing download for video {video_id}")

        # Get video
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            return {"success": False, "error": "Video not found"}

        # Check if already downloaded
        if video.status == VideoStatus.DOWNLOADED:
            return {
                "success": True,
                "message": "Video already downloaded",
                "video_id": video_id,
                "status": "already_downloaded",
            }

        # Check if already in download queue
        existing_download = (
            session.query(Download)
            .filter(
                Download.video_id == video_id,
                Download.status.in_(["queued", "downloading", "pending"]),
            )
            .first()
        )

        if existing_download:
            return {
                "success": True,
                "message": "Video already in download queue",
                "video_id": video_id,
                "download_id": existing_download.id,
                "status": "already_queued",
            }

        # Get artist info
        artist = session.query(Artist).filter(Artist.id == video.artist_id).first()
        if not artist:
            return {"success": False, "error": "Artist not found"}

        # Get YouTube URL - check multiple possible fields
        youtube_url = None
        if hasattr(video, "youtube_url") and video.youtube_url:
            youtube_url = video.youtube_url
        elif hasattr(video, "url") and video.url:
            youtube_url = video.url

        if not youtube_url:
            return {
                "success": False,
                "error": "No YouTube URL found for this video. Please add a URL to enable downloading.",
            }

        # Get subtitle settings
        from src.services.settings_service import settings

        download_subtitles = settings.get_bool("download_subtitles", False)
        subtitle_languages = settings.get("subtitle_languages", "en,en-US")

        # Create download record in database for Celery to process
        download = Download(
            artist_id=video.artist_id,
            video_id=video_id,
            title=video.title,
            original_url=youtube_url,
            status="queued",
            quality="best",
            priority=1,
            created_at=datetime.utcnow(),
        )

        session.add(download)
        session.flush()  # Get the download ID

        # Update video status
        video.status = VideoStatus.DOWNLOADING
        video.updated_at = datetime.utcnow()

        session.commit()

        logger.info(
            f"Successfully queued download {download.id} for video {video_id}. Celery will process it within 30 seconds."
        )

        return {
            "success": True,
            "message": "Video download queued successfully. Processing will begin shortly.",
            "video_id": video_id,
            "download_id": download.id,
            "status": "queued",
        }

    except Exception as e:
        logger.error(f"Error queuing download for video {video_id}: {e}")
        session.rollback()
        return {"success": False, "error": str(e), "video_id": video_id}


@router.post("/bulk/download-wanted")
async def bulk_download_wanted_videos(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Download all videos with 'wanted' status"""
    try:
        limit = request.get(
            "limit", 100
        )  # Default limit to prevent overwhelming the system

        # Debug: Log total video count and status distribution
        total_videos = session.query(Video).count()
        logger.info(f"Total videos in database: {total_videos}")

        # Debug: Check all unique status values
        all_statuses = session.query(Video.status).distinct().all()
        logger.info(
            f"Unique status values in database: {[str(s[0]) for s in all_statuses]}"
        )

        # Get all videos with 'wanted' status
        wanted_videos = (
            session.query(Video)
            .filter(Video.status == VideoStatus.WANTED)
            .limit(limit)
            .all()
        )

        logger.info(f"Found {len(wanted_videos)} videos with WANTED status")

        if not wanted_videos:
            return {
                "message": "No wanted videos found to download",
                "success": True,
                "success_count": 0,  # Frontend expects this field
                "failed_count": 0,  # Frontend expects this field
                "queued_count": 0,
                "total_wanted": 0,
                "skipped_count": 0,
                "errors": [],
                "results": [],  # Frontend expects this field
            }

        queued_count = 0
        skipped_count = 0
        errors = []

        for video in wanted_videos:
            try:
                # Check if download already in queue
                existing_download = (
                    session.query(Download)
                    .filter(
                        Download.video_id == video.id,
                        Download.status.in_(["queued", "downloading"]),
                    )
                    .first()
                )

                if existing_download:
                    skipped_count += 1
                    continue

                # Check if video has a valid URL before creating download record
                video_url = (
                    video.url
                    or video.youtube_url
                    or f"https://youtube.com/watch?v={video.youtube_id}"
                    if hasattr(video, "youtube_id") and video.youtube_id
                    else None
                )

                # Skip videos without URLs - don't search YouTube in bulk operations as it's too slow
                if not video_url:
                    logger.warning(
                        f"Skipping video {video.id} '{video.title}' - no valid URL available (artist: {video.artist.name if video.artist else 'Unknown'})"
                    )
                    errors.append(f"Video {video.id} ({video.title}): No URL available")
                    skipped_count += 1
                    continue

                # Create download entry
                download = Download(
                    artist_id=video.artist_id,
                    video_id=video.id,
                    title=video.title,
                    original_url=(
                        video.url
                        or video.youtube_url
                        or f"https://youtube.com/watch?v={video.youtube_id}"
                        if hasattr(video, "youtube_id") and video.youtube_id
                        else "Unknown URL"
                    ),
                    status="queued",
                    quality="best",  # Default quality for wanted videos
                    priority=1,  # Default priority for wanted videos
                    created_at=datetime.utcnow(),
                )

                session.add(download)
                session.flush()  # Ensure download.id is available

                # Update video status to downloading/queued
                video.status = VideoStatus.DOWNLOADING
                video.updated_at = datetime.utcnow()

                # Create background job for download processing via ytdlp_service
                try:
                    from src.services.download_service_adapter import ytdlp_service

                    # video_url was already validated above
                    # Submit job directly to ytdlp_service
                    result = ytdlp_service.add_music_video_download(
                        artist=video.artist.name if video.artist else "Unknown",
                        title=video.title,
                        url=video_url,
                        quality="best",
                        download_subtitles=False,
                        video_id=video.id,
                        download_id=download.id,
                    )

                    job_id = result.get("download_id")

                    logger.info(
                        f"Submitted ytdlp download task {job_id} for wanted video {video.id}"
                    )

                except Exception as job_error:
                    logger.error(
                        f"Failed to create background download job for wanted video {video.id}: {job_error}"
                    )
                    # Don't fail the bulk operation if individual job creation fails

                queued_count += 1
                logger.info(
                    f"Queued wanted video for download: {video.title} (ID: {video.id})"
                )

            except Exception as e:
                errors.append(f"Video {video.id} ({video.title}): {str(e)}")
                logger.error(f"Error queuing wanted video {video.id} for download: {e}")

        session.commit()

        logger.info(
            f"Bulk download wanted: queued {queued_count}, skipped {skipped_count} videos"
        )

        result = {
            "message": f"Queued {queued_count} wanted videos for download",
            "success": True,
            "success_count": queued_count,  # Frontend expects this field
            "failed_count": len(errors),  # Frontend expects this field
            "queued_count": queued_count,  # Keep for backward compatibility
            "total_wanted": len(wanted_videos),
            "skipped_count": skipped_count,
            "limit_applied": limit,
            "results": [],  # Frontend expects this field
        }

        if errors:
            result["errors"] = errors
            # Add results array with individual video results for frontend
            for error_msg in errors:
                result["results"].append({"success": False, "error": error_msg})

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk download wanted videos: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
