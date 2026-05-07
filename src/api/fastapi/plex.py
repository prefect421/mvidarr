"""
FastAPI Plex Router - Migrated from Flask Blueprint
Plex API endpoints for library synchronization and metadata exchange
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.services.plex_service import plex_service
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/plex",
    tags=["plex"],
    responses={
        404: {"description": "Resource not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.plex")
# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================


class PlexStatusResponse(BaseModel):
    configured: bool
    server_url: Optional[str] = None
    token: Optional[str] = None
    connected: bool
    server_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LibrariesResponse(BaseModel):
    libraries: List[Dict[str, Any]]
    count: int


class MusicLibraryResponse(BaseModel):
    found: bool
    library: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class ArtistsResponse(BaseModel):
    artists: List[Dict[str, Any]]
    count: int


class AlbumsResponse(BaseModel):
    albums: List[Dict[str, Any]]
    count: int


class TracksResponse(BaseModel):
    tracks: List[Dict[str, Any]]
    count: int


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    count: int
    query: str


class SyncFromPlexRequest(BaseModel):
    limit: int = 100


class SyncFromPlexResponse(BaseModel):
    success: bool
    message: str
    results: Dict[str, Any]


class SyncToPlexResponse(BaseModel):
    success: bool
    message: str
    results: Dict[str, Any]


class ArtistStatsResponse(BaseModel):
    artist_name: str
    stats: Dict[str, Any]


class RecentlyPlayedResponse(BaseModel):
    tracks: List[Dict[str, Any]]
    count: int


class LibraryStatsResponse(BaseModel):
    stats: Dict[str, Any]


class CreatePlaylistRequest(BaseModel):
    name: str
    track_keys: List[str]


class CreatePlaylistResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    playlist_id: Optional[str] = None
    error: Optional[str] = None


class ConnectionTestResponse(BaseModel):
    connected: bool
    server_name: Optional[str] = None
    version: Optional[str] = None
    platform: Optional[str] = None
    platform_version: Optional[str] = None
    error: Optional[str] = None


class TestIntegrationResponse(BaseModel):
    status: str
    message: str
    server_name: Optional[str] = None
    version: Optional[str] = None
    platform: Optional[str] = None


class SyncLibraryRequest(BaseModel):
    limit: int = 100


class SyncLibraryResponse(BaseModel):
    success: bool
    processed_count: int
    imported_count: int
    message: str
    error: Optional[str] = None


class ImportArtistsRequest(BaseModel):
    limit: int = 100


class ImportArtistsResponse(BaseModel):
    success: bool
    imported_count: int
    total_artists: int
    message: str
    error: Optional[str] = None


# ========================================================================================
# STATUS AND CONFIGURATION ENDPOINTS
# ========================================================================================


@router.get("/status", response_model=PlexStatusResponse)
async def get_status(current_user: dict = Depends(require_authentication)):
    """Get Plex integration status"""
    try:
        # Check if Plex is configured
        configured = plex_service.server_url and plex_service.server_token is not None

        status_response = PlexStatusResponse(
            configured=configured,
            server_url=plex_service.server_url,
            token=(
                plex_service.server_token[:8] + "..."
                if plex_service.server_token
                else None
            ),
            connected=False,
            server_info=None,
        )

        if configured:
            # Test connection
            connection_test = plex_service.test_connection()
            status_response.connected = connection_test["connected"]

            if connection_test["connected"]:
                status_response.server_info = {
                    "name": connection_test["server_name"],
                    "version": connection_test["version"],
                    "platform": connection_test["platform"],
                    "platform_version": connection_test["platform_version"],
                }
            else:
                status_response.error = connection_test.get("error")

        return status_response

    except Exception as e:
        logger.error(f"Failed to get Plex status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(current_user: dict = Depends(require_authentication)):
    """Test connection to Plex server"""
    try:
        result = plex_service.test_connection()

        return ConnectionTestResponse(**result)

    except Exception as e:
        logger.error(f"Failed to test Plex connection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/test", response_model=TestIntegrationResponse)
async def test_plex_integration(current_user: dict = Depends(require_authentication)):
    """Test Plex integration for settings page"""
    try:
        # Check if Plex is configured
        if not plex_service.server_url or not plex_service.server_token:
            return TestIntegrationResponse(
                status="error",
                message="Plex server not configured. Please set plex_server_url and plex_token in settings.",
            )

        # Test connection
        result = plex_service.test_connection()

        if result["connected"]:
            return TestIntegrationResponse(
                status="success",
                message="Plex server connection successful",
                server_name=result.get("server_name"),
                version=result.get("version"),
                platform=result.get("platform"),
            )
        else:
            return TestIntegrationResponse(
                status="error",
                message=f'Plex server connection failed: {result.get("error", "Unknown error")}',
            )

    except Exception as e:
        logger.error(f"Plex integration test failed: {e}")
        return TestIntegrationResponse(
            status="error",
            message=f"Plex integration test failed: {str(e)}",
        )


# ========================================================================================
# LIBRARY ENDPOINTS
# ========================================================================================


@router.get("/libraries", response_model=LibrariesResponse)
async def get_libraries(current_user: dict = Depends(require_authentication)):
    """Get all Plex libraries"""
    try:
        libraries = plex_service.get_libraries()

        return LibrariesResponse(libraries=libraries, count=len(libraries))

    except Exception as e:
        logger.error(f"Failed to get Plex libraries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/music-library", response_model=MusicLibraryResponse)
async def get_music_library(current_user: dict = Depends(require_authentication)):
    """Get the music library from Plex"""
    try:
        music_library = plex_service.get_music_library()

        if music_library:
            return MusicLibraryResponse(found=True, library=music_library)
        else:
            return MusicLibraryResponse(
                found=False, message="No music library found in Plex"
            )

    except Exception as e:
        logger.error(f"Failed to get music library: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/artists", response_model=ArtistsResponse)
async def get_artists(
    library_key: Optional[str] = Query(None, description="Library key to filter by"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(require_authentication),
):
    """Get artists from Plex music library"""
    try:
        artists = plex_service.get_library_artists(library_key)

        # Apply limit
        if limit > 0:
            artists = artists[:limit]

        return ArtistsResponse(artists=artists, count=len(artists))

    except Exception as e:
        logger.error(f"Failed to get Plex artists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/artists/{artist_key}/albums", response_model=AlbumsResponse)
async def get_artist_albums(
    artist_key: str, current_user: dict = Depends(require_authentication)
):
    """Get albums for a specific artist"""
    try:
        albums = plex_service.get_artist_albums(artist_key)

        return AlbumsResponse(albums=albums, count=len(albums))

    except Exception as e:
        logger.error(f"Failed to get artist albums: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/albums/{album_key}/tracks", response_model=TracksResponse)
async def get_album_tracks(
    album_key: str, current_user: dict = Depends(require_authentication)
):
    """Get tracks for a specific album"""
    try:
        tracks = plex_service.get_album_tracks(album_key)

        return TracksResponse(tracks=tracks, count=len(tracks))

    except Exception as e:
        logger.error(f"Failed to get album tracks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/search", response_model=SearchResponse)
async def search_library(
    query: str = Query(..., description="Search query"),
    library_key: Optional[str] = Query(None, description="Library key to search in"),
    current_user: dict = Depends(require_authentication),
):
    """Search Plex library"""
    try:
        results = plex_service.search_library(query, library_key)

        return SearchResponse(results=results, count=len(results), query=query)

    except Exception as e:
        logger.error(f"Failed to search Plex library: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# SYNCHRONIZATION ENDPOINTS
# ========================================================================================


@router.post("/sync/from-plex", response_model=SyncFromPlexResponse)
async def sync_from_plex(
    request: SyncFromPlexRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Sync artists from Plex to MVidarr"""
    try:
        logger.info(f"Starting sync from Plex with limit: {request.limit}")

        results = plex_service.sync_artists_to_mvidarr(request.limit)

        return SyncFromPlexResponse(
            success=True,
            message=f"Successfully synced {results['imported_artists']} artists from Plex",
            results=results,
        )

    except Exception as e:
        logger.error(f"Failed to sync from Plex: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/sync/to-plex", response_model=SyncToPlexResponse)
