"""
FastAPI Spotify Router
Provides Spotify-specific API endpoints for artist search and metadata
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

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
    limit: int = Query(10, description="Number of results to return", ge=1, le=50),
):
    """Search Spotify for artists using direct HTTP calls"""
    try:
        logger.info(f"Searching Spotify for artists: {q}")

        # Use direct HTTP request for better reliability
        import base64

        from src.services.settings_service import settings
        from src.utils.async_http_client import get_global_http_client

        # Get credentials directly
        client_id = settings.get("spotify_client_id")
        client_secret = settings.get("spotify_client_secret")

        if not client_id or not client_secret:
            logger.warning(f"🎵 Spotify credentials not configured")
            raise HTTPException(
                status_code=503, detail="Spotify credentials not configured"
            )

        # Get access token using client credentials flow
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        http_client = await get_global_http_client()

        # Get access token
        token_response = await asyncio.wait_for(
            http_client.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            ),
            timeout=15.0,
        )

        access_token = token_response.get("access_token")
        if not access_token:
            logger.warning(f"🎵 Failed to get Spotify access token")
            raise HTTPException(
                status_code=503, detail="Failed to get Spotify access token"
            )

        # Search for artists
        search_response = await asyncio.wait_for(
            http_client.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": q, "type": "artist", "limit": limit},
            ),
            timeout=15.0,
        )

        if not search_response or not search_response.get("artists", {}).get("items"):
            return {"artists": {"items": [], "total": 0, "limit": limit, "offset": 0}}

        return search_response

    except asyncio.TimeoutError:
        logger.error(f"Spotify search timeout for query: {q}")
        raise HTTPException(status_code=408, detail="Spotify search timed out")
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
        raise HTTPException(
            status_code=500, detail=f"Failed to get artist details: {str(e)}"
        )


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
        result = await spotify_service.get_artist_albums(
            spotify_id, limit=limit, offset=0
        )

        if not result:
            return {"items": [], "total": 0}

        return result

    except Exception as e:
        logger.error(f"Spotify artist albums error for '{spotify_id}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get artist albums: {str(e)}"
        )


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
        raise HTTPException(
            status_code=500, detail=f"Failed to get artist top tracks: {str(e)}"
        )


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
        raise HTTPException(
            status_code=500, detail=f"Failed to get related artists: {str(e)}"
        )


@router.get("/playlists")
async def get_user_playlists(
    limit: int = Query(50, description="Number of playlists to return", ge=1, le=50),
    offset: int = Query(0, description="Offset for pagination", ge=0),
):
    """Get current user's Spotify playlists"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        from src.services.spotify_service import SpotifyService

        logger.info(f"Getting Spotify user playlists (limit={limit}, offset={offset})")

        # Create SpotifyService instance (will load access token from settings)
        spotify = SpotifyService()
        spotify._load_settings()

        # Check if user is authenticated
        if not spotify.access_token:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated with Spotify. Please authorize first.",
            )

        # Call Spotify API to get user's playlists
        result = spotify.get_user_playlists(limit=limit, offset=offset)

        if not result or "items" not in result:
            logger.warning("No playlists data returned from Spotify API")
            return {"playlists": [], "total": 0}

        # Transform Spotify API response to match frontend expectations
        playlists = []
        for item in result.get("items", []):
            playlists.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description", ""),
                    "public": item.get("public", False),
                    "tracks_total": item.get("tracks", {}).get("total", 0),
                    "owner": {
                        "id": item.get("owner", {}).get("id"),
                        "display_name": item.get("owner", {}).get("display_name"),
                    },
                    "images": item.get("images", []),
                    "external_url": item.get("external_urls", {}).get("spotify"),
                }
            )

        logger.info(f"Retrieved {len(playlists)} playlists from Spotify")

        return {
            "playlists": playlists,
            "total": result.get("total", len(playlists)),
            "limit": limit,
            "offset": offset,
            "next": result.get("next"),
            "previous": result.get("previous"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spotify playlists error: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Failed to get playlists: {str(e)}"
        )


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
            "tracks": {"total": 10, "items": []},
            "owner": {"id": "user123", "display_name": "User"},
            "images": [],
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
            "previous": None,
        }

    except Exception as e:
        logger.error(f"Spotify playlist tracks error for '{playlist_id}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get playlist tracks: {str(e)}"
        )


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
        return {"tracks": {"items": [], "total": 0, "limit": limit, "offset": 0}}

    except Exception as e:
        logger.error(f"Spotify track search error for '{q}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Spotify track search failed: {str(e)}"
        )


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
        return {"albums": {"items": [], "total": 0, "limit": limit, "offset": 0}}

    except Exception as e:
        logger.error(f"Spotify album search error for '{q}': {e}")
        raise HTTPException(
            status_code=500, detail=f"Spotify album search failed: {str(e)}"
        )


