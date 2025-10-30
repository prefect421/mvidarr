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
                "created_at": (
                    video.created_at.isoformat() if video.created_at else None
                ),
                "genres": _safe_parse_genres(getattr(video, "genres", [])),
                "thumbnail_url": f"/api/videos/{video.id}/thumbnail",
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search-artists")
async def search_artists(
    q: str = Query("", min_length=0), session: Session = Depends(get_db_session)
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
        raise HTTPException(status_code=500, detail=str(e))
