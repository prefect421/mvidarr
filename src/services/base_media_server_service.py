"""
Base Media Server Service for unified media server integration architecture
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

import requests
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.base_media_server")


class MediaServerType(Enum):
    """Supported media server types"""

    PLEX = "plex"
    JELLYFIN = "jellyfin"
    EMBY = "emby"


class MediaType(Enum):
    """Media content types"""

    MUSIC = "music"
    VIDEO = "video"
    MOVIE = "movie"
    TV = "tv"


class SyncDirection(Enum):
    """Sync direction options"""

    FROM_SERVER = "from_server"  # Pull from media server to MVidarr
    TO_SERVER = "to_server"  # Push from MVidarr to media server
    BIDIRECTIONAL = "bidirectional"  # Sync both ways


class MediaServerConfig:
    """Configuration for media server connection"""

    def __init__(
        self,
        server_type: MediaServerType,
        server_url: str,
        auth_token: str = None,
        username: str = None,
        password: str = None,
        api_key: str = None,
    ):
        self.server_type = server_type
        self.server_url = server_url.rstrip("/")
        self.auth_token = auth_token
        self.username = username
        self.password = password
        self.api_key = api_key

    def to_dict(self) -> Dict:
        return {
            "server_type": self.server_type.value,
            "server_url": self.server_url,
            "auth_token": self.auth_token,
            "username": self.username,
            "password": self.password,
            "api_key": self.api_key,
        }


class MediaItem:
    """Unified media item representation"""

    def __init__(
        self,
        server_id: str,
        title: str,
        media_type: MediaType,
        artist: str = None,
        album: str = None,
        year: int = None,
        duration: int = None,
        file_path: str = None,
        thumbnail_url: str = None,
        metadata: Dict = None,
    ):
        self.server_id = server_id
        self.title = title
        self.media_type = media_type
        self.artist = artist
        self.album = album
        self.year = year
        self.duration = duration
        self.file_path = file_path
        self.thumbnail_url = thumbnail_url
        self.metadata = metadata or {}
        self.last_played = None
        self.play_count = 0

    def to_dict(self) -> Dict:
        return {
            "server_id": self.server_id,
            "title": self.title,
            "media_type": self.media_type.value,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "duration": self.duration,
            "file_path": self.file_path,
            "thumbnail_url": self.thumbnail_url,
            "metadata": self.metadata,
            "last_played": self.last_played.isoformat() if self.last_played else None,
            "play_count": self.play_count,
        }


class BaseMediaServerService(ABC):
    """Abstract base class for media server integrations"""

    def __init__(self, config: MediaServerConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = 30
        self._connected = False
        self._last_sync = None

    @property
    def server_type(self) -> MediaServerType:
        return self.config.server_type

    @property
    def connected(self) -> bool:
        return self._connected

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the media server"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict:
        """Test connection to media server"""
        pass

    @abstractmethod
    def get_server_info(self) -> Dict:
        """Get server information and capabilities"""
        pass

    @abstractmethod
    def get_libraries(self) -> List[Dict]:
        """Get all libraries from media server"""
        pass

    @abstractmethod
    def get_music_libraries(self) -> List[Dict]:
        """Get music libraries specifically"""
        pass

    @abstractmethod
    def get_library_items(
        self,
        library_id: str,
        media_type: MediaType = None,
        limit: int = None,
        offset: int = None,
    ) -> List[MediaItem]:
        """Get items from a specific library"""
        pass

    @abstractmethod
    def get_artists(self, library_id: str = None) -> List[Dict]:
        """Get all artists from music libraries"""
        pass

    @abstractmethod
    def get_artist_albums(self, artist_id: str) -> List[Dict]:
        """Get albums for a specific artist"""
        pass

    @abstractmethod
    def get_album_tracks(self, album_id: str) -> List[Dict]:
        """Get tracks for a specific album"""
        pass

    @abstractmethod
    def search_media(self, query: str, media_type: MediaType = None) -> List[MediaItem]:
        """Search for media items"""
        pass

    @abstractmethod
    def get_recently_played(self, limit: int = 20) -> List[Dict]:
        """Get recently played items"""
        pass

    @abstractmethod
    def get_play_history(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get play history for user"""
        pass

    @abstractmethod
    def update_play_status(
        self, item_id: str, played: bool, play_count: int = None
    ) -> bool:
        """Update play status for an item"""
        pass

    @abstractmethod
    def scan_library(self, library_id: str = None) -> Dict:
        """Trigger library scan"""
        pass

    @abstractmethod
    def get_sync_status(self) -> Dict:
        """Get current sync/scan status"""
        pass

    def sync_with_mvidarr(
        self,
        sync_direction: SyncDirection = SyncDirection.FROM_SERVER,
        library_ids: List[str] = None,
    ) -> Dict:
        """
        Sync media server content with MVidarr database
        """
        logger.info(
            f"Starting {self.server_type.value} sync with direction: {sync_direction.value}"
        )

        results = {
            "sync_direction": sync_direction.value,
            "server_type": self.server_type.value,
            "artists_processed": 0,
            "videos_processed": 0,
            "new_artists": 0,
            "new_videos": 0,
            "updated_items": 0,
            "errors": [],
            "libraries_synced": [],
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
        }

        try:
            # Get music libraries to sync
            music_libraries = self.get_music_libraries()
            if library_ids:
                music_libraries = [
                    lib for lib in music_libraries if lib.get("id") in library_ids
                ]

            with get_db() as session:
                for library in music_libraries:
                    library_id = library.get("id")
                    library_name = library.get("name", "Unknown")

                    try:
                        logger.info(f"Syncing library: {library_name} ({library_id})")

                        # Sync artists from this library
                        if sync_direction in [
                            SyncDirection.FROM_SERVER,
                            SyncDirection.BIDIRECTIONAL,
                        ]:
                            artists = self.get_artists(library_id)
                            for artist_data in artists:
                                try:
                                    self._sync_artist_from_server(
                                        session, artist_data, results
                                    )
                                except Exception as e:
                                    error_msg = f"Error syncing artist {artist_data.get('name', 'Unknown')}: {str(e)}"
                                    logger.error(error_msg)
                                    results["errors"].append(error_msg)

                        # Sync to server (if bidirectional)
                        if sync_direction in [
                            SyncDirection.TO_SERVER,
                            SyncDirection.BIDIRECTIONAL,
                        ]:
                            self._sync_artists_to_server(session, library_id, results)

                        results["libraries_synced"].append(
                            {
                                "id": library_id,
                                "name": library_name,
                                "type": library.get("type", "music"),
                            }
                        )

                    except Exception as e:
                        error_msg = f"Error syncing library {library_name}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

            results["end_time"] = datetime.utcnow().isoformat()
            self._last_sync = datetime.utcnow()

            logger.info(
                f"Sync completed: {results['new_artists']} new artists, {results['new_videos']} new videos"
            )
            return results

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            results["errors"].append(f"Sync failed: {str(e)}")
            results["end_time"] = datetime.utcnow().isoformat()
            return results

    def _sync_artist_from_server(
        self, session: Session, artist_data: Dict, results: Dict
    ):
        """Sync a single artist from media server to MVidarr"""
        artist_name = artist_data.get("name") or artist_data.get("title")
        if not artist_name:
            return

        results["artists_processed"] += 1

        # Check if artist already exists
        existing_artist = (
            session.query(Artist).filter(Artist.name.ilike(f"%{artist_name}%")).first()
        )

        if not existing_artist:
            # Create new artist
            from src.utils.filename_cleanup import FilenameCleanup

            folder_path = FilenameCleanup.sanitize_folder_name(artist_name)

            new_artist = Artist(
                name=artist_name,
                monitored=True,
                auto_download=False,
                source=f"{self.server_type.value}_sync",
                folder_path=folder_path,
            )

            # Add media server specific metadata
            if hasattr(new_artist, f"{self.server_type.value}_id"):
                setattr(
                    new_artist, f"{self.server_type.value}_id", artist_data.get("id")
                )

            session.add(new_artist)
            session.commit()
            results["new_artists"] += 1

            logger.info(
                f"Created new artist from {self.server_type.value}: {artist_name}"
            )
        else:
            # Update existing artist with media server ID if missing
            if hasattr(existing_artist, f"{self.server_type.value}_id"):
                if not getattr(existing_artist, f"{self.server_type.value}_id"):
                    setattr(
                        existing_artist,
                        f"{self.server_type.value}_id",
                        artist_data.get("id"),
                    )
                    session.commit()
                    results["updated_items"] += 1

    def _sync_artists_to_server(self, session: Session, library_id: str, results: Dict):
        """Sync MVidarr artists to media server (placeholder for bidirectional sync)"""
        # This would be implemented by specific media server services
        # as the approach varies by server type
        logger.info(
            f"Bidirectional sync to {self.server_type.value} not yet implemented"
        )

    def calculate_similarity_score(
        self, mvidarr_item: Dict, server_item: MediaItem
    ) -> float:
        """
        Calculate similarity score between MVidarr item and media server item
        Returns score from 0.0 to 1.0
        """
        score = 0.0
        weight_total = 0.0

        # Artist name matching (40% weight)
        if mvidarr_item.get("artist") and server_item.artist:
            artist_weight = 0.4
            artist_similarity = self._calculate_text_similarity(
                mvidarr_item["artist"], server_item.artist
            )
            score += artist_similarity * artist_weight
            weight_total += artist_weight

        # Title matching (35% weight)
        if mvidarr_item.get("title") and server_item.title:
            title_weight = 0.35
            title_similarity = self._calculate_text_similarity(
                mvidarr_item["title"], server_item.title
            )
            score += title_similarity * title_weight
            weight_total += title_weight

        # Album matching (15% weight)
        if mvidarr_item.get("album") and server_item.album:
            album_weight = 0.15
            album_similarity = self._calculate_text_similarity(
                mvidarr_item["album"], server_item.album
            )
            score += album_similarity * album_weight
            weight_total += album_weight

        # Duration matching (10% weight)
        if mvidarr_item.get("duration") and server_item.duration:
            duration_weight = 0.1
            duration_diff = abs(mvidarr_item["duration"] - server_item.duration)
            max_acceptable_diff = max(30, mvidarr_item["duration"] * 0.1)

            if duration_diff <= max_acceptable_diff:
                duration_similarity = 1.0 - (duration_diff / max_acceptable_diff)
                score += duration_similarity * duration_weight
                weight_total += duration_weight

        return score / weight_total if weight_total > 0 else 0.0

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using simple ratio"""
        import difflib

        return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def get_sync_statistics(self) -> Dict:
        """Get sync statistics and status"""
        return {
            "server_type": self.server_type.value,
            "server_url": self.config.server_url,
            "connected": self.connected,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "authentication_valid": self._connected,
        }
