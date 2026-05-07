"""
Plex Integration Service for library synchronization and metadata exchange
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import defusedxml.ElementTree as ET
import requests
from src.database.connection import get_db
from src.database.models import Artist
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.plex")


class PlexService:
    """Service for Plex Media Server integration"""

    def __init__(self):
        self._load_settings()
        self.music_library_id = None
        self.session = requests.Session()

        # Set up session headers
        if self.server_token:
            self.session.headers.update(
                {
                    "X-Plex-Token": self.server_token,
                    "X-Plex-Client-Identifier": "mvidarr-enhanced",
                    "X-Plex-Product": "MVidarr",
                    "X-Plex-Version": "1.0.0",
                }
            )

    def _load_settings(self):
        """Load Plex settings from database"""
        try:
            from src.services.settings_service import SettingsService

            self.server_url = SettingsService.get(
                "plex_server_url", "http://localhost:32400"
            )
            self.server_token = SettingsService.get("plex_token")
        except Exception as e:
            logger.warning(f"Failed to load Plex settings from database: {e}")
            # Fallback to environment variables
            self.server_url = os.getenv("PLEX_SERVER_URL", "http://localhost:32400")
            self.server_token = os.getenv("PLEX_SERVER_TOKEN")

    def _make_request(self, endpoint: str, params: Dict = None) -> requests.Response:
        """Make authenticated request to Plex server"""
        if not self.server_token:
            raise ValueError("Plex server token not configured")

        url = urljoin(self.server_url, endpoint)

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response

        except requests.RequestException as e:
            logger.error(f"Plex API request failed: {e}")
            raise

    def test_connection(self) -> Dict:
        """Test connection to Plex server"""
        try:
            response = self._make_request("/")

            # Parse XML response
            root = ET.fromstring(response.content)

            return {
                "connected": True,
                "server_name": root.get("friendlyName"),
                "version": root.get("version"),
                "platform": root.get("platform"),
                "platform_version": root.get("platformVersion"),
                "updated_at": root.get("updatedAt"),
            }

        except Exception as e:
            logger.error(f"Failed to connect to Plex server: {e}")
            return {"connected": False, "error": str(e)}

    def get_libraries(self) -> List[Dict]:
        """Get all libraries from Plex server"""
        try:
            response = self._make_request("/library/sections")
            root = ET.fromstring(response.content)

            libraries = []
            for directory in root.findall("Directory"):
                library = {
                    "key": directory.get("key"),
                    "title": directory.get("title"),
                    "type": directory.get("type"),
                    "agent": directory.get("agent"),
                    "scanner": directory.get("scanner"),
                    "language": directory.get("language"),
                    "refreshing": directory.get("refreshing") == "1",
                    "created_at": directory.get("createdAt"),
                    "updated_at": directory.get("updatedAt"),
                }
                libraries.append(library)

            return libraries

        except Exception as e:
            logger.error(f"Failed to get Plex libraries: {e}")
            raise

    def get_music_library(self) -> Optional[Dict]:
        """Get the music library from Plex"""
        try:
            libraries = self.get_libraries()

            for library in libraries:
                if library["type"] == "artist":
                    self.music_library_id = library["key"]
                    return library

            return None

        except Exception as e:
            logger.error(f"Failed to get music library: {e}")
            return None

    def get_library_artists(self, library_key: str = None) -> List[Dict]:
        """Get all artists from music library"""
        try:
            if not library_key:
                music_lib = self.get_music_library()
                if not music_lib:
                    raise ValueError("No music library found")
                library_key = music_lib["key"]

            response = self._make_request(f"/library/sections/{library_key}/all")
            root = ET.fromstring(response.content)

            artists = []
            for directory in root.findall("Directory"):
                artist = {
                    "key": directory.get("key"),
                    "title": directory.get("title"),
                    "type": directory.get("type"),
                    "guid": directory.get("guid"),
                    "rating_key": directory.get("ratingKey"),
                    "thumb": directory.get("thumb"),
                    "art": directory.get("art"),
                    "summary": directory.get("summary"),
                    "index": directory.get("index"),
                    "view_count": int(directory.get("viewCount", 0)),
                    "last_viewed_at": directory.get("lastViewedAt"),
                    "added_at": directory.get("addedAt"),
                    "updated_at": directory.get("updatedAt"),
                }
                artists.append(artist)

            return artists

        except Exception as e:
            logger.error(f"Failed to get library artists: {e}")
            raise

    def get_artist_albums(self, artist_key: str) -> List[Dict]:
        """Get albums for a specific artist"""
        try:
            response = self._make_request(f"/library/metadata/{artist_key}/children")
            root = ET.fromstring(response.content)

            albums = []
            for directory in root.findall("Directory"):
                album = {
                    "key": directory.get("key"),
                    "title": directory.get("title"),
                    "type": directory.get("type"),
                    "guid": directory.get("guid"),
                    "rating_key": directory.get("ratingKey"),
                    "parent_key": directory.get("parentKey"),
                    "parent_title": directory.get("parentTitle"),
                    "thumb": directory.get("thumb"),
                    "art": directory.get("art"),
                    "summary": directory.get("summary"),
                    "index": directory.get("index"),
                    "year": directory.get("year"),
                    "originally_available_at": directory.get("originallyAvailableAt"),
                    "leaf_count": int(directory.get("leafCount", 0)),
                    "viewed_leaf_count": int(directory.get("viewedLeafCount", 0)),
                    "added_at": directory.get("addedAt"),
                    "updated_at": directory.get("updatedAt"),
                }
                albums.append(album)

            return albums

        except Exception as e:
            logger.error(f"Failed to get artist albums: {e}")
            raise

    def get_album_tracks(self, album_key: str) -> List[Dict]:
        """Get tracks for a specific album"""
        try:
            response = self._make_request(f"/library/metadata/{album_key}/children")
            root = ET.fromstring(response.content)

            tracks = []
            for track in root.findall("Track"):
                track_data = {
                    "key": track.get("key"),
                    "title": track.get("title"),
                    "type": track.get("type"),
                    "guid": track.get("guid"),
                    "rating_key": track.get("ratingKey"),
                    "parent_key": track.get("parentKey"),
                    "parent_title": track.get("parentTitle"),
                    "grandparent_key": track.get("grandparentKey"),
                    "grandparent_title": track.get("grandparentTitle"),
                    "thumb": track.get("thumb"),
                    "art": track.get("art"),
                    "summary": track.get("summary"),
                    "index": track.get("index"),
                    "year": track.get("year"),
                    "duration": int(track.get("duration", 0)),
                    "view_count": int(track.get("viewCount", 0)),
                    "last_viewed_at": track.get("lastViewedAt"),
                    "added_at": track.get("addedAt"),
                    "updated_at": track.get("updatedAt"),
                }

                # Get media info
                media_elem = track.find("Media")
                if media_elem is not None:
                    track_data["media"] = {
                        "duration": int(media_elem.get("duration", 0)),
                        "bitrate": int(media_elem.get("bitrate", 0)),
                        "audio_codec": media_elem.get("audioCodec"),
                        "container": media_elem.get("container"),
                    }

                    # Get file path
                    part_elem = media_elem.find("Part")
                    if part_elem is not None:
                        track_data["file_path"] = part_elem.get("file")

                tracks.append(track_data)

            return tracks

        except Exception as e:
            logger.error(f"Failed to get album tracks: {e}")
            raise

    def search_library(self, query: str, library_key: str = None) -> List[Dict]:
        """Search for content in Plex library"""
        try:
            if not library_key:
                music_lib = self.get_music_library()
                if not music_lib:
                    raise ValueError("No music library found")
                library_key = music_lib["key"]

            params = {"query": query, "type": 8}  # Artist type

            response = self._make_request(
                f"/library/sections/{library_key}/search", params
            )
            root = ET.fromstring(response.content)

            results = []
            for directory in root.findall("Directory"):
                result = {
                    "key": directory.get("key"),
                    "title": directory.get("title"),
                    "type": directory.get("type"),
                    "guid": directory.get("guid"),
                    "rating_key": directory.get("ratingKey"),
                    "thumb": directory.get("thumb"),
                    "art": directory.get("art"),
                    "summary": directory.get("summary"),
                    "score": int(directory.get("score", 0)),
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Failed to search Plex library: {e}")
            raise

    def sync_artists_to_mvidarr(self, limit: int = 100) -> Dict:
        """Sync artists from Plex to MVidarr"""
        try:
            # Get Plex artists
            plex_artists = self.get_library_artists()

            results = {
                "total_plex_artists": len(plex_artists),
                "imported_artists": 0,
                "existing_artists": 0,
                "errors": [],
            }

            # Limit processing if specified
            if limit > 0:
                plex_artists = plex_artists[:limit]

            with get_db() as session:
                for plex_artist in plex_artists:
                    try:
                        artist_name = plex_artist["title"]

                        # Check if artist already exists
                        existing_artist = (
                            session.query(Artist)
                            .filter(Artist.name.ilike(f"%{artist_name}%"))
                            .first()
                        )

                        if existing_artist:
                            # Update Plex metadata
                            existing_artist.imvdb_metadata = (
                                existing_artist.imvdb_metadata or {}
                            )
                            existing_artist.imvdb_metadata["plex"] = plex_artist
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
                                monitored=True,
                                auto_download=False,
                                source="plex_sync",
                                imvdb_metadata={"plex": plex_artist},
                                created_at=datetime.now(),
                                folder_path=folder_path,
                            )

                            session.add(new_artist)
                            results["imported_artists"] += 1

                    except Exception as e:
                        error_msg = f"Failed to process artist {plex_artist.get('title', 'unknown')}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

                session.commit()

            logger.info(f"Plex artist sync completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to sync Plex artists: {e}")
            raise

    def sync_mvidarr_to_plex(self) -> Dict:
        """Sync MVidarr artists to Plex for matching"""
        try:
            results = {
                "total_mvidarr_artists": 0,
                "matched_artists": 0,
                "unmatched_artists": 0,
                "errors": [],
            }

            with get_db() as session:
                mvidarr_artists = (
                    session.query(Artist).filter(Artist.monitored == True).all()
                )

                results["total_mvidarr_artists"] = len(mvidarr_artists)

                for artist in mvidarr_artists:
                    try:
                        # Search for artist in Plex
                        search_results = self.search_library(artist.name)

                        if search_results:
                            # Use best match (highest score)
                            best_match = max(search_results, key=lambda x: x["score"])

                            # Update artist with Plex metadata
                            artist.imvdb_metadata = artist.imvdb_metadata or {}
                            artist.imvdb_metadata["plex"] = best_match
                            artist.updated_at = datetime.now()

                            results["matched_artists"] += 1
                            logger.info(
                                f"Matched MVidarr artist '{artist.name}' to Plex: {best_match['title']}"
                            )
                        else:
                            results["unmatched_artists"] += 1
                            logger.debug(
                                f"No Plex match found for artist: {artist.name}"
                            )

                    except Exception as e:
                        error_msg = (
                            f"Failed to search for artist {artist.name}: {str(e)}"
                        )
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

                session.commit()

            logger.info(f"MVidarr to Plex sync completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to sync MVidarr to Plex: {e}")
            raise

    def get_artist_listening_stats(self, artist_name: str) -> Dict:
        """Get listening statistics for an artist from Plex"""
        try:
            # Search for artist
            search_results = self.search_library(artist_name)

            if not search_results:
                return {"found": False, "error": "Artist not found in Plex library"}

            artist = search_results[0]  # Use best match

            # Get artist albums
            albums = self.get_artist_albums(artist["key"])

            # Get detailed stats
            total_tracks = 0
            total_duration = 0
            total_plays = 0
            last_played = None

            for album in albums:
                tracks = self.get_album_tracks(album["key"])
                total_tracks += len(tracks)

                for track in tracks:
                    if track.get("duration"):
                        total_duration += track["duration"]
                    if track.get("view_count"):
                        total_plays += track["view_count"]

                    # Track last played
                    if track.get("last_viewed_at"):
                        track_last_played = int(track["last_viewed_at"])
                        if not last_played or track_last_played > last_played:
                            last_played = track_last_played

            return {
                "found": True,
                "artist": artist,
                "stats": {
                    "total_albums": len(albums),
                    "total_tracks": total_tracks,
                    "total_duration": total_duration,
                    "total_plays": total_plays,
                    "last_played": last_played,
                    "avg_track_duration": (
                        total_duration / total_tracks if total_tracks > 0 else 0
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Failed to get artist listening stats: {e}")
            return {"found": False, "error": str(e)}

    def get_recently_played(self, limit: int = 50) -> List[Dict]:
        """Get recently played tracks from Plex"""
        try:
            # Get recently played from Plex
            params = {"sort": "lastViewedAt:desc", "limit": limit}

            music_lib = self.get_music_library()
            if not music_lib:
                raise ValueError("No music library found")

            response = self._make_request(
                f'/library/sections/{music_lib["key"]}/recentlyViewed', params
            )
            root = ET.fromstring(response.content)

            recently_played = []
            for track in root.findall("Track"):
                track_data = {
                    "title": track.get("title"),
                    "artist": track.get("grandparentTitle"),
                    "album": track.get("parentTitle"),
                    "duration": int(track.get("duration", 0)),
                    "last_viewed_at": track.get("lastViewedAt"),
                    "view_count": int(track.get("viewCount", 0)),
                    "thumb": track.get("thumb"),
                    "art": track.get("art"),
                    "rating_key": track.get("ratingKey"),
                }
                recently_played.append(track_data)

            return recently_played

        except Exception as e:
            logger.error(f"Failed to get recently played tracks: {e}")
            raise

    def get_library_stats(self) -> Dict:
        """Get overall library statistics"""
        try:
            music_lib = self.get_music_library()
            if not music_lib:
                raise ValueError("No music library found")

            # Get basic library info
            response = self._make_request(f'/library/sections/{music_lib["key"]}')
            root = ET.fromstring(response.content)

            library_stats = {
                "title": root.get("title"),
                "type": root.get("type"),
                "refreshing": root.get("refreshing") == "1",
                "created_at": root.get("createdAt"),
                "updated_at": root.get("updatedAt"),
                "scanned_at": root.get("scannedAt"),
            }

            # Get counts
            artists = self.get_library_artists()
            library_stats["artist_count"] = len(artists)

            # Sample some artists to get album/track counts
            total_albums = 0
            total_tracks = 0

            for artist in artists[:10]:  # Sample first 10 artists
                try:
                    albums = self.get_artist_albums(artist["key"])
                    total_albums += len(albums)

                    for album in albums[:5]:  # Sample first 5 albums per artist
                        tracks = self.get_album_tracks(album["key"])
                        total_tracks += len(tracks)

                except Exception as e:
                    logger.warning(
                        f"Failed to get details for artist {artist['title']}: {e}"
                    )

            # Estimate totals based on sample
            if len(artists) > 0:
                avg_albums_per_artist = total_albums / min(len(artists), 10)
                avg_tracks_per_album = total_tracks / max(total_albums, 1)

                library_stats["estimated_album_count"] = int(
                    avg_albums_per_artist * len(artists)
                )
                library_stats["estimated_track_count"] = int(
                    avg_tracks_per_album * library_stats["estimated_album_count"]
                )
            else:
                library_stats["estimated_album_count"] = 0
                library_stats["estimated_track_count"] = 0

            return library_stats

        except Exception as e:
            logger.error(f"Failed to get library stats: {e}")
            raise

    def create_playlist(self, name: str, track_keys: List[str]) -> Dict:
        """Create a playlist in Plex"""
        try:
            music_lib = self.get_music_library()
            if not music_lib:
                raise ValueError("No music library found")

            # Create playlist
            params = {
                "title": name,
                "type": "audio",
                "smart": 0,
                "uri": f'library://{music_lib["key"]}/item/{",".join(track_keys)}',
            }

            response = self._make_request("/playlists", params)

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": f'Playlist "{name}" created successfully',
                    "playlist_id": response.headers.get("Location", "").split("/")[-1],
                }
            else:
                return {"success": False, "error": "Failed to create playlist"}

        except Exception as e:
            logger.error(f"Failed to create Plex playlist: {e}")
            return {"success": False, "error": str(e)}


# Global instance
plex_service = PlexService()
