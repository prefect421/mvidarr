"""
FastAPI Artists Thumbnail API
Extracted from artists.py for better code organization

This module contains all thumbnail-related endpoints for artists:
- Getting/serving thumbnails
- Setting thumbnails from URLs
- Uploading custom thumbnails
- Searching for thumbnails from various sources
- Scanning for missing thumbnails
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
)
from fastapi import Path as FastAPIPath
from fastapi import (
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.api.fastapi.artists_models import ThumbnailSearchRequest
from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.database.connection import get_db_session
from src.database.models import Artist
from src.services.thumbnail_service import ThumbnailService, thumbnail_service
from src.services.wikipedia_service import wikipedia_service
from src.services.youtube_search_service import youtube_search_service

# Router configuration
router = APIRouter(
    prefix="",
    tags=["artists-thumbnails"],
    responses={
        404: {"description": "Artist not found"},
        422: {"description": "Validation error"},
    },
)

# Logger setup
logger = logging.getLogger("mvidarr.api.fastapi.artists_thumbnails")
# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


def _is_placeholder_url(url: str) -> bool:
    """Check if URL is a known placeholder image"""
    if not url:
        return True

    url_lower = url.lower()

    # Known placeholder patterns
    placeholder_patterns = [
        # Last.fm placeholder images
        "2a96cbd8b46e442fc41c2b86b821562f.png",
        "lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f",
        # Generic placeholders
        "placeholder",
        "default",
        "generic",
        "no-image",
        "blank",
        "missing",
        "unavailable",
        "coming-soon",
        "avatar-default",
        "profile-default",
        "default_artist",
        "artist_placeholder",
        "music_placeholder",
        "album_default",
        "cover_default",
        # Common placeholder files
        "grey.gif",
        "transparent.png",
        "1x1.png",
        "spacer.gif",
        "default.jpg",
        "default.png",
        "placeholder.jpg",
        "placeholder.png",
    ]

    return any(pattern in url_lower for pattern in placeholder_patterns)


async def _get_artist_thumbnail_impl(
    artist_id: int,
    size: Optional[str],
    session: Session,
):
    """Implementation for serving artist thumbnail image"""
    try:
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Check if artist has a thumbnail_path in database
        if artist.thumbnail_path and Path(artist.thumbnail_path).exists():
            return FileResponse(
                artist.thumbnail_path,
                media_type="image/jpeg",
                filename=f"artist_{artist_id}_thumbnail.jpg",
            )

        # Construct thumbnail path using actual file naming convention
        thumbnail_dir = Path("data/thumbnails/artists")

        # Try to find thumbnail file by artist name (convert to lowercase and replace spaces with underscores)
        artist_name_safe = artist.name.lower().replace(" ", "_").replace("-", "_")

        # Look for files matching the artist name pattern (both jpg and png)
        if thumbnail_dir.exists():
            for ext in ["jpg", "png", "jpeg"]:
                for thumbnail_file in thumbnail_dir.glob(f"{artist_name_safe}_*.{ext}"):
                    if thumbnail_file.exists():
                        media_type = (
                            "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
                        )
                        return FileResponse(
                            thumbnail_file,
                            media_type=media_type,
                            filename=f"artist_{artist_id}_thumbnail.{ext}",
                        )

        # Return placeholder thumbnail
        placeholder_path = Path("frontend/static/placeholder-artist.png")
        if placeholder_path.exists():
            return FileResponse(
                placeholder_path, media_type="image/png", filename="placeholder.png"
            )
        else:
            raise HTTPException(status_code=404, detail="Thumbnail not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thumbnail for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# THUMBNAIL ENDPOINTS
# ========================================================================================


@router.get("/{artist_id}/thumbnail")
async def get_artist_thumbnail(
    artist_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Serve artist thumbnail image"""
    return await _get_artist_thumbnail_impl(artist_id, None, session)


