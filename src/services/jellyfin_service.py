"""
Jellyfin Media Server integration service for library synchronization and metadata exchange
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

from src.services.base_media_server_service import (
    BaseMediaServerService,
    MediaItem,
    MediaServerConfig,
    MediaServerType,
    MediaType,
)
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.jellyfin")


class JellyfinService(BaseMediaServerService):
    """Service for Jellyfin Media Server integration"""

    def __init__(self):
        # Load configuration from settings
        config = self._load_config()
        super().__init__(config)

        self.user_id = None
        self.device_id = "mvidarr-jellyfin-client"
        self.device_name = "MVidarr"
        self.client_name = "MVidarr"
        self.client_version = "1.0.0"

        # Set up session headers
        self.session.headers.update(
            {
                "X-Emby-Client": self.client_name,
                "X-Emby-Device-Name": self.device_name,
                "X-Emby-Device-Id": self.device_id,
                "X-Emby-Client-Version": self.client_version,
                "Content-Type": "application/json",
            }
        )

        # Authenticate on initialization if credentials are available
        if config.username and config.password:
            self.authenticate()

    def _load_config(self) -> MediaServerConfig:
        """Load Jellyfin configuration from settings"""
        try:
            server_url = SettingsService.get(
                "jellyfin_server_url", "http://localhost:8096"
            )
            username = SettingsService.get("jellyfin_username")
            password = SettingsService.get("jellyfin_password")
            api_key = SettingsService.get("jellyfin_api_key")

            return MediaServerConfig(
                server_type=MediaServerType.JELLYFIN,
                server_url=server_url,
                username=username,
                password=password,
                api_key=api_key,
            )
        except Exception as e:
            logger.error(f"Failed to load Jellyfin configuration: {e}")
            return MediaServerConfig(
                server_type=MediaServerType.JELLYFIN, server_url="http://localhost:8096"
            )

    def authenticate(self) -> bool:
        """Authenticate with Jellyfin server"""
        try:
            if self.config.api_key:
                # Use API key authentication
                self.session.headers["X-Emby-Token"] = self.config.api_key
                # Verify API key works by getting system info
                response = self._make_request("/System/Info")
                if response.status_code == 200:
                    self._connected = True
                    logger.info("Jellyfin API key authentication successful")
                    return True

            if self.config.username and self.config.password:
                # Use username/password authentication
                auth_data = {
                    "Username": self.config.username,
                    "Pw": self.config.password,
                }

                response = self._make_request(
                    "/Users/authenticatebyname", "POST", auth_data
                )

                if response.status_code == 200:
                    auth_result = response.json()
                    access_token = auth_result.get("AccessToken")
                    user_info = auth_result.get("User", {})

                    if access_token:
                        self.session.headers["X-Emby-Token"] = access_token
                        self.user_id = user_info.get("Id")
                        self._connected = True
                        logger.info(
                            f"Jellyfin authentication successful for user: {user_info.get('Name')}"
                        )
                        return True

            logger.error("Jellyfin authentication failed - no valid credentials")
            return False

        except Exception as e:
            logger.error(f"Jellyfin authentication failed: {e}")
            self._connected = False
            return False

    def _make_request(
        self, endpoint: str, method: str = "GET", data: Dict = None
    ) -> requests.Response:
        """Make authenticated request to Jellyfin server"""
        url = urljoin(self.config.server_url, endpoint.lstrip("/"))

        try:
            if method == "GET":
                response = self.session.get(url)
            elif method == "POST":
                response = self.session.post(url, json=data)
            elif method == "PUT":
                response = self.session.put(url, json=data)
            elif method == "DELETE":
                response = self.session.delete(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            return response

        except requests.RequestException as e:
            logger.error(f"Jellyfin API request failed: {e}")
            raise

    def test_connection(self) -> Dict:
        """Test connection to Jellyfin server"""
        try:
            response = self._make_request("/System/Info")

            if response.status_code == 200:
                server_info = response.json()
                return {
                    "connected": True,
                    "server_name": server_info.get("ServerName"),
                    "version": server_info.get("Version"),
                    "product_name": server_info.get("ProductName"),
                    "operating_system": server_info.get("OperatingSystem"),
                    "id": server_info.get("Id"),
                }
            else:
                return {
                    "connected": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                }

        except Exception as e:
            logger.error(f"Failed to connect to Jellyfin server: {e}")
            return {"connected": False, "error": str(e)}

    def get_server_info(self) -> Dict:
        """Get detailed server information"""
        try:
            # Get system info
            system_response = self._make_request("/System/Info")
            system_info = system_response.json()

            # Get public system info (doesn't require auth)
            public_response = self._make_request("/System/Info/Public")
            public_info = public_response.json()

            return {
                "server_name": system_info.get("ServerName"),
                "version": system_info.get("Version"),
                "product_name": system_info.get("ProductName"),
                "operating_system": system_info.get("OperatingSystem"),
                "server_id": system_info.get("Id"),
                "local_address": public_info.get("LocalAddress"),
                "startup_wizard_completed": public_info.get("StartupWizardCompleted"),
                "web_socket_port_number": system_info.get("WebSocketPortNumber"),
                "hardware_acceleration_type": system_info.get(
                    "HardwareAccelerationType"
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get Jellyfin server info: {e}")
            return {}

    def get_libraries(self) -> List[Dict]:
        """Get all libraries from Jellyfin server"""
        try:
            response = self._make_request("/Library/VirtualFolders")

            if response.status_code == 200:
                virtual_folders = response.json()

                libraries = []
                for folder in virtual_folders:
                    library = {
                        "id": folder.get("ItemId"),
                        "name": folder.get("Name"),
                        "collection_type": folder.get("CollectionType"),
                        "locations": folder.get("Locations", []),
                        "library_options": folder.get("LibraryOptions", {}),
                        "refresh_status": folder.get("RefreshStatus"),
                    }
                    libraries.append(library)

                return libraries
            else:
                logger.error(f"Failed to get libraries: HTTP {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Failed to get Jellyfin libraries: {e}")
            return []

    def get_music_libraries(self) -> List[Dict]:
        """Get music libraries specifically"""
        try:
            all_libraries = self.get_libraries()
            music_libraries = []

            for library in all_libraries:
                if library.get("collection_type") == "music":
                    music_libraries.append(library)

            return music_libraries

        except Exception as e:
            logger.error(f"Failed to get music libraries: {e}")
            return []

    def get_library_items(
        self,
        library_id: str,
        media_type: MediaType = None,
        limit: int = None,
        offset: int = None,
    ) -> List[MediaItem]:
        """Get items from a specific library"""
        try:
            params = {
                "ParentId": library_id,
                "Recursive": True,
                "Fields": "BasicSyncInfo,ItemCounts,PrimaryImageAspectRatio,MediaSourceCount,Path",
            }

            if media_type == MediaType.MUSIC:
                params["IncludeItemTypes"] = "Audio"
            elif media_type == MediaType.VIDEO:
                params["IncludeItemTypes"] = "Video"

            if limit:
                params["Limit"] = limit
            if offset:
                params["StartIndex"] = offset

            response = self._make_request("/Items", data=params)

            if response.status_code == 200:
                data = response.json()
                items = []

                for item in data.get("Items", []):
                    media_item = self._convert_jellyfin_item_to_media_item(item)
                    if media_item:
                        items.append(media_item)

                return items
            else:
                logger.error(
                    f"Failed to get library items: HTTP {response.status_code}"
                )
                return []

        except Exception as e:
            logger.error(f"Failed to get library items: {e}")
            return []

    def get_artists(self, library_id: str = None) -> List[Dict]:
        """Get all artists from music libraries"""
        try:
            params = {
                "IncludeItemTypes": "MusicArtist",
                "Recursive": True,
                "Fields": "BasicSyncInfo,ItemCounts,PrimaryImageAspectRatio,SortName",
            }

            if library_id:
                params["ParentId"] = library_id

            response = self._make_request("/Items", data=params)

            if response.status_code == 200:
                data = response.json()
                artists = []

                for item in data.get("Items", []):
                    artist = {
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "sort_name": item.get("SortName"),
                        "type": item.get("Type"),
                        "user_data": item.get("UserData", {}),
                        "image_tags": item.get("ImageTags", {}),
                        "backdrop_image_tags": item.get("BackdropImageTags", []),
                        "location_type": item.get("LocationType"),
                        "media_type": item.get("MediaType"),
                        "overview": item.get("Overview"),
                        "genres": item.get("Genres", []),
                        "album_count": item.get("AlbumCount", 0),
                        "song_count": item.get("SongCount", 0),
                    }
                    artists.append(artist)

                return artists
            else:
                logger.error(f"Failed to get artists: HTTP {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Failed to get artists: {e}")
            return []

    def get_artist_albums(self, artist_id: str) -> List[Dict]:
        """Get albums for a specific artist"""
        try:
            params = {
                "ParentId": artist_id,
                "IncludeItemTypes": "MusicAlbum",
                "Recursive": True,
                "Fields": "BasicSyncInfo,ItemCounts,PrimaryImageAspectRatio,ProductionYear",
            }

            response = self._make_request("/Items", data=params)

            if response.status_code == 200:
                data = response.json()
                albums = []

                for item in data.get("Items", []):
                    album = {
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "type": item.get("Type"),
                        "artist_id": artist_id,
                        "production_year": item.get("ProductionYear"),
                        "user_data": item.get("UserData", {}),
                        "image_tags": item.get("ImageTags", {}),
                        "child_count": item.get("ChildCount", 0),
                        "cumulative_run_time_ticks": item.get("CumulativeRunTimeTicks"),
                        "album_artist": item.get("AlbumArtist"),
                        "artists": item.get("Artists", []),
                        "overview": item.get("Overview"),
                        "genres": item.get("Genres", []),
                    }
                    albums.append(album)

                return albums
            else:
                logger.error(f"Failed to get albums: HTTP {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Failed to get artist albums: {e}")
            return []

    def get_album_tracks(self, album_id: str) -> List[Dict]:
        """Get tracks for a specific album"""
        try:
            params = {
                "ParentId": album_id,
                "IncludeItemTypes": "Audio",
                "Recursive": True,
                "Fields": "BasicSyncInfo,MediaSources,Path,MediaStreams",
            }

            response = self._make_request("/Items", data=params)

            if response.status_code == 200:
                data = response.json()
                tracks = []

                for item in data.get("Items", []):
                    track = {
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "type": item.get("Type"),
                        "album_id": album_id,
                        "artist_items": item.get("ArtistItems", []),
                        "artists": item.get("Artists", []),
                        "album": item.get("Album"),
                        "album_artist": item.get("AlbumArtist"),
                        "index_number": item.get("IndexNumber"),
                        "parent_index_number": item.get("ParentIndexNumber"),
                        "run_time_ticks": item.get("RunTimeTicks"),
                        "production_year": item.get("ProductionYear"),
                        "path": item.get("Path"),
                        "user_data": item.get("UserData", {}),
                        "media_sources": item.get("MediaSources", []),
                    }
                    tracks.append(track)

                return tracks
            else:
                logger.error(f"Failed to get tracks: HTTP {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Failed to get album tracks: {e}")
            return []

    def search_media(self, query: str, media_type: MediaType = None) -> List[MediaItem]:
        """Search for media items"""
        try:
            params = {
                "SearchTerm": query,
                "Limit": 50,
                "Fields": "BasicSyncInfo,MediaSources,Path",
            }

            if media_type == MediaType.MUSIC:
                params["IncludeItemTypes"] = "Audio,MusicArtist,MusicAlbum"
            elif media_type == MediaType.VIDEO:
                params["IncludeItemTypes"] = "Video,Movie"

            response = self._make_request("/Search/Hints", data=params)

            if response.status_code == 200:
                data = response.json()
                items = []

                for search_hint in data.get("SearchHints", []):
                    media_item = self._convert_search_hint_to_media_item(search_hint)
                    if media_item:
                        items.append(media_item)

                return items
            else:
                logger.error(f"Failed to search media: HTTP {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Failed to search media: {e}")
            return []

    def get_recently_played(self, limit: int = 20) -> List[Dict]:
        """Get recently played items"""
        try:
            if not self.user_id:
                logger.error("User ID not available for recently played")
                return []

            params = {"Limit": limit, "Fields": "BasicSyncInfo,Path"}

            response = self._make_request(
                f"/Users/{self.user_id}/Items/Resume", data=params
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("Items", [])
            else:
                logger.error(
                    f"Failed to get recently played: HTTP {response.status_code}"
                )
                return []

        except Exception as e:
            logger.error(f"Failed to get recently played: {e}")
            return []

    def get_play_history(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get play history for user"""
        try:
            target_user_id = user_id or self.user_id
            if not target_user_id:
                logger.error("User ID not available for play history")
                return []

            params = {"Limit": limit, "Fields": "BasicSyncInfo,Path"}

            # Note: Jellyfin doesn't have a direct play history endpoint like Plex
            # This would require custom plugin or activity log parsing
            logger.warning("Jellyfin play history requires additional implementation")
            return []

        except Exception as e:
            logger.error(f"Failed to get play history: {e}")
            return []

    def update_play_status(
        self, item_id: str, played: bool, play_count: int = None
    ) -> bool:
        """Update play status for an item"""
        try:
            if not self.user_id:
                logger.error("User ID not available for updating play status")
                return False

            endpoint = f"/Users/{self.user_id}/PlayedItems/{item_id}"

            if played:
                response = self._make_request(endpoint, "POST")
            else:
                response = self._make_request(endpoint, "DELETE")

            return response.status_code in [200, 204]

        except Exception as e:
            logger.error(f"Failed to update play status: {e}")
            return False

    def scan_library(self, library_id: str = None) -> Dict:
        """Trigger library scan"""
        try:
            if library_id:
                endpoint = f"/Library/VirtualFolders/{library_id}/Refresh"
            else:
                endpoint = "/Library/Refresh"

            response = self._make_request(endpoint, "POST")

            if response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "Library scan initiated successfully",
                    "library_id": library_id,
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                }

        except Exception as e:
            logger.error(f"Failed to scan library: {e}")
            return {"success": False, "error": str(e)}

    def get_sync_status(self) -> Dict:
        """Get current sync/scan status"""
        try:
            response = self._make_request(
                "/System/ActivityLog/Entries", data={"Limit": 50}
            )

            if response.status_code == 200:
                activities = response.json().get("Items", [])

                # Look for library scan activities
                scan_activities = [
                    activity
                    for activity in activities
                    if "library" in activity.get("Name", "").lower()
                    or "scan" in activity.get("Name", "").lower()
                ]

                return {
                    "has_active_scans": any(
                        not activity.get("EndTime") for activity in scan_activities
                    ),
                    "recent_activities": scan_activities[:10],
                }
            else:
                return {"has_active_scans": False, "recent_activities": []}

        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {"has_active_scans": False, "recent_activities": []}

    def _convert_jellyfin_item_to_media_item(self, item: Dict) -> Optional[MediaItem]:
        """Convert Jellyfin item to unified MediaItem"""
        try:
            item_type = item.get("Type", "").lower()

            if item_type == "audio":
                media_type = MediaType.MUSIC
            elif item_type in ["video", "movie"]:
                media_type = MediaType.VIDEO
            else:
                return None

            # Extract duration from RunTimeTicks (100ns intervals)
            run_time_ticks = item.get("RunTimeTicks")
            duration = int(run_time_ticks / 10000000) if run_time_ticks else None

            return MediaItem(
                server_id=item.get("Id"),
                title=item.get("Name"),
                media_type=media_type,
                artist=item.get("AlbumArtist")
                or (item.get("Artists", [{}])[0] if item.get("Artists") else None),
                album=item.get("Album"),
                year=item.get("ProductionYear"),
                duration=duration,
                file_path=item.get("Path"),
                metadata=item,
            )

        except Exception as e:
            logger.error(f"Failed to convert Jellyfin item: {e}")
            return None

    def _convert_search_hint_to_media_item(self, hint: Dict) -> Optional[MediaItem]:
        """Convert Jellyfin search hint to MediaItem"""
        try:
            item_type = hint.get("Type", "").lower()

            if item_type == "audio":
                media_type = MediaType.MUSIC
            elif item_type in ["video", "movie"]:
                media_type = MediaType.VIDEO
            else:
                return None

            return MediaItem(
                server_id=hint.get("ItemId"),
                title=hint.get("Name"),
                media_type=media_type,
                artist=hint.get("AlbumArtist"),
                album=hint.get("Album"),
                year=hint.get("ProductionYear"),
                metadata=hint,
            )

        except Exception as e:
            logger.error(f"Failed to convert search hint: {e}")
            return None


# Global instance
jellyfin_service = JellyfinService()
