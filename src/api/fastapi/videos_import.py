"""
FastAPI Videos Import API Module

This module contains video import operations from external sources.
These endpoints handle importing videos:
- Import from YouTube
- Import from IMVDb

Extracted from videos.py as part of the API modularization effort.

Authentication: All endpoints require session-based authentication via get_current_user dependency.
"""

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import get_current_user_legacy
from src.database.connection import get_db_session
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_import")


async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


# ========================================================================================
# IMPORT OPERATIONS
# ========================================================================================


@router.post("/import-from-youtube")
async def import_from_youtube(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Import a video from YouTube"""
    try:
        youtube_id = request.get("youtube_id", "")
        url = request.get("url", "")
        title = request.get("title", "")
        artist = request.get("artist", "")
        artist_id = request.get("artist_id")
        auto_download = request.get("auto_download", True)

        if not youtube_id:
            raise HTTPException(status_code=400, detail="YouTube ID is required")

        # Generate URL if not provided
        if not url:
            url = f"https://www.youtube.com/watch?v={youtube_id}"

        # Check if video already exists
        existing_video = (
            session.query(Video).filter(Video.youtube_id == youtube_id).first()
        )

        if existing_video:
            return {
                "success": True,
                "message": "Video already exists in library",
                "video_id": existing_video.id,
                "status": "exists",
            }

        # Create new video entry using only valid Video model fields
        new_video = Video(
            title=title or f"YouTube Video {youtube_id}",
            youtube_id=youtube_id,
            youtube_url=url,
            url=url,  # Store the YouTube URL in the generic url field
            source="youtube_import",
            status=VideoStatus.WANTED if auto_download else VideoStatus.MONITORED,
            duration=None,  # Will be updated when metadata is fetched
            discovered_date=datetime.utcnow(),
        )

        # Try to find or create artist
        if artist_id:
            # Use provided artist_id
            artist_obj = session.query(Artist).filter(Artist.id == artist_id).first()
            if artist_obj:
                new_video.artist_id = artist_obj.id
        elif artist:
            # Fall back to finding by artist name
            artist_obj = session.query(Artist).filter(Artist.name == artist).first()
            if not artist_obj:
                artist_obj = Artist(
                    name=artist, monitored=True, source="youtube_import"
                )
                session.add(artist_obj)
                session.flush()  # Get the artist ID
            new_video.artist_id = artist_obj.id

        session.add(new_video)
        session.flush()  # Flush to get the ID without committing
        video_id = new_video.id  # Get the ID while still bound to session
        session.commit()

        logger.info(f"Imported YouTube video: {title} ({youtube_id})")

        return {
            "success": True,
            "message": f"Video '{title}' imported successfully",
            "video_id": video_id,
            "status": "imported",
            "auto_download": auto_download,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing YouTube video: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-from-imvdb")
async def import_from_imvdb(
    request: dict = Body(...), session: Session = Depends(get_db_session)
):
    """Import a video from IMVDb"""
    try:
        imvdb_id = request.get("imvdb_id", "")
        title = request.get("title", "")
        artist = request.get("artist", "")
        artist_id = request.get("artist_id")
        auto_download = request.get("auto_download", True)

        if not imvdb_id:
            raise HTTPException(status_code=400, detail="IMVDb ID is required")

        # Check if video already exists
        existing_video = session.query(Video).filter(Video.imvdb_id == imvdb_id).first()

        if existing_video:
            return {
                "success": True,
                "message": "Video already exists in library",
                "video_id": existing_video.id,
                "status": "exists",
            }

        # Create new video entry using only valid Video model fields
        new_video = Video(
            title=title or f"IMVDb Video {imvdb_id}",
            imvdb_id=imvdb_id,
            source="imvdb_import",
            status=VideoStatus.WANTED if auto_download else VideoStatus.MONITORED,
            duration=None,  # Will be updated when metadata is fetched
            discovered_date=datetime.utcnow(),
        )

        # Try to find or create artist
        if artist_id:
            # Use provided artist_id
            artist_obj = session.query(Artist).filter(Artist.id == artist_id).first()
            if artist_obj:
                new_video.artist_id = artist_obj.id
        elif artist:
            # Fall back to finding by artist name
            artist_obj = session.query(Artist).filter(Artist.name == artist).first()
            if not artist_obj:
                artist_obj = Artist(name=artist, monitored=True, source="imvdb_import")
                session.add(artist_obj)
                session.flush()  # Get the artist ID
            new_video.artist_id = artist_obj.id

        session.add(new_video)
        session.flush()  # Flush to get the ID without committing
        video_id = new_video.id  # Get the ID while still bound to session
        session.commit()

        logger.info(f"Imported IMVDb video: {title} ({imvdb_id})")

        return {
            "success": True,
            "message": f"Video '{title}' imported successfully",
            "video_id": video_id,
            "status": "imported",
            "auto_download": auto_download,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing IMVDb video: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
