"""
Video Batch Operations Service

Handles batch video operations including wanted video downloads and bulk processing.
Extracted from Flask API layer to provide framework-agnostic service functionality.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.video_batch")


def claim_video_for_download(video_id: int) -> bool:
    """Atomically claim a WANTED video for download by flipping its
    status to DOWNLOADING, but only if it is still WANTED (#329).

    Two independently-implemented "download all wanted videos" functions
    exist in this codebase (this module's download_all_wanted_videos_internal
    and videos_downloads.py's bulk_download_wanted_videos), reachable
    concurrently from a Celery worker and a FastAPI background thread --
    separate OS processes with no shared memory. Without an atomic claim,
    both can select and dispatch the same video, and whichever process's
    result writes last silently wins, regardless of which one was
    actually correct.

    Returns True if this caller won the claim (the video was WANTED and
    is now DOWNLOADING), False if it wasn't WANTED to begin with, doesn't
    exist, or a concurrent caller already claimed it. MariaDB/MySQL's
    row-level locking makes this correct under concurrency: two callers
    racing on the same row serialize at the database level, and the
    loser's WHERE clause re-evaluates against the now-committed
    DOWNLOADING value, matching zero rows.

    Must be called -- and its result checked -- before dispatching a
    download, never after.

    Deliberately does NOT use get_db() here: get_db() wraps a
    thread-local scoped_session, and both current callers
    (bulk_download_wanted_videos() and
    download_all_wanted_videos_internal()) already hold their own
    get_db() session open on the same thread when they call this. A
    nested get_db() call can silently resolve to that *same* underlying
    Session object, and this function's own commit()/close() would then
    tear down the caller's session mid-iteration. Using a dedicated
    engine connection/transaction instead makes this function immune to
    whatever session state its caller happens to hold (#329 final
    review).
    """
    from sqlalchemy import update

    import src.database.connection as db_connection

    try:
        if db_connection.db_manager is None:
            db_connection.init_db_standalone()
        engine = db_connection.db_manager.create_engine()
        with engine.begin() as conn:
            result = conn.execute(
                update(Video)
                .where(Video.id == video_id, Video.status == VideoStatus.WANTED)
                .values(status=VideoStatus.DOWNLOADING, updated_at=datetime.utcnow())
            )
            return result.rowcount == 1
    except Exception as e:
        logger.error(f"Failed to claim video {video_id} for download: {e}")
        return False


def claim_video_for_redownload(video_id: int) -> bool:
    """Atomically claim a video for (re)download from any status except
    DOWNLOADING itself (#377).

    Unlike claim_video_for_download() (WANTED-only, used by the two
    wanted-queue dispatchers from #329), this allows claiming from
    WANTED, MONITORED, FAILED, IGNORED, or DOWNLOADED -- any status
    except DOWNLOADING -- because none of this function's callers
    (the bulk-by-IDs and single-video manual download endpoints) are
    WANTED-only: they intentionally support retrying a FAILED video and,
    with force_redownload, re-downloading an already-DOWNLOADED one.
    Gating them on the WANTED-only claim would silently break those
    working use cases. The only thing this refuses is claiming a video
    that's already mid-download, which is exactly the #329-style race
    this exists to prevent.

    Returns True if this caller won the claim, False if the video
    doesn't exist, is already DOWNLOADING, or a concurrent caller
    already claimed it first.

    Deliberately does NOT use get_db() here, for the same reason as
    claim_video_for_download() -- see that function's docstring. Uses
    its own dedicated engine connection/transaction instead, immune to
    whatever get_db() session state its caller already holds open.
    """
    from sqlalchemy import update

    import src.database.connection as db_connection

    try:
        if db_connection.db_manager is None:
            db_connection.init_db_standalone()
        engine = db_connection.db_manager.create_engine()
        with engine.begin() as conn:
            result = conn.execute(
                update(Video)
                .where(Video.id == video_id, Video.status != VideoStatus.DOWNLOADING)
                .values(status=VideoStatus.DOWNLOADING, updated_at=datetime.utcnow())
            )
            return result.rowcount == 1
    except Exception as e:
        logger.error(f"Failed to claim video {video_id} for redownload: {e}")
        # Live-reported (2026-08-20): this call intermittently blocks for
        # the full innodb_lock_wait_timeout and fails with error 1205,
        # recurring in bursts across multiple unrelated videos. Direct
        # live investigation (manual reproduction, polling
        # information_schema.innodb_trx between failures) could never
        # catch the blocking transaction in the act -- by the time a
        # failure was noticed, the lock had already cleared. Capture
        # what else was active on the DB at the moment of THIS failure,
        # so the next occurrence leaves hard evidence instead of
        # requiring another live chase. Best-effort and diagnostic-only
        # -- must never raise past this function or change its return
        # value, and must not assume a MariaDB backend (information_
        # schema.innodb_trx doesn't exist on SQLite, used in tests).
        if "1205" in str(e) or "Lock wait timeout" in str(e):
            try:
                from sqlalchemy import text

                with engine.connect() as diag_conn:
                    trx_rows = diag_conn.execute(
                        text(
                            "SELECT trx_id, trx_state, trx_started, "
                            "trx_mysql_thread_id, trx_query "
                            "FROM information_schema.innodb_trx"
                        )
                    ).fetchall()
                    logger.error(
                        f"Lock-wait-timeout diagnostics for video {video_id}: "
                        f"{len(trx_rows)} active InnoDB transaction(s) at "
                        f"failure time: {trx_rows}"
                    )
            except Exception as diag_error:
                logger.error(
                    f"Could not gather lock-wait-timeout diagnostics for "
                    f"video {video_id}: {diag_error}"
                )
        return False


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


def resolve_video_url(video, session, timeout: int = 30) -> Optional[str]:
    """
    Helper function to resolve video URL using yt-dlp search

    Args:
        video: Video object from database
        session: Database session
        timeout: Max seconds to wait for the yt-dlp search subprocess,
            default 30

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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

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


def download_all_wanted_videos_internal(
    limit: int = 50, video_ids: Optional[List[int]] = None
) -> Dict:
    """
    Internal function to download all videos with WANTED status

    Args:
        limit: Maximum number of wanted videos to process (default: 50).
               Ignored when video_ids is provided.
        video_ids: Optional ordered list of video IDs to download. When provided,
                   only these videos are processed and their order is preserved
                   (used by scheduled_downloads_task to honour scheduling priority).

    Returns:
        dict: Results containing success status, counts, and individual results
    """
    try:
        results = []
        success_count = 0
        failed_count = 0
        skipped_count = 0
        wanted_video_ids = []

        # Import settings service for subtitle configuration
        from src.services.settings_service import settings

        # Read subtitle settings from database once for all downloads
        download_subtitles = settings.get_bool("download_subtitles", False)
        subtitle_languages = settings.get("subtitle_languages", "en,en-US")

        # Determine which videos to download
        with get_db() as session:
            if video_ids:
                # Priority-ordered IDs supplied by the scheduler — fetch in one query
                # then re-sort to preserve the caller's priority ordering.
                rows = (
                    session.query(Video.id, Video.title, Artist.name)
                    .join(Artist)
                    .filter(Video.id.in_(video_ids))
                    .filter(Video.status == VideoStatus.WANTED)
                    .all()
                )
                id_to_row = {r.id: r for r in rows}
                # Preserve the priority order supplied by the caller
                wanted_video_ids = [
                    (id_to_row[vid].id, id_to_row[vid].title, id_to_row[vid].name)
                    for vid in video_ids
                    if vid in id_to_row
                ]
            else:
                wanted_videos = (
                    session.query(Video.id, Video.title, Artist.name)
                    .join(Artist)
                    .filter(Video.status == VideoStatus.WANTED)
                    .limit(limit)
                    .all()
                )
                wanted_video_ids = [(v.id, v.title, v.name) for v in wanted_videos]

            if not wanted_video_ids:
                return {
                    "success": True,
                    "message": "No wanted videos found",
                    "success_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "results": [],
                }

        logger.info(f"Found {len(wanted_video_ids)} wanted videos to download")

        # Process each video individually to avoid session issues
        for video_id, video_title, artist_name in wanted_video_ids:
            claimed = False
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

                    # Atomically claim this video before dispatching (#329)
                    # -- bulk_download_wanted_videos() (the manual-trigger
                    # equivalent of this function) can run concurrently and
                    # select the same WANTED video; only one of them may
                    # win. A failed claim means another process already has
                    # it -- report as skipped, not failed, and move on.
                    if not claim_video_for_download(video_id):
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "skipped": True,
                                "error": "Already claimed by another download process",
                            }
                        )
                        skipped_count += 1
                        continue
                    claimed = True

                    # Import yt-dlp service
                    from src.services.download_service_adapter import ytdlp_service

                    # Queue download -- video.status is already DOWNLOADING,
                    # set and committed by claim_video_for_download() above.
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
                        # #329: the claim above already committed
                        # DOWNLOADING -- dispatch then failed (falsy
                        # result), so revert to WANTED here or this video
                        # is stuck at DOWNLOADING forever: invisible to
                        # every status == WANTED query, never retried by
                        # the next scheduled run. Matches the
                        # revert-on-dispatch-failure precedent in
                        # videos_downloads.py.
                        video.status = VideoStatus.WANTED
                        session.commit()
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
                if claimed:
                    # #329: the claim committed DOWNLOADING before this
                    # exception was raised -- the `with get_db() as
                    # session` block above has already rolled back and
                    # closed on the way out, so revert with a fresh
                    # session rather than reusing it. Same
                    # stuck-forever concern as the dispatch-failure
                    # branch above.
                    try:
                        with get_db() as revert_session:
                            revert_video = (
                                revert_session.query(Video)
                                .filter(Video.id == video_id)
                                .first()
                            )
                            if revert_video:
                                revert_video.status = VideoStatus.WANTED
                                revert_session.commit()
                    except Exception as revert_error:
                        logger.error(
                            f"Failed to revert video {video_id} to WANTED "
                            f"after dispatch exception: {revert_error}"
                        )
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
            "message": f"Processed {len(wanted_video_ids)} videos: {success_count} succeeded, {failed_count} failed, {skipped_count} skipped",
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Failed to download wanted videos: {e}")
        return {
            "success": False,
            "error": str(e),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
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
            # Treat NULL as True — pre-Scheduler-V2 artists have no value set
            # and should still be eligible for downloads
            if hasattr(Artist, "download_enabled"):
                from sqlalchemy import or_

                query = query.filter(
                    or_(
                        Artist.download_enabled == True,
                        Artist.download_enabled.is_(None),
                    )
                )

            # Order by priority (Scheduler V2 enhancement)
            if hasattr(Artist, "schedule_priority"):
                # Priority mapping: high=1, medium=2, low=3 for sorting
                priority_order = case(
                    (Artist.schedule_priority == "high", 1),
                    (Artist.schedule_priority == "medium", 2),
                    (Artist.schedule_priority == "low", 3),
                    else_=2,  # Default to medium priority
                )
                # MariaDB doesn't support NULLS LAST, use CASE for null handling
                from sqlalchemy import func

                query = query.order_by(
                    priority_order,
                    func.coalesce(
                        Artist.priority, 0
                    ).desc(),  # Higher priority artists first (null = 0)
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
