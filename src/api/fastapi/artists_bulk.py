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

from src.api.fastapi.artists_models import BulkDeleteRequest, BulkEditRequest
from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
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
# AUTHENTICATION DEPENDENCIES
# ========================================================================================


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/edit")
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
                "biography": metadata.get("biography")
                or metadata.get("overview")
                or metadata.get("bio"),
                "formed_year": metadata.get("formed_year"),
                "location": metadata.get("location"),
                "website": metadata.get("website"),
                "wikipedia_url": metadata.get("wikipedia_url"),
                "musicbrainz_id": metadata.get("musicbrainz_id"),
                "spotify_id": artist.spotify_id,
                "lastfm_name": artist.lastfm_name or metadata.get("lastfm_name"),
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{artist_id}/navigation")
async def get_artist_navigation(
    artist_id: int = FastAPIPath(..., ge=1),
    sort: str = Query("name", description="Sort field"),
    order: str = Query("asc", description="Sort order"),
    session: Session = Depends(get_db_session),
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
        raise HTTPException(status_code=500, detail=str(e))
