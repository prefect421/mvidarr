"""
Async Spotify API integration service for importing playlists and discovering music videos
"""

import asyncio
import base64
import difflib
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlencode

import aiohttp
from sqlalchemy import and_, func, or_

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import settings
from src.utils.async_http_client import CircuitBreakerOpenError, get_global_http_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.async_spotify")


@dataclass
class SpotifyTokenInfo:
    """Spotify token information"""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None


class AsyncSpotifyService:
    """Async service for Spotify API integration"""

    def __init__(self):
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"

        # Thread-safe token management (lazy initialization to avoid event loop issues)
        self._token_info: Optional[SpotifyTokenInfo] = None
        self._token_lock: Optional[asyncio.Lock] = None

        # Cache for settings to avoid repeated calls
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None
        self._redirect_uri: Optional[str] = None
        self._settings_loaded = False
        self._settings_lock: Optional[asyncio.Lock] = None

    async def _get_token_lock(self) -> asyncio.Lock:
        """Get token lock, creating it if needed (lazy initialization)"""
        if self._token_lock is None:
            # Always create lock in the current running loop context
            self._token_lock = asyncio.Lock()
        return self._token_lock

    async def _get_settings_lock(self) -> asyncio.Lock:
        """Get settings lock, creating it if needed (lazy initialization)"""
        if self._settings_lock is None:
            # Always create lock in the current running loop context
            self._settings_lock = asyncio.Lock()
        return self._settings_lock

    async def _load_settings(self):
        """Load settings once and cache them (thread-safe)"""
        if self._settings_loaded:
            return

        settings_lock = await self._get_settings_lock()
        async with settings_lock:
            if self._settings_loaded:
                return

            try:
                logger.debug("Loading Spotify settings from database")
                # Note: settings.get() is sync - we might need to make this async too
                self._client_id = settings.get("spotify_client_id")
                self._client_secret = settings.get("spotify_client_secret")
                self._redirect_uri = settings.get("spotify_redirect_uri")

                if not self._client_id or not self._client_secret:
                    logger.warning("Spotify credentials not configured")
                    raise ValueError("Spotify client credentials not configured")

                self._settings_loaded = True
                logger.debug("Spotify settings loaded successfully")

            except Exception as e:
                logger.error(f"Failed to load Spotify settings: {e}")
                raise

    @property
    async def client_id(self) -> str:
        """Get client ID, loading settings if needed"""
        await self._load_settings()
        return self._client_id

    @property
    async def client_secret(self) -> str:
        """Get client secret, loading settings if needed"""
        await self._load_settings()
        return self._client_secret

    @property
    async def redirect_uri(self) -> str:
        """Get redirect URI, loading settings if needed"""
        await self._load_settings()
        return self._redirect_uri

    async def get_auth_url(self, scopes: List[str] = None, state: str = None) -> str:
        """Generate Spotify authorization URL"""
        if scopes is None:
            scopes = [
                "playlist-read-private",
                "playlist-read-collaborative",
                "user-library-read",
                "user-read-private",
            ]

        client_id = await self.client_id
        redirect_uri = await self.redirect_uri

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
        }

        if state:
            params["state"] = state

        auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
        logger.info("Generated Spotify authorization URL")
        return auth_url

    async def exchange_code_for_token(self, code: str) -> SpotifyTokenInfo:
        """Exchange authorization code for access token"""
        client_id = await self.client_id
        client_secret = await self.client_secret
        redirect_uri = await self.redirect_uri

        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        try:
            http_client = await get_global_http_client()
            response_data = await http_client.post(
                self.auth_url, headers=headers, data=data
            )

            # Create token info
            expires_in = response_data.get("expires_in", 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            token_info = SpotifyTokenInfo(
                access_token=response_data.get("access_token"),
                refresh_token=response_data.get("refresh_token"),
                token_type=response_data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=response_data.get("scope"),
            )

            # Store token info
            token_lock = await self._get_token_lock()
            async with token_lock:
                self._token_info = token_info

            logger.info("Successfully obtained Spotify access token")
            return token_info

        except Exception as e:
            logger.error(f"Failed to get Spotify access token: {e}")
            raise

    async def refresh_access_token(self) -> SpotifyTokenInfo:
        """Refresh access token using refresh token"""
        token_lock = await self._get_token_lock()
        async with token_lock:
            if not self._token_info or not self._token_info.refresh_token:
                raise ValueError("No refresh token available")

            client_id = await self.client_id
            client_secret = await self.client_secret

            credentials = f"{client_id}:{client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._token_info.refresh_token,
            }

            try:
                http_client = await get_global_http_client()
                response_data = await http_client.post(
                    self.auth_url, headers=headers, data=data
                )

                # Update token info
                expires_in = response_data.get("expires_in", 3600)
                expires_at = datetime.now() + timedelta(seconds=expires_in)

                self._token_info.access_token = response_data.get("access_token")
                self._token_info.expires_at = expires_at

                # Update refresh token if provided
                if response_data.get("refresh_token"):
                    self._token_info.refresh_token = response_data["refresh_token"]

                logger.info("Successfully refreshed Spotify access token")
                return self._token_info

            except Exception as e:
                logger.error(f"Failed to refresh Spotify access token: {e}")
                raise

    async def get_client_credentials_token(self) -> SpotifyTokenInfo:
        """Get access token using client credentials flow"""
        client_id = await self.client_id
        client_secret = await self.client_secret

        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "client_credentials"}

        try:
            http_client = await get_global_http_client()
            response_data = await http_client.post(
                self.auth_url, headers=headers, data=data
            )

            expires_in = response_data.get("expires_in", 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            token_info = SpotifyTokenInfo(
                access_token=response_data.get("access_token"),
                token_type=response_data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=response_data.get("scope"),
            )

            token_lock = await self._get_token_lock()
            async with token_lock:
                self._token_info = token_info

            logger.info("Successfully obtained Spotify client credentials token")
            return token_info

        except Exception as e:
            logger.error(f"Failed to get Spotify client credentials token: {e}")
            raise

    async def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        token_lock = await self._get_token_lock()
        async with token_lock:
            if not self._token_info:
                # Try to get client credentials token
                await self.get_client_credentials_token()
                return

            # Check if token is expired
            if (
                self._token_info.expires_at
                and datetime.now() >= self._token_info.expires_at
            ):

                if self._token_info.refresh_token:
                    await self.refresh_access_token()
                else:
                    # Get new client credentials token
                    await self.get_client_credentials_token()

    async def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict:
        """Make authenticated request to Spotify API"""
        await self._ensure_valid_token()

        token_lock = await self._get_token_lock()
        async with token_lock:
            access_token = self._token_info.access_token

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            http_client = await get_global_http_client()
            response = await http_client.request(
                method=method, url=url, headers=headers, params=params, json=json_data
            )
            return response

        except CircuitBreakerOpenError as e:
            logger.warning(f"Spotify API circuit breaker open: {e}")
            raise
        except Exception as e:
            logger.error(f"Spotify API request failed: {e}")
            raise

    async def get_user_profile(self) -> Dict:
        """Get current user's Spotify profile"""
        return await self._make_request("me")

    async def get_user_playlists(self, limit: int = 50, offset: int = 0) -> Dict:
        """Get user's playlists"""
        params = {"limit": limit, "offset": offset}
        return await self._make_request("me/playlists", params=params)

    async def get_playlist(self, playlist_id: str, fields: str = None) -> Dict:
        """Get a specific playlist"""
        params = {"fields": fields} if fields else None
        return await self._make_request(f"playlists/{playlist_id}", params=params)

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0, fields: str = None
    ) -> Dict:
        """Get tracks from a playlist"""
        params = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields

        return await self._make_request(
            f"playlists/{playlist_id}/tracks", params=params
        )

    async def get_all_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Get all tracks from a playlist (handles pagination)"""
        all_tracks = []
        offset = 0
        limit = 100

        while True:
            try:
                response = await self.get_playlist_tracks(
                    playlist_id, limit=limit, offset=offset
                )

                tracks = response.get("items", [])
                if not tracks:
                    break

                all_tracks.extend(tracks)

                # Check if there are more tracks
                if len(tracks) < limit or response.get("next") is None:
                    break

                offset += limit

                # Add small delay to respect rate limits
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error fetching playlist tracks at offset {offset}: {e}")
                break

        logger.info(f"Retrieved {len(all_tracks)} tracks from playlist {playlist_id}")
        return all_tracks

    async def search_artist(self, query: str, limit: int = 20) -> Dict:
        """Search for artists on Spotify"""
        params = {
            "q": query,
            "type": "artist",
            "limit": limit,
        }
        return await self._make_request("search", params=params)

    async def search_track(self, query: str, limit: int = 20) -> Dict:
        """Search for tracks on Spotify"""
        params = {
            "q": query,
            "type": "track",
            "limit": limit,
        }
        return await self._make_request("search", params=params)

    async def get_artist(self, artist_id: str) -> Dict:
        """Get artist information"""
        return await self._make_request(f"artists/{artist_id}")

    async def get_artist_albums(
        self, artist_id: str, limit: int = 50, offset: int = 0
    ) -> Dict:
        """Get artist's albums"""
        params = {"limit": limit, "offset": offset}
        return await self._make_request(f"artists/{artist_id}/albums", params=params)

    async def get_artist_top_tracks(self, artist_id: str, country: str = "US") -> Dict:
        """Get artist's top tracks"""
        params = {"country": country}
        return await self._make_request(
            f"artists/{artist_id}/top-tracks", params=params
        )

    async def get_artist_related_artists(self, artist_id: str) -> Dict:
        """Get artist's related artists"""
        return await self._make_request(f"artists/{artist_id}/related-artists")

    async def create_playlist(
        self, user_id: str, name: str, description: str = "", public: bool = False
    ) -> Dict:
        """Create a new playlist"""
        json_data = {
            "name": name,
            "description": description,
            "public": public,
        }
        return await self._make_request(
            f"users/{user_id}/playlists", method="POST", json_data=json_data
        )

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_uris: List[str]
    ) -> Dict:
        """Add tracks to a playlist"""
        if len(track_uris) > 100:
            # Split into batches of 100
            results = []
            for i in range(0, len(track_uris), 100):
                batch = track_uris[i : i + 100]
                result = await self.add_tracks_to_playlist(playlist_id, batch)
                results.append(result)
                # Add delay between batches to respect rate limits
                await asyncio.sleep(0.1)
            return {"results": results}

        json_data = {"uris": track_uris}
        return await self._make_request(
            f"playlists/{playlist_id}/tracks", method="POST", json_data=json_data
        )

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_uris: List[str]
    ) -> Dict:
        """Remove tracks from a playlist"""
        json_data = {"uris": track_uris}
        return await self._make_request(
            f"playlists/{playlist_id}/tracks", method="DELETE", json_data=json_data
        )

    async def follow_playlist(self, playlist_id: str, public: bool = True) -> bool:
        """Follow a playlist"""
        json_data = {"public": public}

        try:
            await self._make_request(
                f"playlists/{playlist_id}/followers", method="PUT", json_data=json_data
            )
            return True
        except Exception as e:
            logger.error(f"Failed to follow playlist: {e}")
            return False

    async def unfollow_playlist(self, playlist_id: str) -> bool:
        """Unfollow a playlist"""
        try:
            await self._make_request(
                f"playlists/{playlist_id}/followers", method="DELETE"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to unfollow playlist: {e}")
            return False

    # TODO: The following methods need to be adapted for async database operations
    # For now, they're commented out until we create async database utilities

    # async def import_playlist_artists(self, playlist_id: str) -> Dict:
    #     """Import artists from a Spotify playlist and search for music videos"""
    #     logger.info(f"Importing artists from Spotify playlist: {playlist_id}")
    #     # Implementation would go here with async database operations
    #     pass

    async def get_track_features(self, track_ids: List[str]) -> Dict:
        """Get audio features for tracks"""
        if len(track_ids) > 100:
            # Split into batches of 100
            results = []
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i : i + 100]
                batch_result = await self.get_track_features(batch)
                results.extend(batch_result.get("audio_features", []))
                # Add delay between batches
                await asyncio.sleep(0.1)
            return {"audio_features": results}

        params = {"ids": ",".join(track_ids)}
        return await self._make_request("audio-features", params=params)

    async def get_recommendations(
        self,
        seed_artists: List[str] = None,
        seed_tracks: List[str] = None,
        seed_genres: List[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> Dict:
        """Get track recommendations"""
        params = {"limit": limit}

        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])  # Max 5 seeds
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])

        # Add any audio feature parameters
        for key, value in kwargs.items():
            if key.startswith(("min_", "max_", "target_")):
                params[key] = value

        return await self._make_request("recommendations", params=params)

    async def get_available_genre_seeds(self) -> Dict:
        """Get available genre seeds for recommendations"""
        return await self._make_request("recommendations/available-genre-seeds")


# Global async Spotify service instance
_global_spotify_service: Optional[AsyncSpotifyService] = None
_spotify_lock: Optional[asyncio.Lock] = None


async def _get_global_spotify_lock() -> asyncio.Lock:
    """Get global Spotify lock, creating it if needed (lazy initialization)"""
    global _spotify_lock
    if _spotify_lock is None:
        # Always create lock in the current running loop context
        _spotify_lock = asyncio.Lock()
    return _spotify_lock


async def get_async_spotify_service() -> AsyncSpotifyService:
    """Get global async Spotify service instance"""
    global _global_spotify_service

    if _global_spotify_service is None:
        lock = await _get_global_spotify_lock()
        async with lock:
            if _global_spotify_service is None:
                _global_spotify_service = AsyncSpotifyService()
                logger.info("Created global async Spotify service instance")

    return _global_spotify_service


@asynccontextmanager
async def spotify_service():
    """Context manager for async Spotify service"""
    service = await get_async_spotify_service()
    try:
        yield service
    finally:
        # Any cleanup if needed
        pass
