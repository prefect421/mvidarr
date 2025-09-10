"""
FastAPI Spotify Router
Provides Spotify-specific API endpoints for artist search and metadata
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, Any, List
import asyncio
import logging

# from src.middleware.fastapi_auth_middleware import require_authentication  # Temporarily disabled
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.spotify")

# Create router
router = APIRouter(prefix="/api/spotify", tags=["spotify"])

# Import Spotify service with error handling
try:
    from src.services.async_spotify_service import get_async_spotify_service
    spotify_available = True
    logger.info("Spotify service imported successfully")
except ImportError as e:
    logger.warning(f"Spotify service not available: {e}")
    spotify_available = False
    get_async_spotify_service = None
except Exception as e:
    logger.error(f"Error importing Spotify service: {e}")
    spotify_available = False
    get_async_spotify_service = None


@router.get("/search/artists")
async def search_artists(
    q: str = Query(..., description="Artist search query"),
    limit: int = Query(10, description="Number of results to return", ge=1, le=50)
):
    """Search Spotify for artists"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Searching Spotify for artists: {q}")
        spotify_service = await get_async_spotify_service()
        result = await spotify_service.search_artist(q, limit=limit)
        
        if not result or not result.get('artists', {}).get('items'):
            return {
                "artists": {
                    "items": [],
                    "total": 0,
                    "limit": limit,
                    "offset": 0
                }
            }
            
        return result
        
    except Exception as e:
        logger.error(f"Spotify artist search error for '{q}': {e}")
        raise HTTPException(status_code=500, detail=f"Spotify search failed: {str(e)}")


@router.get("/artist/{spotify_id}")
async def get_artist(
    spotify_id: str,
):
    """Get detailed artist information from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify artist details: {spotify_id}")
        spotify_service = await get_async_spotify_service()
        result = await spotify_service.get_artist(spotify_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Artist not found on Spotify")
            
        return result
        
    except Exception as e:
        logger.error(f"Spotify artist details error for '{spotify_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get artist details: {str(e)}")


@router.get("/artist/{spotify_id}/albums")
async def get_artist_albums(
    spotify_id: str,
    limit: int = Query(20, description="Number of albums to return", ge=1, le=50),
):
    """Get artist's albums from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify albums for artist: {spotify_id}")
        spotify_service = await get_async_spotify_service()
        result = await spotify_service.get_artist_albums(spotify_id, limit=limit, offset=0)
        
        if not result:
            return {"items": [], "total": 0}
            
        return result
        
    except Exception as e:
        logger.error(f"Spotify artist albums error for '{spotify_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get artist albums: {str(e)}")


@router.get("/artist/{spotify_id}/top-tracks")
async def get_artist_top_tracks(
    spotify_id: str,
    market: str = Query("US", description="Market/country code"),
):
    """Get artist's top tracks from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify top tracks for artist: {spotify_id}")
        spotify_service = await get_async_spotify_service()
        result = await spotify_service.get_artist_top_tracks(spotify_id, country=market)
        
        if not result:
            return {"tracks": []}
            
        return result
        
    except Exception as e:
        logger.error(f"Spotify artist top tracks error for '{spotify_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get artist top tracks: {str(e)}")


@router.get("/artist/{spotify_id}/related-artists")
async def get_related_artists(
    spotify_id: str,
):
    """Get related artists from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify related artists for: {spotify_id}")
        spotify_service = await get_async_spotify_service()
        result = await spotify_service.get_artist_related_artists(spotify_id)
        
        if not result:
            return {"artists": []}
            
        return result
        
    except Exception as e:
        logger.error(f"Spotify related artists error for '{spotify_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get related artists: {str(e)}")


