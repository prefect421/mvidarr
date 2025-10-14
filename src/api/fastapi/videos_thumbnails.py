"""
FastAPI Videos Thumbnails API Module

This module contains all thumbnail-related operations for videos.
These endpoints handle thumbnail management:
- Get video thumbnail (image file)
- Get thumbnail info (metadata)
- Search for thumbnails from external sources
- Upload manual thumbnails
- Update/remove thumbnails

Extracted from videos.py as part of the API modularization effort.
Uses Pydantic models from videos_models.py for request/response validation.

Authentication: Most endpoints require session-based authentication via get_current_user dependency.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)
from src.api.fastapi.videos_models import ThumbnailSearchRequest
from src.database.connection import get_db_session
from src.database.models import Video
from src.services.imvdb_service import imvdb_service
from src.services.youtube_service import youtube_service
from src.utils.logger import get_logger

# Router with NO prefix - prefix will be added by parent router
router = APIRouter(
    tags=["videos-thumbnails"],
    responses={
        404: {"description": "Video not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.videos_thumbnails")


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
# THUMBNAIL OPERATIONS
# ========================================================================================


@router.get("/{video_id}/thumbnail")
async def get_video_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    size: Optional[str] = Query(None, pattern="^(small|medium|large)$"),
    session: Session = Depends(get_db_session),
):
    """Get video thumbnail"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # First, check if video has a thumbnail_path in database
        if video.thumbnail_path and video.thumbnail_path.strip():
            thumbnail_file = Path(video.thumbnail_path)
            if thumbnail_file.exists():
                # Detect media type based on file extension
                media_type = "image/jpeg"
                if thumbnail_file.suffix.lower() in [".png"]:
                    media_type = "image/png"
                elif thumbnail_file.suffix.lower() in [".webp"]:
                    media_type = "image/webp"

                return FileResponse(
                    thumbnail_file,
                    media_type=media_type,
                    headers={"content-disposition": "inline"},
                )

        # Check if video has a thumbnail_url that should be downloaded
        if video.thumbnail_url and video.thumbnail_url.strip():
            try:
                # Download and cache the thumbnail
                thumbnail_dir = Path("/home/mike/mvidarr/data/thumbnails/videos")
                thumbnail_dir.mkdir(parents=True, exist_ok=True)

                # Determine file extension from URL
                parsed_url = urlparse(video.thumbnail_url)
                file_extension = Path(parsed_url.path).suffix.lower()
                if not file_extension or file_extension not in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                ]:
                    file_extension = ".jpg"

                cached_thumbnail = thumbnail_dir / f"{video_id}_cached{file_extension}"

                # Download if not already cached
                if not cached_thumbnail.exists():
                    async with httpx.AsyncClient() as client:
                        response = await client.get(video.thumbnail_url, timeout=10)
                        response.raise_for_status()

                        with open(cached_thumbnail, "wb") as f:
                            f.write(response.content)

                # Update database with cached path
                video.thumbnail_path = str(cached_thumbnail)
                session.commit()

                # Return the cached file
                media_type = "image/jpeg"
                if file_extension == ".png":
                    media_type = "image/png"
                elif file_extension == ".webp":
                    media_type = "image/webp"

                return FileResponse(
                    cached_thumbnail,
                    media_type=media_type,
                    headers={"content-disposition": "inline"},
                )

            except Exception as e:
                logger.warning(
                    f"Failed to download thumbnail from URL {video.thumbnail_url}: {e}"
                )
                # Continue to fallback logic

        # Fall back to old naming pattern for compatibility
        thumbnail_dir = Path("/home/mike/mvidarr/data/thumbnails/videos")

        if size:
            thumbnail_file = thumbnail_dir / f"{video_id}_{size}.webp"
        else:
            # Try different sizes in order of preference
            for sz in ["medium", "large", "small"]:
                thumbnail_file = thumbnail_dir / f"{video_id}_{sz}.webp"
                if thumbnail_file.exists():
                    break
            else:
                # Try without size suffix
                thumbnail_file = thumbnail_dir / f"{video_id}.webp"

        if thumbnail_file.exists():
            return FileResponse(
                thumbnail_file,
                media_type="image/webp",
                headers={"content-disposition": "inline"},
            )
        else:
            # Return placeholder thumbnail
            placeholder_path = Path("frontend/static/placeholder-video.png")
            if placeholder_path.exists():
                return FileResponse(
                    placeholder_path,
                    media_type="image/png",
                    headers={"content-disposition": "inline"},
                )
            else:
                raise HTTPException(status_code=404, detail="Thumbnail not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thumbnail for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}/thumbnail/info")
