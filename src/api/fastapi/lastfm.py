"""
FastAPI Last.fm Router
Provides Last.fm-specific API endpoints for listening history and artist discovery
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.lastfm")

# Create router
router = APIRouter(prefix="/api/lastfm", tags=["lastfm"])

# Import Last.fm service with error handling
try:
    from src.services.lastfm_service import lastfm_service

    lastfm_available = True
    logger.info("Last.fm service imported successfully")
except ImportError as e:
    logger.warning(f"Last.fm service not available: {e}")
    lastfm_available = False
    lastfm_service = None
except Exception as e:
    logger.error(f"Error importing Last.fm service: {e}")
    lastfm_available = False
    lastfm_service = None


# Pydantic request models
class ImportArtistsRequest(BaseModel):
    username: Optional[str] = None
    period: str = Field(default="overall", description="Time period for top artists")
    limit: int = Field(
        default=50, ge=1, le=200, description="Number of artists to import"
    )
    min_playcount: int = Field(
        default=1, ge=1, description="Minimum play count for import"
    )


class ImportTracksRequest(BaseModel):
    username: Optional[str] = None
    limit: int = Field(
        default=200, ge=1, le=1000, description="Number of tracks to import"
    )


class SyncHistoryRequest(BaseModel):
    username: Optional[str] = None
    limit: int = Field(
        default=200, ge=1, le=1000, description="Number of tracks to sync"
    )


# Status and configuration endpoints
@router.get("/status")
async def get_lastfm_status():
    """Get Last.fm service status - no authentication required"""
    try:
        if not lastfm_available:
            return {
                "configured": False,
                "authenticated": False,
                "error": "Last.fm service not available",
                "service": "Last.fm Web API",
            }

        # Refresh credentials and check configuration
        try:
            lastfm_service.refresh_credentials()
            configured = (
                lastfm_service.api_key is not None
                and lastfm_service.api_secret is not None
            )
        except Exception as e:
            logger.warning(f"Error checking Last.fm configuration: {e}")
            configured = False

        # Check if user has session
        authenticated = lastfm_service.session_key is not None
        username = getattr(lastfm_service, "username", None)

        return {
            "configured": configured,
            "authenticated": authenticated,
            "username": username,
            "service": "Last.fm Web API",
            "api_key": (
                lastfm_service.api_key[:8] + "..." if lastfm_service.api_key else None
            ),
        }

    except Exception as e:
        logger.error(f"Last.fm status check error: {e}")
        return {
            "configured": False,
            "authenticated": False,
            "error": str(e),
            "service": "Last.fm Web API",
        }


@router.post("/test")
async def test_lastfm_connection():
    """Test Last.fm API connection"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        # Refresh credentials
        lastfm_service.refresh_credentials()

        if not lastfm_service.api_key or not lastfm_service.api_secret:
            raise HTTPException(
                status_code=400,
                detail="Last.fm API credentials not configured. Please set lastfm_api_key and lastfm_api_secret in settings.",
            )

        # Test API connection
        try:
            result = lastfm_service.call_api(
                "artist.search", {"artist": "test", "limit": 1}
            )

            if result and "results" in result:
                return {
                    "status": "success",
                    "message": "Last.fm API connection successful",
                    "test_results": len(
                        result["results"].get("artistmatches", {}).get("artist", [])
                    ),
                }
            else:
                raise HTTPException(
                    status_code=500, detail="Last.fm API returned unexpected response"
                )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Last.fm API connection failed: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Last.fm test error: {e}")
        raise HTTPException(status_code=500, detail=f"Last.fm test failed: {str(e)}")