async def sync_to_plex(current_user: dict = Depends(require_authentication)):
    """Sync MVidarr artists to Plex for matching"""
    try:
        logger.info("Starting sync to Plex for artist matching")

        results = plex_service.sync_mvidarr_to_plex()

        return SyncToPlexResponse(
            success=True,
            message=f"Successfully matched {results['matched_artists']} artists with Plex",
            results=results,
        )

    except Exception as e:
        logger.error(f"Failed to sync to Plex: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/sync-library", response_model=SyncLibraryResponse)
async def sync_library(
    request: SyncLibraryRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Sync Plex library for settings page"""
    try:
        # Sync artists from Plex
        results = plex_service.sync_artists_to_mvidarr(request.limit)

        return SyncLibraryResponse(
            success=True,
            processed_count=results.get("total_artists", 0),
            imported_count=results.get("imported_artists", 0),
            message=f'Successfully processed {results.get("total_artists", 0)} artists from Plex library',
        )

    except Exception as e:
        logger.error(f"Failed to sync library: {e}")
        return SyncLibraryResponse(
            success=False,
            processed_count=0,
            imported_count=0,
            message="Failed to sync library",
            error=str(e),
        )


@router.post("/import-artists", response_model=ImportArtistsResponse)
async def import_artists(
    request: ImportArtistsRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Import artists from Plex for settings page"""
    try:
        # Import artists from Plex
        results = plex_service.sync_artists_to_mvidarr(request.limit)

        return ImportArtistsResponse(
            success=True,
            imported_count=results.get("imported_artists", 0),
            total_artists=results.get("total_artists", 0),
            message=f'Successfully imported {results.get("imported_artists", 0)} artists from Plex',
        )

    except Exception as e:
        logger.error(f"Failed to import artists: {e}")
        return ImportArtistsResponse(
            success=False,
            imported_count=0,
            total_artists=0,
            message="Failed to import artists",
            error=str(e),
        )


# ========================================================================================
# STATISTICS AND ANALYTICS ENDPOINTS
# ========================================================================================


@router.get("/artist/{artist_name}/stats", response_model=ArtistStatsResponse)
async def get_artist_stats(
    artist_name: str, current_user: dict = Depends(require_authentication)
):
    """Get listening statistics for an artist"""
    try:
        stats = plex_service.get_artist_listening_stats(artist_name)

        return ArtistStatsResponse(artist_name=artist_name, stats=stats)

    except Exception as e:
        logger.error(f"Failed to get artist stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/recently-played", response_model=RecentlyPlayedResponse)
async def get_recently_played(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_authentication),
):
    """Get recently played tracks from Plex"""
    try:
        recently_played = plex_service.get_recently_played(limit)

        return RecentlyPlayedResponse(
            tracks=recently_played, count=len(recently_played)
        )

    except Exception as e:
        logger.error(f"Failed to get recently played: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/library/stats", response_model=LibraryStatsResponse)
async def get_library_stats(current_user: dict = Depends(require_authentication)):
    """Get overall library statistics"""
    try:
        stats = plex_service.get_library_stats()

        return LibraryStatsResponse(stats=stats)

    except Exception as e:
        logger.error(f"Failed to get library stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# PLAYLIST ENDPOINTS
# ========================================================================================


@router.post("/playlists", response_model=CreatePlaylistResponse)
async def create_playlist(
    request: CreatePlaylistRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Create a playlist in Plex"""
    try:
        result = plex_service.create_playlist(request.name, request.track_keys)

        if result["success"]:
            return CreatePlaylistResponse(
                success=True,
                message=f"Created playlist: {request.name}",
                playlist_id=result.get("playlist_id"),
            )
        else:
            return CreatePlaylistResponse(
                success=False, error=result.get("error", "Failed to create playlist")
            )

    except Exception as e:
        logger.error(f"Failed to create playlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
