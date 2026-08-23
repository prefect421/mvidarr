"""
FastAPI Artists API - Bulk Operations
Extracted from artists.py for better code organization

This module contains all bulk operation endpoints for the Artists API:
- Bulk delete artists
- Bulk edit artists
- Cleanup zero-video artists
- Get detailed artist information
- Get artist navigation (prev/next)
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.api.fastapi.artists_models import (
    BulkDeleteRequest,
    BulkEditRequest,
    BulkMonitoringRequest,
    MergeArtistsRequest,
    RenameCommandRequest,
    RetagCommandRequest,
)
from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.database.connection import get_db_session
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

# ========================================================================================
# ROUTER SETUP
# ========================================================================================

router = APIRouter(
    prefix="",
    tags=["artists-bulk"],
    responses={
        404: {"description": "Artist not found"},
        422: {"description": "Validation error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.artists_bulk")
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
        from src.utils.filename_cleanup import FilenameCleanup

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
# BULK OPERATIONS
# ========================================================================================


@router.post("/bulk/delete")
async def bulk_delete_artists(
    request: BulkDeleteRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Delete multiple artists with optional video deletion"""
    try:
        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Get artists to delete
        artists = session.query(Artist).filter(Artist.id.in_(request.artist_ids)).all()

        if not artists:
            raise HTTPException(status_code=404, detail="No artists found")

        deleted_count = 0
        videos_affected = 0
        errors = []

        for artist in artists:
            try:
                artist_id = artist.id  # Store ID before delete operation
                artist_name = artist.name

                # Handle associated videos
                if request.delete_videos:
                    # Delete all videos by this artist
                    videos = (
                        session.query(Video).filter(Video.artist_id == artist_id).all()
                    )
                    video_count = len(videos)

                    for video in videos:
                        # Delete video files if they exist
                        if video.local_path and Path(video.local_path).exists():
                            try:
                                Path(video.local_path).unlink()
                            except Exception as e:
                                logger.warning(
                                    f"Failed to delete video file {video.local_path}: {e}"
                                )

                    # Delete video records
                    session.query(Video).filter(Video.artist_id == artist_id).delete()
                    videos_affected += video_count

                else:
                    # Just unlink videos from artist (set artist_id to None)
                    video_count = (
                        session.query(Video)
                        .filter(Video.artist_id == artist_id)
                        .count()
                    )
                    session.query(Video).filter(Video.artist_id == artist_id).update(
                        {"artist_id": None}
                    )
                    videos_affected += video_count

                # Delete artist
                session.delete(artist)
                deleted_count += 1

                logger.info(f"Bulk deleted artist: {artist_name} (ID: {artist_id})")

            except Exception as e:
                artist_id = getattr(artist, "id", "unknown")  # Safe ID retrieval
                errors.append(f"Artist {artist_id}: {str(e)}")
                logger.error(f"Error deleting artist {artist_id}: {e}")

        session.commit()

        logger.info(
            f"Bulk deleted {deleted_count} artists, {videos_affected} videos affected"
        )

        result = {
            "message": f"Bulk delete completed",
            "deleted_count": deleted_count,
            "videos_affected": videos_affected,
            "videos_deleted": request.delete_videos,
            "total_requested": len(request.artist_ids),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-edit")
async def bulk_edit_artists(
    request: BulkEditRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update multiple artists with the same changes"""
    try:
        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        if not request.updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        # Validate update fields
        allowed_fields = {
            "sort_name",
            "folder_path",
            "biography",
            "formed_year",
            "location",
            "website",
            "wikipedia_url",
            "musicbrainz_id",
            "spotify_id",
            "monitored",
            "auto_download",
        }

        invalid_fields = set(request.updates.keys()) - allowed_fields
        if invalid_fields:
            raise HTTPException(
                status_code=400, detail=f"Invalid update fields: {list(invalid_fields)}"
            )

        # Prepare update data
        update_data = dict(request.updates)
        update_data["updated_at"] = datetime.utcnow()

        # Perform bulk update
        updated_count = (
            session.query(Artist)
            .filter(Artist.id.in_(request.artist_ids))
            .update(update_data, synchronize_session=False)
        )

        session.commit()

        logger.info(
            f"Bulk updated {updated_count} artists with changes: {request.updates}"
        )

        return {
            "message": f"Bulk edit completed",
            "updated_count": updated_count,
            "updates_applied": request.updates,
            "total_requested": len(request.artist_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk edit: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-validate-metadata")
async def bulk_validate_metadata(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Validate metadata for multiple artists and identify issues"""
    try:
        artist_ids = request.get("artist_ids", [])
        if not artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Get artists
        artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()

        if not artists:
            raise HTTPException(status_code=404, detail="No artists found")

        validation_results = []
        issues_summary = {
            "total_artists": len(artists),
            "artists_with_issues": 0,
            "missing_imvdb": 0,
            "missing_thumbnail": 0,
            "missing_folder_path": 0,
            "zero_videos": 0,
        }

        for artist in artists:
            issues = []
            has_issues = False

            # Check for IMVDb ID
            if not artist.imvdb_id:
                issues.append("No IMVDb ID linked")
                issues_summary["missing_imvdb"] += 1
                has_issues = True

            # Check for thumbnail
            if not artist.thumbnail_path and not artist.thumbnail_url:
                issues.append("No thumbnail available")
                issues_summary["missing_thumbnail"] += 1
                has_issues = True

            # Check for folder path
            if not artist.folder_path or artist.folder_path.strip() == "":
                issues.append("No folder path set")
                issues_summary["missing_folder_path"] += 1
                has_issues = True

            # Check video count
            video_count = (
                session.query(Video).filter(Video.artist_id == artist.id).count()
            )
            if video_count == 0:
                issues.append("No videos")
                issues_summary["zero_videos"] += 1
                has_issues = True

            if has_issues:
                issues_summary["artists_with_issues"] += 1

            validation_results.append(
                {
                    "artist_id": artist.id,
                    "artist_name": artist.name,
                    "has_issues": has_issues,
                    "issues": issues,
                    "video_count": video_count,
                    "has_imvdb": bool(artist.imvdb_id),
                    "has_thumbnail": bool(
                        artist.thumbnail_path or artist.thumbnail_url
                    ),
                    "has_folder_path": bool(artist.folder_path),
                }
            )

        logger.info(
            f"Validated {len(artists)} artists: {issues_summary['artists_with_issues']} with issues"
        )

        return {
            "success": True,
            "message": f"Validated {len(artists)} artists",
            "summary": issues_summary,
            "results": validation_results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating artist metadata: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-refresh-metadata")
async def bulk_refresh_metadata(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Refresh metadata for multiple artists from external services (IMVDb, Spotify, etc.)"""
    try:
        artist_ids = request.get("artist_ids", [])
        force_refresh = request.get("force_refresh", False)

        if not artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Get artists to verify they exist
        artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()

        if not artists:
            raise HTTPException(status_code=404, detail="No artists found")

        logger.info(
            f"Starting bulk metadata refresh for {len(artists)} artists (force={force_refresh})"
        )

        # Import metadata enrichment service
        from src.services.metadata_artist_enricher import enrich_multiple_artists
        from src.services.metadata_enrichment_service import (
            MetadataEnrichmentService,
        )

        # Create service instance
        service = MetadataEnrichmentService()

        # Enrich all artists
        results = await enrich_multiple_artists(
            service=service,
            artist_ids=artist_ids,
            force_refresh=force_refresh,
            app_context=None,
        )

        # Count successes and failures
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        logger.info(
            f"Bulk metadata refresh complete: {success_count} succeeded, {failure_count} failed"
        )

        return {
            "success": True,
            "message": f"Refreshed metadata for {success_count}/{len(artists)} artists",
            "total": len(artists),
            "succeeded": success_count,
            "failed": failure_count,
            "results": [
                {
                    "artist_id": r.artist_id,
                    "success": r.success,
                    "fields_updated": (
                        r.fields_updated if hasattr(r, "fields_updated") else []
                    ),
                    "errors": r.errors if hasattr(r, "errors") else [],
                }
                for r in results
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk metadata refresh: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/merge")
async def merge_artists(
    request: MergeArtistsRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Merge multiple artists into one primary artist.

    All videos from secondary artists will be reassigned to the primary artist,
    then the secondary artists will be deleted.
    """
    try:
        # Validate primary artist exists
        primary_artist = (
            session.query(Artist).filter(Artist.id == request.primary_artist_id).first()
        )

        if not primary_artist:
            raise HTTPException(
                status_code=404,
                detail=f"Primary artist {request.primary_artist_id} not found",
            )

        # Validate all secondary artists exist
        secondary_artists = (
            session.query(Artist)
            .filter(Artist.id.in_(request.secondary_artist_ids))
            .all()
        )

        if len(secondary_artists) != len(request.secondary_artist_ids):
            found_ids = {a.id for a in secondary_artists}
            missing_ids = set(request.secondary_artist_ids) - found_ids
            raise HTTPException(
                status_code=404,
                detail=f"Secondary artist(s) not found: {list(missing_ids)}",
            )

        # Check if primary artist is in secondary list
        if request.primary_artist_id in request.secondary_artist_ids:
            raise HTTPException(
                status_code=400,
                detail="Primary artist cannot be in the list of secondary artists",
            )

        merged_count = 0
        total_videos_moved = 0
        secondary_names = []

        for secondary_artist in secondary_artists:
            secondary_names.append(secondary_artist.name)

            # Move all videos from secondary to primary
            videos_to_move = (
                session.query(Video)
                .filter(Video.artist_id == secondary_artist.id)
                .all()
            )

            for video in videos_to_move:
                video.artist_id = primary_artist.id
                total_videos_moved += 1

            # Delete the secondary artist
            session.delete(secondary_artist)
            merged_count += 1

            logger.info(
                f"Merged artist '{secondary_artist.name}' (ID: {secondary_artist.id}) "
                f"into '{primary_artist.name}' (ID: {primary_artist.id}), "
                f"moved {len(videos_to_move)} videos"
            )

        # Update primary artist's updated_at timestamp
        primary_artist.updated_at = datetime.utcnow()

        session.commit()

        logger.info(
            f"Merge completed: {merged_count} artists merged into '{primary_artist.name}', "
            f"{total_videos_moved} videos moved"
        )

        return {
            "success": True,
            "message": f"Successfully merged {merged_count} artist(s) into {primary_artist.name}",
            "merged_count": merged_count,
            "primary_artist_id": primary_artist.id,
            "primary_artist_name": primary_artist.name,
            "secondary_artist_names": secondary_names,
            "videos_moved": total_videos_moved,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging artists: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cleanup-zero-videos")
async def cleanup_zero_video_artists(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Delete artists with zero videos"""
    try:
        # Find artists with no videos
        subquery = session.query(Video.artist_id).distinct().subquery()

        zero_video_artists = (
            session.query(Artist)
            .filter(~Artist.id.in_(session.query(subquery.c.artist_id)))
            .all()
        )

        deleted_count = 0
        deleted_names = []

        for artist in zero_video_artists:
            deleted_names.append(artist.name)
            session.delete(artist)
            deleted_count += 1

        session.commit()

        logger.info(f"Cleanup: Deleted {deleted_count} artists with zero videos")

        return {
            "message": f"Cleanup completed",
            "deleted_count": deleted_count,
            "deleted_artists": deleted_names[:10],  # Show first 10 names
            "total_deleted": len(deleted_names),
        }

    except Exception as e:
        logger.error(f"Error in cleanup zero videos: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# ADVANCED ARTIST OPERATIONS
# ========================================================================================


@router.get("/{artist_id}/detailed")
async def get_artist_detailed(
    artist_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get comprehensive artist details with statistics"""
    try:
        # Get artist with comprehensive data
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Get video statistics - MySQL/MariaDB compatible
        from sqlalchemy import case

        video_stats = (
            session.query(
                func.count(Video.id).label("total_videos"),
                func.sum(
                    case((Video.status == VideoStatus.DOWNLOADED, 1), else_=0)
                ).label("downloaded"),
                func.sum(case((Video.status == VideoStatus.WANTED, 1), else_=0)).label(
                    "wanted"
                ),
                func.sum(
                    case((Video.status == VideoStatus.DOWNLOADING, 1), else_=0)
                ).label("downloading"),
                func.avg(Video.duration).label("avg_duration"),
            )
            .filter(Video.artist_id == artist_id)
            .first()
        )

        # Get all videos for the artist (for artist detail page)
        videos = (
            session.query(Video)
            .filter(Video.artist_id == artist_id)
            .order_by(Video.created_at.desc())
            .all()
        )

        # Also get recent videos (first 5) for backward compatibility
        recent_videos = videos[:5]

        # Ensure folder path
        await ensure_artist_folder_path(artist, session)

        # Extract metadata from imvdb_metadata JSON field
        metadata = artist.imvdb_metadata or {}

        return {
            "artist": {
                "id": artist.id,
                "name": artist.name,
                "sort_name": getattr(artist, "sort_name", artist.name),
                "folder_path": artist.folder_path,
                "imvdb_id": artist.imvdb_id,
                "imvdb_slug": getattr(artist, "imvdb_slug", None),
                # Category 2 fields - prefer database over metadata
                "biography": getattr(artist, "biography", None)
                or metadata.get("biography")
                or metadata.get("overview")
                or metadata.get("bio"),
                "formed_year": getattr(artist, "formed_year", None)
                or metadata.get("formed_year"),
                "location": getattr(artist, "location", None)
                or metadata.get("location"),
                "website": getattr(artist, "website", None) or metadata.get("website"),
                "wikipedia_url": getattr(artist, "wikipedia_url", None)
                or metadata.get("wikipedia_url"),
                "musicbrainz_id": getattr(artist, "musicbrainz_id", None)
                or metadata.get("musicbrainz_id"),
                "spotify_id": artist.spotify_id,
                "lastfm_name": artist.lastfm_name or metadata.get("lastfm_name"),
                # Category 1 fields - database only
                "keywords": getattr(artist, "keywords", None),
                "genres": getattr(artist, "genres", None),
                "labels": getattr(artist, "labels", None),
                "members": getattr(artist, "members", None),
                # Category 3 fields - prefer database over metadata
                "overview": getattr(artist, "overview", None)
                or metadata.get("overview"),
                "disbanded_year": getattr(artist, "disbanded_year", None)
                or metadata.get("disbanded_year"),
                "origin_country": getattr(artist, "origin_country", None)
                or metadata.get("origin_country"),
                "spotify_url": getattr(artist, "spotify_url", None)
                or metadata.get("spotify_url"),
                "youtube_url": getattr(artist, "youtube_url", None)
                or metadata.get("youtube_url"),
                "apple_music_url": getattr(artist, "apple_music_url", None)
                or metadata.get("apple_music_url"),
                "twitter_url": getattr(artist, "twitter_url", None)
                or metadata.get("twitter_url"),
                "facebook_url": getattr(artist, "facebook_url", None)
                or metadata.get("facebook_url"),
                "instagram_url": getattr(artist, "instagram_url", None)
                or metadata.get("instagram_url"),
                "quality_profile": getattr(artist, "quality_profile", None),
                "priority": getattr(artist, "priority", None),
                # Settings
                "monitored": getattr(artist, "monitored", True),
                "auto_download": getattr(artist, "auto_download", False),
                # Video type filtering - Issue #191
                "allowed_video_types": getattr(artist, "allowed_video_types", None),
                # Metadata and timestamps
                "imvdb_metadata": artist.imvdb_metadata,
                "created_at": (
                    artist.created_at.isoformat() if artist.created_at else None
                ),
                "updated_at": (
                    artist.updated_at.isoformat() if artist.updated_at else None
                ),
                "thumbnail_url": f"/api/artists/{artist.id}/thumbnail",
            },
            "statistics": {
                "total_videos": video_stats.total_videos or 0,
                "downloaded": video_stats.downloaded or 0,
                "wanted": video_stats.wanted or 0,
                "downloading": video_stats.downloading or 0,
                "total_size_bytes": 0,  # File size info moved to Downloads table
                "average_duration_seconds": float(video_stats.avg_duration or 0),
            },
            "videos": [
                {
                    "id": video.id,
                    "title": video.title,
                    "artist_id": video.artist_id,
                    "artist_name": artist.name,
                    "url": video.url,
                    "youtube_url": video.youtube_url,
                    "video_url": video.url or video.youtube_url,
                    "status": video.status,
                    "file_path": getattr(video, "file_path", video.local_path),
                    "local_path": video.local_path,
                    "duration": video.duration,
                    "created_at": (
                        video.created_at.isoformat() if video.created_at else None
                    ),
                    "updated_at": (
                        video.updated_at.isoformat() if video.updated_at else None
                    ),
                    "thumbnail_url": f"/api/videos/{video.id}/thumbnail",
                }
                for video in videos
            ],
            "recent_videos": [
                {
                    "id": video.id,
                    "title": video.title,
                    "status": video.status,
                    "created_at": (
                        video.created_at.isoformat() if video.created_at else None
                    ),
                }
                for video in recent_videos
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting detailed artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{artist_id}/navigation")
async def get_artist_navigation(
    artist_id: int = FastAPIPath(..., ge=1),
    sort: str = Query("name", description="Sort field"),
    order: str = Query("asc", description="Sort order"),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Get artist navigation info (prev/next artists)"""
    try:
        # Get current artist
        current_artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not current_artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Get all artists sorted by specified field
        sort_column = getattr(Artist, sort, Artist.name)
        query = session.query(Artist).order_by(
            sort_column.asc() if order == "asc" else sort_column.desc()
        )
        all_artists = query.all()

        # Find current artist position
        current_position = None
        for i, artist in enumerate(all_artists):
            if artist.id == artist_id:
                current_position = i
                break

        if current_position is None:
            raise HTTPException(status_code=404, detail="Artist position not found")

        # Get prev/next artists
        prev_artist = (
            all_artists[current_position - 1] if current_position > 0 else None
        )
        next_artist = (
            all_artists[current_position + 1]
            if current_position < len(all_artists) - 1
            else None
        )

        return {
            "current_artist": {
                "id": current_artist.id,
                "name": current_artist.name,
                "position": current_position + 1,
                "total": len(all_artists),
            },
            "prev_artist": (
                {"id": prev_artist.id, "name": prev_artist.name}
                if prev_artist
                else None
            ),
            "next_artist": (
                {"id": next_artist.id, "name": next_artist.name}
                if next_artist
                else None
            ),
            "sort": sort,
            "order": order,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting artist navigation for {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/update-monitoring")
async def bulk_update_monitoring(
    request: BulkMonitoringRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update monitoring settings for multiple artists"""
    try:
        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Prepare update data
        update_data = {}
        if request.monitored is not None:
            update_data["monitored"] = request.monitored

        # Note: monitor_new_items would need to be added to Artist model if needed
        # For now, we only update monitored status

        if not update_data:
            raise HTTPException(status_code=400, detail="No updates provided")

        update_data["updated_at"] = datetime.utcnow()

        # Perform bulk update
        updated_count = (
            session.query(Artist)
            .filter(Artist.id.in_(request.artist_ids))
            .update(update_data, synchronize_session=False)
        )

        session.commit()

        logger.info(
            f"Bulk updated monitoring for {updated_count} artists: {update_data}"
        )

        return {
            "success": True,
            "message": f"Updated monitoring for {updated_count} artist(s)",
            "updated_count": updated_count,
            "updates_applied": update_data,
            "total_requested": len(request.artist_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk update monitoring: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/command/rename")
async def execute_rename_command(
    request: RenameCommandRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Execute RENAME_ARTIST command to organize/rename artist files.

    This would typically integrate with a file organization service.
    For now, returns a success response indicating the command was queued.
    """
    try:
        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Get artists to ensure they exist
        artists = session.query(Artist).filter(Artist.id.in_(request.artist_ids)).all()

        if not artists:
            raise HTTPException(status_code=404, detail="No artists found")

        # TODO: Integrate with actual file organization service
        # For now, we'll just log the command
        logger.info(
            f"RENAME_ARTIST command queued for {len(artists)} artists: {request.artist_ids}"
        )

        return {
            "success": True,
            "message": f"Rename command queued for {len(artists)} artist(s)",
            "artist_count": len(artists),
            "artist_ids": request.artist_ids,
            "note": "File organization feature requires file system integration",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing rename command: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/command/retag")
async def execute_retag_command(
    request: RetagCommandRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Execute RETAG_ARTIST command to write metadata tags to artist files.

    This would typically integrate with a metadata tagging service.
    For now, returns a success response indicating the command was queued.
    """
    try:
        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        # Get artists to ensure they exist
        artists = session.query(Artist).filter(Artist.id.in_(request.artist_ids)).all()

        if not artists:
            raise HTTPException(status_code=404, detail="No artists found")

        # TODO: Integrate with actual metadata tagging service
        # For now, we'll just log the command
        logger.info(
            f"RETAG_ARTIST command queued for {len(artists)} artists: {request.artist_ids}"
        )

        return {
            "success": True,
            "message": f"Retag command queued for {len(artists)} artist(s)",
            "artist_count": len(artists),
            "artist_ids": request.artist_ids,
            "note": "Metadata tagging feature requires file system integration",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing retag command: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# BULK THUMBNAIL SCAN
# ========================================================================================


@router.post("/bulk-thumbnail-scan")
async def bulk_thumbnail_scan(
    request: BulkDeleteRequest,  # Reuses artist_ids field
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Scan selected artists for missing thumbnails and download them.

    This endpoint allows users to scan specific artists for thumbnails
    rather than scanning all artists at once.
    """
    try:
        from src.services.artist_thumbnail_search_service import (
            search_artist_thumbnails,
        )
        from src.services.thumbnail_service import ThumbnailService

        if not request.artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        thumbnail_service = ThumbnailService()
        scanned_count = 0
        found_count = 0

        for artist_id in request.artist_ids:
            try:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()

                if not artist:
                    continue

                scanned_count += 1

                # Skip if already has thumbnail
                if artist.thumbnail_path and Path(artist.thumbnail_path).exists():
                    logger.debug(f"Artist {artist.name} already has thumbnail")
                    continue

                # Same shared cascade as the single-artist search
                # endpoint (#320) — Spotify, Last.fm, cached metadata,
                # Wikipedia, YouTube, in that priority order.
                # stop_at_first_result=True: a bulk scan wants one good
                # hit per artist, not every source queried for all of
                # them.
                results = search_artist_thumbnails(
                    artist.name, artist=artist, stop_at_first_result=True
                )
                thumbnail_url = results[0]["url"] if results else None
                if thumbnail_url:
                    logger.info(
                        f"Found {results[0]['source']} thumbnail for {artist.name}"
                    )

                # Download and save thumbnail
                if thumbnail_url:
                    try:
                        downloaded_path = thumbnail_service.download_artist_thumbnail(
                            artist.name, thumbnail_url
                        )

                        if downloaded_path:
                            artist.thumbnail_path = downloaded_path
                            artist.thumbnail_url = f"/api/artists/{artist_id}/thumbnail"
                            session.commit()
                            found_count += 1
                            logger.info(
                                f"Successfully downloaded thumbnail for {artist.name}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to download thumbnail for {artist.name}: {e}"
                        )

            except Exception as e:
                logger.error(f"Error scanning thumbnail for artist {artist_id}: {e}")
                continue

        return {
            "success": True,
            "scanned_count": scanned_count,
            "found_count": found_count,
            "message": f"Found thumbnails for {found_count} out of {scanned_count} artists",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk thumbnail scan: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
