"""
FastAPI Playlists Features Module
Advanced features: dynamic playlists, thumbnails, and user-specific operations
"""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
)
from fastapi import Path as FastAPIPath
from fastapi import Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.playlists_auth import UserInfo, get_current_user_from_session
from src.api.fastapi.playlists_models import (
    DynamicPlaylistPreviewRequest,
    DynamicPlaylistRequest,
    FilterUpdateRequest,
    PlaylistResponse,
    playlist_to_dict,
)
from src.database.connection import get_db_session
from src.database.models import Playlist, PlaylistEntry, PlaylistType, Video
from src.services.thumbnail_service import ThumbnailService
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.playlists_features")


# ========================================================================================
# DYNAMIC PLAYLISTS (Advanced Feature)
# ========================================================================================


@router.post("/dynamic/preview")
async def preview_dynamic_playlist(
    preview_data: DynamicPlaylistPreviewRequest = Body(...),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Preview videos matching dynamic playlist filter criteria"""
    try:
        # Import dynamic playlist service
        try:
            from src.services.dynamic_playlist_service import dynamic_playlist_service
        except ImportError:
            raise HTTPException(
                status_code=501, detail="Dynamic playlist service not available"
            )

        # Validate filter criteria
        if hasattr(dynamic_playlist_service, "validate_filter_criteria"):
            is_valid, error = dynamic_playlist_service.validate_filter_criteria(
                preview_data.filter_criteria
            )
            if not is_valid:
                raise HTTPException(
                    status_code=400, detail=f"Invalid filter criteria: {error}"
                )

        # Apply filters to get matching videos
        if hasattr(dynamic_playlist_service, "apply_filters"):
            video_ids = dynamic_playlist_service.apply_filters(
                session, preview_data.filter_criteria
            )
        else:
            # Fallback: Basic filter implementation
            video_ids = []

        # Get video details for preview
        total_matches = len(video_ids)
        preview_video_ids = video_ids[: preview_data.limit]

        preview_videos = []
        if preview_video_ids:
            videos = (
                session.query(Video)
                .options(joinedload(Video.artist))
                .filter(Video.id.in_(preview_video_ids))
                .all()
            )

            for video in videos:
                preview_videos.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist_name": video.artist.name if video.artist else None,
                        "duration": video.duration,
                        "thumbnail_url": (
                            f"/api/videos/{video.id}/thumbnail" if video.id else None
                        ),
                    }
                )

        logger.info(
            f"Dynamic playlist preview: {total_matches} matches, showing {len(preview_videos)}"
        )

        return {
            "success": True,
            "preview": {
                "total_matches": total_matches,
                "preview_videos": preview_videos,
                "limit": preview_data.limit,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing dynamic playlist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/dynamic", response_model=PlaylistResponse)
async def create_dynamic_playlist(
    request: Request,
    playlist_data: DynamicPlaylistRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Create dynamic playlist with filter criteria"""
    try:
        # Get authenticated user
        current_user = await get_current_user_from_session(request)
        # Import dynamic playlist service
        try:
            from src.services.dynamic_playlist_service import dynamic_playlist_service
        except ImportError:
            raise HTTPException(
                status_code=501, detail="Dynamic playlist service not available"
            )

        # Validate filter criteria
        if hasattr(dynamic_playlist_service, "validate_filter_criteria"):
            is_valid, error = dynamic_playlist_service.validate_filter_criteria(
                playlist_data.filter_criteria
            )
            if not is_valid:
                raise HTTPException(
                    status_code=400, detail=f"Invalid filter criteria: {error}"
                )

        # Create dynamic playlist
        playlist = Playlist(
            name=playlist_data.name,
            description=playlist_data.description,
            user_id=current_user.id,
            is_public=playlist_data.is_public,
            playlist_type=PlaylistType.DYNAMIC,
            filter_criteria=playlist_data.filter_criteria,
            auto_update=playlist_data.auto_update,
        )

        session.add(playlist)
        session.flush()  # Get the ID

        # Apply initial filters
        if hasattr(dynamic_playlist_service, "apply_filters"):
            video_ids = dynamic_playlist_service.apply_filters(
                session, playlist_data.filter_criteria
            )

            # Add videos to playlist
            for i, video_id in enumerate(video_ids):
                entry = PlaylistEntry(
                    playlist_id=playlist.id, video_id=video_id, position=i + 1
                )
                session.add(entry)

        # Update stats
        if hasattr(playlist, "update_stats"):
            playlist.update_stats()

        session.commit()
        session.refresh(playlist)

        logger.info(f"Created dynamic playlist: {playlist.name} (ID: {playlist.id})")

        return PlaylistResponse(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            user_id=playlist.user_id,
            username=current_user.username,
            is_public=playlist.is_public,
            is_featured=False,
            is_dynamic=True,
            video_count=len(video_ids) if "video_ids" in locals() else 0,
            total_duration=0,
            thumbnail_url=f"/api/playlists/{playlist.id}/thumbnail",
            created_at=playlist.created_at.isoformat() if playlist.created_at else None,
            updated_at=playlist.updated_at.isoformat() if playlist.updated_at else None,
            can_modify=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating dynamic playlist: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{playlist_id}/refresh")
async def refresh_dynamic_playlist(
    playlist_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Manually refresh dynamic playlist"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if not getattr(playlist, "is_dynamic", False):
            raise HTTPException(status_code=400, detail="Playlist is not dynamic")

        # Note: Permission check would go here when auth system is implemented

        # Import dynamic playlist service
        try:
            from src.services.dynamic_playlist_service import dynamic_playlist_service
        except ImportError:
            raise HTTPException(
                status_code=501, detail="Dynamic playlist service not available"
            )

        # Refresh playlist
        if hasattr(dynamic_playlist_service, "refresh_playlist"):
            result = dynamic_playlist_service.refresh_playlist(session, playlist)
            session.commit()

            logger.info(f"Refreshed dynamic playlist {playlist_id}: {result}")

            return {
                "message": "Dynamic playlist refreshed successfully",
                "playlist_id": playlist_id,
                "result": result,
            }
        else:
            raise HTTPException(
                status_code=501, detail="Dynamic playlist refresh not implemented"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing dynamic playlist {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{playlist_id}/filters")
async def update_dynamic_playlist_filters(
    request: Request,
    playlist_id: int = FastAPIPath(..., ge=1),
    filter_data: FilterUpdateRequest = Body(...),
    session: Session = Depends(get_db_session),
):
    """Update dynamic playlist filter criteria"""
    try:
        # Get current user
        current_user = await get_current_user_from_session(request)

        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Check if playlist is dynamic
        try:
            is_dynamic = (
                playlist.is_dynamic()
                if callable(getattr(playlist, "is_dynamic", None))
                else False
            )
        except:
            is_dynamic = False

        if not is_dynamic:
            raise HTTPException(status_code=400, detail="Playlist is not dynamic")

        # Import dynamic playlist service
        try:
            from src.services.dynamic_playlist_service import dynamic_playlist_service
        except ImportError:
            raise HTTPException(
                status_code=501, detail="Dynamic playlist service not available"
            )

        # Validate filter criteria
        if hasattr(dynamic_playlist_service, "validate_filter_criteria"):
            is_valid, error = dynamic_playlist_service.validate_filter_criteria(
                filter_data.filter_criteria
            )
            if not is_valid:
                raise HTTPException(
                    status_code=400, detail=f"Invalid filter criteria: {error}"
                )

        # Update filter criteria
        playlist.filter_criteria = filter_data.filter_criteria

        # Clear existing entries
        session.query(PlaylistEntry).filter(
            PlaylistEntry.playlist_id == playlist_id
        ).delete()

        # Apply new filters to get matching videos
        if hasattr(dynamic_playlist_service, "apply_filters"):
            video_ids = dynamic_playlist_service.apply_filters(
                session, filter_data.filter_criteria
            )

            # Add new entries
            for i, video_id in enumerate(video_ids):
                entry = PlaylistEntry(
                    playlist_id=playlist.id, video_id=video_id, position=i + 1
                )
                session.add(entry)

        # Update stats
        if hasattr(playlist, "update_stats"):
            playlist.update_stats()

        session.commit()
        session.refresh(playlist)

        logger.info(
            f"Updated filters for dynamic playlist {playlist_id}: {playlist.name}"
        )

        return {
            "success": True,
            "message": "Dynamic playlist filters updated successfully",
            "playlist_id": playlist_id,
            "video_count": len(video_ids) if "video_ids" in locals() else 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating dynamic playlist filters {playlist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# THUMBNAIL OPERATIONS
# ========================================================================================


@router.get("/{playlist_id}/thumbnail")
async def get_playlist_thumbnail(
    playlist_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Get playlist thumbnail (or generate from first video)"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # If playlist has a custom thumbnail_url, try to serve it
        if playlist.thumbnail_url:
            # Check if it's a relative path to thumbnails directory
            if playlist.thumbnail_url.startswith("/thumbnails/"):
                # Redirect to the static thumbnail route
                return RedirectResponse(url=playlist.thumbnail_url, status_code=302)
            elif playlist.thumbnail_url.startswith("http"):
                # External URL, redirect to it
                return RedirectResponse(url=playlist.thumbnail_url, status_code=302)

        # Otherwise, try to get thumbnail from first video in playlist
        first_entry = (
            session.query(PlaylistEntry)
            .filter(PlaylistEntry.playlist_id == playlist_id)
            .order_by(PlaylistEntry.position)
            .first()
        )

        if first_entry and first_entry.video_id:
            # Redirect to the first video's thumbnail
            return RedirectResponse(
                url=f"/api/videos/{first_entry.video_id}/thumbnail", status_code=302
            )

        # No thumbnail available
        raise HTTPException(status_code=404, detail="No thumbnail available")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thumbnail for playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{playlist_id}/thumbnail/upload")
async def upload_playlist_thumbnail_url(
    playlist_id: int = FastAPIPath(..., ge=1),
    thumbnail_url: str = Body(..., embed=True),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Upload thumbnail from URL"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        # Use thumbnail service to download and process
        thumbnail_service = ThumbnailService()

        try:
            result = thumbnail_service.upload_from_url(
                thumbnail_url, f"playlist_{playlist_id}", target_dir="playlists"
            )

            logger.info(f"Uploaded thumbnail for playlist {playlist_id}: {result}")

            return {
                "message": "Thumbnail uploaded successfully",
                "playlist_id": playlist_id,
                "thumbnail_url": f"/api/playlists/{playlist_id}/thumbnail",
            }

        except Exception as e:
            logger.error(f"Thumbnail upload failed: {e}")
            raise HTTPException(
                status_code=400, detail=f"Thumbnail upload failed: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading thumbnail for playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{playlist_id}/thumbnail/file")
async def upload_playlist_thumbnail_file(
    playlist_id: int = FastAPIPath(..., ge=1),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """Upload thumbnail file"""
    try:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Note: Permission check would go here when auth system is implemented

        # Validate file
        if file.size > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")

        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Use thumbnail service to process file
        thumbnail_service = ThumbnailService()

        try:
            # Read file content
            file_content = await file.read()

            result = thumbnail_service.upload_from_file(
                file_content,
                file.filename,
                f"playlist_{playlist_id}",
                target_dir="playlists",
            )

            logger.info(f"Uploaded thumbnail file for playlist {playlist_id}: {result}")

            return {
                "message": "Thumbnail file uploaded successfully",
                "playlist_id": playlist_id,
                "thumbnail_url": f"/api/playlists/{playlist_id}/thumbnail",
                "filename": file.filename,
            }

        except Exception as e:
            logger.error(f"Thumbnail file upload failed: {e}")
            raise HTTPException(
                status_code=400, detail=f"Thumbnail upload failed: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading thumbnail file for playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# USER-SPECIFIC OPERATIONS
# ========================================================================================


@router.get("/user/{user_id}")
async def get_user_playlists(
    request: Request,
    user_id: int = FastAPIPath(..., ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
):
    """Get playlists for specific user"""
    try:
        # Get current user for permission checking
        current_user = await get_current_user_from_session(request)

        # Check if requesting own playlists or if admin
        if user_id != 1:  # placeholder user id
            # Only show public playlists for other users
            query = session.query(Playlist).filter(
                Playlist.user_id == user_id, Playlist.is_public == True
            )
        else:
            # Show all playlists for own account or admin
            query = session.query(Playlist).filter(Playlist.user_id == user_id)

        offset = (page - 1) * per_page
        total_count = query.count()

        playlists = (
            query.options(joinedload(Playlist.user))
            .order_by(Playlist.updated_at.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )

        playlist_data = []
        for playlist in playlists:
            data = playlist_to_dict(playlist, include_entries=False, user=current_user)
            playlist_data.append(data)

        return {
            "user_id": user_id,
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
        logger.error(f"Error getting playlists for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