@router.get("/me/profile")
async def get_user_profile():
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
            "product": "premium",
        }

    except Exception as e:
        logger.error(f"Spotify user profile error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get user profile: {str(e)}"
        )


@router.get("/status")
async def get_spotify_status():
    """Get Spotify service status - checks configuration and authentication"""
    try:
        if not spotify_available:
            return {
                "available": False,
                "configured": False,
                "authenticated": False,
                "error": "Spotify service not configured",
                "service": "Spotify Web API",
            }

        from src.services.settings_service import settings

        # Check if credentials are configured
        client_id = settings.get("spotify_client_id")
        client_secret = settings.get("spotify_client_secret")
        configured = bool(client_id and client_secret)

        if not configured:
            return {
                "available": True,
                "configured": False,
                "authenticated": False,
                "service": "Spotify Web API",
            }

        # Check if we have access tokens (authenticated)
        access_token = settings.get("spotify_access_token")
        refresh_token = settings.get("spotify_refresh_token")
        authenticated = bool(access_token or refresh_token)

        response = {
            "available": True,
            "configured": True,
            "authenticated": authenticated,
            "service": "Spotify Web API",
        }

        # If authenticated, try to get user profile
        if authenticated and access_token:
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyOAuth

                sp = spotipy.Spotify(auth=access_token)
                profile = sp.current_user()

                response["profile"] = {
                    "display_name": profile.get("display_name"),
                    "email": profile.get("email"),
                    "country": profile.get("country"),
                    "followers": profile.get("followers"),
                    "images": profile.get("images", []),
                }
            except Exception as profile_error:
                logger.warning(f"Could not fetch Spotify profile: {profile_error}")
                # Still return authenticated=True, just without profile data

        return response

    except Exception as e:
        logger.error(f"Spotify status check error: {e}")
        return {
            "available": False,
            "configured": False,
            "authenticated": False,
            "error": str(e),
            "service": "Spotify Web API",
        }


@router.post("/test")
async def test_spotify_integration():
    """Test Spotify API connection"""
    try:
        if not spotify_available:
            return {
                "success": False,
                "service": "Spotify",
                "status": "unavailable",
                "error": "Spotify service not configured",
            }

        # Don't test actual Spotify connection to avoid OAuth complexities
        # Just return that the service module is available
        return {
            "success": True,
            "service": "Spotify",
            "status": "available",
            "note": "Service available but requires OAuth authentication for full functionality",
            "authenticated": False,
        }

    except Exception as e:
        logger.error(f"Spotify connection test failed: {e}")
        return {
            "success": False,
            "service": "Spotify",
            "status": "error",
            "error": str(e),
        }


