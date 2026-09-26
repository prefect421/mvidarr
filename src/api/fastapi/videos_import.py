"""
FastAPI Videos Import API Module

This module contains video import operations from external sources.
These endpoints handle importing videos:
- Import from YouTube

Extracted from videos.py as part of the API modularization effort.

Authentication: All endpoints require session-based authentication via the require_authentication dependency.
"""

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_import")


# ========================================================================================
# IMPORT OPERATIONS
# ========================================================================================


@router.post("/import-from-youtube")
async def import_from_youtube(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Import a video from YouTube"""
    try:
        youtube_id = request.get("youtube_id", "")
        url = request.get("url", "")
        title = request.get("title", "")
        artist = request.get("artist", "")
        artist_id = request.get("artist_id")

        # Inherit auto_download from artist setting if not explicitly provided
        if "auto_download" in request:
            auto_download = bool(request["auto_download"])
        elif artist_id:
            artist_obj = session.query(Artist).filter(Artist.id == artist_id).first()
            auto_download = artist_obj.auto_download if artist_obj else False
        else:
            auto_download = False

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
        try:
            session.flush()  # Flush to get the ID without committing
            video_id = new_video.id  # Get the ID while still bound to session
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = (
                session.query(Video).filter(Video.youtube_id == youtube_id).first()
            )
            if existing:
                return {
                    "success": True,
                    "message": "Video already exists in library",
                    "video_id": existing.id,
                    "status": "exists",
                }
            raise  # Constraint violation for a different reason -- don't swallow it

        logger.info(f"Imported YouTube video: {title} ({youtube_id})")

        # If auto_download is enabled, trigger download immediately
        if auto_download:
            try:
                # Get subtitle settings
                from src.services.settings_service import settings
                from src.services.ytdlp_service import ytdlp_service

                download_subtitles = settings.get_bool("download_subtitles", False)
                subtitle_languages = settings.get("subtitle_languages", "en,en-US")

                # Trigger download
                download_result = ytdlp_service.add_music_video_download(
                    artist=artist or "Unknown Artist",
                    title=title,
                    url=url,
                    quality="best",
                    video_id=video_id,
                    download_subtitles=download_subtitles,
                    subtitle_languages=subtitle_languages,
                )

                if download_result.get("success"):
                    logger.info(
                        f"Auto-download triggered for YouTube video {video_id}: {title}"
                    )
                else:
                    logger.warning(
                        f"Auto-download failed for YouTube video {video_id}: {download_result.get('error')}"
                    )

            except Exception as download_error:
                logger.error(
                    f"Failed to trigger auto-download for YouTube video {video_id}: {download_error}"
                )
                # Don't fail the import if download fails

        return {
            "success": True,
            "message": f"Video '{title}' imported successfully"
            + (" and download started" if auto_download else ""),
            "video_id": video_id,
            "status": "imported",
            "auto_download": auto_download,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing YouTube video: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