async def get_thumbnail_info(
    video_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get detailed thumbnail information for a video"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        info = {
            "has_thumbnail": bool(video.thumbnail_url or video.thumbnail_path),
            "thumbnail_url": video.thumbnail_url,
            "thumbnail_path": video.thumbnail_path,
            "thumbnail_source": video.thumbnail_source,
            "thumbnail_uploaded_at": (
                video.thumbnail_uploaded_at.isoformat()
                if video.thumbnail_uploaded_at
                else None
            ),
            "thumbnail_metadata": video.thumbnail_metadata,
        }

        # Get file information if local thumbnail exists
        if video.thumbnail_path and Path(video.thumbnail_path).exists():
            try:
                file_path = Path(video.thumbnail_path)
                stat = file_path.stat()
                info.update(
                    {
                        "file_size": stat.st_size,
                        "file_modified": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                        "file_format": file_path.suffix.lower(),
                    }
                )
            except Exception as e:
                logger.warning(
                    f"Could not get file info for {video.thumbnail_path}: {e}"
                )

        return info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thumbnail info for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/thumbnail/search")
async def search_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    search_request: ThumbnailSearchRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Search for video thumbnails using various sources (YouTube, IMVDb, Google)"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Extract video attributes while session is active
        artist_name = video.artist.name if video.artist else "Unknown"
        video_title = video.title
        video_url = video.url
        video_imvdb_id = video.imvdb_id

        # Use video info for search if no custom query provided
        search_query = getattr(search_request, "search_query", "") or ""
        if not search_query:
            search_query = f"{artist_name} {video_title}"

        sources = getattr(search_request, "sources", ["youtube", "imvdb", "google"])
        results = []

        # 1. YouTube thumbnails
        youtube_id = None

        # Try to extract YouTube ID from existing URL if available
        if video_url and "youtube" in sources:
            import re

            patterns = [
                r"(?:youtube\.com/watch\?v=|youtu\.be/)([^&\n?#]+)",
                r"youtube\.com/embed/([^&\n?#]+)",
                r"(?:youtube\.com/v/|youtube\.com/watch\?.*&v=)([^&\n?#]+)",
            ]

            logger.debug(f"Checking video URL for YouTube ID: {video_url}")
            for pattern in patterns:
                match = re.search(pattern, video_url)
                if match:
                    youtube_id = match.group(1)
                    logger.info(f"Extracted YouTube ID from video URL: {youtube_id}")
                    break

        # Search YouTube by artist - song title if no URL or ID found
        if not youtube_id and "youtube" in sources:
            try:
                logger.info(f"Searching YouTube for: {search_query}")
                search_results = youtube_service.search_videos(
                    search_query, max_results=1
                )
                if search_results["success"] and search_results["results"]:
                    # Get video ID from YouTube API response format
                    first_result = search_results["results"][0]
                    youtube_id = first_result["id"]["videoId"]
                    logger.info(f"Found YouTube video via search: {youtube_id}")
            except Exception as e:
                logger.warning(f"YouTube search failed for '{search_query}': {e}")

        # Add YouTube thumbnails if we have an ID (from URL or search)
        if youtube_id and "youtube" in sources:
            try:
                yt_thumbnails = [
                    {
                        "url": f"https://img.youtube.com/vi/{youtube_id}/maxresdefault.jpg",
                        "source": "youtube",
                        "quality": "maxres",
                        "title": f"{video_title} - Max Resolution",
                    },
                    {
                        "url": f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg",
                        "source": "youtube",
                        "quality": "hq",
                        "title": f"{video_title} - High Quality",
                    },
                    {
                        "url": f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg",
                        "source": "youtube",
                        "quality": "mq",
                        "title": f"{video_title} - Medium Quality",
                    },
                ]
                results.extend(yt_thumbnails)
                logger.info(
                    f"Added {len(yt_thumbnails)} YouTube thumbnail options for video {video_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create YouTube thumbnails for video {video_id}: {e}"
                )

        # 2. IMVDb thumbnails
        if "imvdb" in sources:
            try:
                video_details = None

                # First try to get by existing IMVDb ID
                if video_imvdb_id:
                    video_details = imvdb_service.get_video_by_id(video_imvdb_id)
                    logger.debug(f"Retrieved IMVDb data using ID: {video_imvdb_id}")

                # If no ID or no details found, try searching
                if not video_details:
                    logger.info(f"No IMVDb ID found, searching for: {search_query}")
                    try:
                        search_result = imvdb_service.find_best_video_match(
                            artist_name, video_title
                        )
                        if search_result:
                            video_details = search_result
                            logger.info(f"Found IMVDb video via search")
                    except Exception as search_e:
                        logger.debug(f"IMVDb search failed: {search_e}")

                if video_details:
                    # Extract thumbnail metadata using existing extract_metadata method
                    metadata = imvdb_service.extract_metadata(video_details)
                    thumbnail_url = metadata.get("thumbnail_url")

                    if thumbnail_url:
                        imvdb_thumbnails = [
                            {
                                "url": thumbnail_url,
                                "source": "imvdb",
                                "quality": "original",
                                "title": f"{video_title} - IMVDb Original",
                            }
                        ]
                        results.extend(imvdb_thumbnails)
                        logger.info(
                            f"Found IMVDb thumbnail for video {video_id}: {thumbnail_url}"
                        )
                    else:
                        logger.debug(
                            f"No thumbnail URL found in IMVDb data for video {video_id}"
                        )
                else:
                    logger.info(f"No IMVDb thumbnails found for: {search_query}")
            except Exception as e:
                logger.warning(
                    f"Failed to get IMVDb thumbnails for video {video_id}: {e}"
                )

        # 3. Google Images thumbnails
        if "google" in sources:
            try:
                from urllib.parse import quote

                import requests

                logger.info(f"Searching Google Images for: {search_query}")

                # Format query for image search
                image_query = f"{search_query} music video thumbnail"
                encoded_query = quote(image_query)

                # Google Images search URL
                search_url = (
                    f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=off"
                )

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }

                response = requests.get(search_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Simple regex to extract image URLs from the page
                    import re

                    # Look for image URLs in the page content
                    image_pattern = r'"(https?://[^"]*\.(?:jpg|jpeg|png|webp))"'
                    matches = re.findall(image_pattern, response.text)

                    # Filter and clean up the results
                    google_thumbnails = []
                    seen_urls = set()

                    for match in matches[:6]:  # Limit to first 6 results
                        if match not in seen_urls and "encrypted" not in match:
                            seen_urls.add(match)
                            google_thumbnails.append(
                                {
                                    "url": match,
                                    "source": "google",
                                    "quality": "varies",
                                    "title": f"{video_title} - Google Images",
                                }
                            )

                    if google_thumbnails:
                        results.extend(google_thumbnails)
                        logger.info(
                            f"Added {len(google_thumbnails)} Google Images results for video {video_id}"
                        )
                    else:
                        logger.info(
                            f"No Google Images results found for: {search_query}"
                        )
                else:
                    logger.warning(
                        f"Google Images search failed with status: {response.status_code}"
                    )

            except Exception as e:
                logger.warning(
                    f"Failed to search Google Images for video {video_id}: {e}"
                )

        logger.info(
            f"Found {len(results)} thumbnail options for video {video_id} (query: '{search_query}', sources: {sources})"
        )

        # Add debugging info for empty results
        if not results:
            debug_info = {
                "video_url": video_url,
                "imvdb_id": video_imvdb_id,
                "sources_requested": sources,
                "has_youtube_url": bool(
                    video_url
                    and ("youtube.com" in video_url or "youtu.be" in video_url)
                ),
                "has_imvdb_id": bool(video_imvdb_id),
            }
            logger.warning(
                f"No thumbnail results found for video {video_id}. Debug info: {debug_info}"
            )

        return {
            "results": results,
            "query": search_query,
            "sources_searched": sources,
            "total_results": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search thumbnails for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/thumbnail/upload")
async def upload_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Upload a manual thumbnail file for a video"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")

        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
            )

        # Generate filename based on video info
        artist_name = video.artist.name if video.artist else "Unknown"
        video_title = str(video.title) if video.title is not None else "Unknown"
        filename = f"{artist_name} - {video_title}".replace("/", "_").replace("\\", "_")

        # Create thumbnail directory
        thumbnail_dir = Path("/home/mike/mvidarr/data/thumbnails/videos")
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Save file with video ID and appropriate extension
        file_extension = Path(file.filename).suffix or ".jpg"
        thumbnail_filename = f"{video_id}{file_extension}"
        thumbnail_path = thumbnail_dir / thumbnail_filename

        # Write file to disk
        content = await file.read()
        with open(thumbnail_path, "wb") as f:
            f.write(content)

        # Update video thumbnail information
        video.thumbnail_path = str(thumbnail_path)
        video.thumbnail_url = None  # Clear external URL since we have local file
        video.thumbnail_source = "manual"
        video.thumbnail_metadata = {
            "file_size": len(content),
            "content_type": file.content_type,
            "original_filename": file.filename,
        }
        video.thumbnail_uploaded_at = datetime.utcnow()
        session.commit()

        logger.info(f"Uploaded manual thumbnail for video {video_id}")

        return {
            "message": "Thumbnail uploaded successfully",
            "thumbnail_path": str(thumbnail_path),
            "file_size": len(content),
            "content_type": file.content_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading thumbnail for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{video_id}/thumbnail")
async def set_thumbnail(
    video_id: int = FastAPIPath(..., ge=1),
    data: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update video thumbnail URL or remove thumbnail"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        thumbnail_url = data.get("thumbnail_url")
        action = data.get("action", "update")

        if action == "remove":
            # Remove thumbnail files and clear database fields
            if video.thumbnail_path and Path(video.thumbnail_path).exists():
                try:
                    Path(video.thumbnail_path).unlink()
                except Exception as e:
                    logger.warning(
                        f"Could not delete thumbnail file {video.thumbnail_path}: {e}"
                    )

            video.thumbnail_url = None
            video.thumbnail_path = None
            video.thumbnail_source = None
            video.thumbnail_metadata = None
            video.thumbnail_uploaded_at = None
            session.commit()

            logger.info(f"Removed thumbnail for video {video_id}")
            return {"message": "Thumbnail removed successfully"}

        elif action == "update" and thumbnail_url:
            # Update thumbnail URL and clear cached path to force new download
            video.thumbnail_url = thumbnail_url
            video.thumbnail_source = "manual"

            # Clear cached thumbnail path so new URL will be used
            if video.thumbnail_path and Path(video.thumbnail_path).exists():
                try:
                    Path(video.thumbnail_path).unlink()
                except Exception as e:
                    logger.warning(
                        f"Could not delete old thumbnail file {video.thumbnail_path}: {e}"
                    )
                video.thumbnail_path = None

            session.commit()

            logger.info(f"Updated thumbnail URL for video {video_id}")
            return {"message": "Thumbnail URL updated successfully"}

        else:
            raise HTTPException(
                status_code=400, detail="Invalid action or missing thumbnail_url"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update thumbnail for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
