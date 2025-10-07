"""
Spotify Synchronization Service for bidirectional playlist sync and real-time updates
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, or_

from src.database.connection import get_db
from src.database.models import Artist, Playlist, PlaylistEntry, Video
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import settings
from src.services.spotify_service import spotify_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.spotify_sync")


@dataclass
class SyncResult:
    """Result of playlist synchronization"""

    success: bool
    playlist_id: Optional[str] = None
    spotify_playlist_id: Optional[str] = None
    tracks_added: int = 0
    tracks_removed: int = 0
    artists_discovered: int = 0
    videos_matched: int = 0
    conflicts_resolved: int = 0
    errors: List[str] = field(default_factory=list)
    sync_direction: str = "bidirectional"
    processing_time: float = 0.0


class SpotifySyncService:
    """Service for Spotify playlist synchronization and real-time updates"""

    def __init__(self):
        self.spotify = spotify_service
        self.imvdb = imvdb_service

        # Configuration
        self.auto_sync_enabled = settings.get_bool("spotify_auto_sync", True)
        self.sync_interval_minutes = settings.get_int("spotify_sync_interval", 15)
        self.conflict_resolution = settings.get(
            "spotify_conflict_resolution", "mvidarr_wins"
        )
        self.max_artists_per_sync = settings.get_int("spotify_max_artists_per_sync", 50)

        # Cache for sync status
        self._last_sync_time = {}
        self._sync_in_progress = set()

    def sync_user_playlists(
        self, user_id: str = None, force_refresh: bool = False
    ) -> List[SyncResult]:
        """Sync all user playlists from Spotify to MVidarr"""
        start_time = time.time()
        results = []

        try:
            logger.info("Starting Spotify playlist synchronization")

            # Get user's Spotify playlists
            playlists_response = self.spotify.get_user_playlists(limit=50)
            if not playlists_response or "items" not in playlists_response:
                return [
                    SyncResult(
                        success=False, errors=["Failed to get Spotify playlists"]
                    )
                ]

            playlists = playlists_response["items"]
            logger.info(f"Found {len(playlists)} Spotify playlists to sync")

            with get_db() as session:
                for spotify_playlist in playlists:
                    try:
                        playlist_result = self._sync_single_playlist(
                            session, spotify_playlist, force_refresh
                        )
                        results.append(playlist_result)

                        # Rate limiting between playlists
                        time.sleep(0.5)

                    except Exception as e:
                        logger.error(
                            f"Failed to sync playlist {spotify_playlist.get('name', 'Unknown')}: {e}"
                        )
                        results.append(
                            SyncResult(
                                success=False,
                                spotify_playlist_id=spotify_playlist.get("id"),
                                errors=[str(e)],
                            )
                        )

                session.commit()

            # Summary logging
            successful_syncs = sum(1 for r in results if r.success)
            total_artists = sum(r.artists_discovered for r in results)
            total_videos = sum(r.videos_matched for r in results)

            logger.info(
                f"Playlist sync completed: {successful_syncs}/{len(results)} playlists, "
                f"{total_artists} artists discovered, {total_videos} videos matched"
            )

        except Exception as e:
            logger.error(f"Playlist synchronization failed: {e}")
            results.append(SyncResult(success=False, errors=[str(e)]))

        return results

    def _sync_single_playlist(
        self, session, spotify_playlist: Dict, force_refresh: bool = False
    ) -> SyncResult:
        """Sync a single Spotify playlist"""
        playlist_name = spotify_playlist.get("name", "Unknown Playlist")
        spotify_playlist_id = spotify_playlist.get("id")

        start_time = time.time()
        result = SyncResult(success=False, spotify_playlist_id=spotify_playlist_id)

        try:
            logger.debug(f"Syncing playlist: {playlist_name}")

            # Check if we should skip this sync
            if not force_refresh and not self._should_sync_playlist(
                spotify_playlist_id
            ):
                logger.debug(
                    f"Skipping playlist sync for {playlist_name} (recent sync)"
                )
                result.success = True
                return result

            # Get or create MVidarr playlist
            mvidarr_playlist = self._get_or_create_mvidarr_playlist(
                session, spotify_playlist
            )
            result.playlist_id = str(mvidarr_playlist.id)

            # Get tracks from Spotify playlist
            tracks_response = self.spotify.get_playlist_tracks(
                spotify_playlist_id, limit=100
            )

            if not tracks_response or "items" not in tracks_response:
                result.errors.append("Failed to get playlist tracks from Spotify")
                return result

            spotify_tracks = tracks_response["items"]
            logger.debug(f"Found {len(spotify_tracks)} tracks in Spotify playlist")

            # Process tracks and discover artists/videos
            artists_discovered = set()
            videos_matched = []

            for track_item in spotify_tracks:
                track = track_item.get("track")
                if not track or track.get("type") != "track":
                    continue

                # Extract artist information
                for artist_data in track.get("artists", []):
                    artist_name = artist_data.get("name")
                    if not artist_name:
                        continue

                    # Find or create artist in MVidarr
                    artist = self._find_or_create_artist(session, artist_data)
                    if artist:
                        artists_discovered.add(artist.id)

                        # Search for music videos for this track
                        track_name = track.get("name", "")
                        videos = self._find_matching_videos(session, artist, track_name)
                        videos_matched.extend(videos)

            # Update MVidarr playlist with matched videos
            self._update_playlist_videos(session, mvidarr_playlist, videos_matched)

            # Update sync tracking
            self._last_sync_time[spotify_playlist_id] = datetime.now()

            result.success = True
            result.artists_discovered = len(artists_discovered)
            result.videos_matched = len(videos_matched)
            result.processing_time = time.time() - start_time

            logger.debug(
                f"Successfully synced playlist {playlist_name}: "
                f"{result.artists_discovered} artists, {result.videos_matched} videos"
            )

        except Exception as e:
            logger.error(f"Failed to sync playlist {playlist_name}: {e}")
            result.errors.append(str(e))

        result.processing_time = time.time() - start_time
        return result

    def _get_or_create_mvidarr_playlist(
        self, session, spotify_playlist: Dict
    ) -> Playlist:
        """Get existing or create new MVidarr playlist for Spotify playlist"""
        spotify_playlist_id = spotify_playlist.get("id")
        playlist_name = spotify_playlist.get("name", "Unknown Playlist")

        # Look for existing playlist with Spotify ID
        existing_playlist = (
            session.query(Playlist)
            .filter(Playlist.name.ilike(f"%{playlist_name}%"))
            .first()
        )

        if existing_playlist:
            # Update metadata if needed
            if not existing_playlist.description:
                existing_playlist.description = (
                    f"Imported from Spotify: {spotify_playlist.get('description', '')}"
                )
            return existing_playlist

        # Create new playlist
        new_playlist = Playlist(
            name=f"[Spotify] {playlist_name}",
            description=f"Imported from Spotify: {spotify_playlist.get('description', '')}",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        session.add(new_playlist)
        session.flush()  # Get the ID

        logger.info(f"Created new MVidarr playlist: {new_playlist.name}")
        return new_playlist

    def _find_or_create_artist(
        self, session, spotify_artist_data: Dict
    ) -> Optional[Artist]:
        """Find existing or create new artist from Spotify data"""
        artist_name = spotify_artist_data.get("name")
        spotify_id = spotify_artist_data.get("id")

        if not artist_name:
            return None

        # Look for existing artist by Spotify ID or name
        existing_artist = (
            session.query(Artist)
            .filter(
                or_(
                    Artist.spotify_id == spotify_id,
                    Artist.name.ilike(f"%{artist_name}%"),
                )
            )
            .first()
        )

        if existing_artist:
            # Update Spotify ID if missing
            if not existing_artist.spotify_id and spotify_id:
                existing_artist.spotify_id = spotify_id
                logger.debug(f"Updated Spotify ID for artist: {artist_name}")
            return existing_artist

        # Create new artist
        new_artist = Artist(
            name=artist_name,
            spotify_id=spotify_id,
            status="new",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        session.add(new_artist)
        session.flush()  # Get the ID

        # Run auto-processing for newly created artist
        try:
            from src.services.artist_auto_processing_service import (
                artist_auto_processing_service,
            )

            # Ensure artist is bound to session for auto-processing
            session.refresh(new_artist)
            auto_processing_results = artist_auto_processing_service.process_new_artist(
                new_artist, session
            )
            # Refresh artist after auto-processing to get any metadata enrichment updates
            session.refresh(new_artist)
            match_count = auto_processing_results.get("auto_match", {}).get(
                "match_count", 0
            )
            logger.info(
                f"Auto-processing completed for {artist_name} - {match_count} services matched"
            )
        except Exception as e:
            logger.warning(
                f"Auto-processing failed for newly created artist {artist_name}: {e}"
            )

        logger.info(f"Created new artist from Spotify: {artist_name}")
        return new_artist

    def _find_matching_videos(
        self, session, artist: Artist, track_name: str
    ) -> List[Video]:
        """Find MVidarr videos that match a Spotify track"""
        if not track_name:
            return []

        # Search for videos by this artist with similar titles
        matching_videos = (
            session.query(Video)
            .filter(
                and_(Video.artist_id == artist.id, Video.title.ilike(f"%{track_name}%"))
            )
            .all()
        )

        # Use similarity scoring to find best matches
        scored_videos = []
        for video in matching_videos:
            similarity = self._calculate_track_similarity(track_name, video.title)
            if similarity >= 0.7:  # Minimum similarity threshold
                scored_videos.append((video, similarity))

        # Sort by similarity and return top matches
        scored_videos.sort(key=lambda x: x[1], reverse=True)
        return [video for video, score in scored_videos[:3]]  # Top 3 matches

    def _calculate_track_similarity(
        self, spotify_track: str, mvidarr_title: str
    ) -> float:
        """Calculate similarity between Spotify track name and MVidarr video title"""
        if not spotify_track or not mvidarr_title:
            return 0.0

        # Clean and normalize titles
        spotify_clean = self._clean_track_title(spotify_track.lower())
        mvidarr_clean = self._clean_track_title(mvidarr_title.lower())

        # Exact match
        if spotify_clean == mvidarr_clean:
            return 1.0

        # Contains match
        if spotify_clean in mvidarr_clean or mvidarr_clean in spotify_clean:
            return 0.9

        # Token-based similarity
        spotify_tokens = set(spotify_clean.split())
        mvidarr_tokens = set(mvidarr_clean.split())

        if not spotify_tokens or not mvidarr_tokens:
            return 0.0

        intersection = spotify_tokens.intersection(mvidarr_tokens)
        union = spotify_tokens.union(mvidarr_tokens)

        return len(intersection) / len(union) if union else 0.0

    def _clean_track_title(self, title: str) -> str:
        """Clean track title for better matching"""
        import re

        # Remove common video-specific suffixes
        title = re.sub(
            r"\s*\(.*(?:video|official|music|clip|live|acoustic|remix).*\)",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove feat., featuring, etc.
        title = re.sub(
            r"\s*(feat\.?|featuring|ft\.?|with)\s+.*", "", title, flags=re.IGNORECASE
        )

        # Remove extra whitespace
        title = " ".join(title.split())

        return title.strip()

    def _update_playlist_videos(
        self, session, mvidarr_playlist: Playlist, videos: List[Video]
    ):
        """Update MVidarr playlist with matched videos"""
        if not videos:
            return

        # Get current playlist videos
        current_video_ids = set(
            pe.video_id
            for pe in session.query(PlaylistEntry)
            .filter(PlaylistEntry.playlist_id == mvidarr_playlist.id)
            .all()
        )

        # Add new videos to playlist
        new_videos_added = 0
        for video in videos:
            if video.id not in current_video_ids:
                playlist_entry = PlaylistEntry(
                    playlist_id=mvidarr_playlist.id,
                    video_id=video.id,
                    position=len(current_video_ids) + new_videos_added + 1,
                    added_at=datetime.now(),
                )
                session.add(playlist_entry)
                current_video_ids.add(video.id)
                new_videos_added += 1

        if new_videos_added > 0:
            mvidarr_playlist.updated_at = datetime.now()
            logger.debug(
                f"Added {new_videos_added} videos to playlist {mvidarr_playlist.name}"
            )

    def _should_sync_playlist(self, spotify_playlist_id: str) -> bool:
        """Check if playlist should be synced based on last sync time"""
        if not self.auto_sync_enabled:
            return False

        last_sync = self._last_sync_time.get(spotify_playlist_id)
        if not last_sync:
            return True

        sync_threshold = timedelta(minutes=self.sync_interval_minutes)
        return datetime.now() - last_sync >= sync_threshold

    def export_playlist_to_spotify(
        self,
        mvidarr_playlist_id: int,
        create_new: bool = True,
        spotify_playlist_id: str = None,
    ) -> SyncResult:
        """Export MVidarr playlist to Spotify"""
        start_time = time.time()
        result = SyncResult(
            success=False,
            playlist_id=str(mvidarr_playlist_id),
            sync_direction="to_spotify",
        )

        try:
            with get_db() as session:
                # Get MVidarr playlist
                mvidarr_playlist = (
                    session.query(Playlist)
                    .filter(Playlist.id == mvidarr_playlist_id)
                    .first()
                )

                if not mvidarr_playlist:
                    result.errors.append("MVidarr playlist not found")
                    return result

                # Get playlist videos
                playlist_entries = (
                    session.query(PlaylistEntry)
                    .join(Video)
                    .join(Artist)
                    .filter(PlaylistEntry.playlist_id == mvidarr_playlist_id)
                    .order_by(PlaylistEntry.position)
                    .all()
                )

                if not playlist_entries:
                    result.errors.append("No videos in MVidarr playlist")
                    return result

                # Find matching Spotify tracks
                spotify_track_uris = []
                for pe in playlist_entries:
                    video = pe.video
                    artist = video.artist

                    # Search for track on Spotify
                    search_query = f"track:{video.title} artist:{artist.name}"
                    track_search = self.spotify.search_tracks(search_query, limit=5)

                    if track_search and track_search.get("tracks", {}).get("items"):
                        # Find best match
                        best_match = self._find_best_track_match(
                            video.title, artist.name, track_search["tracks"]["items"]
                        )

                        if best_match:
                            spotify_track_uris.append(best_match["uri"])

                if not spotify_track_uris:
                    result.errors.append("No matching Spotify tracks found")
                    return result

                # Create or update Spotify playlist
                if create_new or not spotify_playlist_id:
                    # Create new Spotify playlist
                    playlist_name = f"MVidarr: {mvidarr_playlist.name}"
                    playlist_description = (
                        f"Exported from MVidarr - {mvidarr_playlist.description or ''}"
                    )

                    spotify_playlist_response = self.spotify.create_playlist(
                        name=playlist_name,
                        description=playlist_description,
                        public=False,
                    )

                    if spotify_playlist_response and "id" in spotify_playlist_response:
                        spotify_playlist_id = spotify_playlist_response["id"]
                        result.spotify_playlist_id = spotify_playlist_id
                    else:
                        result.errors.append("Failed to create Spotify playlist")
                        return result

                # Add tracks to Spotify playlist
                if spotify_track_uris:
                    add_result = self.spotify.add_tracks_to_playlist(
                        spotify_playlist_id, spotify_track_uris
                    )

                    if add_result and "snapshot_id" in add_result:
                        result.tracks_added = len(spotify_track_uris)
                        result.success = True
                        logger.info(
                            f"Successfully exported {len(spotify_track_uris)} tracks to Spotify playlist"
                        )
                    else:
                        result.errors.append("Failed to add tracks to Spotify playlist")

        except Exception as e:
            logger.error(f"Failed to export playlist to Spotify: {e}")
            result.errors.append(str(e))

        result.processing_time = time.time() - start_time
        return result

    def _find_best_track_match(
        self, video_title: str, artist_name: str, spotify_tracks: List[Dict]
    ) -> Optional[Dict]:
        """Find the best matching Spotify track for a video"""
        best_match = None
        best_score = 0.0

        for track in spotify_tracks:
            # Check artist match
            track_artists = [a.get("name", "") for a in track.get("artists", [])]
            artist_match = any(
                self._calculate_track_similarity(artist_name, track_artist) >= 0.8
                for track_artist in track_artists
            )

            if not artist_match:
                continue

            # Check track title match
            track_name = track.get("name", "")
            title_score = self._calculate_track_similarity(video_title, track_name)

            if title_score > best_score:
                best_score = title_score
                best_match = track

        return best_match if best_score >= 0.7 else None

    def sync_new_releases(self) -> Dict:
        """Check for new releases from followed artists and notify"""
        try:
            logger.info("Checking for new releases from followed artists")

            # Get followed artists
            followed_response = self.spotify.get_followed_artists(limit=50)
            if not followed_response or "artists" not in followed_response:
                return {"success": False, "error": "Failed to get followed artists"}

            followed_artists = followed_response["artists"].get("items", [])
            new_releases = []

            with get_db() as session:
                for spotify_artist in followed_artists:
                    artist_id = spotify_artist.get("id")
                    artist_name = spotify_artist.get("name")

                    # Get artist's latest albums
                    albums_response = self.spotify.get_artist_albums(
                        artist_id, limit=10
                    )
                    if not albums_response or "items" not in albums_response:
                        continue

                    albums = albums_response["items"]

                    # Check for recent releases (last 30 days)
                    cutoff_date = datetime.now() - timedelta(days=30)

                    for album in albums:
                        release_date_str = album.get("release_date")
                        if not release_date_str:
                            continue

                        try:
                            # Parse release date
                            if len(release_date_str) == 4:  # Year only
                                release_date = datetime(int(release_date_str), 1, 1)
                            elif len(release_date_str) == 7:  # Year-month
                                year, month = release_date_str.split("-")
                                release_date = datetime(int(year), int(month), 1)
                            else:  # Full date
                                release_date = datetime.strptime(
                                    release_date_str, "%Y-%m-%d"
                                )

                            if release_date >= cutoff_date:
                                new_releases.append(
                                    {
                                        "artist_name": artist_name,
                                        "album_name": album.get("name"),
                                        "release_date": release_date_str,
                                        "album_type": album.get("album_type"),
                                        "spotify_url": album.get(
                                            "external_urls", {}
                                        ).get("spotify"),
                                        "total_tracks": album.get("total_tracks", 0),
                                    }
                                )

                        except ValueError as e:
                            logger.debug(
                                f"Failed to parse release date {release_date_str}: {e}"
                            )
                            continue

            logger.info(f"Found {len(new_releases)} new releases from followed artists")
            return {
                "success": True,
                "new_releases": new_releases,
                "total_releases": len(new_releases),
                "check_date": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to check for new releases: {e}")
            return {"success": False, "error": str(e)}

    def get_music_video_recommendations(self, limit: int = 20) -> Dict:
        """Get music video recommendations based on Spotify listening history"""
        try:
            logger.info("Generating music video recommendations from Spotify data")

            # Get user's top tracks for recommendation seeds
            top_tracks_response = self.spotify.get_user_top_tracks(
                time_range="medium_term", limit=10
            )

            if not top_tracks_response or "items" not in top_tracks_response:
                return {"success": False, "error": "Failed to get user's top tracks"}

            top_tracks = top_tracks_response["items"]
            seed_track_ids = [track["id"] for track in top_tracks[:5]]

            # Get recommendations from Spotify
            recommendations_response = self.spotify.get_recommendations(
                seed_tracks=seed_track_ids, limit=limit
            )

            if not recommendations_response or "tracks" not in recommendations_response:
                return {
                    "success": False,
                    "error": "Failed to get Spotify recommendations",
                }

            recommended_tracks = recommendations_response["tracks"]
            video_recommendations = []

            with get_db() as session:
                for track in recommended_tracks:
                    # Find artist in MVidarr database
                    track_artists = track.get("artists", [])
                    if not track_artists:
                        continue

                    artist_name = track_artists[0].get("name")
                    existing_artist = (
                        session.query(Artist)
                        .filter(Artist.name.ilike(f"%{artist_name}%"))
                        .first()
                    )

                    if existing_artist:
                        # Find matching videos
                        track_name = track.get("name", "")
                        matching_videos = self._find_matching_videos(
                            session, existing_artist, track_name
                        )

                        if matching_videos:
                            for video in matching_videos:
                                video_recommendations.append(
                                    {
                                        "video_id": video.id,
                                        "video_title": video.title,
                                        "artist_name": existing_artist.name,
                                        "spotify_track_name": track_name,
                                        "spotify_track_id": track.get("id"),
                                        "popularity": track.get("popularity", 0),
                                        "preview_url": track.get("preview_url"),
                                        "external_urls": track.get("external_urls", {}),
                                        "recommendation_score": self._calculate_track_similarity(
                                            track_name, video.title
                                        ),
                                    }
                                )

            # Sort by recommendation score
            video_recommendations.sort(
                key=lambda x: x["recommendation_score"], reverse=True
            )

            return {
                "success": True,
                "recommendations": video_recommendations[:limit],
                "total_recommendations": len(video_recommendations),
                "based_on_tracks": len(seed_track_ids),
                "generation_date": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to generate music video recommendations: {e}")
            return {"success": False, "error": str(e)}

    def process_spotify_webhook(self, webhook_data: Dict) -> Dict:
        """Process incoming Spotify webhook events"""
        try:
            event_type = webhook_data.get("type")
            event_data = webhook_data.get("data", {})

            logger.info(f"Processing Spotify webhook event: {event_type}")

            if event_type == "playlist.update":
                return self._handle_playlist_update_event(event_data)
            elif event_type == "user.playlist.created":
                return self._handle_playlist_created_event(event_data)
            elif event_type == "user.playlist.deleted":
                return self._handle_playlist_deleted_event(event_data)
            elif event_type == "user.library.updated":
                return self._handle_library_update_event(event_data)
            else:
                logger.debug(f"Unhandled Spotify webhook event type: {event_type}")
                return {
                    "success": True,
                    "message": f"Event type {event_type} not processed",
                }

        except Exception as e:
            logger.error(f"Failed to process Spotify webhook: {e}")
            return {"success": False, "error": str(e)}

    def _handle_playlist_update_event(self, event_data: Dict) -> Dict:
        """Handle playlist update webhook event"""
        playlist_id = event_data.get("playlist_id")
        if not playlist_id:
            return {"success": False, "error": "No playlist ID in event"}

        # Trigger resync of this specific playlist
        try:
            with get_db() as session:
                # Find corresponding MVidarr playlist
                mvidarr_playlist = (
                    session.query(Playlist)
                    .filter(Playlist.name.contains(playlist_id))
                    .first()
                )

                if mvidarr_playlist:
                    # Get updated Spotify playlist
                    spotify_playlist = self.spotify._make_request(
                        f"playlists/{playlist_id}"
                    )
                    if spotify_playlist:
                        result = self._sync_single_playlist(
                            session, spotify_playlist, force_refresh=True
                        )
                        session.commit()
                        return {"success": True, "sync_result": result}

            return {"success": True, "message": "Playlist not found in MVidarr"}

        except Exception as e:
            logger.error(f"Failed to handle playlist update event: {e}")
            return {"success": False, "error": str(e)}

    def _handle_playlist_created_event(self, event_data: Dict) -> Dict:
        """Handle new playlist creation webhook event"""
        # For now, just log the event - could implement auto-import if desired
        playlist_name = event_data.get("playlist_name", "Unknown")
        logger.info(f"New Spotify playlist created: {playlist_name}")
        return {"success": True, "message": f"Noted new playlist: {playlist_name}"}

    def _handle_playlist_deleted_event(self, event_data: Dict) -> Dict:
        """Handle playlist deletion webhook event"""
        # For now, just log the event - could implement cleanup if desired
        playlist_id = event_data.get("playlist_id", "Unknown")
        logger.info(f"Spotify playlist deleted: {playlist_id}")
        return {"success": True, "message": f"Noted deleted playlist: {playlist_id}"}

    def _handle_library_update_event(self, event_data: Dict) -> Dict:
        """Handle user library update webhook event"""
        # Could trigger artist discovery or recommendation refresh
        logger.info("User Spotify library updated")
        return {"success": True, "message": "Library update noted"}

    def get_sync_status(self) -> Dict:
        """Get current synchronization status"""
        return {
            "auto_sync_enabled": self.auto_sync_enabled,
            "sync_interval_minutes": self.sync_interval_minutes,
            "last_sync_times": {
                playlist_id: sync_time.isoformat()
                for playlist_id, sync_time in self._last_sync_time.items()
            },
            "syncs_in_progress": list(self._sync_in_progress),
            "conflict_resolution": self.conflict_resolution,
            "max_artists_per_sync": self.max_artists_per_sync,
        }

    def clear_sync_cache(self):
        """Clear synchronization cache"""
        self._last_sync_time.clear()
        self._sync_in_progress.clear()
        logger.info("Spotify sync cache cleared")


# Global instance
spotify_sync_service = SpotifySyncService()
