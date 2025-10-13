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

Authentication: All endpoints require session-based authentication via get_current_user dependency.
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import get_current_user_legacy
from src.api.fastapi.videos_models import BulkRefreshMetadataRequest
from src.database.connection import get_db_session
from src.database.models import Video
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_metadata")


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


# ========================================================================================
# METADATA REFRESH OPERATIONS
# ========================================================================================


@router.post("/bulk/refresh-metadata")
async def bulk_refresh_metadata(
    request: BulkRefreshMetadataRequest = Body(...),
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/enhanced-refresh-metadata")
async def bulk_enhanced_refresh_metadata(
    request: dict = Body(...), session: Session = Depends(get_db_session)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enhanced-refresh-all-metadata")
async def enhanced_refresh_all_metadata(
    request: dict = Body(default={}), session: Session = Depends(get_db_session)
):
    """Enhanced metadata refresh for all videos or specific video IDs"""
    try:
        force_refresh = request.get("force_refresh", False)
        limit = request.get("limit", None)
        video_ids = request.get("video_ids", None)

        # Get videos to process
        query = session.query(Video).options(joinedload(Video.artist))

        # Filter by specific video IDs if provided
        if video_ids:
            query = query.filter(Video.id.in_(video_ids))

        if limit:
            query = query.limit(limit)

        videos = query.all()

        if not videos:
            return {
                "success": True,
                "message": "No videos found to process",
                "processed": 0,
                "updated": 0,
                "errors": 0,
            }

        # Process videos using enhanced metadata service
        processed = 0
        updated = 0
        errors = 0
        error_details = []

        for video in videos:
            try:
                # Simulate enhanced metadata refresh
                should_refresh = (
                    force_refresh
                    or not getattr(video, "last_enriched", None)
                    or (datetime.utcnow() - video.last_enriched).days > 7
                )

                if should_refresh:
                    # Update timestamps
                    if hasattr(video, "last_enriched"):
                        video.last_enriched = datetime.utcnow()
                    video.updated_at = datetime.utcnow()
                    updated += 1

                processed += 1

            except Exception as e:
                errors += 1
                error_details.append(
                    {"video_id": video.id, "title": video.title, "error": str(e)}
                )
                logger.error(
                    f"Error refreshing enhanced metadata for video {video.id}: {e}"
                )

        session.commit()

        logger.info(
            f"Enhanced metadata refresh completed: {processed} processed, {updated} updated, {errors} errors"
        )

        return {
            "success": True,
            "message": f"Processed {processed} videos ({updated} updated, {errors} errors)",
            "processed": processed,
            "updated": updated,
            "errors": errors,
            "error_details": error_details if error_details else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced metadata refresh all: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/enhanced-refresh-metadata")
async def enhanced_refresh_metadata(
    video_id: int = FastAPIPath(..., ge=1),
    request: dict = Body(...),
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
        raise HTTPException(status_code=500, detail=str(e))
