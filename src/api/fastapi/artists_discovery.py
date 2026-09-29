"""
FastAPI Artists Discovery API - Artist and Video Discovery Operations
Extracted from artists.py for better code organization

This module contains endpoints for:
- Video discovery for artists
- Auto-processing operations
"""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.database.connection import get_db_session
from src.database.models import Artist, Video
from src.services.artist_auto_processing_service import artist_auto_processing_service
from src.services.youtube_search_service import youtube_search_service
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

router = APIRouter(
    prefix="",
    tags=["artists-discovery"],
    responses={
        404: {"description": "Artist not found"},
        422: {"description": "Validation error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.artists_discovery")
# ========================================================================================
# UTILITY FUNCTIONS
# ========================================================================================


async def ensure_artist_folder_path(artist: Artist, session: Session) -> str:
    """
    Ensure artist has a folder_path set. If missing, generate one.

    This addresses Issue #16 where artists (especially from YouTube imports)
    may not have folder paths set.
    """
    if not artist.folder_path or artist.folder_path.strip() == "":
        artist.folder_path = FilenameCleanup.sanitize_folder_name(artist.name)
        logger.info(
            f"Generated missing folder_path for artist '{artist.name}': '{artist.folder_path}'"
        )

        try:
            session.commit()
            logger.info(f"Saved folder_path to database for artist '{artist.name}'")
        except Exception as e:
            logger.error(f"Failed to save folder_path for artist '{artist.name}': {e}")
            session.rollback()

    return artist.folder_path


# ========================================================================================
# VIDEO DISCOVERY OPERATIONS
# ========================================================================================


@router.post("/{artist_id}/videos/discover")
async def discover_artist_videos(
    artist_id: int = FastAPIPath(..., ge=1),
    request: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enhanced video discovery with filtering, sorting, and bulk operations"""
    try:
        # Get the artist
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Get enhanced discovery options from request
        limit = min(int(request.get("limit", 50)), 200)  # Increased max limit
        auto_import = request.get("auto_import", False)

        # New filtering options
        filter_options = request.get("filters", {})
        year_from = filter_options.get("year_from")
        year_to = filter_options.get("year_to")
        include_existing = filter_options.get("include_existing", True)
        directors_filter = filter_options.get("directors", [])

        # Sorting options
        sort_by = request.get("sort_by", "year")  # year, title, directors
        sort_order = request.get("sort_order", "desc")  # desc, asc

        # Extract artist data for use outside session
        artist_name = artist.name

        async def search_youtube():
            youtube_videos = []
            youtube_error = None
            try:
                logger.info(f"Searching YouTube for videos by {artist_name}")

                # Search YouTube for music videos by this artist
                youtube_results = await asyncio.to_thread(
                    youtube_search_service.search_artist_videos, artist_name, limit
                )

                # Check if YouTube API returned an error
                if youtube_results and youtube_results.get("error"):
                    youtube_error = youtube_results.get("error")
                    logger.error(
                        f"YouTube API error for {artist_name}: {youtube_error}"
                    )
                elif youtube_results and youtube_results.get("videos"):
                    yt_video_list = youtube_results["videos"]
                    logger.info(
                        f"Found {len(yt_video_list)} videos from YouTube for {artist_name}"
                    )

                    # Convert YouTube results to our standard format
                    for yt_video in yt_video_list:
                        youtube_id = yt_video.get("youtube_id")
                        youtube_video = {
                            "id": youtube_id,
                            "youtube_id": youtube_id,  # Frontend expects this field
                            "title": yt_video.get("title", "Unknown"),
                            "song_title": yt_video.get("title", "Unknown"),
                            "url": f"https://youtube.com/watch?v={youtube_id}",
                            "youtube_url": f"https://youtube.com/watch?v={youtube_id}",
                            "artist": {"name": artist_name},
                            "year": yt_video.get("upload_year"),
                            "duration": yt_video.get("duration"),
                            "image_url": yt_video.get("thumbnail_url"),
                            "view_count": yt_video.get("view_count"),
                            "channel": yt_video.get("channel_title"),
                            "source": "youtube",
                        }
                        youtube_videos.append(youtube_video)

                    logger.info(
                        f"Converted {len(youtube_videos)} YouTube videos to standard format"
                    )
                else:
                    logger.warning(f"No YouTube results found for {artist_name}")

            except Exception as e:
                youtube_error = str(e)
                logger.error(
                    f"YouTube video search failed for {artist_name}: {e}",
                    exc_info=True,
                )
            return youtube_videos, youtube_error

        logger.info(f"Starting YouTube search for {artist_name}")
        all_discovered_videos, youtube_error = await search_youtube()
        logger.info(f"Total discovered videos: {len(all_discovered_videos)}")

        # Get existing videos from database
        existing_videos = []
        try:
            db_videos = session.query(Video).filter(Video.artist_id == artist_id).all()
            existing_videos = [
                {"id": v.id, "title": v.title, "url": v.youtube_url} for v in db_videos
            ]
            logger.info(
                f"Found {len(existing_videos)} existing videos for {artist_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to get existing videos for {artist_name}: {e}")

        # Process and filter discovered videos
        discovered_videos = []
        stats = {
            "total_discovered": len(all_discovered_videos),
            "total_existing": len(existing_videos),
            "youtube_results": len(all_discovered_videos),
            "youtube_error": youtube_error,  # Include error for debugging
            "with_thumbnails": 0,
            "high_quality": 0,
            "available_for_import": 0,
        }

        # Note: Discovery shows only external (YouTube) results, not database videos
        # Database videos are used only for existence checking and filtering

        # Process all discovered videos
        logger.info(
            f"Processing {len(all_discovered_videos)} discovered videos for enrichment"
        )
        for video in all_discovered_videos:
            # Check if video already exists
            video_exists = any(
                existing_video.get("url") == video.get("url")
                or existing_video.get("title").lower() == video.get("title", "").lower()
                for existing_video in existing_videos
            )

            # Skip videos that already exist in database (discovery shows only new videos)
            if video_exists:
                continue

            # Apply year filtering
            video_year = video.get("year")
            if year_from and video_year and int(video_year) < int(year_from):
                continue
            if year_to and video_year and int(video_year) > int(year_to):
                continue

            # Apply directors filtering
            if directors_filter:
                video_directors = video.get("directors", [])
                if not any(
                    director in video_directors for director in directors_filter
                ):
                    continue

            youtube_id = video.get("youtube_id")
            logger.debug(
                f"Processing video: {video.get('song_title', video.get('title', 'Unknown'))} | Has youtube_id: {youtube_id}"
            )

            # Enrich video data - normalize field names for frontend compatibility
            enriched_video = {
                **video,
                "title": video.get("song_title")
                or video.get("title", "Unknown"),  # Normalize title field
                "song_title": video.get(
                    "song_title", "Unknown"
                ),  # Keep original for compatibility
                "artist_name": artist_name,  # Add artist name for display
                "exists_in_library": video_exists,
                "already_exists": video_exists,  # Frontend compatibility
                "imported": False,  # New videos are not imported yet
                "youtube_id": youtube_id,  # Frontend expects this field
                "can_import": not video_exists
                and bool(video.get("url") or video.get("youtube_url")),
                "thumbnail_available": bool(
                    video.get("image_url") or video.get("image")
                ),
                "thumbnail_url": video.get("image_url")
                or (
                    video.get("image", {}).get("o")
                    if isinstance(video.get("image"), dict)
                    else None
                ),
                "quality_indicator": video.get("quality", "unknown"),
                "source": "youtube",
            }

            discovered_videos.append(enriched_video)

            # Update stats
            if enriched_video["thumbnail_available"]:
                stats["with_thumbnails"] += 1
            if enriched_video["can_import"]:
                stats["available_for_import"] += 1
            if video.get("quality") in ["hd", "high"]:
                stats["high_quality"] += 1

        # Sort results
        if sort_by == "year":
            discovered_videos.sort(
                key=lambda x: int(x.get("year", 0) or 0), reverse=(sort_order == "desc")
            )
        elif sort_by == "title":
            discovered_videos.sort(
                key=lambda x: (x.get("song_title") or x.get("title", "")).lower(),
                reverse=(sort_order == "desc"),
            )

        logger.info(
            f"Video discovery completed for {artist_name}: {len(discovered_videos)} videos after filtering"
        )

        return {
            "success": True,
            "artist_id": artist_id,
            "artist_name": artist_name,
            "discovered_videos": discovered_videos,
            "stats": stats,
            "filters_applied": filter_options,
            "sort_config": {"sort_by": sort_by, "sort_order": sort_order},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering videos for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Video discovery failed: {str(e)}")


# ========================================================================================
# AUTO-PROCESSING OPERATIONS
# ========================================================================================


@router.post("/{artist_id}/auto-process")
async def manually_process_artist(
    artist_id: int,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Manually run auto-processing (auto-match, metadata enrichment, thumbnails) for an existing artist"""
    try:
        # Get the artist
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail=f"Artist {artist_id} not found")

        logger.info(
            f"Manually running auto-processing for artist {artist.name} (ID: {artist_id})"
        )

        # Phase 1: Run synchronous auto-match (fast operation)
        from src.services.artist_auto_processing_service import (
            ArtistAutoProcessingService,
        )

        auto_match_results = ArtistAutoProcessingService._run_auto_match(
            artist.id, artist.name, session
        )

        # Commit auto-match results
        session.commit()

        logger.info(
            f"Auto-match completed for {artist.name}: {auto_match_results['match_count']} services matched"
        )

        # Phase 2: Dispatch async tasks (metadata enrichment, thumbnails)
        from src.jobs.metadata_tasks import enrich_artist_metadata_task

        task = enrich_artist_metadata_task.delay(
            artist_id=artist_id, force_refresh=True
        )

        logger.info(
            f"Manual auto-processing completed for {artist.name} - metadata enrichment task {task.id} queued"
        )

        return {
            "success": True,
            "artist_id": artist_id,
            "artist_name": artist.name,
            "auto_match": auto_match_results,
            "metadata_task_id": task.id,
            "message": f"Auto-match completed, metadata enrichment queued for {artist.name}",
        }

    except Exception as e:
        logger.error(f"Error manually processing artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-auto-process")
async def bulk_auto_process_artists(
    force_refresh: bool = False,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Run auto-processing for all artists that are missing metadata or thumbnails"""
    try:
        # Find artists that need auto-processing
        if force_refresh:
            # Process all artists if force refresh is requested
            artists_to_process = session.query(Artist).all()
            logger.info(
                f"Force refresh requested - processing all {len(artists_to_process)} artists"
            )
        else:
            # Find artists missing critical data (no external service IDs, no metadata, no thumbnails)
            artists_to_process = (
                session.query(Artist)
                .filter(
                    and_(
                        or_(
                            Artist.spotify_id.is_(None),
                            Artist.lastfm_name.is_(None),
                            Artist.musicbrainz_id.is_(None),
                            Artist.biography.is_(None),
                            Artist.thumbnail_url.is_(None),
                        )
                    )
                )
                .all()
            )
            logger.info(
                f"Found {len(artists_to_process)} artists needing auto-processing"
            )

        if not artists_to_process:
            return {
                "success": True,
                "processed_count": 0,
                "message": "No artists need auto-processing",
            }

        processed_count = 0
        success_count = 0
        error_count = 0
        results = []

        # Import dependencies
        from src.jobs.metadata_tasks import enrich_artist_metadata_task
        from src.services.artist_auto_processing_service import (
            ArtistAutoProcessingService,
        )

        # Process each artist
        for artist in artists_to_process:
            try:
                logger.info(f"Auto-processing artist: {artist.name} (ID: {artist.id})")

                # Phase 1: Run synchronous auto-match (fast)
                auto_match_results = ArtistAutoProcessingService._run_auto_match(
                    artist.id, artist.name, session
                )

                # Commit after auto-match
                session.commit()

                # Phase 2: Queue async metadata enrichment task
                task = enrich_artist_metadata_task.delay(
                    artist_id=artist.id, force_refresh=force_refresh
                )

                processed_count += 1
                success_count += 1

                results.append(
                    {
                        "artist_id": artist.id,
                        "artist_name": artist.name,
                        "success": True,
                        "auto_match_count": auto_match_results.get("match_count", 0),
                        "metadata_task_id": task.id,
                        "metadata_queued": True,
                    }
                )

                logger.info(
                    f"Queued metadata enrichment task {task.id} for {artist.name}"
                )

            except Exception as e:
                error_count += 1
                logger.error(
                    f"Error processing artist {artist.name} (ID: {artist.id}): {e}"
                )
                results.append(
                    {
                        "artist_id": artist.id,
                        "artist_name": artist.name,
                        "success": False,
                        "error": str(e),
                    }
                )

        logger.info(
            f"Bulk auto-processing completed: {processed_count} processed, {success_count} successful, {error_count} errors"
        )

        return {
            "success": True,
            "processed_count": processed_count,
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
            "message": f"Processed {processed_count} artists ({success_count} successful, {error_count} errors)",
        }

    except Exception as e:
        logger.error(f"Error in bulk auto-processing: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
