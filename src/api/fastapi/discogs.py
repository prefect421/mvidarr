"""
FastAPI Discogs Router
Provides Discogs-specific API endpoints for release search and metadata
"""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.discogs")

# Create router
router = APIRouter(prefix="/api/discogs", tags=["discogs"])

# Import Discogs service with error handling
try:
    from src.services.discogs_service import discogs_service
except ImportError:
    logger.warning("Discogs service not available")
    discogs_service = None


@router.post("/search-release")
async def search_release(
    data: Dict[str, Any], current_user: dict = Depends(require_authentication)
):
    """Search Discogs for release information"""
    try:
        if not discogs_service:
            raise HTTPException(status_code=503, detail="Discogs service not available")

        track_name = data.get("track")
        artist_name = data.get("artist")

        if not track_name or not artist_name:
            raise HTTPException(
                status_code=400, detail="Track name and artist name required"
            )

        logger.info(f"Searching Discogs for: {track_name} by {artist_name}")

        # Run Discogs search in background thread since it may be blocking
        result = await asyncio.to_thread(
            discogs_service.search_release, track_name, artist_name
        )

        if not result:
            return {
                "results": [],
                "total": 0,
                "query": {"track": track_name, "artist": artist_name},
                "service": "discogs",
            }

        return {
            "results": result,
            "total": len(result),
            "query": {"track": track_name, "artist": artist_name},
            "service": "discogs",
        }

    except Exception as e:
        logger.error(
            f"Discogs search error for '{data.get('track', 'unknown')}' by '{data.get('artist', 'unknown')}': {e}"
        )
        raise HTTPException(status_code=500, detail=f"Discogs search failed: {str(e)}")


@router.get("/release/{release_id}")
async def get_release(
    release_id: int, current_user: dict = Depends(require_authentication)
):
    """Get detailed release information from Discogs by release ID"""
    try:
        if not discogs_service:
            raise HTTPException(status_code=503, detail="Discogs service not available")

        logger.info(f"Getting Discogs release details: {release_id}")
        result = await asyncio.to_thread(
            discogs_service.get_release_details, release_id
        )

        if not result:
            raise HTTPException(status_code=404, detail="Release not found in Discogs")

        return result

    except Exception as e:
        logger.error(f"Discogs release details error for '{release_id}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get release details: {str(e)}"
        )


@router.get("/status")
async def get_discogs_status(current_user: dict = Depends(require_authentication)):
    """Get Discogs service status"""
    try:
        if not discogs_service:
            return {"available": False, "error": "Discogs service not configured"}

        return {
            "available": True,
            "service": "Discogs API",
            "enabled": discogs_service.enabled,
            "authenticated": discogs_service._token is not None,
        }

    except Exception as e:
        logger.error(f"Discogs status check error: {e}")
        return {"available": False, "error": str(e)}


@router.get("/test")
async def test_connection(current_user: dict = Depends(require_authentication)):
    """Test Discogs API connectivity"""
    try:
        if not discogs_service:
            return {
                "success": False,
                "service": "Discogs",
                "status": "unavailable",
                "error": "Discogs service not available",
            }

        # Run connection test in background thread since it may be blocking
        is_connected = await asyncio.to_thread(discogs_service.test_connection)

        return {
            "success": is_connected,
            "service": "Discogs",
            "status": "connected" if is_connected else "disconnected",
            "enabled": discogs_service.enabled if discogs_service else False,
            "authenticated": (
                discogs_service._token is not None if discogs_service else False
            ),
        }

    except Exception as e:
        logger.error(f"Discogs connection test failed: {e}")
        return {
            "success": False,
            "service": "Discogs",
            "status": "error",
            "error": str(e),
        }