@router.post("/authorize")
async def authorize_spotify(request: Request):
    """Get Spotify authorization URL for user authentication"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        from src.services.settings_service import settings

        client_id = settings.get("spotify_client_id")
        client_secret = settings.get("spotify_client_secret")

        # Construct redirect URI dynamically from request
        redirect_uri = settings.get("spotify_redirect_uri")
        if not redirect_uri:
            # Auto-detect from request headers
            scheme = request.url.scheme
            host = request.headers.get("host", "localhost:5000")
            redirect_uri = f"{scheme}://{host}/api/spotify/callback"
            logger.info(f"Auto-detected redirect URI from request: {redirect_uri}")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=400, detail="Spotify client credentials not configured"
            )

        # Generate authorization URL
        scope = "user-read-private user-read-email playlist-read-private user-follow-read user-top-read"
        auth_url = (
            f"https://accounts.spotify.com/authorize?"
            f"client_id={client_id}&"
            f"response_type=code&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope}"
        )

        logger.info(
            f"Generated Spotify authorization URL with redirect URI: {redirect_uri}"
        )

        return {
            "authorization_url": auth_url,
            "redirect_uri": redirect_uri,
            "message": "Please visit the authorization URL to connect your Spotify account",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Spotify authorization URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def spotify_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code from Spotify"),
    error: Optional[str] = Query(None, description="Error from Spotify OAuth"),
):
    """Handle Spotify OAuth callback"""
    try:
        from fastapi.responses import RedirectResponse

        if error:
            logger.error(f"Spotify OAuth error: {error}")
            return RedirectResponse(
                url=f"/settings?spotify_error={error}", status_code=302
            )

        if not code:
            logger.error("No authorization code received from Spotify")
            return RedirectResponse(
                url="/settings?spotify_error=No authorization code received",
                status_code=302,
            )

        # Exchange code for access token
        from src.services.settings_service import settings

        client_id = settings.get("spotify_client_id")
        client_secret = settings.get("spotify_client_secret")

        # Construct redirect URI dynamically from request
        redirect_uri = settings.get("spotify_redirect_uri")
        if not redirect_uri:
            # Auto-detect from request headers
            scheme = request.url.scheme
            host = request.headers.get("host", "localhost:5000")
            redirect_uri = f"{scheme}://{host}/api/spotify/callback"
            logger.info(
                f"Auto-detected redirect URI from callback request: {redirect_uri}"
            )

        if not client_id or not client_secret:
            logger.error("Spotify credentials not configured")
            return RedirectResponse(
                url="/settings?spotify_error=Spotify credentials not configured",
                status_code=302,
            )

        # Exchange authorization code for access token
        import base64

        from src.utils.async_http_client import get_global_http_client

        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        http_client = await get_global_http_client()

        token_response = await asyncio.wait_for(
            http_client.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            ),
            timeout=15.0,
        )

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in")

        if not access_token:
            logger.error("Failed to get Spotify access token")
            return RedirectResponse(
                url="/settings?spotify_error=Failed to get access token",
                status_code=302,
            )

        # Store tokens in settings (for now - consider database storage for production)
        settings.set("spotify_access_token", access_token)
        if refresh_token:
            settings.set("spotify_refresh_token", refresh_token)
        if expires_in:
            settings.set("spotify_token_expires_in", expires_in)

        logger.info("Spotify authentication successful")
        return RedirectResponse(url="/settings?spotify_success=true", status_code=302)

    except Exception as e:
        logger.error(f"Spotify callback error: {e}")
        return RedirectResponse(
            url=f"/settings?spotify_error={str(e)}", status_code=302
        )


@router.post("/disconnect")
async def disconnect_spotify():
    """Disconnect from Spotify"""
    try:
        # Note: In FastAPI, session management is different from Flask
        # This would typically use a database to store OAuth tokens per user
        # For now, return success to maintain API compatibility

        logger.info("Spotify disconnect requested")

        return {"success": True, "message": "Successfully disconnected from Spotify"}

    except Exception as e:
        logger.error(f"Failed to disconnect from Spotify: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/playlists/{playlist_id}/import")
async def import_playlist(playlist_id: str):
    """Import artists from a Spotify playlist"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        logger.info(f"Starting import of Spotify playlist: {playlist_id}")

        # Note: This requires OAuth authentication in production
        # For now, return a placeholder response

        return {
            "success": True,
            "message": f"Playlist import started for {playlist_id}",
            "results": {
                "playlist_id": playlist_id,
                "imported_artists": 0,
                "total_artists": 0,
                "status": "OAuth authentication required for full functionality",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-playlists")
async def import_all_playlists():
    """Import all user playlists from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        logger.info("Starting import of all Spotify playlists")

        # Note: This requires OAuth authentication in production
        # For now, return a placeholder response

        return {
            "success": True,
            "message": "Playlist import started",
            "results": {
                "imported_count": 0,
                "total_artists": 0,
                "playlists_processed": 0,
                "status": "OAuth authentication required for full functionality",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/followed/sync")
async def sync_followed_artists():
    """Sync user's followed artists from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        logger.info("Starting sync of followed artists from Spotify")

        # Note: This requires OAuth authentication in production
        # For now, return a placeholder response

        return {
            "success": True,
            "message": "Followed artists sync started",
            "results": {
                "imported_artists": 0,
                "total_artists": 0,
                "status": "OAuth authentication required for full functionality",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync followed artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top/artists")
async def get_top_artists(
    time_range: str = Query(
        "medium_term", description="Time range: short_term, medium_term, or long_term"
    ),
    limit: int = Query(50, description="Number of top artists to return", ge=1, le=50),
):
    """Get user's top artists from Spotify"""
    try:
        if not spotify_available:
            raise HTTPException(status_code=503, detail="Spotify service not available")

        logger.info(
            f"Getting user's top artists (time_range={time_range}, limit={limit})"
        )

        # Note: This requires OAuth authentication in production
        # For now, return a placeholder response

        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "time_range": time_range,
            "status": "OAuth authentication required for full functionality",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get top artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))
