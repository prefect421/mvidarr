"""
Last.fm Integration Service for listening history and artist discovery
"""

import os
import time
from datetime import datetime
from typing import Dict, List

import requests

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.lastfm")


class LastFmService:
    """Service for Last.fm integration and listening history"""

    def __init__(self):
        self.base_url = "https://ws.audioscrobbler.com/2.0/"
        self.session_key = None
        self.username = None
        self.refresh_credentials()

    def refresh_credentials(self):
        """Refresh API credentials from environment or settings"""
        # Use SettingsService class methods directly for better Flask context handling
        from src.services.settings_service import SettingsService

        # Try environment variables first, then settings
        self.api_key = os.getenv("LASTFM_API_KEY") or SettingsService.get(
            "lastfm_api_key"
        )
        self.api_secret = os.getenv("LASTFM_API_SECRET") or SettingsService.get(
            "lastfm_api_secret"
        )
        logger.debug(
            f"Last.fm credentials refreshed - API key: {'present' if self.api_key else 'missing'}, secret: {'present' if self.api_secret else 'missing'}"
        )

    @property
    def enabled(self):
        """Check if Last.fm integration is enabled"""
        self.refresh_credentials()
        # Last.fm is enabled if we have an API key
        return bool(self.api_key)

    def get_auth_url(self) -> str:
        """Generate Last.fm authentication URL"""
        if not self.api_key:
            self.refresh_credentials()
        if not self.api_key:
            raise ValueError("Last.fm API key not configured")

        auth_url = f"https://www.last.fm/api/auth/?api_key={self.api_key}"
        return auth_url

    def get_session_key(self, token: str) -> Dict:
        """Get session key from authentication token"""
        if not self.api_key or not self.api_secret:
            self.refresh_credentials()
        if not self.api_key or not self.api_secret:
            raise ValueError("Last.fm API credentials not configured")

        import hashlib

        # Create method signature
        params = {"method": "auth.getSession", "api_key": self.api_key, "token": token}

        # Create signature
        sig_params = sorted(params.items())
        sig_string = "".join([f"{k}{v}" for k, v in sig_params]) + self.api_secret
        signature = hashlib.md5(sig_string.encode()).hexdigest()

        params["api_sig"] = signature
        params["format"] = "json"

        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()

            data = response.json()

            if "error" in data:
                raise ValueError(f"Last.fm API error: {data['message']}")

            session_info = data.get("session", {})
            self.session_key = session_info.get("key")
            self.username = session_info.get("name")

            return {
                "session_key": self.session_key,
                "username": self.username,
                "subscriber": session_info.get("subscriber") == "1",
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get Last.fm session: {e}")
            raise

    def _make_request(self, method: str, params: Dict = None) -> Dict:
        """Make authenticated request to Last.fm API"""
        if not self.api_key:
            self.refresh_credentials()
        if not self.api_key:
            raise ValueError("Last.fm API key not configured")

        request_params = {"method": method, "api_key": self.api_key, "format": "json"}

        if params:
            request_params.update(params)

        try:
            response = requests.get(self.base_url, params=request_params)
            response.raise_for_status()

            data = response.json()

            if "error" in data:
                raise ValueError(f"Last.fm API error: {data['message']}")

            return data

        except requests.RequestException as e:
            logger.error(f"Last.fm API request failed: {e}")
            raise

    def call_api(self, method: str, params: Dict = None) -> Dict:
        """Generic API call method for testing and direct calls"""
        return self._make_request(method, params)

    def get_user_info(self, username: str = None) -> Dict:
        """Get user information"""
        user = username or self.username
        if not user:
            raise ValueError("Username required")

        data = self._make_request("user.getInfo", {"user": user})

        user_info = data.get("user", {})
        return {
            "username": user_info.get("name"),
            "realname": user_info.get("realname"),
            "playcount": int(user_info.get("playcount", 0)),
            "artist_count": int(user_info.get("artist_count", 0)),
            "track_count": int(user_info.get("track_count", 0)),
            "album_count": int(user_info.get("album_count", 0)),
            "image": user_info.get("image", []),
            "country": user_info.get("country"),
            "age": user_info.get("age"),
            "gender": user_info.get("gender"),
            "subscriber": user_info.get("subscriber") == "1",
            "registered": user_info.get("registered", {}).get("unixtime"),
        }

    def get_user_top_artists(
        self,
        username: str = None,
        period: str = "overall",
        limit: int = 50,
        page: int = 1,
    ) -> Dict:
        """Get user's top artists"""
        user = username or self.username
        if not user:
            raise ValueError("Username required")

        params = {
            "user": user,
            "period": period,  # overall, 7day, 1month, 3month, 6month, 12month
            "limit": limit,
            "page": page,
        }

        data = self._make_request("user.getTopArtists", params)

        top_artists = data.get("topartists", {})
        artists = []

        for artist_data in top_artists.get("artist", []):
            artists.append(
                {
                    "name": artist_data.get("name"),
                    "playcount": int(artist_data.get("playcount", 0)),
                    "listeners": int(artist_data.get("listeners", 0)),
                    "mbid": artist_data.get("mbid"),
                    "url": artist_data.get("url"),
                    "image": artist_data.get("image", []),
                    "rank": int(artist_data.get("@attr", {}).get("rank", 0)),
                }
            )

        return {
            "artists": artists,
            "total": int(top_artists.get("@attr", {}).get("total", 0)),
            "page": int(top_artists.get("@attr", {}).get("page", 1)),
            "per_page": int(top_artists.get("@attr", {}).get("perPage", limit)),
            "total_pages": int(top_artists.get("@attr", {}).get("totalPages", 1)),
            "period": period,
        }

    def get_user_top_tracks(
        self,
        username: str = None,
        period: str = "overall",
        limit: int = 50,
        page: int = 1,
    ) -> Dict:
        """Get user's top tracks"""
        user = username or self.username
        if not user:
            raise ValueError("Username required")

        params = {"user": user, "period": period, "limit": limit, "page": page}

        data = self._make_request("user.getTopTracks", params)

        top_tracks = data.get("toptracks", {})
        tracks = []

        for track_data in top_tracks.get("track", []):
            tracks.append(
                {
                    "name": track_data.get("name"),
                    "artist": track_data.get("artist", {}).get("name"),
                    "playcount": int(track_data.get("playcount", 0)),
                    "listeners": int(track_data.get("listeners", 0)),
                    "mbid": track_data.get("mbid"),
                    "url": track_data.get("url"),
                    "image": track_data.get("image", []),
                    "rank": int(track_data.get("@attr", {}).get("rank", 0)),
                }
            )

        return {
            "tracks": tracks,
            "total": int(top_tracks.get("@attr", {}).get("total", 0)),
            "page": int(top_tracks.get("@attr", {}).get("page", 1)),
            "per_page": int(top_tracks.get("@attr", {}).get("perPage", limit)),
            "total_pages": int(top_tracks.get("@attr", {}).get("totalPages", 1)),
            "period": period,
        }

    def get_recent_tracks(
        self,
        username: str = None,
        limit: int = 50,
        page: int = 1,
        from_timestamp: int = None,
        to_timestamp: int = None,
    ) -> Dict:
        """Get user's recent tracks"""
        user = username or self.username
        if not user:
            raise ValueError("Username required")

        params = {
            "user": user,
            "limit": limit,
            "page": page,
            "extended": "1",  # Get extended info
        }

        if from_timestamp:
            params["from"] = from_timestamp
        if to_timestamp:
            params["to"] = to_timestamp

        data = self._make_request("user.getRecentTracks", params)

        recent_tracks = data.get("recenttracks", {})
        tracks = []

        for track_data in recent_tracks.get("track", []):
            # Check if track is currently playing
            now_playing = "@attr" in track_data and "nowplaying" in track_data["@attr"]

            track_info = {
                "name": track_data.get("name"),
                "artist": track_data.get("artist", {}).get("#text")
                or track_data.get("artist"),
                "album": track_data.get("album", {}).get("#text")
                or track_data.get("album"),
                "mbid": track_data.get("mbid"),
                "url": track_data.get("url"),
                "image": track_data.get("image", []),
                "now_playing": now_playing,
            }

            # Add timestamp if not currently playing
            if not now_playing and "date" in track_data:
                track_info["timestamp"] = int(track_data["date"].get("uts", 0))
                track_info["date"] = track_data["date"].get("#text")

            tracks.append(track_info)

        return {
            "tracks": tracks,
            "total": int(recent_tracks.get("@attr", {}).get("total", 0)),
            "page": int(recent_tracks.get("@attr", {}).get("page", 1)),
            "per_page": int(recent_tracks.get("@attr", {}).get("perPage", limit)),
            "total_pages": int(recent_tracks.get("@attr", {}).get("totalPages", 1)),
        }

    def search_artist(self, artist_name: str, limit: int = 10) -> List[Dict]:
        """Search for artists by name"""
        try:
            params = {"artist": artist_name, "limit": limit}
            data = self._make_request("artist.search", params)

            results = []
            artists = data.get("results", {}).get("artistmatches", {}).get("artist", [])

            # Handle single result case
            if isinstance(artists, dict):
                artists = [artists]

            for artist in artists:
                results.append(
                    {
                        "name": artist.get("name"),
                        "mbid": artist.get("mbid"),
                        "url": artist.get("url"),
                        "image": artist.get("image", []),
                        "streamable": artist.get("streamable") == "1",
                        "listeners": int(artist.get("listeners", 0)),
                        "source": "lastfm",
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Error searching Last.fm for artist '{artist_name}': {e}")
            return []

    def get_artist_info(self, artist_name: str, username: str = None) -> Dict:
        """Get artist information"""
        params = {"artist": artist_name}

        if username:
            params["username"] = username

        data = self._make_request("artist.getInfo", params)

        artist_info = data.get("artist", {})

        # Get user playcount if username provided
        user_playcount = 0
        if username and "stats" in artist_info:
            user_playcount = int(artist_info["stats"].get("userplaycount", 0))

        return {
            "name": artist_info.get("name"),
            "mbid": artist_info.get("mbid"),
            "url": artist_info.get("url"),
            "image": artist_info.get("image", []),
            "streamable": artist_info.get("streamable") == "1",
            "ontour": artist_info.get("ontour") == "1",
            "playcount": int(artist_info.get("stats", {}).get("playcount", 0)),
            "listeners": int(artist_info.get("stats", {}).get("listeners", 0)),
            "user_playcount": user_playcount,
            "bio": artist_info.get("bio", {}).get("summary", ""),
            "tags": [
                tag.get("name") for tag in artist_info.get("tags", {}).get("tag", [])
            ],
            # Extract similar artists from the artist info if available
            "similar": (
                [
                    similar.get("name")
                    for similar in artist_info.get("similar", {}).get("artist", [])
                ]
                if "similar" in artist_info
                else []
            ),
        }

    def get_artist_top_tracks(self, artist_name: str, limit: int = 5) -> Dict:
        """Get artist's top tracks from Last.fm"""
        try:
            params = {"artist": artist_name, "limit": limit}
            data = self._make_request("artist.getTopTracks", params)

            top_tracks_data = data.get("toptracks", {})
            tracks = []

            track_list = top_tracks_data.get("track", [])
            # Handle single track case
            if isinstance(track_list, dict):
                track_list = [track_list]

            for track_data in track_list:
                tracks.append(
                    {
                        "name": track_data.get("name"),
                        "playcount": int(track_data.get("playcount", 0)),
                        "listeners": int(track_data.get("listeners", 0)),
                        "mbid": track_data.get("mbid"),
                        "url": track_data.get("url"),
                        "image": track_data.get("image", []),
                        "rank": int(track_data.get("@attr", {}).get("rank", 0)),
                    }
                )

            logger.debug(
                f"🎵 LAST.FM: Found {len(tracks)} top tracks for {artist_name}"
            )
            return {
                "toptracks": {
                    "track": tracks,
                    "@attr": top_tracks_data.get("@attr", {}),
                }
            }

        except Exception as e:
            logger.warning(
                f"🎵 LAST.FM: Could not get top tracks for {artist_name}: {e}"
            )
            return {"toptracks": {"track": []}}

    def get_similar_artists(self, artist_name: str, limit: int = 5) -> List[str]:
        """Get similar artists from Last.fm"""
        try:
            params = {"artist": artist_name, "limit": limit}
            data = self._make_request("artist.getSimilar", params)

            similar_artists = data.get("similarartists", {})
            artists = []

            for artist_data in similar_artists.get("artist", []):
                artist_name = artist_data.get("name")
                if artist_name:
                    artists.append(artist_name)

            logger.debug(f"🎵 LAST.FM: Found {len(artists)} similar artists: {artists}")
            return artists

        except Exception as e:
            logger.warning(f"🎵 LAST.FM: Could not get similar artists: {e}")
            return []

    def get_loved_tracks(
        self, username: str = None, limit: int = 50, page: int = 1
    ) -> Dict:
        """Get user's loved tracks"""
        user = username or self.username
        if not user:
            raise ValueError("Username required")

        params = {"user": user, "limit": limit, "page": page}

        data = self._make_request("user.getLovedTracks", params)

        loved_tracks = data.get("lovedtracks", {})
        tracks = []

        for track_data in loved_tracks.get("track", []):
            tracks.append(
                {
                    "name": track_data.get("name"),
                    "artist": track_data.get("artist", {}).get("name"),
                    "mbid": track_data.get("mbid"),
                    "url": track_data.get("url"),
                    "image": track_data.get("image", []),
                    "date": track_data.get("date", {}).get("#text"),
                    "timestamp": int(track_data.get("date", {}).get("uts", 0)),
                }
            )

        return {
            "tracks": tracks,
            "total": int(loved_tracks.get("@attr", {}).get("total", 0)),
            "page": int(loved_tracks.get("@attr", {}).get("page", 1)),
            "per_page": int(loved_tracks.get("@attr", {}).get("perPage", limit)),
            "total_pages": int(loved_tracks.get("@attr", {}).get("totalPages", 1)),
        }

    def import_top_artists(
        self,
        username: str = None,
        period: str = "overall",
        limit: int = 50,
        min_playcount: int = 1,
    ) -> Dict:
        """Import user's top artists to MVidarr"""
        try:
            # Get top artists from Last.fm
            top_artists_data = self.get_user_top_artists(username, period, limit)

            results = {
                "total_artists": len(top_artists_data["artists"]),
                "imported_artists": 0,
                "existing_artists": 0,
                "videos_found": 0,
                "errors": [],
            }

            with get_db() as session:
                for artist_data in top_artists_data["artists"]:
                    try:
                        # Filter by minimum playcount
                        if artist_data["playcount"] < min_playcount:
                            continue

                        artist_name = artist_data["name"]

                        # Check if artist already exists
                        existing_artist = (
                            session.query(Artist)
                            .filter(Artist.name.ilike(f"%{artist_name}%"))
                            .first()
                        )

                        if existing_artist:
                            # Update Last.fm metadata
                            existing_artist.lastfm_name = artist_name
                            if not existing_artist.source:
                                existing_artist.source = "lastfm_import"
                            existing_artist.updated_at = datetime.now()
                            results["existing_artists"] += 1
                        else:
                            # Create new artist
                            from src.utils.filename_cleanup import FilenameCleanup

                            folder_path = FilenameCleanup.sanitize_folder_name(
                                artist_name
                            )

                            new_artist = Artist(
                                name=artist_name,
                                lastfm_name=artist_name,
                                monitored=True,
                                auto_download=False,
                                source="lastfm_import",
                                created_at=datetime.now(),
                                folder_path=folder_path,
                            )

                            session.add(new_artist)
                            session.flush()  # Get the ID

                            # Try to find videos via IMVDB
                            try:
                                imvdb_results = imvdb_service.search_artist(artist_name)
                                if imvdb_results and imvdb_results.get("results"):
                                    # Use first match
                                    artist_match = imvdb_results["results"][0]
                                    new_artist.imvdb_id = str(artist_match["id"])
                                    new_artist.imvdb_metadata = artist_match

                                    # Get videos for this artist
                                    videos = imvdb_service.get_artist_videos(
                                        artist_match["id"]
                                    )
                                    if videos:
                                        for video_data in videos[
                                            :10
                                        ]:  # Limit to first 10
                                            existing_video = (
                                                session.query(Video)
                                                .filter(
                                                    Video.imvdb_id
                                                    == str(video_data["id"])
                                                )
                                                .first()
                                            )

                                            if not existing_video:
                                                new_video = Video(
                                                    title=video_data["song_title"],
                                                    artist_id=new_artist.id,
                                                    imvdb_id=str(video_data["id"]),
                                                    url=video_data.get("url"),
                                                    thumbnail_url=video_data.get(
                                                        "image", {}
                                                    ).get("o"),
                                                    year=video_data.get("year"),
                                                    directors=video_data.get(
                                                        "directors", []
                                                    ),
                                                    producers=video_data.get(
                                                        "producers", []
                                                    ),
                                                    status=VideoStatus.WANTED,
                                                    source="lastfm_import",
                                                    imvdb_metadata=video_data,
                                                    created_at=datetime.now(),
                                                )
                                                session.add(new_video)
                                                results["videos_found"] += 1

                            except Exception as e:
                                logger.warning(
                                    f"Failed to get IMVDB data for {artist_name}: {e}"
                                )

                            results["imported_artists"] += 1

                    except Exception as e:
                        error_msg = f"Failed to process artist {artist_data.get('name', 'unknown')}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

                session.commit()

            logger.info(f"Last.fm import completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to import Last.fm top artists: {e}")
            raise

    def sync_loved_tracks(self, username: str = None, limit: int = 200) -> Dict:
        """Sync user's loved tracks and try to find music videos"""
        try:
            # Get loved tracks
            loved_tracks_data = self.get_loved_tracks(username, limit)

            results = {
                "total_tracks": len(loved_tracks_data["tracks"]),
                "artists_processed": 0,
                "videos_found": 0,
                "errors": [],
            }

            # Group tracks by artist
            artist_tracks = {}
            for track in loved_tracks_data["tracks"]:
                artist_name = track["artist"]
                if artist_name not in artist_tracks:
                    artist_tracks[artist_name] = []
                artist_tracks[artist_name].append(track)

            with get_db() as session:
                for artist_name, tracks in artist_tracks.items():
                    try:
                        # Find or create artist
                        existing_artist = (
                            session.query(Artist)
                            .filter(Artist.name.ilike(f"%{artist_name}%"))
                            .first()
                        )

                        if not existing_artist:
                            # Create new artist
                            from src.utils.filename_cleanup import FilenameCleanup

                            folder_path = FilenameCleanup.sanitize_folder_name(
                                artist_name
                            )

                            new_artist = Artist(
                                name=artist_name,
                                lastfm_name=artist_name,
                                monitored=True,
                                auto_download=False,
                                source="lastfm_loved",
                                created_at=datetime.now(),
                                folder_path=folder_path,
                            )
                            session.add(new_artist)
                            session.flush()
                            artist = new_artist
                        else:
                            artist = existing_artist
                            if not artist.lastfm_name:
                                artist.lastfm_name = artist_name

                        # Try to find videos for loved tracks
                        try:
                            if not artist.imvdb_id:
                                imvdb_results = imvdb_service.search_artist(artist_name)
                                if imvdb_results and imvdb_results.get("results"):
                                    artist_match = imvdb_results["results"][0]
                                    artist.imvdb_id = str(artist_match["id"])
                                    artist.imvdb_metadata = artist_match

                            if artist.imvdb_id:
                                videos = imvdb_service.get_artist_videos(
                                    int(artist.imvdb_id)
                                )
                                if videos:
                                    for video_data in videos[:5]:  # Limit to first 5
                                        existing_video = (
                                            session.query(Video)
                                            .filter(
                                                Video.imvdb_id == str(video_data["id"])
                                            )
                                            .first()
                                        )

                                        if not existing_video:
                                            new_video = Video(
                                                title=video_data["song_title"],
                                                artist_id=artist.id,
                                                imvdb_id=str(video_data["id"]),
                                                url=video_data.get("url"),
                                                thumbnail_url=video_data.get(
                                                    "image", {}
                                                ).get("o"),
                                                year=video_data.get("year"),
                                                directors=video_data.get(
                                                    "directors", []
                                                ),
                                                producers=video_data.get(
                                                    "producers", []
                                                ),
                                                status=VideoStatus.WANTED,
                                                source="lastfm_loved",
                                                imvdb_metadata=video_data,
                                                created_at=datetime.now(),
                                            )
                                            session.add(new_video)
                                            results["videos_found"] += 1

                        except Exception as e:
                            logger.warning(
                                f"Failed to get videos for {artist_name}: {e}"
                            )

                        results["artists_processed"] += 1

                    except Exception as e:
                        error_msg = f"Failed to process artist {artist_name}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

                session.commit()

            logger.info(f"Last.fm loved tracks sync completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to sync Last.fm loved tracks: {e}")
            raise

    def get_listening_stats(self, username: str = None, days: int = 30) -> Dict:
        """Get detailed listening statistics"""
        try:
            user = username or self.username
            if not user:
                raise ValueError("Username required")

            # Get recent tracks for the specified period
            to_timestamp = int(time.time())
            from_timestamp = to_timestamp - (days * 24 * 60 * 60)

            recent_tracks = self.get_recent_tracks(
                username=user,
                limit=200,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
            )

            # Analyze listening patterns
            artist_counts = {}
            daily_counts = {}
            total_tracks = 0

            for track in recent_tracks["tracks"]:
                if track.get("now_playing"):
                    continue

                artist = track.get("artist", "Unknown")
                timestamp = track.get("timestamp", 0)

                if timestamp > 0:
                    # Count by artist
                    artist_counts[artist] = artist_counts.get(artist, 0) + 1

                    # Count by day
                    day = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                    daily_counts[day] = daily_counts.get(day, 0) + 1

                    total_tracks += 1

            # Top artists
            top_artists = sorted(
                artist_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]

            # Daily listening pattern
            daily_pattern = [
                {"date": k, "count": v} for k, v in sorted(daily_counts.items())
            ]

            return {
                "period_days": days,
                "total_tracks": total_tracks,
                "unique_artists": len(artist_counts),
                "avg_daily_tracks": round(total_tracks / days, 1) if days > 0 else 0,
                "top_artists": [
                    {"name": name, "count": count} for name, count in top_artists
                ],
                "daily_pattern": daily_pattern,
                "most_active_day": (
                    max(daily_counts.items(), key=lambda x: x[1])
                    if daily_counts
                    else None
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get listening stats: {e}")
            raise


# Global instance
lastfm_service = LastFmService()
