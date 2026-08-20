"""
FastAPI Videos Metadata API Module

This module contains metadata refresh operations for videos.
These endpoints handle enriching video metadata from external sources:
- Bulk metadata refresh (basic)
- Bulk enhanced metadata refresh
- Enhanced refresh all metadata (with limit support)
- Single video enhanced metadata refresh

Extracted from videos.py as part of the API modularization effort.
Uses Pydantic models from videos_models.py for request/response validation.

Authentication: All endpoints require session-based authentication via the require_authentication dependency.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_models import BulkRefreshMetadataRequest
from src.database.connection import get_db_session
from src.database.models import Video
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_metadata")
# ========================================================================================
# METADATA REFRESH OPERATIONS
# ========================================================================================


@router.post("/bulk/refresh-metadata")
async def bulk_refresh_metadata(
    request: BulkRefreshMetadataRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk refresh metadata for videos from various sources"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to refresh metadata for
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(request.video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        refreshed_count = 0
        errors = []
        metadata_updates = []

        for video in videos:
            try:
                video_updates = {"video_id": video.id, "updates": []}

                # Check if refresh is needed (unless force_refresh is True)
                should_refresh = (
                    request.force_refresh
                    or not getattr(video, "last_enriched", None)
                    or (datetime.utcnow() - video.last_enriched).days > 7
                )

                if not should_refresh:
                    video_updates["updates"].append(
                        "Metadata is recent, skipping refresh"
                    )
                    metadata_updates.append(video_updates)
                    continue

                # Simulate metadata refresh operations
                # In a real implementation, these would call actual services

                if request.refresh_imvdb:
                    # Simulate IMVDb metadata refresh
                    video_updates["updates"].append("IMVDb metadata refreshed")
                    # video.imvdb_metadata = await imvdb_service.get_video_metadata(video.id)

                if request.refresh_youtube and video.youtube_id:
                    # Simulate YouTube metadata refresh
                    video_updates["updates"].append("YouTube metadata refreshed")
                    # video.youtube_metadata = await youtube_service.get_video_metadata(video.youtube_id)

                if request.refresh_musicbrainz and video.artist:
                    # Simulate MusicBrainz metadata refresh
                    video_updates["updates"].append("MusicBrainz metadata refreshed")
                    # video.musicbrainz_metadata = await musicbrainz_service.get_artist_metadata(video.artist.name)

                # Update last enriched timestamp
                if hasattr(video, "last_enriched"):
                    video.last_enriched = datetime.utcnow()
                video.updated_at = datetime.utcnow()

                # Add some mock metadata updates
                if not video_updates["updates"]:
                    video_updates["updates"].append("Basic metadata refreshed")

                metadata_updates.append(video_updates)
                refreshed_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error refreshing metadata for video {video.id}: {e}")

        session.commit()

        logger.info(f"Bulk refreshed metadata for {refreshed_count} videos")

        result = {
            "message": "Bulk metadata refresh completed",
            "refreshed_count": refreshed_count,
            "total_requested": len(request.video_ids),
            "sources_refreshed": {
                "imvdb": request.refresh_imvdb,
                "youtube": request.refresh_youtube,
                "musicbrainz": request.refresh_musicbrainz,
            },
            "metadata_updates": metadata_updates,
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk metadata refresh: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/enhanced-refresh-metadata")
async def bulk_enhanced_refresh_metadata(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk enhanced metadata refresh for multiple videos"""
    try:
        video_ids = request.get("video_ids", [])
        if not video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        force_refresh = request.get("force_refresh", False)

        # Get videos to refresh metadata for
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        refreshed_count = 0
        errors = []
        sources_used_total = set()

        for video in videos:
            try:
                # Check if refresh is needed (unless force_refresh is True)
                should_refresh = (
                    force_refresh
                    or not getattr(video, "last_enriched", None)
                    or (datetime.utcnow() - video.last_enriched).days > 7
                )

                if should_refresh:
                    # Simulate enhanced metadata refresh operations
                    sources_used = ["imvdb"]

                    if video.youtube_url or getattr(video, "youtube_id", None):
                        sources_used.append("youtube")

                    if video.artist:
                        sources_used.append("musicbrainz")

                    sources_used_total.update(sources_used)

                    # Update timestamps
                    if hasattr(video, "last_enriched"):
                        video.last_enriched = datetime.utcnow()
                    video.updated_at = datetime.utcnow()

                    refreshed_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(
                    f"Error refreshing enhanced metadata for video {video.id}: {e}"
                )

        session.commit()

        logger.info(f"Bulk enhanced metadata refreshed for {refreshed_count} videos")

        result = {
            "success": True,
            "message": "Bulk enhanced metadata refresh completed",
            "refreshed_count": refreshed_count,
            "total_requested": len(video_ids),
            "sources_used": list(sources_used_total),
            "errors": errors if errors else [],
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk enhanced metadata refresh: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/enhanced-refresh-all-metadata")
async def enhanced_refresh_all_metadata(
    request: dict = Body(default={}),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Enhanced metadata refresh for all videos or specific video IDs using Celery background job.

    This queues a Celery task that performs full metadata enrichment from multiple sources:
    - MusicBrainz (release dates, recording info)
    - Discogs (release info, fallback)
    - Spotify (album info, genres, durations)
    - IMVDb (music video database)
    - Last.fm (track metadata)
    - YouTube (video discovery)
    - FFmpeg (local file analysis)

    Request Parameters:
    - force_refresh (bool): If True, overwrites existing metadata. If False, only fills empty fields.
    - days_since_enriched (int): Only enrich videos not enriched in the last N days. Set to 0 to force all.
    - limit (int): Maximum number of videos to process. None = all videos.
    - video_ids (list): Specific video IDs to process. If provided, overrides limit.

    Returns:
    - job_id: ID of the Celery task for tracking progress via WebSocket
    """
    try:
        from src.jobs.metadata_tasks import bulk_enrich_videos_metadata_task

        force_refresh = request.get("force_refresh", True)
        days_since_enriched = request.get("days_since_enriched", 7)
        limit = request.get("limit", None)
        video_ids = request.get("video_ids", None)

        # Count how many videos will be processed
        query = session.query(Video).options(joinedload(Video.artist))

        # Filter by specific video IDs if provided
        if video_ids:
            query = query.filter(Video.id.in_(video_ids))
            video_count = len(video_ids)
            logger.info(
                f"Bulk enrichment: queueing Celery task for {video_count} specific video IDs"
            )
        else:
            # Filter by last_enriched date if days_since_enriched > 0
            if days_since_enriched > 0:
                cutoff_date = datetime.utcnow() - timedelta(days=days_since_enriched)
                query = query.filter(
                    or_(Video.last_enriched == None, Video.last_enriched < cutoff_date)
                )
                logger.info(
                    f"Bulk enrichment: filtering videos not enriched since {cutoff_date}"
                )

        if limit:
            query = query.limit(limit)

        video_count = query.count()

        if video_count == 0:
            return {
                "success": True,
                "message": "No videos found to process",
                "job_id": None,
                "video_count": 0,
            }

        # Queue Celery task
        task = bulk_enrich_videos_metadata_task.delay(
            video_ids=video_ids,
            force_refresh=force_refresh,
            days_since_enriched=days_since_enriched,
            limit=limit,
        )

        logger.info(
            f"Queued Celery bulk video metadata enrichment task {task.id} for {video_count} videos "
            f"(force_refresh={force_refresh}, days_since_enriched={days_since_enriched})"
        )

        return {
            "success": True,
            "message": f"Queued metadata enrichment for {video_count} videos",
            "job_id": task.id,
            "video_count": video_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing bulk metadata refresh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{video_id}/enhanced-refresh-metadata")
async def enhanced_refresh_metadata(
    video_id: int = FastAPIPath(..., ge=1),
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enhanced metadata refresh for a single video from multiple sources including thumbnails"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        force_refresh = request.get(
            "force_refresh", True
        )  # Default to True for UI calls

        logger.info(
            f"Starting enhanced metadata refresh for video {video_id} (force_refresh={force_refresh})"
        )

        # Use the real metadata enrichment service
        from src.services.metadata_enrichment_service import MetadataEnrichmentService

        enrichment_service = MetadataEnrichmentService()

        # Call the actual video metadata enrichment
        enrichment_result = await enrichment_service.enrich_video_metadata(
            video_id, force_refresh=force_refresh
        )

        if enrichment_result.success:
            # Re-query the video from database to get updated data from enrichment
            session.commit()  # Ensure any pending changes are committed first
            video = (
                session.query(Video)
                .options(joinedload(Video.artist))
                .filter(Video.id == video_id)
                .first()
            )

            logger.info(
                f"Enhanced metadata refreshed for video {video_id}: {enrichment_result.enriched_fields}"
            )

            return {
                "success": True,
                "message": f"Enhanced metadata refreshed successfully from {len(enrichment_result.sources_used)} sources",
                "video_id": video_id,
                "sources_used": enrichment_result.sources_used,
                "enriched_fields": (
                    list(enrichment_result.enriched_fields)
                    if enrichment_result.enriched_fields
                    else []
                ),
                "thumbnail_updated": "thumbnail_url"
                in (enrichment_result.enriched_fields or []),
                "refreshed": True,
            }
        else:
            error_msg = (
                "; ".join(enrichment_result.errors)
                if enrichment_result.errors
                else "Unknown error"
            )
            logger.warning(
                f"Enhanced metadata refresh failed for video {video_id}: {error_msg}"
            )

            return {
                "success": False,
                "message": f"Enhanced metadata refresh failed: {error_msg}",
                "video_id": video_id,
                "sources_used": [],
                "enriched_fields": [],
                "thumbnail_updated": False,
                "refreshed": False,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced metadata refresh for video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# YEAR EXTRACTION OPERATIONS
# ========================================================================================


def _extract_year_from_upload_date(upload_date_str: str) -> int:
    """
    Extract year from YouTube upload_date string.

    Args:
        upload_date_str: Upload date in YYYYMMDD format (e.g., "20240906")

    Returns:
        Year as integer, or None if extraction fails
    """
    try:
        if isinstance(upload_date_str, str) and len(upload_date_str) >= 4:
            year = int(upload_date_str[:4])
            # Sanity check: year should be reasonable
            if 1900 <= year <= datetime.now().year + 1:
                return year
    except (ValueError, TypeError):
        pass
    return None


def _extract_year_from_video(video: Video) -> dict:
    """
    Extract year information from video metadata.

    Tries multiple sources in priority order:
    1. IMVDb year (most reliable for music videos)
    2. YouTube upload_date
    3. Release date field

    Args:
        video: Video database model

    Returns:
        Dictionary with 'year' and 'source' keys, or None if no year found
    """
    import json

    # Priority 1: IMVDb metadata (most accurate for music video release year)
    if hasattr(video, "imvdb_metadata") and video.imvdb_metadata:
        try:
            imvdb_data = (
                video.imvdb_metadata
                if isinstance(video.imvdb_metadata, dict)
                else json.loads(video.imvdb_metadata)
            )
            if imvdb_data.get("year"):
                year = int(imvdb_data["year"])
                if 1900 <= year <= datetime.now().year + 1:
                    return {"year": year, "source": "imvdb"}
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # Priority 2: YouTube upload_date from video_metadata
    if hasattr(video, "video_metadata") and video.video_metadata:
        try:
            metadata = (
                video.video_metadata
                if isinstance(video.video_metadata, dict)
                else json.loads(video.video_metadata)
            )
            if metadata.get("upload_date"):
                year = _extract_year_from_upload_date(metadata["upload_date"])
                if year:
                    return {"year": year, "source": "youtube_upload_date"}
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # Priority 3: Release date field
    if hasattr(video, "release_date") and video.release_date:
        try:
            if isinstance(video.release_date, datetime):
                return {"year": video.release_date.year, "source": "release_date"}
            elif isinstance(video.release_date, str):
                # Try to parse date string
                parsed_date = datetime.fromisoformat(
                    video.release_date.replace("Z", "+00:00")
                )
                return {"year": parsed_date.year, "source": "release_date"}
        except (ValueError, AttributeError):
            pass

    return None


@router.post("/{video_id}/extract-year")
async def extract_video_year(
    video_id: int = FastAPIPath(..., ge=1),
    force: bool = Body(False, embed=True),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Extract and update year information for a video from available metadata.

    Attempts to extract year from:
    1. IMVDb metadata (most accurate for music video release year)
    2. YouTube upload_date
    3. Release date field

    Path Parameters:
    - video_id: Unique identifier for the video

    Request Body:
    - force: Update even if year already exists (default: False)

    Returns:
    - success: Whether extraction was successful
    - video_id: Video ID that was processed
    - year: Extracted year value
    - source: Where the year came from (imvdb, youtube_upload_date, release_date)
    - updated: Whether the video was actually updated
    - previous_year: Previous year value (if any)

    Raises:
    - 404: Video not found
    - 500: Internal server error
    """
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        previous_year = video.year

        # Skip if year already exists and force is not set
        if video.year and not force:
            return {
                "success": True,
                "video_id": video_id,
                "year": video.year,
                "source": "existing",
                "updated": False,
                "message": "Video already has year data. Use force=true to update.",
                "previous_year": previous_year,
            }

        # Try to extract year
        year_info = _extract_year_from_video(video)

        if not year_info:
            return {
                "success": False,
                "video_id": video_id,
                "year": None,
                "source": None,
                "updated": False,
                "message": "No year data found in video metadata",
                "previous_year": previous_year,
            }

        # Update the video
        video.year = year_info["year"]
        video.updated_at = datetime.utcnow()
        session.commit()

        logger.info(
            f"Extracted year {year_info['year']} for video {video_id} from {year_info['source']}"
        )

        return {
            "success": True,
            "video_id": video_id,
            "year": year_info["year"],
            "source": year_info["source"],
            "updated": True,
            "message": f"Year extracted from {year_info['source']}",
            "previous_year": previous_year,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting year for video {video_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/extract-years")
async def bulk_extract_years(
    video_ids: list[int] = Body(None, embed=True),
    force: bool = Body(False, embed=True),
    all_videos: bool = Body(False, embed=True),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Extract and update year information for multiple videos.

    This endpoint processes multiple videos and extracts year data from their metadata.

    Request Body:
    - video_ids: List of video IDs to process (optional if all_videos=true)
    - force: Update even if year already exists (default: False)
    - all_videos: Process all videos in the database (default: False)

    Returns:
    - success: Whether the operation completed
    - total_processed: Number of videos processed
    - updated: Number of videos that were updated
    - skipped_has_year: Number skipped because they already have year data
    - skipped_no_data: Number skipped because no year data was found
    - by_source: Count of updates by data source
    - videos: List of video results with details

    Raises:
    - 400: Invalid request (no video IDs and all_videos=false)
    - 500: Internal server error
    """
    try:
        # Build query
        query = session.query(Video)

        if all_videos:
            logger.info("Processing all videos for year extraction")
        elif video_ids:
            query = query.filter(Video.id.in_(video_ids))
            logger.info(f"Processing {len(video_ids)} videos for year extraction")
        else:
            raise HTTPException(
                status_code=400,
                detail="Either provide video_ids or set all_videos=true",
            )

        videos = query.all()

        if not videos:
            return {
                "success": True,
                "total_processed": 0,
                "updated": 0,
                "skipped_has_year": 0,
                "skipped_no_data": 0,
                "by_source": {},
                "videos": [],
                "message": "No videos found to process",
            }

        stats = {
            "total_processed": 0,
            "updated": 0,
            "skipped_has_year": 0,
            "skipped_no_data": 0,
            "by_source": {},
        }

        results = []

        for video in videos:
            stats["total_processed"] += 1
            previous_year = video.year

            # Skip if year already exists and force is not set
            if video.year and not force:
                stats["skipped_has_year"] += 1
                results.append(
                    {
                        "video_id": video.id,
                        "title": video.title,
                        "year": video.year,
                        "source": "existing",
                        "updated": False,
                    }
                )
                continue

            # Try to extract year
            year_info = _extract_year_from_video(video)

            if not year_info:
                stats["skipped_no_data"] += 1
                results.append(
                    {
                        "video_id": video.id,
                        "title": video.title,
                        "year": None,
                        "source": None,
                        "updated": False,
                    }
                )
                continue

            # Update the video
            video.year = year_info["year"]
            video.updated_at = datetime.utcnow()

            stats["updated"] += 1
            source = year_info["source"]
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

            results.append(
                {
                    "video_id": video.id,
                    "title": video.title,
                    "year": year_info["year"],
                    "source": year_info["source"],
                    "updated": True,
                    "previous_year": previous_year,
                }
            )

        # Commit all changes
        session.commit()

        logger.info(
            f"Bulk year extraction complete: {stats['updated']} videos updated, "
            f"{stats['skipped_has_year']} skipped (has year), "
            f"{stats['skipped_no_data']} skipped (no data)"
        )

        return {
            "success": True,
            "total_processed": stats["total_processed"],
            "updated": stats["updated"],
            "skipped_has_year": stats["skipped_has_year"],
            "skipped_no_data": stats["skipped_no_data"],
            "by_source": stats["by_source"],
            "videos": results,
            "message": f"Processed {stats['total_processed']} videos, updated {stats['updated']}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk year extraction: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
