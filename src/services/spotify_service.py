"""
Spotify API integration service for importing playlists and discovering music videos
"""

import base64
import difflib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlencode

import requests
from sqlalchemy import and_, func, or_

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.spotify")


class SpotifyService:
    """Service for Spotify API integration"""

    def __init__(self):
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        self.access_token = None
        self.refresh_token = None
        self.token_expires = None
        # Cache for settings to avoid repeated calls
        self._client_id = None
        self._client_secret = None
        self._redirect_uri = None
        self._settings_loaded = False

    def _load_settings(self):
        """Load settings once and cache them"""
        if self._settings_loaded:
            logger.debug("Spotify settings already loaded, skipping reload")
            return

        try:
            logger.debug("Loading Spotify settings from database")
            self._client_id = settings.get("spotify_client_id")
            self._client_secret = settings.get("spotify_client_secret")

            # Try to get configured redirect URI first
            configured_uri = settings.get("spotify_redirect_uri")
            if configured_uri:
                self._redirect_uri = configured_uri
                logger.debug(f"Using configured redirect URI: {self._redirect_uri}")
            else:
                # Construct default redirect URI using server settings
                server_host = settings.get(
                    "server_host", "127.0.0.1"
                )  # Use IPv4 loopback instead of localhost
                server_port = settings.get("server_port", 5000)
                self._redirect_uri = (
                    f"http://{server_host}:{server_port}/api/spotify/callback"
                )
                logger.debug(f"Using default redirect URI: {self._redirect_uri}")

            self._settings_loaded = True
            logger.debug("Spotify settings loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Spotify settings: {e}")
            # Set fallback values
            self._client_id = None
            self._client_secret = None
            self._redirect_uri = "http://127.0.0.1:5000/api/spotify/callback"
            self._settings_loaded = True
            logger.warning(f"Using fallback redirect URI: {self._redirect_uri}")

    @property
    def client_id(self):
        """Get Spotify client ID from database settings"""
        self._load_settings()
        return self._client_id

    @property
    def client_secret(self):
        """Get Spotify client secret from database settings"""
        self._load_settings()
        return self._client_secret

    @property
    def redirect_uri(self):
        """Get Spotify redirect URI from database settings or construct default"""
        self._load_settings()
        return self._redirect_uri

    @property
    def enabled(self):
        """Check if Spotify integration is enabled"""
        self._load_settings()
        # Spotify is enabled if we have client_id and client_secret
        return bool(self._client_id and self._client_secret)

    def clear_cache(self):
        """Clear cached settings to force reload"""
        self._settings_loaded = False
        self._client_id = None
        self._client_secret = None
        self._redirect_uri = None

    def reload_settings(self):
        """Force reload of settings from database"""
        self.clear_cache()
        self._load_settings()
        logger.info("Spotify settings reloaded from database")

    def get_auth_url(self) -> str:
        """Generate Spotify authorization URL"""
        scopes = [
            "playlist-read-private",
            "playlist-read-collaborative",
            "playlist-modify-public",
            "playlist-modify-private",
            "user-library-read",
            "user-library-modify",
            "user-follow-read",
            "user-top-read",
        ]

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "show_dialog": "true",
        }

        return f"https://accounts.spotify.com/authorize?{urlencode(params)}"

    def get_access_token(self, code: str) -> Dict:
        """Exchange authorization code for access token"""
        if not self.client_id or not self.client_secret:
            raise ValueError("Spotify client credentials not configured")

        # Prepare credentials
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            response = requests.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in)

            logger.info("Successfully obtained Spotify access token")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to get Spotify access token: {e}")
            raise

    def refresh_access_token(self) -> Dict:
        """Refresh access token using refresh token"""
        if not self.refresh_token:
            raise ValueError("No refresh token available")

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}

        try:
            response = requests.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data.get("access_token")

            # Update refresh token if provided
            if token_data.get("refresh_token"):
                self.refresh_token = token_data["refresh_token"]

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in)

            logger.info("Successfully refreshed Spotify access token")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to refresh Spotify access token: {e}")
            raise

    def get_client_credentials_token(self) -> Dict:
        """Get access token using client credentials flow"""
        if not self.client_id or not self.client_secret:
            raise ValueError("Spotify client credentials not configured")

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully obtained Spotify client credentials token")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to get Spotify client credentials token: {e}")
            raise

    def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        if not self.access_token:
            raise ValueError("No access token available")

        if self.token_expires and datetime.now() >= self.token_expires:
            self.refresh_access_token()

    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make authenticated request to Spotify API"""
        self._ensure_valid_token()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Spotify API request failed: {e}")
            raise

    def get_user_profile(self) -> Dict:
        """Get current user's Spotify profile"""
        return self._make_request("me")

    def get_user_playlists(self, limit: int = 50, offset: int = 0) -> Dict:
        """Get user's playlists"""
        params = {"limit": limit, "offset": offset}
        return self._make_request("me/playlists", params)

    def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0
    ) -> Dict:
        """Get tracks from a specific playlist"""
        params = {
            "limit": limit,
            "offset": offset,
            "fields": "items(track(id,name,artists(name,id),album(name,images),duration_ms,external_urls,popularity)),next,total",
        }
        return self._make_request(f"playlists/{playlist_id}/tracks", params)

    def get_user_top_artists(
        self, time_range: str = "medium_term", limit: int = 50
    ) -> Dict:
        """Get user's top artists"""
        params = {
            "time_range": time_range,  # short_term, medium_term, long_term
            "limit": limit,
        }
        return self._make_request("me/top/artists", params)

    def get_user_top_tracks(
        self, time_range: str = "medium_term", limit: int = 50
    ) -> Dict:
        """Get user's top tracks"""
        params = {"time_range": time_range, "limit": limit}
        return self._make_request("me/top/tracks", params)

    def get_followed_artists(self, limit: int = 50) -> Dict:
        """Get artists the user follows"""
        params = {"type": "artist", "limit": limit}
        return self._make_request("me/following", params)

    def search_artist(self, artist_name: str, limit: int = 10) -> Dict:
        """Search for artists on Spotify"""
        params = {"q": artist_name, "type": "artist", "limit": limit}
        return self._make_request("search", params)

    def get_artist(self, artist_id: str) -> Dict:
        """Get detailed information about a specific artist including genres"""
        return self._make_request(f"artists/{artist_id}")

    def search_tracks(self, query: str, limit: int = 10) -> Dict:
        """Search for tracks on Spotify"""
        params = {"q": query, "type": "track", "limit": limit}
        return self._make_request("search", params)

    def get_artist_albums(self, artist_id: str, limit: int = 50) -> Dict:
        """Get albums by an artist"""
        params = {"include_groups": "album,single", "limit": limit, "market": "US"}
        return self._make_request(f"artists/{artist_id}/albums", params)

    def get_artist_top_tracks(self, artist_id: str, market: str = "US") -> Dict:
        """Get artist's top tracks"""
        params = {"market": market}
        return self._make_request(f"artists/{artist_id}/top-tracks", params)

    def get_recommendations(
        self,
        seed_artists: List[str] = None,
        seed_tracks: List[str] = None,
        seed_genres: List[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> Dict:
        """Get track recommendations based on seeds"""
        params = {"limit": limit}

        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])  # Max 5 seeds
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])

        # Add audio feature parameters if provided
        for key, value in kwargs.items():
            if key.startswith(("target_", "min_", "max_")):
                params[key] = value

        return self._make_request("recommendations", params)

    def get_track_audio_features(self, track_id: str) -> Dict:
        """Get audio features for a track"""
        return self._make_request(f"audio-features/{track_id}")

    def get_multiple_track_audio_features(self, track_ids: List[str]) -> Dict:
        """Get audio features for multiple tracks"""
        if len(track_ids) > 100:
            track_ids = track_ids[:100]  # Spotify limit
        params = {"ids": ",".join(track_ids)}
        return self._make_request("audio-features", params)

    def get_related_artists(self, artist_id: str) -> Dict:
        """Get related artists for a given artist"""
        return self._make_request(f"artists/{artist_id}/related-artists")

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        collaborative: bool = False,
    ) -> Dict:
        """Create a new playlist for the current user"""
        user_profile = self.get_user_profile()
        if not user_profile or "id" not in user_profile:
            raise ValueError("Unable to get user ID for playlist creation")

        user_id = user_profile["id"]
        endpoint = f"users/{user_id}/playlists"

        data = {
            "name": name,
            "description": description,
            "public": public,
            "collaborative": collaborative,
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.post(
                f"{self.base_url}/{endpoint}", headers=headers, json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create Spotify playlist: {e}")
            return {}

    def add_tracks_to_playlist(self, playlist_id: str, track_uris: List[str]) -> Dict:
        """Add tracks to a playlist"""
        if len(track_uris) > 100:
            # Split into batches of 100
            results = []
            for i in range(0, len(track_uris), 100):
                batch = track_uris[i : i + 100]
                result = self.add_tracks_to_playlist(playlist_id, batch)
                results.append(result)
            return {"snapshot_ids": [r.get("snapshot_id") for r in results]}

        endpoint = f"playlists/{playlist_id}/tracks"
        data = {"uris": track_uris}

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.post(
                f"{self.base_url}/{endpoint}", headers=headers, json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to add tracks to playlist: {e}")
            return {}

    def remove_tracks_from_playlist(
        self, playlist_id: str, track_uris: List[str]
    ) -> Dict:
        """Remove tracks from a playlist"""
        endpoint = f"playlists/{playlist_id}/tracks"
        data = {"uris": track_uris}

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.delete(
                f"{self.base_url}/{endpoint}", headers=headers, json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to remove tracks from playlist: {e}")
            return {}

    def follow_playlist(self, playlist_id: str, public: bool = True) -> bool:
        """Follow a playlist"""
        endpoint = f"playlists/{playlist_id}/followers"
        data = {"public": public}

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.put(
                f"{self.base_url}/{endpoint}", headers=headers, json=data
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to follow playlist: {e}")
            return False

    def unfollow_playlist(self, playlist_id: str) -> bool:
        """Unfollow a playlist"""
        endpoint = f"playlists/{playlist_id}/followers"

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.delete(f"{self.base_url}/{endpoint}", headers=headers)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to unfollow playlist: {e}")
            return False

    def import_playlist_artists(self, playlist_id: str) -> Dict:
        """Import artists from a Spotify playlist and search for music videos"""
        logger.info(f"Importing artists from Spotify playlist: {playlist_id}")

        try:
            # Get playlist details first
            playlist_info = self._make_request(f"playlists/{playlist_id}")
            playlist_name = playlist_info.get("name", "Unknown Playlist")

            # Get all tracks from playlist
            all_tracks = []
            offset = 0
            limit = 100

            while True:
                tracks_data = self.get_playlist_tracks(playlist_id, limit, offset)
                tracks = tracks_data.get("items", [])

                if not tracks:
                    break

                all_tracks.extend(tracks)

                if len(tracks) < limit:
                    break

                offset += limit

            # Extract unique artists
            artists_data = {}
            for track_item in all_tracks:
                track = track_item.get("track")
                if not track:
                    continue

                for artist in track.get("artists", []):
                    artist_id = artist.get("id")
                    artist_name = artist.get("name")

                    if artist_id and artist_name and artist_id not in artists_data:
                        artists_data[artist_id] = {
                            "name": artist_name,
                            "spotify_id": artist_id,
                            "tracks": [],
                        }

                    if artist_id in artists_data:
                        artists_data[artist_id]["tracks"].append(
                            {
                                "name": track.get("name"),
                                "popularity": track.get("popularity", 0),
                            }
                        )

            # Process artists and find music videos
            results = {
                "playlist_name": playlist_name,
                "total_tracks": len(all_tracks),
                "unique_artists": len(artists_data),
                "imported_artists": 0,
                "found_videos": 0,
                "errors": [],
            }

            with get_db() as session:
                for spotify_id, artist_data in artists_data.items():
                    try:
                        # Check if artist already exists
                        existing_artist = (
                            session.query(Artist)
                            .filter(
                                or_(
                                    Artist.name.ilike(f"%{artist_data['name']}%"),
                                    Artist.spotify_id == spotify_id,
                                )
                            )
                            .first()
                        )

                        if existing_artist:
                            # Update Spotify ID if missing
                            if not existing_artist.spotify_id:
                                existing_artist.spotify_id = spotify_id
                                session.commit()

                            logger.info(f"Artist already exists: {artist_data['name']}")
                            continue

                        # Search for artist on IMVDb
                        imvdb_results = imvdb_service.search_artist(artist_data["name"])

                        if imvdb_results and imvdb_results.get("results"):
                            # Use the first (most relevant) result
                            imvdb_artist = imvdb_results["results"][0]

                            # Create new artist
                            from src.utils.filename_cleanup import FilenameCleanup

                            folder_path = FilenameCleanup.sanitize_folder_name(
                                artist_data["name"]
                            )

                            new_artist = Artist(
                                name=artist_data["name"],
                                imvdb_id=imvdb_artist.get("id"),
                                spotify_id=spotify_id,
                                monitored=True,
                                auto_download=False,
                                source="spotify_import",
                                folder_path=folder_path,
                            )

                            session.add(new_artist)
                            session.commit()

                            results["imported_artists"] += 1

                            # Search for music videos
                            video_results = imvdb_service.get_artist_videos(
                                imvdb_artist.get("id")
                            )

                            if video_results and video_results.get("results"):
                                for video_data in video_results["results"]:
                                    # Check if video already exists
                                    existing_video = (
                                        session.query(Video)
                                        .filter(Video.imvdb_id == video_data.get("id"))
                                        .first()
                                    )

                                    if existing_video:
                                        continue

                                    # Create new video
                                    new_video = Video(
                                        title=video_data.get("song_title", "Unknown"),
                                        artist_id=new_artist.id,
                                        imvdb_id=video_data.get("id"),
                                        video_url=video_data.get("image", {}).get("o"),
                                        thumbnail_url=video_data.get("image", {}).get(
                                            "l"
                                        ),
                                        year=video_data.get("year"),
                                        status=VideoStatus.WANTED,
                                        source="spotify_import",
                                    )

                                    session.add(new_video)
                                    results["found_videos"] += 1

                                session.commit()

                            logger.info(
                                f"Imported artist: {artist_data['name']} with {len(video_results.get('results', []))} videos"
                            )

                        else:
                            # Create artist without IMVDb data
                            from src.utils.filename_cleanup import FilenameCleanup

                            folder_path = FilenameCleanup.sanitize_folder_name(
                                artist_data["name"]
                            )

                            new_artist = Artist(
                                name=artist_data["name"],
                                spotify_id=spotify_id,
                                monitored=True,
                                auto_download=False,
                                source="spotify_import",
                                folder_path=folder_path,
                            )

                            session.add(new_artist)
                            session.commit()

                            results["imported_artists"] += 1
                            logger.info(
                                f"Imported artist without IMVDb data: {artist_data['name']}"
                            )

                    except Exception as e:
                        error_msg = (
                            f"Error importing artist {artist_data['name']}: {str(e)}"
                        )
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

            logger.info(f"Playlist import completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to import playlist: {e}")
            raise

    def sync_followed_artists(self) -> Dict:
        """Sync user's followed artists from Spotify"""
        logger.info("Syncing followed artists from Spotify")

        try:
            # Get followed artists
            followed_data = self.get_followed_artists(limit=50)
            artists = followed_data.get("artists", {}).get("items", [])

            results = {
                "total_followed": len(artists),
                "imported_artists": 0,
                "found_videos": 0,
                "errors": [],
            }

            with get_db() as session:
                for artist_data in artists:
                    try:
                        artist_name = artist_data.get("name")
                        spotify_id = artist_data.get("id")

                        # Check if artist already exists
                        existing_artist = (
                            session.query(Artist)
                            .filter(
                                or_(
                                    Artist.name.ilike(f"%{artist_name}%"),
                                    Artist.spotify_id == spotify_id,
                                )
                            )
                            .first()
                        )

                        if existing_artist:
                            # Update Spotify ID if missing
                            if not existing_artist.spotify_id:
                                existing_artist.spotify_id = spotify_id
                                session.commit()
                            continue

                        # Search for artist on IMVDb
                        imvdb_results = imvdb_service.search_artist(artist_name)

                        if imvdb_results and imvdb_results.get("results"):
                            imvdb_artist = imvdb_results["results"][0]

                            # Create new artist
                            from src.utils.filename_cleanup import FilenameCleanup

                            folder_path = FilenameCleanup.sanitize_folder_name(
                                artist_name
                            )

                            new_artist = Artist(
                                name=artist_name,
                                imvdb_id=imvdb_artist.get("id"),
                                spotify_id=spotify_id,
                                monitored=True,
                                auto_download=False,
                                source="spotify_followed",
                                folder_path=folder_path,
                            )

                            session.add(new_artist)
                            session.commit()

                            results["imported_artists"] += 1

                            # Find music videos
                            video_results = imvdb_service.get_artist_videos(
                                imvdb_artist.get("id")
                            )

                            if video_results and video_results.get("results"):
                                for video_data in video_results["results"]:
                                    existing_video = (
                                        session.query(Video)
                                        .filter(Video.imvdb_id == video_data.get("id"))
                                        .first()
                                    )

                                    if existing_video:
                                        continue

                                    new_video = Video(
                                        title=video_data.get("song_title", "Unknown"),
                                        artist_id=new_artist.id,
                                        imvdb_id=video_data.get("id"),
                                        video_url=video_data.get("image", {}).get("o"),
                                        thumbnail_url=video_data.get("image", {}).get(
                                            "l"
                                        ),
                                        year=video_data.get("year"),
                                        status=VideoStatus.WANTED,
                                        source="spotify_followed",
                                    )

                                    session.add(new_video)
                                    results["found_videos"] += 1

                                session.commit()

                    except Exception as e:
                        error_msg = (
                            f"Error importing followed artist {artist_name}: {str(e)}"
                        )
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

            logger.info(f"Followed artists sync completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to sync followed artists: {e}")
            raise

    def calculate_metadata_similarity(
        self, spotify_track: Dict, video_data: Dict
    ) -> float:
        """
        Calculate similarity score between Spotify track and video data
        Returns score from 0.0 to 1.0 (1.0 = perfect match)
        """
        score = 0.0
        weight_total = 0.0

        # Artist name matching (40% weight)
        artist_weight = 0.4
        spotify_artists = [
            a.get("name", "").lower() for a in spotify_track.get("artists", [])
        ]
        video_artist = video_data.get("artist_name", "").lower()

        artist_similarity = 0.0
        for spotify_artist in spotify_artists:
            similarity = difflib.SequenceMatcher(
                None, spotify_artist, video_artist
            ).ratio()
            artist_similarity = max(artist_similarity, similarity)

        score += artist_similarity * artist_weight
        weight_total += artist_weight

        # Track name matching (35% weight)
        track_weight = 0.35
        spotify_track_name = spotify_track.get("name", "").lower()
        video_title = video_data.get("song_title", video_data.get("title", "")).lower()

        # Clean up common variations
        spotify_clean = re.sub(
            r"\s*\(.*\)\s*|\s*\[.*\]\s*|-\s*remaster.*", "", spotify_track_name
        )
        video_clean = re.sub(
            r"\s*\(.*\)\s*|\s*\[.*\]\s*|-\s*remaster.*", "", video_title
        )

        track_similarity = difflib.SequenceMatcher(
            None, spotify_clean, video_clean
        ).ratio()
        score += track_similarity * track_weight
        weight_total += track_weight

        # Album matching (15% weight) - if available
        album_weight = 0.15
        spotify_album = spotify_track.get("album", {}).get("name", "").lower()
        video_album = video_data.get("album", "").lower()

        if spotify_album and video_album:
            album_similarity = difflib.SequenceMatcher(
                None, spotify_album, video_album
            ).ratio()
            score += album_similarity * album_weight
            weight_total += album_weight

        # Duration matching (10% weight) - if available
        duration_weight = 0.1
        spotify_duration = (
            spotify_track.get("duration_ms", 0) / 1000
        )  # Convert to seconds
        video_duration = video_data.get("duration", 0)

        if spotify_duration > 0 and video_duration > 0:
            # Calculate duration similarity (closer durations get higher scores)
            duration_diff = abs(spotify_duration - video_duration)
            max_acceptable_diff = max(
                30, spotify_duration * 0.1
            )  # 10% or 30 seconds max

            if duration_diff <= max_acceptable_diff:
                duration_similarity = 1.0 - (duration_diff / max_acceptable_diff)
                score += duration_similarity * duration_weight
                weight_total += duration_weight

        # Normalize score by total weights applied
        if weight_total > 0:
            score = score / weight_total

        return min(1.0, max(0.0, score))

    def enhanced_metadata_matching(
        self,
        spotify_tracks: List[Dict],
        video_results: List[Dict],
        threshold: float = 0.85,
    ) -> List[Tuple[Dict, Dict, float]]:
        """
        Perform enhanced metadata matching between Spotify tracks and video results
        Returns list of (spotify_track, video_data, similarity_score) tuples above threshold
        """
        matches = []

        for spotify_track in spotify_tracks:
            best_matches = []

            for video_data in video_results:
                similarity = self.calculate_metadata_similarity(
                    spotify_track, video_data
                )

                if similarity >= threshold:
                    best_matches.append((spotify_track, video_data, similarity))

            # Sort by similarity score (highest first) and take best matches
            best_matches.sort(key=lambda x: x[2], reverse=True)
            matches.extend(best_matches[:3])  # Top 3 matches per track

        return matches

    def discover_music_videos_from_listening_history(
        self, time_range: str = "medium_term", limit: int = 50
    ) -> Dict:
        """
        Discover music videos based on user's Spotify listening history
        """
        logger.info(
            f"Discovering music videos from Spotify listening history (timerange: {time_range})"
        )

        try:
            # Get user's top tracks
            top_tracks_data = self.get_user_top_tracks(time_range, limit)
            top_tracks = top_tracks_data.get("items", [])

            results = {
                "discovered_videos": [],
                "total_tracks_analyzed": len(top_tracks),
                "high_confidence_matches": 0,
                "potential_matches": 0,
                "errors": [],
            }

            with get_db() as session:
                for track in top_tracks:
                    try:
                        artists = track.get("artists", [])
                        if not artists:
                            continue

                        primary_artist = artists[0].get("name")

                        # Search for videos by this artist
                        imvdb_results = imvdb_service.search_artist(primary_artist)

                        if imvdb_results and imvdb_results.get("results"):
                            # Get artist videos
                            imvdb_artist = imvdb_results["results"][0]
                            video_results = imvdb_service.get_artist_videos(
                                imvdb_artist.get("id")
                            )

                            if video_results and video_results.get("results"):
                                # Enhanced metadata matching
                                matches = self.enhanced_metadata_matching(
                                    [track], video_results["results"], threshold=0.85
                                )

                                for spotify_track, video_data, similarity in matches:
                                    # Check if video already exists
                                    existing_video = (
                                        session.query(Video)
                                        .filter(Video.imvdb_id == video_data.get("id"))
                                        .first()
                                    )

                                    if existing_video:
                                        continue

                                    # Categorize match confidence
                                    if similarity >= 0.9:
                                        results["high_confidence_matches"] += 1
                                        confidence = "high"
                                    else:
                                        results["potential_matches"] += 1
                                        confidence = "medium"

                                    results["discovered_videos"].append(
                                        {
                                            "video_data": video_data,
                                            "spotify_track": spotify_track,
                                            "similarity_score": similarity,
                                            "confidence": confidence,
                                            "artist": primary_artist,
                                            "recommendation_source": "listening_history",
                                        }
                                    )

                    except Exception as e:
                        error_msg = f"Error processing track {track.get('name', 'Unknown')}: {str(e)}"
                        logger.warning(error_msg)
                        results["errors"].append(error_msg)

            # Sort by similarity score
            results["discovered_videos"].sort(
                key=lambda x: x["similarity_score"], reverse=True
            )

            logger.info(
                f"Discovery completed: {results['high_confidence_matches']} high confidence, {results['potential_matches']} potential matches"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to discover music videos from listening history: {e}")
            raise

    def get_new_releases_for_followed_artists(
        self, country: str = "US", limit: int = 50
    ) -> Dict:
        """
        Get new releases from followed artists for notifications
        """
        logger.info("Getting new releases for followed artists")

        try:
            # Get followed artists
            followed_data = self.get_followed_artists(limit)
            artists = followed_data.get("artists", {}).get("items", [])

            results = {
                "new_releases": [],
                "artists_checked": len(artists),
                "total_releases": 0,
                "errors": [],
            }

            # Check for new releases from each artist
            for artist in artists:
                try:
                    artist_id = artist.get("id")
                    artist_name = artist.get("name")

                    # Get recent albums/singles (last 90 days)
                    albums_data = self.get_artist_albums(artist_id, limit=20)

                    for album in albums_data.get("items", []):
                        release_date = album.get("release_date")
                        if not release_date:
                            continue

                        # Check if release is within last 90 days
                        try:
                            release_datetime = datetime.strptime(
                                release_date, "%Y-%m-%d"
                            )
                            days_ago = (datetime.now() - release_datetime).days

                            if days_ago <= 90:
                                results["new_releases"].append(
                                    {
                                        "artist_name": artist_name,
                                        "artist_id": artist_id,
                                        "album_name": album.get("name"),
                                        "album_id": album.get("id"),
                                        "release_date": release_date,
                                        "album_type": album.get("album_type"),
                                        "total_tracks": album.get("total_tracks", 0),
                                        "days_since_release": days_ago,
                                        "images": album.get("images", []),
                                        "external_urls": album.get("external_urls", {}),
                                    }
                                )
                                results["total_releases"] += 1

                        except ValueError:
                            # Handle partial dates or invalid formats
                            continue

                except Exception as e:
                    error_msg = f"Error checking releases for {artist_name}: {str(e)}"
                    logger.warning(error_msg)
                    results["errors"].append(error_msg)

            # Sort by release date (newest first)
            results["new_releases"].sort(key=lambda x: x["release_date"], reverse=True)

            logger.info(
                f"Found {results['total_releases']} new releases from {results['artists_checked']} artists"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to get new releases: {e}")
            raise


# Global instance
spotify_service = SpotifyService()
