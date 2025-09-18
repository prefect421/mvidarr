"""
FastAPI Lidarr Router - Migrated from Flask Blueprint
Lidarr API integration for MVidarr
"""

import json
import requests
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.fastapi.auth_dependencies import get_current_user_legacy, require_authentication_legacy
from src.database.connection import get_db
from src.database.models import Artist
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/lidarr",
    tags=["lidarr"],
    responses={
        404: {"description": "Resource not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.lidarr")


# ========================================================================================
# AUTHENTICATION
# ========================================================================================

async def get_current_user():
    """Get current authenticated user"""
    return await get_current_user_legacy()


async def require_authentication(current_user: dict = Depends(get_current_user)):
    """Dependency to require authentication for protected endpoints"""
    return await require_authentication_legacy(current_user)


# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================

class LidarrTestResponse(BaseModel):
    status: str
    message: str
    server_info: Optional[Dict[str, Any]] = None


class SyncLibraryResponse(BaseModel):
    success: bool
    message: str
    processed_count: int
    synced_count: int
    error: Optional[str] = None


class ImportArtistsResponse(BaseModel):
    success: bool
    message: str
    total_artists: int
    monitored_artists: int
    imported_count: int
    error: Optional[str] = None


class SyncAlbumsResponse(BaseModel):
    success: bool
    message: str
    total_albums: int
    processed_count: int
    error: Optional[str] = None


class WantedAlbumsResponse(BaseModel):
    success: bool
    wanted_albums: List[Dict[str, Any]]
    total_wanted: int
    error: Optional[str] = None


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================

def get_lidarr_settings():
    """Get Lidarr settings from database"""
    server_url = SettingsService.get("lidarr_server_url")
    api_key = SettingsService.get("lidarr_api_key")
    
    if not server_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lidarr server URL or API key not configured"
        )
    
    return server_url.rstrip("/"), api_key


def make_lidarr_request(endpoint: str, server_url: str, api_key: str, timeout: int = 30):
    """Make a request to Lidarr API"""
    headers = {"X-Api-Key": api_key}
    url = f"{server_url}/api/v1{endpoint}" if not endpoint.startswith("/api/v1") else f"{server_url}{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Lidarr API request failed: HTTP {response.status_code}"
            )
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Lidarr request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection failed: {str(e)}"
        )


# ========================================================================================
# TEST AND CONFIGURATION ENDPOINTS
# ========================================================================================

