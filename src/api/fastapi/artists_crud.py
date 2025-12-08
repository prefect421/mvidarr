"""
FastAPI Artists API - CRUD Operations
Extracted from artists.py for better code organization

This module contains core CRUD operations for artists:
- List/search artists
- Get individual artist
- Create new artist
- Update existing artist
- Delete artist
- Advanced search
- Search suggestions
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
)
from fastapi import Path as FastAPIPath
from fastapi import (
    Query,
)
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from src.api.fastapi.artists_models import (
    ArtistCreateRequest,
    ArtistResponse,
    ArtistUpdateRequest,
)
from src.api.fastapi.auth_dependencies import (
    get_current_user_legacy,
    require_authentication_legacy,
)
from src.database.connection import get_db_session
from src.database.models import Artist, Video
from src.utils.logger import get_logger

router = APIRouter(
    prefix="",
    tags=["artists-crud"],
    responses={
        404: {"description": "Artist not found"},
        422: {"description": "Validation error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.artists_crud")


# ========================================================================================
# AUTHENTICATION - PROPER IMPLEMENTATION
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
# CORE ARTIST CRUD OPERATIONS
# ========================================================================================


@router.get("/", response_model=Dict[str, Any])
async def list_artists(
    query: Optional[str] = Query(None, description="Search query"),
    search: Optional[str] = Query(None, description="Search query (alternative name)"),
    sort_by: str = Query("name", pattern="^(name|video_count|created_at|updated_at)$"),
    sort: str = Query("name", description="Sort field (alternative name)"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    order: str = Query("asc", description="Sort order (alternative name)"),
    limit: int = Query(50, ge=1, le=500),
    per_page: int = Query(
        50, ge=1, le=500, description="Items per page (alternative name)"
    ),
    offset: int = Query(0, ge=0),
    page: int = Query(1, ge=1, description="Page number"),
    has_videos: Optional[bool] = Query(None, description="Filter by video existence"),
    has_imvdb: Optional[bool] = Query(None, description="Filter by IMVDb link"),
    has_imvdb_id: Optional[bool] = Query(
        None, description="Filter by IMVDb ID (alternative name)"
    ),
    has_thumbnail: Optional[bool] = Query(
        None, description="Filter by thumbnail existence"
    ),
    monitored: Optional[bool] = Query(None, description="Filter by monitoring status"),
    auto_download: Optional[bool] = Query(
        None, description="Filter by auto-download status"
    ),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    min_videos: Optional[int] = Query(None, description="Minimum video count"),
    max_videos: Optional[int] = Query(None, description="Maximum video count"),
    date_from: Optional[str] = Query(None, description="Filter by created date from"),
    date_to: Optional[str] = Query(None, description="Filter by created date to"),
    keywords: Optional[str] = Query(None, description="Filter by keywords"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """List all tracked artists with search and filtering - OPTIMIZED"""
    try:
        # Handle alternative parameter names for frontend compatibility
        search_query = query or search
        sort_field = sort_by if sort_by != "name" else sort
        sort_direction = sort_order if sort_order != "asc" else order
        items_per_page = per_page if per_page != 50 else limit
        has_imvdb_filter = has_imvdb if has_imvdb is not None else has_imvdb_id

        # Convert page-based pagination to offset-based
        if page > 1:
            offset = (page - 1) * items_per_page

        # Start with optimized query approach
        # Create video count subquery (used for both optimized and fallback paths)
        video_count_subquery = (
            session.query(Video.artist_id, func.count(Video.id).label("video_count"))
            .filter(Video.status.in_(["DOWNLOADED", "WANTED", "DOWNLOADING"]))
            .group_by(Video.artist_id)
            .subquery()
        )

        try:
            from src.database.performance_optimizations import (
                DatabasePerformanceOptimizer,
            )

            optimizer = DatabasePerformanceOptimizer()
            # Use optimized query but we still need the subquery for filtering
            base_query = (
                session.query(
                    Artist,
                    func.coalesce(video_count_subquery.c.video_count, 0).label(
                        "video_count"
                    ),
                )
                .outerjoin(
                    video_count_subquery, Artist.id == video_count_subquery.c.artist_id
                )
                .group_by(Artist.id)
            )

        except ImportError:
            logger.warning("Performance optimizer not available, using fallback query")

            # Fallback uses the same subquery approach
            base_query = (
                session.query(
                    Artist,
                    func.coalesce(video_count_subquery.c.video_count, 0).label(
                        "video_count"
                    ),
                )
                .outerjoin(
                    video_count_subquery, Artist.id == video_count_subquery.c.artist_id
                )
                .group_by(Artist.id)
            )

        # Apply search filter
        if search_query:
            search_filter = or_(
                Artist.name.ilike(f"%{search_query}%"),
                Artist.name.ilike(f"%{search_query}%"),
            )
            base_query = base_query.filter(search_filter)

        # Apply filters
        if has_videos is not None:
            # Use the labeled column directly to avoid alias issues
            from sqlalchemy import literal_column

            if has_videos:
                base_query = base_query.having(literal_column("video_count") > 0)
            else:
                base_query = base_query.having(literal_column("video_count") == 0)

        if has_imvdb_filter is not None:
            if has_imvdb_filter:
                base_query = base_query.filter(Artist.imvdb_id.isnot(None))
            else:
                base_query = base_query.filter(Artist.imvdb_id.is_(None))

        # Apply monitored filter
        if monitored is not None:
            base_query = base_query.filter(Artist.monitored == monitored)

        # Apply auto_download filter
        if auto_download is not None:
            base_query = base_query.filter(Artist.auto_download == auto_download)

        # Apply thumbnail filter
        if has_thumbnail is not None:
            if has_thumbnail:
                base_query = base_query.filter(
                    or_(
                        Artist.thumbnail_path.isnot(None),
                        Artist.thumbnail_url.isnot(None),
                    )
                )
            else:
                base_query = base_query.filter(
                    and_(
                        Artist.thumbnail_path.is_(None), Artist.thumbnail_url.is_(None)
                    )
                )

        # Apply video count filters
        # Use the labeled column directly to avoid alias issues when filters modify the query
        from sqlalchemy import literal_column

        if min_videos is not None:
            base_query = base_query.having(literal_column("video_count") >= min_videos)

        if max_videos is not None:
            base_query = base_query.having(literal_column("video_count") <= max_videos)

        # Apply sorting
        if sort_field == "name":
            sort_column = Artist.name
        elif sort_field == "video_count":
            sort_column = "video_count"
        elif sort_field == "created_at":
            sort_column = Artist.created_at
        elif sort_field == "updated_at":
            sort_column = Artist.updated_at
        else:
            sort_column = Artist.name

        if sort_direction == "desc":
            if sort_field == "video_count":
                base_query = base_query.order_by(desc("video_count"))
            else:
                base_query = base_query.order_by(desc(sort_column))
        else:
            base_query = base_query.order_by(sort_column)

        # Get total count
        total_count = base_query.count()

        # Apply pagination
        results = base_query.offset(offset).limit(items_per_page).all()

        # Process results
        artists = []
        for result in results:
            if hasattr(result, "Artist"):
                artist = result.Artist
                video_count = result.video_count
            else:
                artist = result[0]
                video_count = result[1]

            # Ensure folder path
            await ensure_artist_folder_path(artist, session)

            # Check if artist has thumbnail
            has_thumbnail = bool(
                getattr(artist, "thumbnail_path", None)
                or getattr(artist, "thumbnail_url", None)
            )

            # Check if artist has IMVDB data
            has_imvdb_data = bool(
                artist.imvdb_id or getattr(artist, "imvdb_metadata", None)
            )

            artist_dict = {
                "id": artist.id,
                "name": artist.name,
                "sort_name": getattr(artist, "sort_name", artist.name),
                "folder_path": artist.folder_path,
                "imvdb_id": artist.imvdb_id,
                "imvdb_slug": getattr(artist, "imvdb_slug", None),
                "thumbnail_url": (
                    f"/api/artists/{artist.id}/thumbnail" if artist.id else None
                ),
                "biography": getattr(artist, "biography", None),
                "formed_year": getattr(artist, "formed_year", None),
                "location": getattr(artist, "location", None),
                "website": getattr(artist, "website", None),
                "wikipedia_url": getattr(artist, "wikipedia_url", None),
                "musicbrainz_id": getattr(artist, "musicbrainz_id", None),
                "spotify_id": artist.spotify_id,
                "monitored": getattr(
                    artist, "monitored", True
                ),  # Default to True for compatibility
                "auto_download": getattr(
                    artist, "auto_download", False
                ),  # Default to False
                "has_thumbnail": has_thumbnail,
                "has_imvdb_data": has_imvdb_data,
                "video_count": video_count or 0,
                "created_at": (
                    artist.created_at.isoformat() if artist.created_at else None
                ),
                "updated_at": (
                    artist.updated_at.isoformat() if artist.updated_at else None
                ),
            }
            artists.append(artist_dict)

        # Calculate pagination info for frontend compatibility
        total_pages = (total_count + items_per_page - 1) // items_per_page
        current_page = (offset // items_per_page) + 1

        return {
            "artists": artists,
            "count": len(artists),
            "total": total_count,
            "page": current_page,
            "pages": total_pages,
            "per_page": items_per_page,
            "search": {
                "query": search_query,
                "filters": {
                    "has_videos": has_videos,
                    "has_imvdb": has_imvdb_filter,
                    "has_thumbnail": has_thumbnail,
                    "monitored": monitored,
                    "auto_download": auto_download,
                    "min_videos": min_videos,
                    "max_videos": max_videos,
                },
            },
            "pagination": {
                "total": total_count,
                "limit": items_per_page,
                "offset": offset,
                "page": current_page,
                "pages": total_pages,
                "has_more": offset + items_per_page < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Error listing artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{artist_id}", response_model=ArtistResponse)
async def get_artist(
    artist_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get specific artist by ID with video count"""
    try:
        # Get artist with video count
        result = (
            session.query(Artist, func.count(Video.id).label("video_count"))
            .outerjoin(Video)
            .filter(Artist.id == artist_id)
            .group_by(Artist.id)
            .first()
        )

        if not result:
            raise HTTPException(status_code=404, detail="Artist not found")

        artist, video_count = result

        # Ensure folder path
        await ensure_artist_folder_path(artist, session)

        return ArtistResponse(
            id=artist.id,
            name=artist.name,
            sort_name=getattr(artist, "sort_name", artist.name),
            folder_path=artist.folder_path,
            imvdb_id=artist.imvdb_id,
            imvdb_slug=getattr(artist, "imvdb_slug", None),
            thumbnail_url=f"/api/artists/{artist.id}/thumbnail",
            biography=getattr(artist, "biography", None),
            formed_year=getattr(artist, "formed_year", None),
            location=getattr(artist, "location", None),
            website=getattr(artist, "website", None),
            wikipedia_url=getattr(artist, "wikipedia_url", None),
            musicbrainz_id=getattr(artist, "musicbrainz_id", None),
            spotify_id=artist.spotify_id,
            monitored=getattr(
                artist, "monitored", True
            ),  # Default to True for compatibility
            auto_download=getattr(artist, "auto_download", False),  # Default to False
            imvdb_metadata=artist.imvdb_metadata,  # Include metadata for song recommendations
            video_count=video_count or 0,
            created_at=artist.created_at,
            updated_at=artist.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ArtistResponse)
