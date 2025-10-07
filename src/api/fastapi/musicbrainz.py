"""
FastAPI MusicBrainz Router
Provides MusicBrainz-specific API endpoints for artist search and metadata
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.musicbrainz")

# Create router
router = APIRouter(prefix="/api/musicbrainz", tags=["musicbrainz"])

# Import MusicBrainz service with error handling
try:
    from src.services.musicbrainz_service import musicbrainz_service
except ImportError:
    logger.warning("MusicBrainz service not available")
    musicbrainz_service = None


@router.post("/search-artist")
async def search_artist(
    data: Dict[str, Any], current_user: dict = Depends(require_authentication)
):
    """Search MusicBrainz for artist information"""
    try:
        if not musicbrainz_service:
            raise HTTPException(
                status_code=503, detail="MusicBrainz service not available"
            )

        artist = data.get("artist")
        if not artist:
            raise HTTPException(status_code=400, detail="Artist name required")

        logger.info(f"Searching MusicBrainz for artist: {artist}")

        # Run MusicBrainz search in background thread since it may be blocking
        result = await asyncio.to_thread(musicbrainz_service.search_artist, artist)

        if not result:
            return {
                "results": [],
                "total": 0,
                "query": artist,
                "service": "musicbrainz",
            }

        # Ensure result is in expected format
        if isinstance(result, dict):
            results = [result]
        elif isinstance(result, list):
            results = result
        else:
            results = []

        return {
            "results": results,
            "total": len(results),
            "query": artist,
            "service": "musicbrainz",
        }

    except Exception as e:
        logger.error(
            f"MusicBrainz search error for '{data.get('artist', 'unknown')}': {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"MusicBrainz search failed: {str(e)}"
        )


@router.get("/artist/{mbid}")
async def get_artist(mbid: str, current_user: dict = Depends(require_authentication)):
    """Get detailed artist information from MusicBrainz by MBID"""
    try:
        if not musicbrainz_service:
            raise HTTPException(
                status_code=503, detail="MusicBrainz service not available"
            )

        logger.info(f"Getting MusicBrainz artist details: {mbid}")
        result = await asyncio.to_thread(musicbrainz_service.get_artist, mbid)

        if not result:
            raise HTTPException(
                status_code=404, detail="Artist not found in MusicBrainz"
            )

        return result

    except Exception as e:
        logger.error(f"MusicBrainz artist details error for '{mbid}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get artist details: {str(e)}"
        )


@router.get("/artist/{mbid}/releases")
async def get_artist_releases(
    mbid: str, limit: int = 25, current_user: dict = Depends(require_authentication)
):
    """Get artist's releases from MusicBrainz"""
    try:
        if not musicbrainz_service:
            raise HTTPException(
                status_code=503, detail="MusicBrainz service not available"
            )

        logger.info(f"Getting MusicBrainz releases for artist: {mbid}")
        result = await asyncio.to_thread(
            musicbrainz_service.get_artist_releases, mbid, limit=limit
        )

        if not result:
            return {"releases": [], "total": 0}

        return result

    except Exception as e:
        logger.error(f"MusicBrainz artist releases error for '{mbid}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get artist releases: {str(e)}"
        )


@router.get("/status")
async def get_musicbrainz_status(current_user: dict = Depends(require_authentication)):
    """Get MusicBrainz service status"""
    try:
        if not musicbrainz_service:
            return {"available": False, "error": "MusicBrainz service not configured"}

        # Test if MusicBrainz service is working with a simple search
        test_result = await asyncio.to_thread(musicbrainz_service.search_artist, "test")

        return {
            "available": True,
            "service": "MusicBrainz API",
            "test_successful": test_result is not None,
        }

    except Exception as e:
        logger.error(f"MusicBrainz status check error: {e}")
        return {"available": False, "error": str(e)}


@router.get("/test")
async def test_connection(current_user: dict = Depends(require_authentication)):
    """Test MusicBrainz API connectivity"""
    try:
        if not musicbrainz_service:
            return {
                "success": False,
                "service": "MusicBrainz",
                "status": "unavailable",
                "error": "MusicBrainz service not available",
            }

        # Run connection test in background thread since it may be blocking
        is_connected = await asyncio.to_thread(musicbrainz_service.test_connection)

        return {
            "success": is_connected,
            "service": "MusicBrainz",
            "status": "connected" if is_connected else "disconnected",
            "enabled": musicbrainz_service.enabled if musicbrainz_service else False,
        }

    except Exception as e:
        logger.error(f"MusicBrainz connection test failed: {e}")
        return {
            "success": False,
            "service": "MusicBrainz",
            "status": "error",
            "error": str(e),
        }
