"""
FastAPI Videos Search API - Extracted Search Operations

This module contains all search-related endpoints extracted from videos.py:
- GET /search - Advanced video search with filters
- GET /search-artists - Artist name search
- GET /universal-search - Unified search across local and external sources
- POST /{video_id}/lyrics/search - Lyrics search and storage

All search functionality is isolated here for better organization and maintainability.
"""

import asyncio
import json
import urllib.parse
from typing import Dict, List, Optional, Union

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.database.models import Artist, Video
from src.utils.logger import get_logger

# Router configuration - using prefix="" as per requirements
router = APIRouter(
    prefix="",
    tags=["videos-search"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.videos_search")


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


def _safe_parse_genres(genres: Union[str, List[str], None]) -> List[str]:
    """Safely parse genres field that may be JSON string or list"""
    if isinstance(genres, list):
        return genres
    if not genres:
        return []
    if isinstance(genres, str):
        try:
            genres = genres.strip()
            if not genres:
                return []
            return json.loads(genres)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse genres JSON: {genres}, error: {e}")
            return []
    return []


# ========================================================================================
# SEARCH ENDPOINTS
# ========================================================================================


@router.get("/universal-search", response_model=Dict)
async def universal_search(
    q: str = Query(..., min_length=1),
    extended: bool = Query(False),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Universal search endpoint that searches across videos, artists, IMVDb, and YouTube"""
    try:
        query = q.lower()

        # Local database search (skip if extended mode)
        video_results = []
        artist_results = []

        if not extended:
            # Search local videos
            videos = (
                session.query(Video)
                .join(Artist)
                .filter(
                    Video.title.ilike(f"%{query}%") | Artist.name.ilike(f"%{query}%")
                )
                .limit(5)
                .all()
            )

            for video in videos:
                video_results.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist": video.artist.name if video.artist else "Unknown",
                        "status": (
                            video.status.value
                            if hasattr(video.status, "value")
                            else str(video.status)
                        ),
                        "year": getattr(video, "year", None),
                        "thumbnail": f"/api/videos/{video.id}/thumbnail",
                        "duration": getattr(video, "duration", None),
                        "quality": getattr(video, "quality", None),
                        "url": f"/video/{video.id}",
                    }
                )

            # Search local artists
            artists = (
                session.query(Artist)
                .filter(Artist.name.ilike(f"%{query}%"))
                .limit(5)
                .all()
            )

            for artist in artists:
                artist_results.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "video_count": len(artist.videos) if artist.videos else 0,
                        "monitored": getattr(artist, "monitored", True),
                        "genres": [],
                        "url": f"/artist/{artist.id}",
                    }
                )

        # External search results
        external_results = []

        # IMVDb Search
        try:
            from src.services.imvdb_service import imvdb_service

            imvdb_limit = 8 if extended else 3

            if imvdb_service:
                imvdb_search_result = await asyncio.to_thread(
                    imvdb_service.search_artist_videos, query, imvdb_limit
                )

                if imvdb_search_result and imvdb_search_result.get("videos"):
                    imvdb_results = []
                    logger.debug(
                        f"Sample IMVDb video data: {imvdb_search_result['videos'][0] if imvdb_search_result['videos'] else 'No videos'}"
                    )
                    for video in imvdb_search_result["videos"][:imvdb_limit]:
                        # Extract artist name from nested structure with multiple fallbacks
                        artist_name = ""
                        artist_data = video.get("artist")

                        if isinstance(artist_data, dict):
                            # Try common artist name fields
                            artist_name = (
                                artist_data.get("name")
                                or artist_data.get("artist_name")
                                or artist_data.get("entity_name")
                                or ""
                            )
                        elif isinstance(artist_data, str):
                            artist_name = artist_data

                        # Additional fallbacks
                        if not artist_name:
                            artist_name = (
                                video.get("artist_name", "")
                                or video.get("entity_name", "")
                                or video.get("band_name", "")
                                or query.title()  # Use the search query as artist name
                            )

                        imvdb_results.append(
                            {
                                "source": "IMVDb",
                                "id": str(video.get("id", "")),
                                "title": video.get("song_title", ""),
                                "artist": artist_name,
                                "year": video.get("year", None),
                                "thumbnail": (
                                    video.get("image", {}).get("o", "")
                                    if video.get("image")
                                    else ""
                                ),
                                "action": "add_to_library",
                                "video_id": str(video.get("id", "")),
                                "imvdb_url": (
                                    f"https://imvdb.com/video/{video.get('id', '')}"
                                    if video.get("id")
                                    else ""
                                ),
                            }
                        )
                    external_results.extend(imvdb_results)
                    logger.info(
                        f"Found {len(imvdb_results)} IMVDb results for: {query}"
                    )
                else:
                    logger.info(f"No IMVDb results found for: {query}")
        except Exception as e:
            logger.warning(f"IMVDb search failed: {e}")

        # YouTube Search
        try:
            from src.services.youtube_search_service import youtube_search_service

            youtube_limit = 10 if extended else 5

            if youtube_search_service and youtube_search_service.api_key:
                youtube_search_result = await asyncio.to_thread(
                    youtube_search_service.search_artist_videos, query, youtube_limit
                )

                if youtube_search_result and youtube_search_result.get("videos"):
                    youtube_results = []
                    for video in youtube_search_result["videos"][:youtube_limit]:
                        youtube_results.append(
                            {
                                "source": "YouTube",
                                "id": video.get("youtube_id", ""),
                                "title": video.get("title", ""),
                                "artist": video.get("channel_title", ""),
                                "thumbnail": video.get("thumbnail_url", ""),
                                "duration": (
                                    str(video.get("duration", ""))
                                    if video.get("duration")
                                    else ""
                                ),
                                "view_count": (
                                    str(video.get("view_count", ""))
                                    if video.get("view_count")
                                    else ""
                                ),
                                "action": "add_to_library",
                                "video_id": video.get("youtube_id", ""),
                                "youtube_url": video.get("youtube_url", ""),
                            }
                        )
                    external_results.extend(youtube_results)
                    logger.info(
                        f"Found {len(youtube_results)} YouTube results for: {query}"
                    )
                else:
                    yt_error = (
                        youtube_search_result.get("error", "")
                        if youtube_search_result
                        else ""
                    )
                    if yt_error:
                        logger.warning(
                            f"YouTube search returned 0 results with error: {yt_error}"
                        )
                    else:
                        logger.info(f"No YouTube results found for: {query}")
            else:
                logger.warning(
                    "YouTube API key not configured, skipping YouTube search"
                )
        except Exception as e:
            logger.warning(f"YouTube search failed: {e}")

        # Structured response matching Flask format
        response = {
            "videos": video_results,
            "artists": artist_results,
            "external": external_results,
            "total": len(video_results) + len(artist_results) + len(external_results),
        }

        return response

    except Exception as e:
        logger.error(f"Universal search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/search")
async def search_videos(
    query: Optional[str] = Query(None),
    artist_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    genre: Optional[str] = Query(None),
    limit: int = Query(50, le=500, ge=1),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Search videos with filters"""
    try:
        # Build base query
        query_builder = session.query(Video).options(joinedload(Video.artist))

        # Apply text search
        if query:
            search_filter = or_(
                Video.title.ilike(f"%{query}%"),
                Video.artist.has(Artist.name.ilike(f"%{query}%")),
            )
            query_builder = query_builder.filter(search_filter)

        # Apply filters
        if artist_id:
            query_builder = query_builder.filter(Video.artist_id == artist_id)
        if status:
            query_builder = query_builder.filter(Video.status == status)
        if year:
            # Assuming we have a year field or extract from created_at
            query_builder = query_builder.filter(
                func.extract("year", Video.created_at) == year
            )
        if genre:
            # Search in genres JSON field
            query_builder = query_builder.filter(Video.genres.like(f'%"{genre}"%'))

        # Apply sorting
        sort_column = getattr(Video, sort_by, Video.created_at)
        if sort_order == "desc":
            query_builder = query_builder.order_by(sort_column.desc())
        else:
            query_builder = query_builder.order_by(sort_column.asc())

        # Get total count
        total_count = query_builder.count()

        # Apply pagination
        videos = query_builder.offset(offset).limit(limit).all()

        # Convert to response format
        video_responses = []
        for video in videos:
            video_dict = {
                "id": video.id,
                "title": video.title,
                "artist_id": video.artist_id,
                "artist_name": video.artist.name if video.artist else None,
                "url": video.url,
                "youtube_url": video.youtube_url,
                "video_url": video.url
                or video.youtube_url,  # For JavaScript compatibility
                "status": video.status,
                "file_path": getattr(video, "file_path", video.local_path),
                "local_path": video.local_path,  # For JavaScript compatibility
                "file_size": getattr(video, "file_size", None),
                "duration": video.duration,
                "resolution": getattr(video, "resolution", None),
                "fps": getattr(video, "fps", None),
                "codec": getattr(video, "codec", None),
                "bitrate": getattr(video, "bitrate", None),
                "created_at": (
                    video.created_at.isoformat() if video.created_at else None
                ),
                "updated_at": (
                    video.updated_at.isoformat() if video.updated_at else None
                ),
                "genres": _safe_parse_genres(getattr(video, "genres", [])),
                "thumbnail_url": f"/api/videos/{video.id}/thumbnail",
                "quality": getattr(video, "quality", None),
                "video_metadata": getattr(video, "video_metadata", None),
                "lyrics": getattr(video, "lyrics", None),
                "year": getattr(video, "year", None),
                "release_date": (
                    video.release_date.isoformat() if video.release_date else None
                ),
                "album": getattr(video, "album", None),
            }
            video_responses.append(video_dict)

        return {
            "videos": video_responses,
            "search": {
                "query": query,
                "filters": {
                    "artist_id": artist_id,
                    "status": status,
                    "year": year,
                    "genre": genre,
                },
            },
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Error searching videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/search-artists")
async def search_artists(
    q: str = Query("", min_length=0),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Search for existing artists by name"""
    try:
        query = q.strip()

        if not query or len(query) < 2:
            return {"artists": []}

        # Search for artists whose names contain the query (case-insensitive)
        artists = (
            session.query(Artist)
            .filter(Artist.name.ilike(f"%{query}%"))
            .filter(Artist.name != "Unknown Artist")
            .order_by(Artist.name)
            .limit(10)
            .all()
        )

        # Format results
        results = []
        for artist in artists:
            # Count videos for this artist
            video_count = (
                session.query(Video).filter(Video.artist_id == artist.id).count()
            )

            results.append(
                {"id": artist.id, "name": artist.name, "video_count": video_count}
            )

        return {"artists": results}

    except Exception as e:
        logger.error(f"Error searching artists: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{video_id}/lyrics/search")
async def search_video_lyrics(
    video_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Search and retrieve lyrics for a video"""
    try:
        video = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        logger.info(f"Searching lyrics for video {video_id}: {video.title}")

        artist_name = video.artist.name if video.artist else None
        raw_title = video.title

        # Clean the song title by removing artist name if it's at the beginning
        song_title = raw_title
        if artist_name and raw_title.lower().startswith(artist_name.lower()):
            # Remove artist name and common separators
            song_title = raw_title[len(artist_name) :].strip()
            # Remove common separators like " - ", " | ", etc.
            for separator in [" - ", " | ", " : ", ": ", " – "]:
                if song_title.startswith(separator):
                    song_title = song_title[len(separator) :].strip()
                    break

        logger.info(
            f"🎵 Extracted artist: '{artist_name}', raw title: '{raw_title}', cleaned title: '{song_title}'"
        )

        if not artist_name or not song_title:
            raise HTTPException(
                status_code=400,
                detail="Artist name and song title are required for lyrics search",
            )

        # Search for lyrics using multiple sources
        lyrics_found = None
        source_used = None

        # Define lyrics search function locally to avoid import issues
        def search_lyrics_direct(artist, title):
            """Search for lyrics using Lyrics.ovh API directly"""
            try:
                artist_clean = artist.strip()
                title_clean = title.strip()
                artist_encoded = urllib.parse.quote(artist_clean)
                title_encoded = urllib.parse.quote(title_clean)
                url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{title_encoded}"

                logger.info(f"Making lyrics request to: {url}")
                response = requests.get(url, timeout=10)
                logger.info(f"Lyrics API response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    lyrics = data.get("lyrics", "")
                    if lyrics:
                        lyrics = lyrics.strip()
                        lyrics = "\n".join(
                            line.strip() for line in lyrics.split("\n") if line.strip()
                        )
                        if len(lyrics) > 50:
                            return lyrics
                return None
            except Exception as e:
                logger.warning(f"Lyrics search failed: {e}")
                return None

        # Try lyrics search
        lyrics_sources = [
            ("Lyrics.ovh", search_lyrics_direct),
        ]

        for source_name, search_func in lyrics_sources:
            try:
                logger.info(
                    f"Searching {source_name} for lyrics: {artist_name} - {song_title}"
                )
                lyrics_result = search_func(artist_name, song_title)
                logger.info(
                    f"Lyrics search result: {lyrics_result[:100] if lyrics_result else 'None'}..."
                )

                if (
                    lyrics_result and len(lyrics_result.strip()) > 50
                ):  # Ensure we got substantial lyrics
                    lyrics_found = lyrics_result
                    source_used = source_name
                    logger.info(
                        f"✅ Found lyrics from {source_name} ({len(lyrics_result)} chars)"
                    )
                    break
                else:
                    logger.warning(
                        f"❌ No substantial lyrics from {source_name} (got: {lyrics_result[:50] if lyrics_result else 'None'})"
                    )
            except Exception as e:
                logger.warning(f"Failed to search {source_name}: {e}")

        if not lyrics_found:
            raise HTTPException(
                status_code=404, detail="No lyrics found from any source"
            )

        # Save lyrics to database (if lyrics field exists)
        try:
            # Note: Assuming there's a lyrics field on video model
            video.lyrics = lyrics_found
            session.commit()
            logger.info(f"Lyrics saved for video {video_id} from {source_used}")
        except Exception as e:
            logger.warning(f"Could not save lyrics to database: {e}")

        return {
            "success": True,
            "lyrics": lyrics_found,
            "source": source_used,
            "message": f"Lyrics found from {source_used} and saved successfully!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching lyrics for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