async def create_artist(
    artist_data: ArtistCreateRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Add new artist to tracking"""
    try:
        # Check if artist already exists
        existing = session.query(Artist).filter(Artist.name == artist_data.name).first()

        if existing:
            raise HTTPException(
                status_code=409, detail=f"Artist '{artist_data.name}' already exists"
            )

        # Create new artist
        artist = Artist(
            name=artist_data.name,
            monitored=artist_data.monitored,
            auto_download=artist_data.auto_download,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Set IMVDb ID if provided
        if artist_data.imvdb_id:
            artist.imvdb_id = artist_data.imvdb_id

        # Set folder path or generate it
        if artist_data.folder_path:
            artist.folder_path = artist_data.folder_path
        else:
            await ensure_artist_folder_path(artist, session)

        session.add(artist)
        session.flush()  # Get the ID

        # Always run auto-processing for new artists (auto-match, metadata, thumbnails)
        try:
            from src.services.artist_auto_processing_service import (
                artist_auto_processing_service,
            )

            # Run auto-processing pipeline for all new artists
            auto_results = artist_auto_processing_service.process_new_artist(
                artist, session
            )
            logger.info(f"Auto-processing results for {artist.name}: {auto_results}")

        except ImportError:
            logger.warning("Artist auto-processing service not available")
        except Exception as e:
            logger.error(f"Auto-processing failed for {artist.name}: {e}")

        # Auto-discover videos if specifically requested
        if artist_data.auto_discover:
            try:
                # Add video discovery logic here if needed
                logger.info(f"Video auto-discovery requested for {artist.name}")
                # TODO: Implement video discovery if not already covered by auto-processing
            except Exception as e:
                logger.error(f"Video discovery failed for {artist.name}: {e}")

        session.commit()
        session.refresh(artist)

        logger.info(f"Created new artist: {artist.name} (ID: {artist.id})")

        return ArtistResponse(
            id=artist.id,
            name=artist.name,
            sort_name=getattr(artist, "sort_name", artist.name),
            folder_path=artist.folder_path,
            imvdb_id=artist.imvdb_id,
            imvdb_slug=getattr(artist, "imvdb_slug", None),
            thumbnail_url=f"/api/artists/{artist.id}/thumbnail",
            biography=getattr(artist, "biography", None),
            formed_year=getattr(artist, "formed_year", None),
            location=getattr(artist, "location", None),
            website=getattr(artist, "website", None),
            wikipedia_url=getattr(artist, "wikipedia_url", None),
            musicbrainz_id=getattr(artist, "musicbrainz_id", None),
            spotify_id=artist.spotify_id,
            monitored=getattr(artist, "monitored", True),
            auto_download=getattr(artist, "auto_download", False),
            video_count=0,
            created_at=artist.created_at,
            updated_at=artist.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating artist: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{artist_id}")
async def update_artist(
    artist_id: int = FastAPIPath(..., ge=1),
    update_data: ArtistUpdateRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update artist information"""
    try:
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Update fields if provided
        update_fields = update_data.dict(exclude_unset=True)

        for field, value in update_fields.items():
            setattr(artist, field, value)

        artist.updated_at = datetime.utcnow()
        session.commit()

        # Get updated artist with video count
        result = (
            session.query(Artist, func.count(Video.id).label("video_count"))
            .outerjoin(Video)
            .filter(Artist.id == artist_id)
            .group_by(Artist.id)
            .first()
        )

        artist, video_count = result

        logger.info(f"Updated artist {artist_id}: {artist.name}")

        artist_response = ArtistResponse(
            id=artist.id,
            name=artist.name,
            sort_name=getattr(artist, "sort_name", artist.name),
            folder_path=artist.folder_path,
            imvdb_id=artist.imvdb_id,
            imvdb_slug=getattr(artist, "imvdb_slug", None),
            thumbnail_url=f"/api/artists/{artist.id}/thumbnail",
            biography=getattr(artist, "biography", None),
            formed_year=getattr(artist, "formed_year", None),
            location=getattr(artist, "location", None),
            website=getattr(artist, "website", None),
            wikipedia_url=getattr(artist, "wikipedia_url", None),
            musicbrainz_id=getattr(artist, "musicbrainz_id", None),
            spotify_id=artist.spotify_id,
            monitored=getattr(
                artist, "monitored", True
            ),  # Default to True for compatibility
            auto_download=getattr(artist, "auto_download", False),  # Default to False
            imvdb_metadata=artist.imvdb_metadata,  # Include metadata for song recommendations
            video_count=video_count or 0,
            created_at=artist.created_at,
            updated_at=artist.updated_at,
        )

        return {
            "success": True,
            "message": f"Artist '{artist.name}' updated successfully",
            "artist": artist_response.dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating artist {artist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{artist_id}")
async def delete_artist(
    artist_id: int = FastAPIPath(..., ge=1),
    delete_videos: bool = Query(False, description="Also delete associated videos"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Delete individual artist"""
    try:
        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        artist_name = artist.name

        # Check if artist has videos
        video_count = session.query(Video).filter(Video.artist_id == artist_id).count()

        if video_count > 0 and not delete_videos:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete artist '{artist_name}' - it has {video_count} associated videos. Use delete_videos=true to delete videos along with the artist.",
            )

        # Handle associated videos if deletion is requested
        if delete_videos and video_count > 0:
            # Delete all videos by this artist
            videos = session.query(Video).filter(Video.artist_id == artist_id).all()

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
            logger.info(f"Deleted {video_count} videos for artist {artist_name}")
        else:
            video_count = 0

        # Delete artist
        session.delete(artist)
        session.commit()

        logger.info(f"Deleted artist: {artist_name} (ID: {artist_id})")

        return {
            "message": f"Artist '{artist_name}' deleted successfully",
            "videos_affected": video_count,
            "videos_deleted": delete_videos,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting artist {artist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# ADVANCED SEARCH AND DISCOVERY OPERATIONS
# ========================================================================================


@router.get("/search/advanced")
async def advanced_search(
    name: Optional[str] = Query(None, description="Artist name search"),
    has_videos: Optional[bool] = Query(None, description="Filter by video existence"),
    has_imvdb: Optional[bool] = Query(None, description="Filter by IMVDb link"),
    formed_after: Optional[int] = Query(None, description="Formed after year"),
    formed_before: Optional[int] = Query(None, description="Formed before year"),
    location: Optional[str] = Query(None, description="Location search"),
    sort_by: str = Query("name", pattern="^(name|video_count|formed_year|created_at)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Advanced search with multiple filters"""
    try:
        # Build base query with video count
        video_count_subquery = (
            session.query(Video.artist_id, func.count(Video.id).label("video_count"))
            .filter(Video.status.in_(["DOWNLOADED", "WANTED", "DOWNLOADING"]))
            .group_by(Video.artist_id)
            .subquery()
        )

        query = session.query(
            Artist,
            func.coalesce(video_count_subquery.c.video_count, 0).label("video_count"),
        ).outerjoin(video_count_subquery, Artist.id == video_count_subquery.c.artist_id)

        # Apply filters
        if name:
            query = query.filter(
                or_(Artist.name.ilike(f"%{name}%"), Artist.sort_name.ilike(f"%{name}%"))
            )

        if has_videos is not None:
            if has_videos:
                query = query.having(
                    func.coalesce(video_count_subquery.c.video_count, 0) > 0
                )
            else:
                query = query.having(
                    func.coalesce(video_count_subquery.c.video_count, 0) == 0
                )

        if has_imvdb is not None:
            if has_imvdb:
                query = query.filter(Artist.imvdb_id.isnot(None))
            else:
                query = query.filter(Artist.imvdb_id.is_(None))

        if formed_after:
            query = query.filter(Artist.formed_year >= formed_after)

        if formed_before:
            query = query.filter(Artist.formed_year <= formed_before)

        if location:
            query = query.filter(Artist.location.ilike(f"%{location}%"))

        # Apply sorting
        if sort_by == "name":
            sort_column = Artist.name
        elif sort_by == "video_count":
            sort_column = "video_count"
        elif sort_by == "formed_year":
            sort_column = Artist.formed_year
        elif sort_by == "created_at":
            sort_column = Artist.created_at
        else:
            sort_column = Artist.name

        if sort_order == "desc":
            if sort_by == "video_count":
                query = query.order_by(desc("video_count"))
            else:
                query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)

        # Get total count
        total_count = query.count()

        # Apply pagination
        results = query.offset(offset).limit(limit).all()

        # Process results
        artists = []
        for artist, video_count in results:
            # Check if artist has thumbnail
            has_thumbnail = bool(
                getattr(artist, "thumbnail_path", None)
                or getattr(artist, "thumbnail_url", None)
            )

            # Check if artist has IMVDB data
            has_imvdb_data = bool(
                artist.imvdb_id or getattr(artist, "imvdb_metadata", None)
            )

            artist_dict = {
                "id": artist.id,
                "name": artist.name,
                "sort_name": getattr(artist, "sort_name", artist.name),
                "folder_path": artist.folder_path,
                "imvdb_id": artist.imvdb_id,
                "formed_year": getattr(artist, "formed_year", None),
                "location": getattr(artist, "location", None),
                "monitored": getattr(
                    artist, "monitored", True
                ),  # Default to True for compatibility
                "auto_download": getattr(
                    artist, "auto_download", False
                ),  # Default to False
                "has_thumbnail": has_thumbnail,
                "has_imvdb_data": has_imvdb_data,
                "video_count": video_count or 0,
                "thumbnail_url": f"/api/artists/{artist.id}/thumbnail",
            }
            artists.append(artist_dict)

        return {
            "artists": artists,
            "search": {
                "filters": {
                    "name": name,
                    "has_videos": has_videos,
                    "has_imvdb": has_imvdb,
                    "formed_after": formed_after,
                    "formed_before": formed_before,
                    "location": location,
                }
            },
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Error in advanced search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_db_session),
):
    """Get search suggestions for artist names"""
    try:
        # Search for artists matching the query
        suggestions = (
            session.query(Artist.name)
            .filter(Artist.name.ilike(f"%{q}%"))
            .limit(limit)
            .all()
        )

        # Extract just the names
        suggestion_list = [s[0] for s in suggestions]

        return {"query": q, "suggestions": suggestion_list}

    except Exception as e:
        logger.error(f"Error getting search suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
