"""
FastAPI Videos Downloads API Module

This module contains all download-related operations for videos.
These endpoints handle video download management:
- Single video download (with multiple variants)
- Bulk video downloads
- Download wanted videos
- Debug download endpoints

Extracted from videos.py as part of the API modularization effort.
The resolve_video_url() helper below wraps
src.services.video_batch_service.resolve_video_url() (the real,
working implementation) rather than defining its own resolution
logic or importing from the parent module.

Authentication: All endpoints require session-based authentication via the require_authentication dependency.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_models import BulkDownloadRequest
from src.database.connection import get_db_session
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.video_batch_service import (
    claim_video_for_download,
)
from src.services.video_batch_service import (
    resolve_video_url as _resolve_video_url_sync,
)
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_downloads")


async def resolve_video_url(
    video: Video, session: Session, timeout: int = 30
) -> Optional[str]:
    """
    Resolve a video's download URL via yt-dlp search, off the event loop.

    #380.1: this used to import a same-named function from
    src.api.fastapi.videos, which does not define one -- every call
    raised ImportError. The real, working implementation lives in
    video_batch_service.resolve_video_url() (checks video.url, falls
    back to video.youtube_url, then does a live yt-dlp search as a
    last resort, persisting the result on success). It is synchronous
    (a blocking subprocess.run call), so it's run via asyncio.to_thread
    here rather than awaited directly -- awaiting a non-coroutine would
    raise a TypeError, and calling it bare would block this async
    handler's event loop for up to `timeout` seconds.

    Args:
        video: Video object
        session: Database session
        timeout: Max seconds to wait for the yt-dlp search subprocess,
            default 30. Callers resolving many videos in a loop (e.g.
            bulk_download_videos()) should pass a shorter value.

    Returns:
        str: Resolved URL or None
    """
    return await asyncio.to_thread(_resolve_video_url_sync, video, session, timeout)


# ========================================================================================
# DOWNLOAD OPERATIONS
# ========================================================================================

# bulk_download_videos() resolves URLs for potentially many videos in a
# single request, each via a live yt-dlp search subprocess (#379.3). A
# per-video timeout shorter than resolve_video_url()'s 30s default, plus
# an overall wall-clock budget for the whole batch, keeps one slow/stuck
# request from ballooning into a many-minutes-long request.
BULK_URL_RESOLUTION_TIMEOUT_SECONDS = 10
BULK_URL_RESOLUTION_BUDGET_SECONDS = 60


@router.post("/bulk/download")
async def bulk_download_videos(
    request: BulkDownloadRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
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
        failed_count = 0
        errors = []
        url_resolution_time_used = 0.0

        for video in videos:
            claimed = False
            original_status = None
            try:
                video_id = video.id  # Store ID before any operations
                # Skip if already downloaded
                if video.status == VideoStatus.DOWNLOADED:
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
                    if url_resolution_time_used >= BULK_URL_RESOLUTION_BUDGET_SECONDS:
                        errors.append(
                            f"Video {video_id}: Skipped URL resolution "
                            f"(bulk request's {BULK_URL_RESOLUTION_BUDGET_SECONDS}s "
                            f"resolution time budget exhausted)"
                        )
                        continue
                    resolution_start = time.monotonic()
                    resolved_url = await resolve_video_url(
                        video, session, timeout=BULK_URL_RESOLUTION_TIMEOUT_SECONDS
                    )
                    url_resolution_time_used += time.monotonic() - resolution_start
                    if not resolved_url:
                        errors.append(f"Video {video_id}: No valid URL found")
                        continue
                    video_url = resolved_url

                from src.services.video_batch_service import (
                    claim_video_for_redownload,
                )

                # Refresh before capturing. This does NOT by itself
                # guarantee a fresh read: with no isolation_level set,
                # MariaDB/InnoDB defaults to REPEATABLE READ, so a plain
                # SELECT inside an already-open transaction (true for the
                # FIRST video here) still returns that transaction's
                # original snapshot. For videos 2+, it's the PRIOR video's
                # commit (#377) that actually makes the read fresh. Real
                # correctness against a concurrent status change comes
                # from the atomic row-locked UPDATE inside the claim call
                # below, not from this refresh (#379).
                session.refresh(video, attribute_names=["status"])
                # Capture the real pre-claim status so a revert (below)
                # restores it exactly, rather than assuming WANTED -- the
                # claim below can succeed from FAILED, MONITORED, or
                # DOWNLOADED too (#377).
                original_status = video.status

                if not claim_video_for_redownload(video_id):
                    skipped_count += 1
                    continue
                claimed = True

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

                # Commit per-video, immediately after the flush above,
                # instead of once at the very end of the whole loop
                # (#377). Two reasons:
                #   1. The claim above already committed
                #      status=DOWNLOADING durably on its own connection.
                #      If this session's terminal commit lived at the end
                #      of the loop instead and *that* commit failed, every
                #      Download row staged across the entire batch would
                #      be discarded while every claim in the batch stayed
                #      durably committed -- stranding the whole batch at
                #      DOWNLOADING with zero Download rows.
                #   2. Narrows the lock hold time on this FK-referencing
                #      flush/commit to a single row, rather than holding
                #      it open across the whole batch concurrent with
                #      claims taking exclusive locks on separate
                #      connections from other requests (deadlock risk).
                session.commit()

                # Submit job to ytdlp_service. #379.6: revert on ANY
                # dispatch failure now -- both a raised exception and a
                # falsy/{"success": False} result -- not just leave the
                # video at DOWNLOADING and the Download row at "queued"
                # forever either way. #377 deliberately left this
                # unhandled, reasoning the Download row was enough of a
                # paper trail; on reflection a permanently-stuck
                # DOWNLOADING/"queued" pair with no explanation is the
                # same "stuck forever" problem #329 and #377 both exist
                # to close. Mirrors download_all_wanted_videos_internal()
                # (video_batch_service.py, #329) as closely as this
                # function's shape allows.
                dispatch_error_message = None
                result = None
                try:
                    from src.services.download_service_adapter import ytdlp_service

                    result = ytdlp_service.add_music_video_download(
                        artist=video.artist.name if video.artist else "Unknown Artist",
                        title=video.title,
                        url=video_url,
                        quality="best",
                        download_subtitles=False,
                        video_id=video_id,
                        download_id=download.id,
                    )
                except Exception as download_error:
                    dispatch_error_message = str(download_error)
                    logger.error(
                        f"Failed to submit download task for video {video_id}: {download_error}"
                    )

                if result and result.get("success"):
                    logger.info(
                        f"✅ Submitted bulk download job {result.get('id')} for video {video_id}"
                    )
                    queued_count += 1
                else:
                    if dispatch_error_message is None:
                        dispatch_error_message = (
                            result.get("error", "Unknown dispatch error")
                            if result
                            else "Unknown dispatch error"
                        )
                    # This assignment only emits an UPDATE because the
                    # earlier session.commit() above expired `video`
                    # (expire_on_commit=True, the sessionmaker default in
                    # src/database/connection.py) -- it re-sets a value
                    # the attribute would otherwise already hold. If that
                    # default ever changes, this write silently no-ops,
                    # stranding the video at DOWNLOADING.
                    video.status = original_status
                    download.status = "failed"
                    download.error_message = dispatch_error_message
                    session.commit()
                    errors.append(f"Video {video_id}: {dispatch_error_message}")
                    failed_count += 1
                    logger.error(
                        f"Dispatch failed for video {video_id}, reverted to "
                        f"{original_status}: {dispatch_error_message}"
                    )

            except Exception as e:
                video_id = getattr(video, "id", "unknown")  # Safe ID retrieval
                errors.append(f"Video {video_id}: {str(e)}")
                logger.error(f"Error queuing download for video {video_id}: {e}")
                # Roll back this request's shared session before moving on
                # to the next video in the loop. Unlike
                # download_all_wanted_videos_internal()'s precedent (which
                # opens a brand-new get_db() session per iteration, so a
                # failure there can't affect the next video), this endpoint
                # loops over one FastAPI-injected session shared across the
                # whole batch. A failed flush/commit above leaves that
                # shared session in a pending-rollback state; without this
                # rollback, every subsequent iteration's session.query/add
                # would raise PendingRollbackError -- the same
                # whole-batch-lost failure mode Finding 1 closes for
                # video_discovery_service.py, just reachable here too.
                try:
                    session.rollback()
                except Exception:
                    pass
                if claimed and original_status is not None:
                    # The claim above already committed DOWNLOADING
                    # durably on its own connection before whatever raised
                    # here. Revert it using a *fresh* session, not this
                    # request's own `session` -- it may be in a broken
                    # transaction state after whatever raised (e.g. a
                    # flush/commit failure), mirroring
                    # download_all_wanted_videos_internal()'s
                    # revert-via-fresh-session pattern (#329/#377). Without
                    # this, the video is stuck at DOWNLOADING forever:
                    # invisible to every status == WANTED query, never
                    # retried by any subsequent run.
                    try:
                        from src.database.connection import get_db

                        with get_db() as revert_session:
                            revert_video = (
                                revert_session.query(Video)
                                .filter(Video.id == video_id)
                                .first()
                            )
                            if revert_video:
                                revert_video.status = original_status
                                revert_session.commit()
                    except Exception as revert_error:
                        logger.error(
                            f"Failed to revert video {video_id} to "
                            f"{original_status} after bulk download "
                            f"exception: {revert_error}"
                        )

        logger.info(
            f"Bulk queued {queued_count} downloads, skipped {skipped_count}, "
            f"failed {failed_count}"
        )

        result = {
            "message": "Bulk download completed",
            "queued_count": queued_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{video_id}/download")
async def queue_video_download(
    video_id: int = FastAPIPath(..., ge=1),
    request: Dict[str, Any] = Body(default={}),
    current_user: dict = Depends(require_authentication),
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

        # Claim the video for (re)download now that the URL has been
        # resolved and the Download row is staged. Claiming any earlier
        # (e.g. before URL resolution) risks permanently stranding the
        # video in DOWNLOADING if resolution then fails, since the claim
        # commits its own independent transaction immediately (#377).
        original_status = video.status

        from src.services.video_batch_service import claim_video_for_redownload

        if not claim_video_for_redownload(video_id):
            return {
                "message": "Video is currently downloading",
                "video_id": video_id,
                "download_id": None,
            }

        # Submit download to unified service via ytdlp_service adapter
        try:
            # Persist the staged Download row now that the claim has
            # succeeded. This commit lives inside this try block (not
            # before it) so that if it raises -- lock timeout, transient
            # DB error, constraint violation -- the except handler below
            # still reverts video.status back to original_status instead
            # of leaving the video permanently stranded at DOWNLOADING,
            # since the claim already committed that write durably on its
            # own separate connection (#377).
            session.commit()

            from src.services.download_service_adapter import ytdlp_service
            from src.services.settings_service import settings

            # Get subtitle settings
            download_subtitles = settings.get_bool("download_subtitles", False)
            subtitle_languages = settings.get("subtitle_languages", "en,en-US")

            # Get video URL
            video_url = (
                video.url
                or video.youtube_url
                or f"https://youtube.com/watch?v={video.youtube_id}"
                if hasattr(video, "youtube_id") and video.youtube_id
                else None
            )

            if not video_url:
                raise ValueError("No valid URL found for video")

            # Submit to unified download service
            result = ytdlp_service.add_music_video_download(
                artist=video.artist.name if video.artist else "Unknown Artist",
                title=video.title,
                url=video_url,
                quality="best",
                download_subtitles=download_subtitles,
                subtitle_languages=subtitle_languages,
                video_id=video_id,
                download_id=download.id,
            )

            logger.info(
                f"Submitted download to unified service for video {video_id}: {result}"
            )

        except Exception as download_error:
            logger.error(
                f"Failed to submit download to unified service for video {video_id}: {download_error}"
            )
            # Revert to the video's real pre-claim status, not a hardcoded
            # WANTED -- claim_video_for_redownload() can claim from FAILED,
            # MONITORED, or DOWNLOADED too (#377), and blindly reverting a
            # retried FAILED video to WANTED would silently enroll it in the
            # auto-download queue.
            video.status = original_status
            session.commit()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start download: {str(download_error)}",
            )

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{video_id}/download-debug")
async def queue_video_download_debug(
    video_id: int = FastAPIPath(..., ge=1),
    request: Dict[str, Any] = Body(default={}),
    current_user: dict = Depends(require_authentication),
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
    current_user: dict = Depends(require_authentication),
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

        # Claim the video for (re)download now that the YouTube URL has
        # been confirmed and the Download row is staged. Claiming any
        # earlier (e.g. before the URL-availability check) risks
        # permanently stranding the video in DOWNLOADING if that check
        # then fails, since the claim commits its own independent
        # transaction immediately (#377).
        original_status = video.status

        from src.services.video_batch_service import claim_video_for_redownload

        if not claim_video_for_redownload(video_id):
            return {
                "success": True,
                "message": "Video is currently downloading",
                "video_id": video_id,
                "status": "already_downloading",
            }

        # Submit download to unified service via ytdlp_service adapter
        try:
            # Persist the staged Download row now that the claim has
            # succeeded. This commit lives inside this try block (not
            # before it) so that if it raises -- lock timeout, transient
            # DB error, constraint violation -- the except handler below
            # still reverts video.status back to original_status instead
            # of leaving the video permanently stranded at DOWNLOADING,
            # since the claim already committed that write durably on its
            # own separate connection (#377).
            session.commit()

            from src.services.download_service_adapter import ytdlp_service

            # Submit to unified download service
            result = ytdlp_service.add_music_video_download(
                artist=artist.name,
                title=video.title,
                url=youtube_url,
                quality="best",
                download_subtitles=download_subtitles,
                subtitle_languages=subtitle_languages,
                video_id=video_id,
                download_id=download.id,
            )

            logger.info(
                f"Successfully submitted download {download.id} for video {video_id} to unified service: {result}"
            )

            return {
                "success": True,
                "message": "Video download started successfully.",
                "video_id": video_id,
                "download_id": download.id,
                "status": "downloading",
            }

        except Exception as download_error:
            logger.error(
                f"Failed to submit download to unified service for video {video_id}: {download_error}"
            )
            # Revert to the video's real pre-claim status, not a hardcoded
            # WANTED -- claim_video_for_redownload() can claim from FAILED,
            # MONITORED, or DOWNLOADED too (#377), and blindly reverting a
            # retried FAILED video to WANTED would silently enroll it in the
            # auto-download queue.
            video.status = original_status
            session.commit()
            return {
                "success": False,
                "error": f"Failed to start download: {str(download_error)}",
                "video_id": video_id,
            }

    except Exception as e:
        logger.error(f"Error queuing download for video {video_id}: {e}")
        session.rollback()
        return {"success": False, "error": str(e), "video_id": video_id}


@router.post("/bulk/download-wanted")
async def bulk_download_wanted_videos(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
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

                # Atomically claim this video before dispatching (#329) --
                # download_all_wanted_videos_internal() (the Celery-side
                # equivalent of this function) can run concurrently and
                # select the same WANTED video; only one of them may win.
                # A failed claim means another process already has it --
                # a normal, healthy skip, not an error.
                if not claim_video_for_download(video.id):
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

                # video.status is already DOWNLOADING, committed by
                # claim_video_for_download() above. We never reassign
                # video.status anywhere in this loop after the claim, so
                # SQLAlchemy's dirty-tracking emits no UPDATE for it at
                # this function's final session.commit() -- the claim
                # can't be stomped. (A session.refresh() here would not
                # even see the post-claim value under MariaDB's default
                # REPEATABLE READ isolation, since this outer session's
                # snapshot predates the claim -- confirmed during final
                # review, not worth the round-trip either way.)

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
        raise HTTPException(status_code=500, detail="Internal server error")