@router.post("/test", response_model=LidarrTestResponse)
async def test_lidarr_connection(
    current_user: dict = Depends(require_authentication)
):
    """Test Lidarr server connection and API key"""
    try:
        server_url, api_key = get_lidarr_settings()

        # Test system status endpoint
        headers = {"X-Api-Key": api_key}
        response = requests.get(
            f"{server_url}/api/v1/system/status", headers=headers, timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return LidarrTestResponse(
                status="success",
                message=f'Connected to Lidarr {data.get("version", "unknown")}',
                server_info={
                    "version": data.get("version"),
                    "build_time": data.get("buildTime"),
                    "is_production": data.get("isProduction"),
                    "branch": data.get("branch"),
                },
            )
        else:
            return LidarrTestResponse(
                status="error",
                message=f"Failed to connect to Lidarr: HTTP {response.status_code}",
            )

    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Lidarr connection test failed: {e}")
        return LidarrTestResponse(
            status="error",
            message=f"Connection failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Lidarr test error: {e}")
        return LidarrTestResponse(
            status="error",
            message=f"Test failed: {str(e)}"
        )


# ========================================================================================
# LIBRARY SYNC ENDPOINTS
# ========================================================================================

@router.post("/sync-library", response_model=SyncLibraryResponse)
async def sync_lidarr_library(
    current_user: dict = Depends(require_authentication)
):
    """Sync artist library from Lidarr to MVidarr"""
    try:
        server_url, api_key = get_lidarr_settings()

        # Get all artists from Lidarr
        artists = make_lidarr_request("/artist", server_url, api_key)
        synced_count = 0

        # Process each artist
        with get_db() as session:
            for artist in artists:
                try:
                    # Check if artist already exists in MVidarr
                    existing_artist = (
                        session.query(Artist)
                        .filter_by(name=artist["artistName"])
                        .first()
                    )

                    if not existing_artist:
                        # Add new artist to MVidarr
                        from src.utils.filename_cleanup import FilenameCleanup

                        folder_path = FilenameCleanup.sanitize_folder_name(
                            artist["artistName"]
                        )

                        new_artist = Artist(
                            name=artist["artistName"],
                            imvdb_id=artist.get("foreignArtistId"),
                            monitored=artist.get("monitored", False),
                            source="lidarr",
                            folder_path=folder_path,
                        )
                        session.add(new_artist)
                        synced_count += 1
                        logger.info(f"Added artist from Lidarr: {artist['artistName']}")
                    else:
                        # Update existing artist monitoring status
                        existing_artist.monitored = artist.get("monitored", False)
                        existing_artist.source = "lidarr"

                except Exception as e:
                    logger.error(
                        f"Error processing artist {artist.get('artistName', 'unknown')}: {e}"
                    )
                    continue

            session.commit()

        return SyncLibraryResponse(
            success=True,
            message=f"Successfully synced {synced_count} artists from Lidarr",
            processed_count=len(artists),
            synced_count=synced_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lidarr library sync failed: {e}")
        return SyncLibraryResponse(
            success=False,
            message="Sync failed",
            processed_count=0,
            synced_count=0,
            error=str(e)
        )


@router.post("/import-artists", response_model=ImportArtistsResponse)
async def import_lidarr_artists(
    current_user: dict = Depends(require_authentication)
):
    """Import monitored artists from Lidarr and search for their music videos"""
    try:
        server_url, api_key = get_lidarr_settings()

        # Get monitored artists from Lidarr
        artists = make_lidarr_request("/artist", server_url, api_key)
        monitored_artists = [a for a in artists if a.get("monitored", False)]
        imported_count = 0

        # Process each monitored artist
        with get_db() as session:
            for artist in monitored_artists:
                try:
                    # Check if artist already exists in MVidarr
                    existing_artist = (
                        session.query(Artist)
                        .filter_by(name=artist["artistName"])
                        .first()
                    )

                    if not existing_artist:
                        # Add new artist to MVidarr
                        from src.utils.filename_cleanup import FilenameCleanup

                        folder_path = FilenameCleanup.sanitize_folder_name(
                            artist["artistName"]
                        )

                        new_artist = Artist(
                            name=artist["artistName"],
                            imvdb_id=artist.get("foreignArtistId"),
                            monitored=True,  # Set to monitored since they're monitored in Lidarr
                            source="lidarr",
                            folder_path=folder_path,
                        )
                        session.add(new_artist)
                        imported_count += 1
                        logger.info(
                            f"Imported monitored artist from Lidarr: {artist['artistName']}"
                        )
                    else:
                        # Update existing artist to monitored
                        existing_artist.monitored = True
                        existing_artist.source = "lidarr"

                except Exception as e:
                    logger.error(
                        f"Error importing artist {artist.get('artistName', 'unknown')}: {e}"
                    )
                    continue

            session.commit()

        return ImportArtistsResponse(
            success=True,
            message=f"Successfully imported {imported_count} monitored artists from Lidarr",
            total_artists=len(artists),
            monitored_artists=len(monitored_artists),
            imported_count=imported_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lidarr artist import failed: {e}")
        return ImportArtistsResponse(
            success=False,
            message="Import failed",
            total_artists=0,
            monitored_artists=0,
            imported_count=0,
            error=str(e)
        )


@router.post("/sync-albums", response_model=SyncAlbumsResponse)
async def sync_lidarr_albums(
    current_user: dict = Depends(require_authentication)
):
    """Sync album information from Lidarr to help identify wanted music videos"""
    try:
        server_url, api_key = get_lidarr_settings()

        # Get all albums from Lidarr
        albums = make_lidarr_request("/album", server_url, api_key)
        processed_count = 0

        # Process each album
        for album in albums:
            try:
                # Get artist name from artist ID
                artist_data = make_lidarr_request(f"/artist/{album['artistId']}", server_url, api_key, timeout=10)
                artist_name = artist_data["artistName"]

                # Check if artist exists in MVidarr
                with get_db() as session:
                    existing_artist = (
                        session.query(Artist).filter_by(name=artist_name).first()
                    )

                    if existing_artist:
                        # Log album information for potential video discovery
                        logger.info(
                            f"Lidarr album sync: {artist_name} - {album['title']} ({album.get('releaseDate', 'unknown date')})"
                        )

                        # Store album information in a custom table if needed
                        # For now, we'll just log it for video discovery purposes
                        processed_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing album {album.get('title', 'unknown')}: {e}"
                )
                continue

        return SyncAlbumsResponse(
            success=True,
            message=f"Successfully processed {processed_count} albums from Lidarr",
            total_albums=len(albums),
            processed_count=processed_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lidarr album sync failed: {e}")
        return SyncAlbumsResponse(
            success=False,
            message="Album sync failed",
            total_albums=0,
            processed_count=0,
            error=str(e)
        )


# ========================================================================================
# WANTED ALBUMS ENDPOINT
# ========================================================================================

@router.get("/wanted-albums", response_model=WantedAlbumsResponse)
async def get_wanted_albums(
    current_user: dict = Depends(require_authentication)
):
    """Get list of wanted/missing albums from Lidarr for video discovery"""
    try:
        server_url, api_key = get_lidarr_settings()

        # Get wanted albums from Lidarr
        data = make_lidarr_request("/wanted/missing", server_url, api_key)
        wanted_albums = []

        for album in data.get("records", []):
            try:
                # Get artist name from artist ID
                artist_data = make_lidarr_request(f"/artist/{album['artistId']}", server_url, api_key, timeout=10)
                wanted_albums.append(
                    {
                        "artist": artist_data["artistName"],
                        "album": album["title"],
                        "releaseDate": album.get("releaseDate"),
                        "monitored": album.get("monitored", False),
                    }
                )

            except Exception as e:
                logger.error(
                    f"Error processing wanted album {album.get('title', 'unknown')}: {e}"
                )
                continue

        return WantedAlbumsResponse(
            success=True,
            wanted_albums=wanted_albums,
            total_wanted=len(wanted_albums),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lidarr wanted albums request failed: {e}")
        return WantedAlbumsResponse(
            success=False,
            wanted_albums=[],
            total_wanted=0,
            error=str(e)
        )