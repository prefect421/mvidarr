"""
Dynamic Playlist Service for Issue #109

Handles dynamic playlist creation, updating, and filter execution.
Provides automatic video inclusion based on metadata criteria.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Playlist, PlaylistEntry, PlaylistType, Video
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

logger = get_logger("mvidarr.services.dynamic_playlist")


class DynamicPlaylistService:
    """Service for managing dynamic playlists with automatic video inclusion"""

    def __init__(self):
        self.logger = logger

    @monitor_performance("dynamic_playlist.create")
    def create_dynamic_playlist(
        self,
        name: str,
        description: Optional[str],
        user_id: int,
        filter_criteria: Dict[str, Any],
        is_public: bool = False,
        auto_update: bool = True,
    ) -> Playlist:
        """Create a new dynamic playlist with filter criteria"""

        with get_db() as session:
            # Create the playlist
            playlist = Playlist(
                name=name,
                description=description,
                user_id=user_id,
                is_public=is_public,
                playlist_type=PlaylistType.DYNAMIC,
                filter_criteria=filter_criteria,
                auto_update=auto_update,
                last_updated=None,  # Will be set when first populated
            )

            # Validate filter criteria
            if not playlist.validate_filter_criteria():
                raise ValueError("Invalid filter criteria provided")

            session.add(playlist)
            session.commit()

            # Get the playlist ID before any potential refresh issues
            playlist_id = playlist.id

            # Populate with initial videos using the ID to avoid session binding issues
            self.update_dynamic_playlist(playlist_id, session=session)

            self.logger.info(
                f"Created dynamic playlist '{name}' (ID: {playlist.id}) for user {user_id}"
            )
            return playlist

    @monitor_performance("dynamic_playlist.update")
    def update_dynamic_playlist(
        self, playlist_id: int, session: Optional[Session] = None
    ) -> bool:
        """Update a dynamic playlist by re-evaluating its filter criteria"""

        use_existing_session = session is not None
        if not session:
            session = get_db().__enter__()

        try:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )
            if not playlist:
                self.logger.warning(f"Dynamic playlist {playlist_id} not found")
                return False

            if not playlist.is_dynamic():
                self.logger.warning(f"Playlist {playlist_id} is not dynamic")
                return False

            if not playlist.filter_criteria:
                self.logger.warning(
                    f"Dynamic playlist {playlist_id} has no filter criteria"
                )
                return False

            # Get current video IDs in playlist
            current_video_ids = {entry.video_id for entry in playlist.entries}

            # Execute filter criteria to get matching videos
            matching_videos = self.execute_filter_criteria(
                playlist.filter_criteria, session
            )
            matching_video_ids = {video.id for video in matching_videos}

            # Calculate changes
            videos_to_add = matching_video_ids - current_video_ids
            videos_to_remove = current_video_ids - matching_video_ids

            changes_made = False

            # Remove videos that no longer match
            if videos_to_remove:
                session.query(PlaylistEntry).filter(
                    and_(
                        PlaylistEntry.playlist_id == playlist_id,
                        PlaylistEntry.video_id.in_(videos_to_remove),
                    )
                ).delete(synchronize_session=False)
                changes_made = True
                self.logger.debug(
                    f"Removed {len(videos_to_remove)} videos from playlist {playlist_id}"
                )

            # Add new matching videos
            if videos_to_add:
                # Get current max position
                max_position = (
                    session.query(func.max(PlaylistEntry.position))
                    .filter(PlaylistEntry.playlist_id == playlist_id)
                    .scalar()
                    or 0
                )

                # Add new entries
                new_entries = []
                for i, video_id in enumerate(videos_to_add, start=1):
                    entry = PlaylistEntry(
                        playlist_id=playlist_id,
                        video_id=video_id,
                        position=max_position + i,
                        added_by=playlist.user_id,  # System adds for dynamic playlists
                        added_at=datetime.utcnow(),
                    )
                    new_entries.append(entry)

                session.add_all(new_entries)
                changes_made = True
                self.logger.debug(
                    f"Added {len(videos_to_add)} videos to playlist {playlist_id}"
                )

            # Update playlist metadata
            playlist.last_updated = datetime.utcnow()
            playlist.update_stats()  # Recalculate video count and duration

            if not use_existing_session:
                session.commit()

            if changes_made:
                self.logger.info(
                    f"Updated dynamic playlist {playlist_id}: +{len(videos_to_add)}, -{len(videos_to_remove)} videos"
                )
            else:
                self.logger.debug(
                    f"No changes needed for dynamic playlist {playlist_id}"
                )

            return changes_made

        except Exception as e:
            if not use_existing_session:
                session.rollback()
            self.logger.error(f"Error updating dynamic playlist {playlist_id}: {e}")
            raise
        finally:
            if not use_existing_session:
                session.__exit__(None, None, None)

    @monitor_performance("dynamic_playlist.execute_filter")
    def execute_filter_criteria(
        self, filter_criteria: Dict[str, Any], session: Session
    ) -> List[Video]:
        """Execute filter criteria and return matching videos"""

        # Start with base video query
        query = session.query(Video).join(Artist, Video.artist_id == Artist.id)

        # Apply filters
        conditions = []

        # Genre filter
        if "genres" in filter_criteria and filter_criteria["genres"]:
            genres = filter_criteria["genres"]
            if isinstance(genres, str):
                genres = [genres]

            # Search in video metadata genres or artist genres
            genre_conditions = []
            for genre in genres:
                genre_conditions.append(
                    or_(
                        Video.video_metadata["genres"].astext.contains(genre),
                        Artist.genres.contains(genre),
                    )
                )
            conditions.append(or_(*genre_conditions))

        # Artist filter
        if "artists" in filter_criteria and filter_criteria["artists"]:
            artists = filter_criteria["artists"]
            if isinstance(artists, str):
                artists = [artists]

            artist_conditions = []
            for artist in artists:
                artist_conditions.append(Artist.name.ilike(f"%{artist}%"))
            conditions.append(or_(*artist_conditions))

        # Year range filter
        if "year_range" in filter_criteria:
            year_range = filter_criteria["year_range"]
            if "min" in year_range and year_range["min"]:
                conditions.append(Video.year >= year_range["min"])
            if "max" in year_range and year_range["max"]:
                conditions.append(Video.year <= year_range["max"])

        # Duration range filter (in seconds)
        if "duration_range" in filter_criteria:
            duration_range = filter_criteria["duration_range"]
            if "min" in duration_range and duration_range["min"]:
                conditions.append(Video.duration >= duration_range["min"])
            if "max" in duration_range and duration_range["max"]:
                conditions.append(Video.duration <= duration_range["max"])

        # Quality filter
        if "quality" in filter_criteria and filter_criteria["quality"]:
            quality_list = filter_criteria["quality"]
            if isinstance(quality_list, str):
                quality_list = [quality_list]
            conditions.append(Video.quality.in_(quality_list))

        # Status filter
        if "status" in filter_criteria and filter_criteria["status"]:
            status_list = filter_criteria["status"]
            if isinstance(status_list, str):
                status_list = [status_list]

            from src.database.models import VideoStatus

            status_enums = []
            for status_str in status_list:
                try:
                    status_enums.append(VideoStatus(status_str))
                except ValueError:
                    self.logger.warning(f"Invalid video status: {status_str}")

            if status_enums:
                conditions.append(Video.status.in_(status_enums))

        # Keywords filter (search in title and description)
        if "keywords" in filter_criteria and filter_criteria["keywords"]:
            keywords = filter_criteria["keywords"]
            if isinstance(keywords, str):
                keywords = [keywords]

            keyword_conditions = []
            for keyword in keywords:
                keyword_conditions.append(
                    or_(
                        Video.title.ilike(f"%{keyword}%"),
                        (
                            Video.description.ilike(f"%{keyword}%")
                            if Video.description
                            else False
                        ),
                    )
                )
            conditions.append(or_(*keyword_conditions))

        # Apply all conditions
        if conditions:
            query = query.filter(and_(*conditions))

        # Order by most recent first
        query = query.order_by(Video.created_at.desc())

        # Limit results to prevent performance issues (configurable)
        max_results = filter_criteria.get("max_results", 1000)
        query = query.limit(max_results)

        results = query.all()
        self.logger.debug(f"Filter criteria matched {len(results)} videos")
        return results

    @monitor_performance("dynamic_playlist.update_all")
    def update_all_dynamic_playlists(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """Update all dynamic playlists that need updating"""

        with get_db() as session:
            # Find dynamic playlists that need updating
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)

            playlists_to_update = (
                session.query(Playlist)
                .filter(
                    and_(
                        Playlist.playlist_type == PlaylistType.DYNAMIC,
                        Playlist.auto_update == True,
                        or_(
                            Playlist.last_updated.is_(None),
                            Playlist.last_updated < cutoff_time,
                        ),
                    )
                )
                .all()
            )

            updated_count = 0
            error_count = 0
            total_changes = 0

            for playlist in playlists_to_update:
                try:
                    changes_made = self.update_dynamic_playlist(
                        playlist.id, session=session
                    )
                    if changes_made:
                        total_changes += 1
                    updated_count += 1
                except Exception as e:
                    error_count += 1
                    self.logger.error(f"Failed to update playlist {playlist.id}: {e}")

            session.commit()

            result = {
                "playlists_checked": len(playlists_to_update),
                "playlists_updated": updated_count,
                "playlists_with_changes": total_changes,
                "errors": error_count,
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.logger.info(f"Dynamic playlist update batch: {result}")
            return result

    def get_dynamic_playlist_templates(self) -> List[Dict[str, Any]]:
        """Get predefined templates for dynamic playlists"""

        return [
            {
                "id": "recent_releases",
                "name": "Recent Releases",
                "description": "Videos from the last 2 years",
                "filter_criteria": {
                    "year_range": {
                        "min": datetime.now().year - 2,
                        "max": datetime.now().year,
                    },
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "the_80s",
                "name": "The 80s",
                "description": "Music videos from the 1980s",
                "filter_criteria": {
                    "year_range": {"min": 1980, "max": 1989},
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "the_90s",
                "name": "The 90s",
                "description": "Music videos from the 1990s",
                "filter_criteria": {
                    "year_range": {"min": 1990, "max": 1999},
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "short_videos",
                "name": "Short Videos",
                "description": "Videos under 4 minutes",
                "filter_criteria": {
                    "duration_range": {"min": 0, "max": 240},  # 4 minutes in seconds
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "hd_quality",
                "name": "HD Quality",
                "description": "High definition videos (720p and above)",
                "filter_criteria": {
                    "quality": ["720p", "1080p", "1440p", "2160p"],
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "rock_music",
                "name": "Rock Music",
                "description": "Rock and related genres",
                "filter_criteria": {
                    "genres": ["rock", "alternative rock", "hard rock", "indie rock"],
                    "status": ["DOWNLOADED"],
                },
            },
            {
                "id": "pop_hits",
                "name": "Pop Hits",
                "description": "Pop music videos",
                "filter_criteria": {
                    "genres": ["pop", "dance-pop", "electropop", "synth-pop"],
                    "status": ["DOWNLOADED"],
                },
            },
        ]

    def preview_filter_criteria(
        self, filter_criteria: Dict[str, Any], limit: int = 50
    ) -> Dict[str, Any]:
        """Preview what videos would match the given filter criteria"""

        with get_db() as session:
            # Add limit to prevent performance issues during preview
            preview_criteria = filter_criteria.copy()
            preview_criteria["max_results"] = limit

            matching_videos = self.execute_filter_criteria(preview_criteria, session)

            return {
                "total_matches": len(matching_videos),
                "preview_videos": [
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist": video.artist.name if video.artist else None,
                        "year": video.year,
                        "duration": video.duration,
                        "quality": video.quality,
                        "status": video.status.value,
                        "thumbnail_url": video.thumbnail_url,
                    }
                    for video in matching_videos[:limit]
                ],
                "filter_criteria": filter_criteria,
                "preview_limit": limit,
            }


# Global service instance
dynamic_playlist_service = DynamicPlaylistService()
