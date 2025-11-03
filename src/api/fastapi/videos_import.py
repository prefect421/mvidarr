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

        # Fetch full video metadata from IMVDb (including sources for YouTube URL)
        from src.services.imvdb_service import imvdb_service

        imvdb_metadata = imvdb_service.get_video_by_id(
            str(imvdb_id), include_sources=True
        )

        # Extract YouTube URL from IMVDb metadata
        youtube_url = None
        youtube_id = None
        if imvdb_metadata:
            extracted_metadata = imvdb_service.extract_metadata(imvdb_metadata)
            youtube_url = extracted_metadata.get("youtube_url")
            youtube_id = extracted_metadata.get("youtube_id")

            # Use IMVDb metadata for title if not provided
            if not title and extracted_metadata.get("title"):
                title = extracted_metadata["title"]

            # Use IMVDb metadata for artist if not provided
            if not artist and extracted_metadata.get("artist_name"):
                artist = extracted_metadata["artist_name"]

            logger.info(
                f"IMVDb metadata fetched for {imvdb_id}: YouTube URL {'found' if youtube_url else 'NOT FOUND'}"
            )
        else:
            logger.warning(f"Could not fetch IMVDb metadata for video {imvdb_id}")

        # Create new video entry using only valid Video model fields
        new_video = Video(
            title=title or f"IMVDb Video {imvdb_id}",
            imvdb_id=imvdb_id,
            youtube_url=youtube_url,
            youtube_id=youtube_id,
            url=youtube_url,  # Store YouTube URL in generic url field
            source="imvdb_import",
            status=VideoStatus.WANTED if auto_download else VideoStatus.MONITORED,
            duration=None,  # Will be updated when metadata is fetched
            discovered_date=datetime.utcnow(),
            imvdb_metadata=imvdb_metadata,  # Store full IMVDb metadata
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

        # If auto_download is enabled, trigger download immediately
        download_started = False
        if auto_download:
            try:
                # First, we need to get the YouTube URL for this IMVDb video
                # IMVDb videos need to have a youtube_url or we need to search for one
                if new_video.youtube_url or new_video.url:
                    video_url = new_video.youtube_url or new_video.url

                    # Get subtitle settings
                    from src.services.settings_service import settings
                    from src.services.ytdlp_service import ytdlp_service

                    download_subtitles = settings.get_bool("download_subtitles", False)
                    subtitle_languages = settings.get("subtitle_languages", "en,en-US")

                    # Trigger download
                    download_result = ytdlp_service.add_music_video_download(
                        artist=artist or "Unknown Artist",
                        title=title,
                        url=video_url,
                        quality="best",
                        video_id=video_id,
                        download_subtitles=download_subtitles,
                        subtitle_languages=subtitle_languages,
                    )

                    if download_result.get("success"):
                        download_started = True
                        logger.info(
                            f"Auto-download triggered for IMVDb video {video_id}: {title}"
                        )
                    else:
                        logger.warning(
                            f"Auto-download failed for IMVDb video {video_id}: {download_result.get('error')}"
                        )
                else:
                    logger.warning(
                        f"Cannot auto-download IMVDb video {video_id}: No YouTube URL available"
                    )

            except Exception as download_error:
                logger.error(
                    f"Failed to trigger auto-download for IMVDb video {video_id}: {download_error}"
                )
                # Don't fail the import if download fails

        # Build appropriate message based on what actually happened
        message = f"Video '{title}' imported successfully"
        if download_started:
            message += " and download started"
        elif auto_download:
            # User wanted auto-download but it couldn't start
            message += " (download not started - no YouTube URL available)"

        return {
            "success": True,
            "message": message,
            "video_id": video_id,
            "status": "imported",
            "auto_download": auto_download,
            "download_started": download_started,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing IMVDb video: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
