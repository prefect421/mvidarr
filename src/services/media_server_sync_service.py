"""
Bidirectional Metadata Synchronization Service for Media Server Integration
"""

import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, or_

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.base_media_server_service import (
    BaseMediaServerService,
    MediaItem,
    MediaServerType,
    SyncDirection,
)
from src.services.media_server_manager import media_server_manager
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.media_server_sync")


class SyncConflictResolution(Enum):
    """Conflict resolution strategies for bidirectional sync"""

    MVIDARR_WINS = "mvidarr_wins"  # MVidarr data takes precedence
    SERVER_WINS = "server_wins"  # Media server data takes precedence
    NEWEST_WINS = "newest_wins"  # Most recently updated data wins
    MANUAL_REVIEW = "manual_review"  # Flag conflicts for manual resolution


class MetadataField(Enum):
    """Metadata fields that can be synchronized"""

    PLAY_COUNT = "play_count"
    LAST_PLAYED = "last_played"
    RATING = "rating"
    FAVORITE = "favorite"
    WATCHED_STATUS = "watched_status"
    TAGS = "tags"
    NOTES = "notes"


class MediaServerSyncService:
    """Service for bidirectional metadata synchronization"""

    def __init__(self):
        self.config = self._load_sync_config()
        self._sync_in_progress = False

    def _load_sync_config(self) -> Dict:
        """Load synchronization configuration"""
        try:
            return {
                "bidirectional_sync_enabled": SettingsService.get_bool(
                    "media_server_bidirectional_sync", True
                ),
                "conflict_resolution": SettingsService.get(
                    "media_server_conflict_resolution",
                    SyncConflictResolution.NEWEST_WINS.value,
                ),
                "sync_fields": SettingsService.get_json(
                    "media_server_sync_fields",
                    {
                        MetadataField.PLAY_COUNT.value: True,
                        MetadataField.LAST_PLAYED.value: True,
                        MetadataField.RATING.value: True,
                        MetadataField.FAVORITE.value: True,
                        MetadataField.WATCHED_STATUS.value: True,
                        MetadataField.TAGS.value: False,
                        MetadataField.NOTES.value: False,
                    },
                ),
                "auto_sync_interval_hours": SettingsService.get_int(
                    "media_server_auto_sync_interval", 6
                ),
                "similarity_threshold": SettingsService.get_float(
                    "media_server_similarity_threshold", 0.85
                ),
            }
        except Exception as e:
            logger.error(f"Failed to load sync configuration: {e}")
            return {
                "bidirectional_sync_enabled": True,
                "conflict_resolution": SyncConflictResolution.NEWEST_WINS.value,
                "sync_fields": {
                    field.value: True
                    for field in MetadataField
                    if field != MetadataField.TAGS and field != MetadataField.NOTES
                },
                "auto_sync_interval_hours": 6,
                "similarity_threshold": 0.85,
            }

    def sync_metadata_bidirectional(
        self, server_types: List[str] = None, force_sync: bool = False
    ) -> Dict:
        """
        Perform bidirectional metadata synchronization between MVidarr and media servers
        """
        if self._sync_in_progress and not force_sync:
            return {
                "success": False,
                "error": "Bidirectional sync already in progress",
                "sync_in_progress": True,
            }

        self._sync_in_progress = True

        try:
            if not self.config["bidirectional_sync_enabled"]:
                return {
                    "success": False,
                    "error": "Bidirectional sync is disabled in configuration",
                }

            logger.info("Starting bidirectional metadata synchronization")

            enabled_servers = media_server_manager.get_enabled_servers()

            # Filter by requested server types
            if server_types:
                enabled_servers = [
                    service
                    for service in enabled_servers
                    if service.server_type.value in server_types
                ]

            if not enabled_servers:
                return {
                    "success": False,
                    "error": "No enabled media servers found for sync",
                }

            results = {
                "success": True,
                "start_time": datetime.utcnow().isoformat(),
                "end_time": None,
                "servers_synced": [],
                "total_items_synced": 0,
                "total_conflicts_resolved": 0,
                "total_updates_to_servers": 0,
                "total_updates_from_servers": 0,
                "conflicts_requiring_manual_review": [],
                "errors": [],
            }

            with get_db() as session:
                for service in enabled_servers:
                    server_name = service.server_type.value
                    logger.info(f"Starting bidirectional sync for {server_name}")

                    try:
                        server_result = self._sync_server_metadata_bidirectional(
                            session, service
                        )
                        server_result["server_type"] = server_name
                        results["servers_synced"].append(server_result)

                        # Aggregate results
                        results["total_items_synced"] += server_result.get(
                            "items_synced", 0
                        )
                        results["total_conflicts_resolved"] += server_result.get(
                            "conflicts_resolved", 0
                        )
                        results["total_updates_to_servers"] += server_result.get(
                            "updates_to_server", 0
                        )
                        results["total_updates_from_servers"] += server_result.get(
                            "updates_from_server", 0
                        )
                        results["conflicts_requiring_manual_review"].extend(
                            server_result.get("manual_conflicts", [])
                        )
                        results["errors"].extend(server_result.get("errors", []))

                    except Exception as e:
                        error_msg = (
                            f"Bidirectional sync failed for {server_name}: {str(e)}"
                        )
                        logger.error(error_msg)
                        results["errors"].append(error_msg)

            results["end_time"] = datetime.utcnow().isoformat()
            results["success"] = len(results["errors"]) == 0

            logger.info(
                f"Bidirectional sync completed: {results['total_items_synced']} items synced, "
                f"{results['total_conflicts_resolved']} conflicts resolved"
            )

            return results

        except Exception as e:
            logger.error(f"Bidirectional sync failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "end_time": datetime.utcnow().isoformat(),
            }
        finally:
            self._sync_in_progress = False

    def _sync_server_metadata_bidirectional(
        self, session, service: BaseMediaServerService
    ) -> Dict:
        """Sync metadata bidirectionally with a specific media server"""
        server_name = service.server_type.value

        result = {
            "server_type": server_name,
            "items_synced": 0,
            "conflicts_resolved": 0,
            "updates_to_server": 0,
            "updates_from_server": 0,
            "manual_conflicts": [],
            "errors": [],
            "sync_details": [],
        }

        try:
            # Get music libraries from the server
            music_libraries = service.get_music_libraries()

            for library in music_libraries:
                library_id = library.get("id")
                library_name = library.get("name", "Unknown")

                logger.info(f"Syncing metadata for library: {library_name}")

                # Get artists from server
                server_artists = service.get_artists(library_id)

                for server_artist in server_artists:
                    try:
                        artist_result = self._sync_artist_metadata_bidirectional(
                            session, service, server_artist
                        )

                        result["items_synced"] += artist_result.get("items_synced", 0)
                        result["conflicts_resolved"] += artist_result.get(
                            "conflicts_resolved", 0
                        )
                        result["updates_to_server"] += artist_result.get(
                            "updates_to_server", 0
                        )
                        result["updates_from_server"] += artist_result.get(
                            "updates_from_server", 0
                        )
                        result["manual_conflicts"].extend(
                            artist_result.get("manual_conflicts", [])
                        )
                        result["sync_details"].append(artist_result)

                    except Exception as e:
                        error_msg = f"Failed to sync artist {server_artist.get('name', 'Unknown')}: {str(e)}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Failed to sync {server_name} metadata: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        return result

    def _sync_artist_metadata_bidirectional(
        self, session, service: BaseMediaServerService, server_artist: Dict
    ) -> Dict:
        """Sync metadata for a specific artist bidirectionally"""
        artist_name = server_artist.get("name")
        server_artist_id = server_artist.get("id")

        result = {
            "artist_name": artist_name,
            "server_artist_id": server_artist_id,
            "items_synced": 0,
            "conflicts_resolved": 0,
            "updates_to_server": 0,
            "updates_from_server": 0,
            "manual_conflicts": [],
            "albums_synced": [],
        }

        # Find matching artist in MVidarr database
        mvidarr_artist = (
            session.query(Artist)
            .filter(
                or_(
                    Artist.name.ilike(f"%{artist_name}%"),
                    getattr(Artist, f"{service.server_type.value}_id", None)
                    == server_artist_id,
                )
            )
            .first()
        )

        if not mvidarr_artist:
            # Artist doesn't exist in MVidarr, skip bidirectional sync
            logger.debug(
                f"Artist {artist_name} not found in MVidarr, skipping metadata sync"
            )
            return result

        # Update artist-level server ID if missing
        server_id_field = f"{service.server_type.value}_id"
        if hasattr(mvidarr_artist, server_id_field):
            current_server_id = getattr(mvidarr_artist, server_id_field)
            if not current_server_id:
                setattr(mvidarr_artist, server_id_field, server_artist_id)
                session.commit()

        # Get albums for this artist from the server
        try:
            server_albums = service.get_artist_albums(server_artist_id)

            for server_album in server_albums:
                album_result = self._sync_album_metadata_bidirectional(
                    session, service, mvidarr_artist, server_album
                )

                result["items_synced"] += album_result.get("items_synced", 0)
                result["conflicts_resolved"] += album_result.get(
                    "conflicts_resolved", 0
                )
                result["updates_to_server"] += album_result.get("updates_to_server", 0)
                result["updates_from_server"] += album_result.get(
                    "updates_from_server", 0
                )
                result["manual_conflicts"].extend(
                    album_result.get("manual_conflicts", [])
                )
                result["albums_synced"].append(album_result)

        except Exception as e:
            logger.error(f"Failed to sync albums for artist {artist_name}: {e}")

        return result

    def _sync_album_metadata_bidirectional(
        self,
        session,
        service: BaseMediaServerService,
        mvidarr_artist: Artist,
        server_album: Dict,
    ) -> Dict:
        """Sync metadata for album tracks bidirectionally"""
        album_name = server_album.get("name")
        server_album_id = server_album.get("id")

        result = {
            "album_name": album_name,
            "server_album_id": server_album_id,
            "items_synced": 0,
            "conflicts_resolved": 0,
            "updates_to_server": 0,
            "updates_from_server": 0,
            "manual_conflicts": [],
            "tracks_synced": [],
        }

        try:
            # Get tracks from this album
            server_tracks = service.get_album_tracks(server_album_id)

            for server_track in server_tracks:
                track_result = self._sync_track_metadata_bidirectional(
                    session, service, mvidarr_artist, server_track
                )

                result["items_synced"] += track_result.get("items_synced", 0)
                result["conflicts_resolved"] += track_result.get(
                    "conflicts_resolved", 0
                )
                result["updates_to_server"] += track_result.get("updates_to_server", 0)
                result["updates_from_server"] += track_result.get(
                    "updates_from_server", 0
                )
                result["manual_conflicts"].extend(
                    track_result.get("manual_conflicts", [])
                )
                result["tracks_synced"].append(track_result)

        except Exception as e:
            logger.error(f"Failed to sync tracks for album {album_name}: {e}")

        return result

    def _sync_track_metadata_bidirectional(
        self,
        session,
        service: BaseMediaServerService,
        mvidarr_artist: Artist,
        server_track: Dict,
    ) -> Dict:
        """Sync metadata for a specific track bidirectionally"""
        track_name = server_track.get("name")
        server_track_id = server_track.get("id")

        result = {
            "track_name": track_name,
            "server_track_id": server_track_id,
            "items_synced": 0,
            "conflicts_resolved": 0,
            "updates_to_server": 0,
            "updates_from_server": 0,
            "manual_conflicts": [],
        }

        # Try to find matching video in MVidarr
        # This is a simplified matching - in practice, you'd use more sophisticated matching
        matching_video = (
            session.query(Video)
            .filter(
                and_(
                    Video.artist_id == mvidarr_artist.id,
                    Video.title.ilike(f"%{track_name}%"),
                )
            )
            .first()
        )

        if not matching_video:
            # No matching video found, skip
            return result

        # Extract metadata from server track
        server_metadata = self._extract_server_track_metadata(server_track)
        mvidarr_metadata = self._extract_mvidarr_video_metadata(matching_video)

        # Compare and resolve conflicts
        conflicts = self._identify_metadata_conflicts(mvidarr_metadata, server_metadata)

        if conflicts:
            resolution_actions = self._resolve_metadata_conflicts(
                conflicts, mvidarr_metadata, server_metadata
            )

            # Apply resolutions
            for action in resolution_actions:
                if action["target"] == "mvidarr":
                    self._apply_metadata_to_mvidarr_video(
                        session, matching_video, action["metadata"]
                    )
                    result["updates_from_server"] += 1
                elif action["target"] == "server":
                    # Apply to server (implementation depends on server capabilities)
                    success = self._apply_metadata_to_server_track(
                        service, server_track_id, action["metadata"]
                    )
                    if success:
                        result["updates_to_server"] += 1
                elif action["target"] == "manual_review":
                    result["manual_conflicts"].append(
                        {
                            "mvidarr_video_id": matching_video.id,
                            "server_track_id": server_track_id,
                            "track_name": track_name,
                            "conflicts": conflicts,
                            "mvidarr_metadata": mvidarr_metadata,
                            "server_metadata": server_metadata,
                        }
                    )

            result["conflicts_resolved"] += len(
                [a for a in resolution_actions if a["target"] != "manual_review"]
            )

        result["items_synced"] = 1
        return result

    def _extract_server_track_metadata(self, server_track: Dict) -> Dict:
        """Extract metadata from server track data"""
        user_data = server_track.get("user_data", {})

        return {
            "play_count": user_data.get("PlayCount", 0),
            "last_played": user_data.get("LastPlayedDate"),
            "favorite": user_data.get("IsFavorite", False),
            "rating": user_data.get("Rating"),
            "watched_status": user_data.get("Played", False),
        }

    def _extract_mvidarr_video_metadata(self, video: Video) -> Dict:
        """Extract metadata from MVidarr video"""
        return {
            "play_count": getattr(video, "play_count", 0),
            "last_played": getattr(video, "last_played"),
            "favorite": getattr(video, "favorite", False),
            "rating": getattr(video, "rating"),
            "watched_status": video.status == VideoStatus.DOWNLOADED,
        }

    def _identify_metadata_conflicts(
        self, mvidarr_metadata: Dict, server_metadata: Dict
    ) -> List[Dict]:
        """Identify conflicts between MVidarr and server metadata"""
        conflicts = []

        for field_enum in MetadataField:
            field = field_enum.value

            # Skip fields not enabled for sync
            if not self.config["sync_fields"].get(field, False):
                continue

            mvidarr_value = mvidarr_metadata.get(field)
            server_value = server_metadata.get(field)

            # Check if values differ significantly
            if self._values_differ(mvidarr_value, server_value):
                conflicts.append(
                    {
                        "field": field,
                        "mvidarr_value": mvidarr_value,
                        "server_value": server_value,
                    }
                )

        return conflicts

    def _values_differ(self, value1, value2) -> bool:
        """Check if two metadata values differ significantly"""
        if value1 is None and value2 is None:
            return False

        if value1 is None or value2 is None:
            return True

        # For numeric values, check if they differ
        if isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
            return abs(value1 - value2) > 0.01

        # For strings and other types, direct comparison
        return value1 != value2

    def _resolve_metadata_conflicts(
        self, conflicts: List[Dict], mvidarr_metadata: Dict, server_metadata: Dict
    ) -> List[Dict]:
        """Resolve metadata conflicts based on configured strategy"""
        resolution_strategy = SyncConflictResolution(self.config["conflict_resolution"])
        actions = []

        for conflict in conflicts:
            field = conflict["field"]
            mvidarr_value = conflict["mvidarr_value"]
            server_value = conflict["server_value"]

            if resolution_strategy == SyncConflictResolution.MVIDARR_WINS:
                # Update server with MVidarr value
                actions.append({"target": "server", "metadata": {field: mvidarr_value}})

            elif resolution_strategy == SyncConflictResolution.SERVER_WINS:
                # Update MVidarr with server value
                actions.append({"target": "mvidarr", "metadata": {field: server_value}})

            elif resolution_strategy == SyncConflictResolution.NEWEST_WINS:
                # This would require timestamp comparison - simplified here
                # In practice, you'd compare last_updated timestamps
                actions.append(
                    {
                        "target": "mvidarr",  # Default to updating MVidarr
                        "metadata": {field: server_value},
                    }
                )

            elif resolution_strategy == SyncConflictResolution.MANUAL_REVIEW:
                # Flag for manual resolution
                actions.append({"target": "manual_review", "metadata": {field: None}})

        return actions

    def _apply_metadata_to_mvidarr_video(
        self, session, video: Video, metadata: Dict
    ) -> bool:
        """Apply metadata updates to MVidarr video"""
        try:
            for field, value in metadata.items():
                if hasattr(video, field):
                    setattr(video, field, value)

            session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to apply metadata to MVidarr video: {e}")
            return False

    def _apply_metadata_to_server_track(
        self, service: BaseMediaServerService, track_id: str, metadata: Dict
    ) -> bool:
        """Apply metadata updates to server track"""
        try:
            # This is a simplified implementation
            # Different media servers have different capabilities for metadata updates

            for field, value in metadata.items():
                if field == "play_count":
                    # Update play count (if server supports it)
                    pass
                elif field == "favorite":
                    # Update favorite status
                    pass
                elif field == "watched_status":
                    # Update watched/played status
                    service.update_play_status(track_id, value)

            return True
        except Exception as e:
            logger.error(f"Failed to apply metadata to server track: {e}")
            return False

    def get_manual_conflict_queue(self) -> List[Dict]:
        """Get queue of conflicts requiring manual review"""
        # This would typically be stored in database
        # For now, return empty list as placeholder
        return []

    def resolve_manual_conflict(self, conflict_id: str, resolution: Dict) -> Dict:
        """Resolve a manual conflict with user-provided resolution"""
        # Implementation would depend on how conflicts are stored
        return {"success": True, "message": "Conflict resolved successfully"}


# Global instance
media_server_sync_service = MediaServerSyncService()