@router.get("/{artist_id}/thumbnail/info")
async def get_artist_thumbnail_info(
    artist_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get thumbnail information for artist"""
    try:
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Check if artist has thumbnail
        has_thumbnail = bool(artist.thumbnail_path)

        response = {
            "has_thumbnail": has_thumbnail,
            "thumbnail_path": artist.thumbnail_path,
            "thumbnail_source": getattr(artist, "thumbnail_source", None),
            "thumbnail_uploaded_at": getattr(artist, "thumbnail_uploaded_at", None),
            "metadata": getattr(artist, "thumbnail_metadata", None),
        }

        # Add file info if thumbnail exists
        if has_thumbnail and artist.thumbnail_path:
            try:
                from pathlib import Path

                thumb_path = Path(artist.thumbnail_path)
                if thumb_path.exists():
                    stat = thumb_path.stat()
                    response["file_info"] = {
                        "size": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified": stat.st_mtime,
                    }
            except Exception:
                # If file doesn't exist, don't include file_info
                pass

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thumbnail info for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{artist_id}/thumbnail/{size}")
async def get_artist_thumbnail_with_size(
    artist_id: int = FastAPIPath(..., ge=1),
    size: str = FastAPIPath(..., pattern="^(small|medium|large)$"),
    session: Session = Depends(get_db_session),
):
    """Serve artist thumbnail image with size as path parameter"""
    return await _get_artist_thumbnail_impl(artist_id, size, session)


@router.put("/{artist_id}/thumbnail")
async def set_artist_thumbnail(
    artist_id: int = FastAPIPath(..., ge=1),
    thumbnail_data: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """
    Set artist thumbnail from URL or search result

    This is the FIRST version from line 1221 - uses ThumbnailService for downloading.
    REASONING: This version is preferred because:
    1. Uses ThumbnailService.download_artist_thumbnail() which has proper User-Agent
       headers for Wikipedia and other sources (avoiding 403 errors)
    2. Leverages existing thumbnail service infrastructure
    3. More maintainable - centralized thumbnail download logic
    4. Sets thumbnail_url to API endpoint format (/api/artists/{id}/thumbnail)

    The second version (line 1616) was likely a duplicate attempt that uses httpx
    directly and doesn't leverage the service layer properly.
    """
    try:
        from datetime import datetime

        import requests

        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Check if this is a delete request
        remove_thumbnail = thumbnail_data.get("remove_thumbnail", False)

        if remove_thumbnail:
            # Handle thumbnail deletion
            try:
                from src.services.thumbnail_service import ThumbnailService

                thumbnail_service = ThumbnailService()

                # Delete existing thumbnail files if they exist
                if artist.thumbnail_path:
                    thumbnail_service.delete_thumbnail_files(artist.thumbnail_path)

                # Clear thumbnail references
                artist.thumbnail_url = None
                artist.thumbnail_path = None
                session.commit()

                logger.info(f"Successfully deleted thumbnail for artist {artist.name}")
                return {"success": True, "message": "Thumbnail deleted successfully"}

            except Exception as e:
                logger.error(f"Error deleting thumbnail for artist {artist_id}: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to delete thumbnail: {str(e)}"
                )

        thumbnail_url = thumbnail_data.get("thumbnail_url")
        if not thumbnail_url:
            raise HTTPException(
                status_code=400,
                detail="thumbnail_url is required for setting thumbnail",
            )

        # Download the thumbnail using ThumbnailService (with proper headers for Wikipedia)
        try:
            from src.services.thumbnail_service import (
                ThumbnailDownloadError,
                ThumbnailPlaceholderError,
                ThumbnailService,
                ThumbnailValidationError,
            )

            thumbnail_service = ThumbnailService()

            # Use ThumbnailService which has proper User-Agent headers for Wikipedia and other sources
            # Use raise_on_error=True for better error messages
            downloaded_path = thumbnail_service.download_artist_thumbnail(
                artist.name, thumbnail_url, raise_on_error=True
            )

            if not downloaded_path:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to download thumbnail - unknown error",
                )

            # Update artist record
            artist.thumbnail_path = downloaded_path
            artist.thumbnail_url = f"/api/artists/{artist_id}/thumbnail"
            artist.thumbnail_source = "manual"
            artist.thumbnail_uploaded_at = datetime.utcnow()

            session.commit()

            return {
                "success": True,
                "message": "Thumbnail set successfully",
                "thumbnail_path": downloaded_path,
                "thumbnail_url": f"/api/artists/{artist_id}/thumbnail",
            }

        except ThumbnailPlaceholderError as e:
            logger.warning(f"Placeholder image rejected for artist {artist.name}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot use this image: {str(e)}",
            )
        except ThumbnailDownloadError as e:
            logger.error(f"Failed to download thumbnail from {thumbnail_url}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download thumbnail: {str(e)}",
            )
        except ThumbnailValidationError as e:
            logger.error(f"Thumbnail validation failed for {thumbnail_url}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image: {str(e)}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downloading thumbnail from {thumbnail_url}: {e}")
            raise HTTPException(
                status_code=400, detail=f"Failed to download thumbnail: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting thumbnail for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{artist_id}/thumbnail/upload")
async def upload_artist_thumbnail(
    artist_id: int = FastAPIPath(..., ge=1),
    thumbnail: UploadFile = File(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Upload a custom thumbnail for an artist"""
    try:
        from datetime import datetime

        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Validate file type
        if not thumbnail.content_type or not thumbnail.content_type.startswith(
            "image/"
        ):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Create thumbnails directory if it doesn't exist
        thumbnail_dir = Path("data/thumbnails/artists")
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        import uuid

        file_ext = Path(thumbnail.filename).suffix if thumbnail.filename else ".jpg"
        artist_name_safe = artist.name.lower().replace(" ", "_").replace("-", "_")
        filename = f"{artist_name_safe}_{uuid.uuid4().hex[:12]}{file_ext}"
        file_path = thumbnail_dir / filename

        # Save uploaded file
        content = await thumbnail.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Update artist record
        artist.thumbnail_path = str(file_path)
        artist.thumbnail_url = str(file_path)
        artist.thumbnail_source = "manual"
        artist.thumbnail_uploaded_at = datetime.utcnow()

        session.commit()

        return {
            "success": True,
            "message": "Thumbnail uploaded successfully",
            "thumbnail_path": str(file_path),
            "filename": filename,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading thumbnail for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{artist_id}/thumbnail/search")
async def search_artist_thumbnail(
    artist_id: int = FastAPIPath(..., ge=1),
    search_request: ThumbnailSearchRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Search for artist thumbnail from various sources"""
    try:
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        search_query = search_request.query or artist.name

        # Search for thumbnails based on source
        thumbnail_results = []

        if search_request.source in ["auto", "wikipedia"]:
            try:
                logger.info(f"Searching Wikipedia for thumbnails: {search_query}")

                # Try multiple search variations for better Wikipedia matches
                search_terms = [search_query]

                # Add common variations for known problematic cases
                if search_query.upper() == "REM":
                    search_terms.extend(["R.E.M.", "R.E.M. band", "REM band"])
                elif "." not in search_query and len(search_query.split()) == 1:
                    # For single-word artists, try adding "band" or "musician"
                    search_terms.extend(
                        [f"{search_query} band", f"{search_query} musician"]
                    )

                wikipedia_url = None
                for term in search_terms:
                    logger.debug(f"Trying Wikipedia search term: {term}")
                    wikipedia_url = wikipedia_service.search_artist_thumbnail(term)
                    if wikipedia_url:
                        logger.info(
                            f"Wikipedia search successful with term '{term}': {wikipedia_url}"
                        )
                        break

                if wikipedia_url:
                    thumbnail_results.append(
                        {
                            "source": "wikipedia",
                            "url": wikipedia_url,
                            "title": f"{search_query} - Wikipedia",
                            "description": f"Wikipedia thumbnail for {search_query}",
                        }
                    )
                else:
                    logger.info(
                        f"No Wikipedia thumbnail found for any variation of: {search_query}"
                    )
            except Exception as e:
                logger.warning(f"Wikipedia thumbnail search failed: {e}")

        if search_request.source in ["auto", "youtube"]:
            try:
                logger.info(f"Searching YouTube for thumbnails: {search_query}")
                youtube_url = youtube_search_service.search_artist_channel_thumbnail(
                    search_query
                )
                logger.info(f"YouTube search result: {youtube_url}")
                if youtube_url:
                    thumbnail_results.append(
                        {
                            "source": "youtube",
                            "url": youtube_url,
                            "title": f"{search_query} - YouTube Channel",
                            "channel": search_query,
                        }
                    )
            except Exception as e:
                logger.warning(f"YouTube thumbnail search failed: {e}")

        # Check for existing metadata images (Spotify, Last.fm, etc.)
        if search_request.source in ["auto", "spotify", "lastfm", "metadata"]:
            try:
                logger.info(f"Checking existing metadata images for: {search_query}")
                if artist.imvdb_metadata:
                    metadata = artist.imvdb_metadata
                    images = metadata.get("images", [])

                    # Helper function to check if image is a placeholder
                    def is_placeholder_image(url):
                        if not url:
                            return True
                        placeholder_patterns = [
                            "2a96cbd8b46e442fc41c2b86b821562f.png",
                            "4128a6eb29f94943c9d206c08e625904",
                            "c6f59c1e5e7240a4c0d427abd71f3dbb",
                            "placeholder",
                            "default",
                            "generic",
                            "no-image",
                        ]
                        return any(
                            pattern in url.lower() for pattern in placeholder_patterns
                        )

                    # Process Last.fm/metadata images
                    valid_images = []
                    for img in images:
                        img_url = None
                        img_size = "unknown"

                        # Handle different image formats
                        if isinstance(img, dict):
                            img_url = img.get("#text") or img.get("url")
                            img_size = img.get("size", "unknown")
                        elif isinstance(img, str):
                            img_url = img

                        # Skip placeholder images
                        if img_url and not is_placeholder_image(img_url):
                            valid_images.append(
                                {
                                    "url": img_url,
                                    "size": img_size,
                                    "source": (
                                        "lastfm" if "lastfm" in img_url else "metadata"
                                    ),
                                }
                            )

                    # Add valid images to results (prefer larger sizes)
                    size_priority = {
                        "mega": 5,
                        "extralarge": 4,
                        "large": 3,
                        "medium": 2,
                        "small": 1,
                        "": 0,
                        "unknown": 0,
                    }
                    valid_images.sort(
                        key=lambda x: size_priority.get(x["size"], 0), reverse=True
                    )

                    for img in valid_images[:3]:  # Limit to top 3 images
                        thumbnail_results.append(
                            {
                                "source": img["source"],
                                "url": img["url"],
                                "title": f"{search_query} - {img['source'].title()} Image ({img['size']})",
                                "size": img["size"],
                            }
                        )

                    if valid_images:
                        logger.info(
                            f"Found {len(valid_images)} valid metadata images for {search_query}"
                        )
                    else:
                        logger.debug(
                            f"No valid (non-placeholder) metadata images found for {search_query}"
                        )
                else:
                    logger.debug(f"No metadata available for {search_query}")
            except Exception as e:
                logger.warning(f"Metadata image retrieval failed: {e}")

        # Log summary for debugging
        if thumbnail_results:
            sources_found = [r["source"] for r in thumbnail_results]
            logger.info(
                f"Thumbnail search for '{search_query}' found {len(thumbnail_results)} results from: {sources_found}"
            )
        else:
            # Check if YouTube API is configured
            youtube_configured = bool(youtube_search_service.api_key)
            logger.warning(
                f"No thumbnails found for '{search_query}'. "
                f"YouTube API configured: {youtube_configured}. "
                f"Source: {search_request.source}"
            )

        return {
            "artist_id": artist_id,
            "artist_name": artist.name,
            "search_query": search_query,
            "source": search_request.source,
            "thumbnails": thumbnail_results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching thumbnails for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scan-missing-thumbnails")
async def scan_missing_thumbnails(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Scan all artists missing thumbnails and try to find images"""
    try:
        from pathlib import Path

        from sqlalchemy import or_

        # Get artists with NULL/empty thumbnail_path
        artists_null_path = (
            session.query(Artist.id, Artist.name, Artist.thumbnail_path)
            .filter(
                or_(
                    Artist.thumbnail_path.is_(None),
                    Artist.thumbnail_path == "",
                )
            )
            .all()
        )

        # Also get artists with thumbnail_path set - we'll check if files exist
        artists_with_path = (
            session.query(Artist.id, Artist.name, Artist.thumbnail_path)
            .filter(
                Artist.thumbnail_path.isnot(None),
                Artist.thumbnail_path != "",
            )
            .all()
        )

        # Build list of artists needing thumbnails:
        # 1. Those with NULL/empty path
        # 2. Those with path set but file doesn't exist
        artists_without_thumbnails = []

        for artist_id, artist_name, thumb_path in artists_null_path:
            artists_without_thumbnails.append((artist_id, artist_name))

        stale_count = 0
        for artist_id, artist_name, thumb_path in artists_with_path:
            if not Path(thumb_path).exists():
                artists_without_thumbnails.append((artist_id, artist_name))
                stale_count += 1
                # Clear the stale path from database
                artist = session.query(Artist).filter(Artist.id == artist_id).first()
                if artist:
                    artist.thumbnail_path = None
                    artist.thumbnail_url = None

        if stale_count > 0:
            session.commit()
            logger.info(f"Cleared {stale_count} stale thumbnail paths from database")

        missing_count = len(artists_without_thumbnails)
        updated_count = 0

        logger.info(
            f"Starting thumbnail scan for {missing_count} artists without thumbnails "
            f"({len(artists_null_path)} null/empty, {stale_count} stale paths)"
        )

        # Import time for rate limiting
        import time

        # Process each artist with rate limiting to avoid 429 errors
        for idx, artist_data in enumerate(artists_without_thumbnails):
            # Add delay between requests to avoid rate limiting (1 second between artists)
            if idx > 0:
                time.sleep(1.0)
            try:
                artist_id, artist_name = artist_data
                logger.info(
                    f"Searching thumbnails for artist: {artist_name} (ID: {artist_id})"
                )

                thumbnail_url = None

                # Try multiple sources for thumbnails
                # 1. Try Google Images first (most variety)
                try:
                    import re
                    from urllib.parse import quote

                    image_query = f"{artist_name} musician artist photo"
                    encoded_query = quote(image_query)
                    search_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=off"

                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }

                    import requests

                    response = requests.get(search_url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        # Extract image URLs from the page
                        image_pattern = r'"(https?://[^"]*\.(?:jpg|jpeg|png))"'
                        matches = re.findall(image_pattern, response.text)

                        # Filter results - skip Google's own domains and tiny images
                        for match in matches[:10]:
                            if (
                                "gstatic.com" not in match
                                and "google.com" not in match
                                and not _is_placeholder_url(match)
                            ):
                                thumbnail_url = match
                                logger.info(
                                    f"Found Google Images thumbnail for {artist_name}: {thumbnail_url}"
                                )
                                break
                except Exception as e:
                    logger.debug(f"Google Images search failed for {artist_name}: {e}")

                # 2. Try Wikipedia if Google didn't work
                if not thumbnail_url:
                    try:
                        wikipedia_url = wikipedia_service.search_artist_thumbnail(
                            artist_name
                        )
                        if wikipedia_url and not _is_placeholder_url(wikipedia_url):
                            thumbnail_url = wikipedia_url
                            logger.info(
                                f"Found Wikipedia thumbnail for {artist_name}: {wikipedia_url}"
                            )
                    except Exception as e:
                        logger.debug(f"Wikipedia search failed for {artist_name}: {e}")

                # 3. Try YouTube channel thumbnail if others didn't work
                if not thumbnail_url:
                    try:
                        from src.services.youtube_search_service import (
                            search_artist_channel_thumbnail,
                        )

                        youtube_url = search_artist_channel_thumbnail(artist_name)
                        if youtube_url and not _is_placeholder_url(youtube_url):
                            thumbnail_url = youtube_url
                            logger.info(
                                f"Found YouTube thumbnail for {artist_name}: {youtube_url}"
                            )
                    except Exception as e:
                        logger.debug(f"YouTube search failed for {artist_name}: {e}")

                # 3. If we found a thumbnail, download and set it
                if thumbnail_url:
                    try:
                        from src.services.thumbnail_service import ThumbnailService

                        thumbnail_service = ThumbnailService()

                        # Download the thumbnail
                        downloaded_path = thumbnail_service.download_artist_thumbnail(
                            artist_name, thumbnail_url
                        )

                        if downloaded_path:
                            # Update artist with thumbnail
                            artist = (
                                session.query(Artist)
                                .filter(Artist.id == artist_id)
                                .first()
                            )
                            if artist:
                                artist.thumbnail_path = downloaded_path
                                artist.thumbnail_url = (
                                    f"/api/artists/{artist_id}/thumbnail"
                                )
                                session.commit()
                                updated_count += 1
                                logger.info(
                                    f"Successfully updated thumbnail for {artist_name}"
                                )
                        else:
                            logger.warning(
                                f"Failed to download thumbnail for {artist_name}"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to download thumbnail for {artist_name}: {e}"
                        )
                else:
                    logger.info(f"No suitable thumbnail found for {artist_name}")

            except Exception as e:
                logger.error(f"Error processing thumbnail for {artist_name}: {e}")
                continue

        return {
            "success": True,
            "message": f"Thumbnail scan completed",
            "missing_count": missing_count,
            "stale_cleared": stale_count,
            "updated_count": updated_count,
            "found_rate": (
                f"{(updated_count/missing_count*100):.1f}%"
                if missing_count > 0
                else "0%"
            ),
        }

    except Exception as e:
        logger.error(f"Error scanning missing thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
