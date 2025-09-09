"""
FastAPI Spotify Router
Provides Spotify-specific API endpoints for artist search and metadata
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, Any, List
import asyncio
import logging

from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.spotify")

# Create router
router = APIRouter(prefix="/api/spotify", tags=["spotify"])

# Import Spotify service with error handling
try:
    from src.services.async_spotify_service import get_async_spotify_service
    spotify_available = True
except ImportError:
    logger.warning("Spotify service not available")
    spotify_available = False
    get_async_spotify_service = None


@router.get("/search/artists")
async def search_artists(
    q: str = Query(..., description="Artist search query"),
    limit: int = Query(10, description="Number of results to return", ge=1, le=50),
    current_user: dict = Depends(require_authentication)
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
    current_user: dict = Depends(require_authentication)
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
    current_user: dict = Depends(require_authentication)
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
    current_user: dict = Depends(require_authentication)
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
    current_user: dict = Depends(require_authentication)
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


@router.get("/status")
async def get_spotify_status(
    current_user: dict = Depends(require_authentication)
):
    """Get Spotify service status"""
    try:
        if not spotify_available:
            return {
                "available": False,
                "error": "Spotify service not configured"
            }
        
        # Test if Spotify service is working
        spotify_service = await get_async_spotify_service()
        test_result = await spotify_service.search_artist("test", limit=1)
        
        return {
            "available": True,
            "authenticated": test_result is not None,
            "service": "Spotify Web API"
        }
        
    except Exception as e:
        logger.error(f"Spotify status check error: {e}")
        return {
            "available": False,
            "error": str(e)
        }