@router.get("/playlists")
async def get_user_playlists(
    limit: int = Query(20, description="Number of playlists to return", ge=1, le=50),
    offset: int = Query(0, description="Offset for pagination", ge=0)
):
    """Get current user's Spotify playlists"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
        
        logger.info("Getting Spotify user playlists")
        spotify_service = await get_async_spotify_service()
        
        # Mock response since this requires OAuth authentication
        # In production, this would require proper user authentication
        return {
            "items": [
                {
                    "id": "mock_playlist_1",
                    "name": "My Music Videos",
                    "description": "Personal collection of music videos",
                    "public": False,
                    "tracks": {"total": 50},
                    "owner": {"id": "user123", "display_name": "User"},
                    "images": []
                },
                {
                    "id": "mock_playlist_2", 
                    "name": "Favorites",
                    "description": "My favorite tracks",
                    "public": True,
                    "tracks": {"total": 25},
                    "owner": {"id": "user123", "display_name": "User"},
                    "images": []
                }
            ],
            "total": 2,
            "limit": limit,
            "offset": offset,
            "next": None,
            "previous": None
        }
        
    except Exception as e:
        logger.error(f"Spotify playlists error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get playlists: {str(e)}")


@router.get("/playlist/{playlist_id}")
async def get_playlist(
    playlist_id: str,
):
    """Get specific Spotify playlist"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify playlist: {playlist_id}")
        
        # Mock response for now
        return {
            "id": playlist_id,
            "name": "Mock Playlist",
            "description": "Mock playlist for development",
            "public": False,
            "tracks": {
                "total": 10,
                "items": []
            },
            "owner": {"id": "user123", "display_name": "User"},
            "images": []
        }
        
    except Exception as e:
        logger.error(f"Spotify playlist error for '{playlist_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get playlist: {str(e)}")


@router.get("/playlist/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: str,
    limit: int = Query(20, description="Number of tracks to return", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
):
    """Get tracks from Spotify playlist"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Getting Spotify playlist tracks: {playlist_id}")
        
        # Mock response
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "next": None,
            "previous": None
        }
        
    except Exception as e:
        logger.error(f"Spotify playlist tracks error for '{playlist_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get playlist tracks: {str(e)}")


@router.get("/search/tracks")
async def search_tracks(
    q: str = Query(..., description="Track search query"),
    limit: int = Query(10, description="Number of results to return", ge=1, le=50),
):
    """Search Spotify for tracks"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Searching Spotify for tracks: {q}")
        spotify_service = await get_async_spotify_service()
        
        # Mock search response for now
        return {
            "tracks": {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": 0
            }
        }
        
    except Exception as e:
        logger.error(f"Spotify track search error for '{q}': {e}")
        raise HTTPException(status_code=500, detail=f"Spotify track search failed: {str(e)}")


@router.get("/search/albums")
async def search_albums(
    q: str = Query(..., description="Album search query"),
    limit: int = Query(10, description="Number of results to return", ge=1, le=50),
):
    """Search Spotify for albums"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Searching Spotify for albums: {q}")
        spotify_service = await get_async_spotify_service()
        
        # Mock search response for now
        return {
            "albums": {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": 0
            }
        }
        
    except Exception as e:
        logger.error(f"Spotify album search error for '{q}': {e}")
        raise HTTPException(status_code=500, detail=f"Spotify album search failed: {str(e)}")


@router.get("/me/profile")
async def get_user_profile(
):
    """Get current user's Spotify profile"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info("Getting Spotify user profile")
        
        # Mock user profile
        return {
            "id": "mock_user_123",
            "display_name": "Mock User",
            "email": "user@example.com",
            "country": "US",
            "followers": {"total": 0},
            "images": [],
            "product": "premium"
        }
        
    except Exception as e:
        logger.error(f"Spotify user profile error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user profile: {str(e)}")


@router.get("/status")
async def get_spotify_status():
    """Get Spotify service status - no authentication required"""
    try:
        if not spotify_available:
            return {
                "available": False,
                "error": "Spotify service not configured",
                "service": "Spotify Web API"
            }
        
        # Don't test actual Spotify connection to avoid timeouts
        # Just return that the service module is available
        return {
            "available": True,
            "authenticated": False,  # Would require OAuth setup
            "service": "Spotify Web API",
            "note": "Service available but requires OAuth authentication for full functionality"
        }
        
    except Exception as e:
        logger.error(f"Spotify status check error: {e}")
        return {
            "available": False,
            "error": str(e),
            "service": "Spotify Web API"
        }