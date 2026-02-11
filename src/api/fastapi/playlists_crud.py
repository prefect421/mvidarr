"""
FastAPI Playlists CRUD Module
Core CRUD operations, video management, and bulk operations for playlists
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.playlists_auth import UserInfo, get_current_user_from_session
from src.api.fastapi.playlists_models import (
    AddVideoRequest,
    BulkDeleteRequest,
    PlaylistCreateRequest,
    PlaylistResponse,
    PlaylistUpdateRequest,
    ReorderVideoRequest,
    playlist_to_dict,
)
from src.database.connection import get_db_session
from src.database.models import Playlist, PlaylistEntry, User, Video
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.playlists_crud")


# ========================================================================================
# CORE PLAYLIST CRUD OPERATIONS
# ========================================================================================


@router.get("/test")
async def test_endpoint():
    """Simple test endpoint to check if route works"""
    return {"success": True, "message": "Test endpoint working"}


@router.get("/debug")
async def debug_endpoint():
    """Debug endpoint to isolate the issue"""
    return {"success": True, "message": "Debug endpoint working"}


@router.get("/simple")
async def simple_endpoint():
    """Simplest possible endpoint"""
    return {"message": "simple"}


@router.get("/", response_model=Dict[str, Any])
async def get_playlists(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
):
    """Get paginated list of playlists accessible to current user"""
    try:
        offset = (page - 1) * per_page

        # Show all playlists (user owns all playlists in single-user system)
        # In multi-user system, this would filter by user_id or is_public
        query = session.query(Playlist)

        total_count = query.count()

        playlists = (
            query.options(joinedload(Playlist.user))
            .order_by(Playlist.updated_at.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )

        # Convert playlists to safe dictionary format
        playlist_data = []
        for playlist in playlists:
            data = {
                "id": playlist.id,
                "name": playlist.name,
                "description": playlist.description,
                "user_id": playlist.user_id,
                "username": playlist.user.username if playlist.user else None,
                "is_public": playlist.is_public,
                "is_featured": playlist.is_featured,
                "video_count": getattr(playlist, "video_count", 0),
                "total_duration": getattr(playlist, "total_duration", 0),
                "thumbnail_url": (
                    f"/api/playlists/{playlist.id}/thumbnail" if playlist.id else None
                ),
                "created_at": (
                    playlist.created_at.isoformat() if playlist.created_at else None
                ),
                "updated_at": (
                    playlist.updated_at.isoformat() if playlist.updated_at else None
                ),
                "can_modify": False,  # Simplified for now
            }
            playlist_data.append(data)

        return {
            "playlists": playlist_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "pages": (total_count + per_page - 1) // per_page,
                "has_next": offset + per_page < total_count,
                "has_prev": page > 1,
            },
        }

    except Exception as e:
        logger.error(f"Error getting playlists: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{playlist_id}", response_model=Dict[str, Any])
async def get_playlist(
    request: Request,
    playlist_id: int = FastAPIPath(..., ge=1),
    include_entries: bool = Query(True),
    session: Session = Depends(get_db_session),
):
    """Get specific playlist with optional entries"""
    try:
        # Get current user for permission checking
        current_user = await get_current_user_from_session(request)

        query = session.query(Playlist).options(joinedload(Playlist.user))

        if include_entries:
            query = query.options(
                joinedload(Playlist.entries)
                .joinedload(PlaylistEntry.video)
                .joinedload(Video.artist)
            )

        playlist = query.filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Allow access to all playlists (single-user system)
        # In multi-user system, would check: playlist.user_id == current_user.id or playlist.is_public

        playlist_data = playlist_to_dict(
            playlist, include_entries=include_entries, user=current_user
        )

        return {"success": True, "playlist": playlist_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/", response_model=PlaylistResponse)
async def create_playlist(
    request: Request,
    playlist_data: PlaylistCreateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Create new playlist"""
    try:
        # Get authenticated user
        current_user = await get_current_user_from_session(request)

        # Only admins can create featured playlists
        if playlist_data.is_featured and not current_user.can_access_admin():
            raise HTTPException(
                status_code=403, detail="Only admins can create featured playlists"
            )

        # Create playlist
        playlist = Playlist(
            name=playlist_data.name,
            description=playlist_data.description,
            user_id=current_user.id,
            is_public=playlist_data.is_public,
            is_featured=playlist_data.is_featured,
        )

        session.add(playlist)
        session.flush()  # Get the ID

        # Update stats
        if hasattr(playlist, "update_stats"):
            playlist.update_stats()

        session.commit()
        session.refresh(playlist)

        logger.info(f"Created playlist: {playlist.name} (ID: {playlist.id})")

        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            user_id=playlist.user_id,
            username=current_user.username,
            is_public=playlist.is_public,
            is_featured=playlist.is_featured,
            is_dynamic=False,
            video_count=0,
            total_duration=0,
            thumbnail_url=f"/api/playlists/{playlist.id}/thumbnail",
            created_at=playlist.created_at.isoformat() if playlist.created_at else None,
            updated_at=playlist.updated_at.isoformat() if playlist.updated_at else None,
            can_modify=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating playlist: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    update_data: PlaylistUpdateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Update playlist details"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented
        # Currently allows all modifications for development

        # Update fields
        update_fields = update_data.dict(exclude_unset=True)

        # Note: Admin check for featured status would go here when auth is implemented
        # For now, allow featured status updates in development

        # Allowlist of fields that can be updated
        allowed_fields = {
            "name",
            "description",
            "is_public",
            "is_featured",
            "playlist_type",
            "filter_criteria",
            "sort_order",
        }
        for field, value in update_fields.items():
            if field not in allowed_fields:
                continue
            setattr(playlist, field, value)

        session.commit()
        session.refresh(playlist)

        logger.info(f"Updated playlist {playlist_id}: {playlist.name}")

        # Check if playlist is dynamic by calling the method
        try:
            is_dynamic = (
                playlist.is_dynamic()
                if callable(getattr(playlist, "is_dynamic", None))
                else False
            )
        except:
            is_dynamic = False

        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            user_id=playlist.user_id,
            username=playlist.user.username if playlist.user else None,
            is_public=playlist.is_public,
            is_featured=playlist.is_featured,
            is_dynamic=is_dynamic,
            video_count=getattr(playlist, "video_count", 0),
            total_duration=getattr(playlist, "total_duration", 0),
            thumbnail_url=f"/api/playlists/{playlist.id}/thumbnail",
            created_at=playlist.created_at.isoformat() if playlist.created_at else None,
            updated_at=playlist.updated_at.isoformat() if playlist.updated_at else None,
            can_modify=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Delete playlist"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        playlist_name = playlist.name

        # Delete playlist (cascade should handle entries)
        session.delete(playlist)
        session.commit()

        logger.info(f"Deleted playlist: {playlist_name} (ID: {playlist_id})")

        return {"message": f"Playlist '{playlist_name}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# PLAYLIST VIDEO MANAGEMENT OPERATIONS
# ========================================================================================


@router.post("/{playlist_id}/videos")
async def add_videos_to_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    request_data: AddVideoRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Add video(s) to playlist"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        # Validate videos exist
        videos = session.query(Video).filter(Video.id.in_(request_data.video_ids)).all()
        found_video_ids = {v.id for v in videos}
        missing_video_ids = set(request_data.video_ids) - found_video_ids

        if missing_video_ids:
            raise HTTPException(
                status_code=404, detail=f"Videos not found: {list(missing_video_ids)}"
            )

        # Check for existing entries
        existing_entries = (
            session.query(PlaylistEntry)
            .filter(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.video_id.in_(request_data.video_ids),
            )
            .all()
        )

        existing_video_ids = {e.video_id for e in existing_entries}
        new_video_ids = found_video_ids - existing_video_ids

        if not new_video_ids:
            return {"message": "All videos already in playlist", "added_count": 0}

        # Determine starting position
        if request_data.position:
            start_position = request_data.position
            # Shift existing entries down
            session.query(PlaylistEntry).filter(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.position >= start_position,
            ).update(
                {PlaylistEntry.position: PlaylistEntry.position + len(new_video_ids)}
            )
        else:
            # Add to end
            max_position = (
                session.query(func.max(PlaylistEntry.position))
                .filter(PlaylistEntry.playlist_id == playlist_id)
                .scalar()
                or 0
            )
            start_position = max_position + 1

        # Add new entries
        new_entries = []
        for i, video_id in enumerate(sorted(new_video_ids)):
            entry = PlaylistEntry(
                playlist_id=playlist_id, video_id=video_id, position=start_position + i
            )
            session.add(entry)
            new_entries.append(entry)

        # Update playlist stats
        if hasattr(playlist, "update_stats"):
            playlist.update_stats()

        session.commit()

        logger.info(f"Added {len(new_entries)} videos to playlist {playlist_id}")

        return {
            "message": f"Added {len(new_entries)} videos to playlist",
            "added_count": len(new_entries),
            "skipped_count": len(existing_video_ids),
            "playlist_id": playlist_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding videos to playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{playlist_id}/videos/{entry_id}")
async def remove_video_from_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    entry_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Remove video from playlist"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        # Find the entry
        entry = (
            session.query(PlaylistEntry)
            .filter(
                PlaylistEntry.id == entry_id, PlaylistEntry.playlist_id == playlist_id
            )
            .first()
        )

        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found in playlist")

        removed_position = entry.position

        # Remove entry
        session.delete(entry)

        # Shift remaining entries up
        session.query(PlaylistEntry).filter(
            PlaylistEntry.playlist_id == playlist_id,
            PlaylistEntry.position > removed_position,
        ).update({PlaylistEntry.position: PlaylistEntry.position - 1})

        # Update playlist stats
        if hasattr(playlist, "update_stats"):
            playlist.update_stats()

        session.commit()

        logger.info(f"Removed entry {entry_id} from playlist {playlist_id}")

        return {"message": "Video removed from playlist"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing video from playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{playlist_id}/videos/reorder")
async def reorder_videos_in_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    reorder_data: ReorderVideoRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Reorder videos in playlist"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        # Find the entry
        entry = (
            session.query(PlaylistEntry)
            .filter(
                PlaylistEntry.id == reorder_data.entry_id,
                PlaylistEntry.playlist_id == playlist_id,
            )
            .first()
        )

        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found in playlist")

        old_position = entry.position
        new_position = reorder_data.new_position

        if old_position == new_position:
            return {"message": "No change in position"}

        # Get max position
        max_position = (
            session.query(func.max(PlaylistEntry.position))
            .filter(PlaylistEntry.playlist_id == playlist_id)
            .scalar()
            or 0
        )

        if new_position > max_position:
            new_position = max_position

        # Reorder entries
        if old_position < new_position:
            # Moving down - shift entries up
            session.query(PlaylistEntry).filter(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.position > old_position,
                PlaylistEntry.position <= new_position,
            ).update({PlaylistEntry.position: PlaylistEntry.position - 1})
        else:
            # Moving up - shift entries down
            session.query(PlaylistEntry).filter(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.position >= new_position,
                PlaylistEntry.position < old_position,
            ).update({PlaylistEntry.position: PlaylistEntry.position + 1})

        # Update the entry position
        entry.position = new_position

        session.commit()

        logger.info(
            f"Reordered entry {reorder_data.entry_id} in playlist {playlist_id}: {old_position} -> {new_position}"
        )

        return {
            "message": f"Video moved from position {old_position} to {new_position}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering videos in playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# BULK OPERATIONS
# ========================================================================================


@router.post("/bulk/delete")
async def bulk_delete_playlists(
    request: BulkDeleteRequest = Body(...), session: Session = Depends(get_db_session)
):
    """Delete multiple playlists"""
    try:
        if not request.playlist_ids:
            raise HTTPException(status_code=400, detail="No playlist IDs provided")

        # Get playlists to delete
        playlists = (
            session.query(Playlist).filter(Playlist.id.in_(request.playlist_ids)).all()
        )

        if not playlists:
            raise HTTPException(status_code=404, detail="No playlists found")

        deleted_count = 0
        errors = []

        for playlist in playlists:
            try:
                # Note: Permission check would go here when auth system is implemented

                playlist_name = playlist.name
                session.delete(playlist)
                deleted_count += 1

                logger.info(
                    f"Bulk deleted playlist: {playlist_name} (ID: {playlist.id})"
                )

            except Exception as e:
                errors.append(f"Playlist {playlist.id}: {str(e)}")
                logger.error(f"Error deleting playlist {playlist.id}: {e}")

        session.commit()

        logger.info(f"Bulk deleted {deleted_count} playlists")

        result = {
            "message": f"Bulk delete completed",
            "deleted_count": deleted_count,
            "total_requested": len(request.playlist_ids),
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