# Authentication endpoints
@router.get("/auth/url")
async def get_auth_url():
    """Get Last.fm authentication URL"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        # Refresh credentials
        lastfm_service.refresh_credentials()

        if not lastfm_service.api_key:
            raise HTTPException(
                status_code=400,
                detail="Last.fm integration not configured. Please set LASTFM_API_KEY and LASTFM_API_SECRET",
            )

        auth_url = lastfm_service.get_auth_url()
        return {"auth_url": auth_url, "configured": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate Last.fm auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def handle_callback(token: Optional[str] = Query(None)):
    """Handle Last.fm authentication callback"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not token:
            raise HTTPException(
                status_code=400, detail="No authentication token received"
            )

        # Get session key
        session_data = lastfm_service.get_session_key(token)

        # Store session data in service (instead of Flask session)
        lastfm_service.session_key = session_data.get("session_key")
        lastfm_service.username = session_data.get("username")

        logger.info(
            f"Last.fm authentication successful for user: {session_data.get('username')}"
        )

        return {
            "success": True,
            "message": "Successfully authenticated with Last.fm",
            "username": session_data.get("username"),
            "subscriber": session_data.get("subscriber"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Last.fm callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# User profile and data endpoints
@router.get("/profile")
async def get_profile(username: Optional[str] = Query(None)):
    """Get Last.fm user profile"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        profile = lastfm_service.get_user_info(username)

        return {
            "profile": profile,
            "authenticated": lastfm_service.session_key is not None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Last.fm profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top/artists")
async def get_top_artists(
    username: Optional[str] = Query(None),
    period: str = Query("overall", description="Time period"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    page: int = Query(1, ge=1, description="Page number"),
):
    """Get user's top artists from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        # Validate period
        valid_periods = ["overall", "7day", "1month", "3month", "6month", "12month"]
        if period not in valid_periods:
            period = "overall"

        top_artists = lastfm_service.get_user_top_artists(username, period, limit, page)

        return {
            "artists": top_artists["artists"],
            "total": top_artists["total"],
            "page": top_artists["page"],
            "per_page": top_artists["per_page"],
            "total_pages": top_artists["total_pages"],
            "period": top_artists["period"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get top artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top/tracks")
async def get_top_tracks(
    username: Optional[str] = Query(None),
    period: str = Query("overall", description="Time period"),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    page: int = Query(1, ge=1, description="Page number"),
):
    """Get user's top tracks from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        # Validate period
        valid_periods = ["overall", "7day", "1month", "3month", "6month", "12month"]
        if period not in valid_periods:
            period = "overall"

        top_tracks = lastfm_service.get_user_top_tracks(username, period, limit, page)

        return {
            "tracks": top_tracks["tracks"],
            "total": top_tracks["total"],
            "page": top_tracks["page"],
            "per_page": top_tracks["per_page"],
            "total_pages": top_tracks["total_pages"],
            "period": top_tracks["period"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get top tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_tracks(
    username: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    page: int = Query(1, ge=1, description="Page number"),
    from_timestamp: Optional[int] = Query(None, alias="from"),
    to_timestamp: Optional[int] = Query(None, alias="to"),
):
    """Get user's recent tracks from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        recent_tracks = lastfm_service.get_recent_tracks(
            username, limit, page, from_timestamp, to_timestamp
        )

        return {
            "tracks": recent_tracks["tracks"],
            "total": recent_tracks["total"],
            "page": recent_tracks["page"],
            "per_page": recent_tracks["per_page"],
            "total_pages": recent_tracks["total_pages"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loved")
async def get_loved_tracks(
    username: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    page: int = Query(1, ge=1, description="Page number"),
):
    """Get user's loved tracks from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        loved_tracks = lastfm_service.get_loved_tracks(username, limit, page)

        return {
            "tracks": loved_tracks["tracks"],
            "total": loved_tracks["total"],
            "page": loved_tracks["page"],
            "per_page": loved_tracks["per_page"],
            "total_pages": loved_tracks["total_pages"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get loved tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artist/{artist_name}")
async def get_artist_info(artist_name: str, username: Optional[str] = Query(None)):
    """Get artist information from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        artist_info = lastfm_service.get_artist_info(artist_name, username)

        return {"artist": artist_info}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artist info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_listening_stats(
    username: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365, description="Number of days for stats"),
):
    """Get detailed listening statistics"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        if not username:
            username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        stats = lastfm_service.get_listening_stats(username, days)

        return {"stats": stats, "username": username}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get listening stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import and synchronization endpoints
@router.post("/import/top-artists")
async def import_top_artists(
    request: ImportArtistsRequest,
    current_user: dict = Depends(require_authentication_legacy)
):
    """Import user's top artists to MVidarr"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        username = request.username
        if not username:
            # Try to get from settings or service
            try:
                from src.services.settings_service import SettingsService

                username = SettingsService.get("lastfm_username", "")
            except:
                pass

            if not username:
                username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        # Validate period
        valid_periods = ["overall", "7day", "1month", "3month", "6month", "12month"]
        period = request.period if request.period in valid_periods else "overall"

        logger.info(
            f"Starting import of top artists for user: {username}, period: {period}"
        )

        results = lastfm_service.import_top_artists(
            username, period, request.limit, request.min_playcount
        )

        return {
            "success": True,
            "message": f"Successfully imported {results['imported_artists']} artists from Last.fm",
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import top artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/loved-tracks")
async def import_loved_tracks(request: ImportTracksRequest):
    """Import user's loved tracks and find music videos"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        username = request.username
        if not username:
            # Try to get from settings or service
            try:
                from src.services.settings_service import SettingsService

                username = SettingsService.get("lastfm_username", "")
            except:
                pass

            if not username:
                username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        logger.info(f"Starting import of loved tracks for user: {username}")

        results = lastfm_service.sync_loved_tracks(username, request.limit)

        return {
            "success": True,
            "message": f"Successfully processed {results['artists_processed']} artists from {results['total_tracks']} loved tracks",
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import loved tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-history")
async def sync_history(request: SyncHistoryRequest):
    """Sync listening history from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        username = request.username
        if not username:
            # Try to get from settings or service
            try:
                from src.services.settings_service import SettingsService

                username = SettingsService.get("lastfm_username", "")
            except:
                pass

            if not username:
                username = getattr(lastfm_service, "username", None)

        if not username:
            raise HTTPException(
                status_code=400, detail="No username provided or not authenticated"
            )

        logger.info(f"Starting sync of listening history for user: {username}")

        results = lastfm_service.sync_loved_tracks(username, request.limit)

        return {
            "success": True,
            "processed_count": results.get("total_tracks", 0),
            "artists_processed": results.get("artists_processed", 0),
            "message": f'Successfully processed {results.get("total_tracks", 0)} tracks from Last.fm history',
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect():
    """Disconnect from Last.fm"""
    try:
        if not lastfm_available:
            raise HTTPException(status_code=503, detail="Last.fm service not available")

        # Clear service data
        lastfm_service.session_key = None
        lastfm_service.username = None

        logger.info("Last.fm disconnected successfully")

        return {"success": True, "message": "Successfully disconnected from Last.fm"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect from Last.fm: {e}")
        raise HTTPException(status_code=500, detail=str(e))
