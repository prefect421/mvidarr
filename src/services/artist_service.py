"""
MVidarr - Artist Management Service
Handles tracked artists and their automatic video discovery
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ArtistService:
    """Service for managing tracked artists"""

    def __init__(self, database_manager, youtube_service):
        self.db = database_manager
        self.youtube_service = youtube_service

    def add_tracked_artist(
        self,
        user_id: int,
        artist_name: str,
        search_terms: str = None,
        auto_download: bool = True,
    ) -> Dict[str, Any]:
        """Add a new tracked artist"""
        try:
            artist_name = artist_name.strip()
            if not artist_name:
                return {"success": False, "error": "Artist name is required"}

            # Check if artist is already tracked
            existing_query = """
                SELECT id FROM tracked_artists 
                WHERE user_id = %s AND LOWER(artist_name) = LOWER(%s)
            """
            existing = self.db.execute_query(
                existing_query, (user_id, artist_name), fetch=True
            )

            if existing:
                return {
                    "success": False,
                    "error": f'Artist "{artist_name}" is already being tracked',
                }

            # Test search to validate artist exists
            search_result = self.youtube_service.search_artist_videos(artist_name, 5)
            if not search_result["success"]:
                return {
                    "success": False,
                    "error": f'Could not find videos for "{artist_name}": {search_result["error"]}',
                }

            videos_found = len(search_result["results"])

            # Insert new tracked artist
            insert_query = """
                INSERT INTO tracked_artists 
                (user_id, artist_name, search_terms, auto_download, videos_found) 
                VALUES (%s, %s, %s, %s, %s)
            """

            self.db.execute_query(
                insert_query,
                (user_id, artist_name, search_terms, auto_download, videos_found),
            )

            # Get the newly created artist
            artist_query = """
                SELECT * FROM tracked_artists 
                WHERE user_id = %s AND artist_name = %s
                ORDER BY created_at DESC LIMIT 1
            """
            artist_data = self.db.execute_query(
                artist_query, (user_id, artist_name), fetch=True
            )

            if artist_data:
                artist = artist_data[0]
                logger.info(f"Artist '{artist_name}' added for user {user_id}")

                return {
                    "success": True,
                    "message": f'Successfully added "{artist_name}" to tracked artists',
                    "artist": {
                        "id": artist["id"],
                        "name": artist["artist_name"],
                        "auto_download": artist["auto_download"],
                        "videos_found": artist["videos_found"],
                        "created_at": (
                            artist["created_at"].isoformat()
                            if artist["created_at"]
                            else None
                        ),
                        "is_active": artist["is_active"],
                    },
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to retrieve newly added artist",
                }

        except Exception as e:
            logger.error(f"Error adding tracked artist: {e}")
            return {"success": False, "error": f"Failed to add artist: {str(e)}"}

    def get_tracked_artists(self, user_id: int) -> Dict[str, Any]:
        """Get all tracked artists for a user"""
        try:
            query = """
                SELECT * FROM tracked_artists 
                WHERE user_id = %s 
                ORDER BY artist_name
            """

            artists_data = self.db.execute_query(query, (user_id,), fetch=True)

            artists = []
            for artist in artists_data:
                artists.append(
                    {
                        "id": artist["id"],
                        "name": artist["artist_name"],
                        "search_terms": artist["search_terms"],
                        "auto_download": artist["auto_download"],
                        "quality_preference": artist["quality_preference"],
                        "format_preference": artist["format_preference"],
                        "is_active": artist["is_active"],
                        "last_checked": (
                            artist["last_checked"].isoformat()
                            if artist["last_checked"]
                            else None
                        ),
                        "videos_found": artist["videos_found"],
                        "created_at": (
                            artist["created_at"].isoformat()
                            if artist["created_at"]
                            else None
                        ),
                    }
                )

            return {"success": True, "artists": artists, "total": len(artists)}

        except Exception as e:
            logger.error(f"Error getting tracked artists: {e}")
            return {
                "success": False,
                "error": "Failed to load tracked artists",
                "artists": [],
            }

    def remove_tracked_artist(self, user_id: int, artist_id: int) -> Dict[str, Any]:
        """Remove a tracked artist"""
        try:
            # Check if artist exists and belongs to user
            check_query = """
                SELECT artist_name FROM tracked_artists 
                WHERE id = %s AND user_id = %s
            """
            artist_data = self.db.execute_query(
                check_query, (artist_id, user_id), fetch=True
            )

            if not artist_data:
                return {
                    "success": False,
                    "error": "Artist not found or not owned by user",
                }

            artist_name = artist_data[0]["artist_name"]

            # Delete the artist
            delete_query = "DELETE FROM tracked_artists WHERE id = %s AND user_id = %s"
            rows_affected = self.db.execute_query(delete_query, (artist_id, user_id))

            if rows_affected > 0:
                logger.info(
                    f"Artist '{artist_name}' (ID: {artist_id}) removed for user {user_id}"
                )
                return {
                    "success": True,
                    "message": f'Successfully removed "{artist_name}" from tracked artists',
                }
            else:
                return {"success": False, "error": "Failed to remove artist"}

        except Exception as e:
            logger.error(f"Error removing tracked artist: {e}")
            return {"success": False, "error": f"Failed to remove artist: {str(e)}"}

    def update_artist_settings(
        self, user_id: int, artist_id: int, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update settings for a tracked artist"""
        try:
            # Build update query dynamically
            update_fields = []
            update_values = []

            allowed_fields = [
                "auto_download",
                "quality_preference",
                "format_preference",
                "is_active",
                "search_terms",
            ]

            for field, value in settings.items():
                if field in allowed_fields:
                    update_fields.append(f"{field} = %s")
                    update_values.append(value)

            if not update_fields:
                return {"success": False, "error": "No valid settings provided"}

            # Add user_id and artist_id for WHERE clause
            update_values.extend([user_id, artist_id])

            query = f"""
                UPDATE tracked_artists 
                SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND id = %s
            """

            rows_affected = self.db.execute_query(query, tuple(update_values))

            if rows_affected > 0:
                return {
                    "success": True,
                    "message": "Artist settings updated successfully",
                }
            else:
                return {
                    "success": False,
                    "error": "Artist not found or no changes made",
                }

        except Exception as e:
            logger.error(f"Error updating artist settings: {e}")
            return {
                "success": False,
                "error": f"Failed to update artist settings: {str(e)}",
            }

    def check_for_new_videos(
        self, user_id: int, artist_id: int = None
    ) -> Dict[str, Any]:
        """Check for new videos from tracked artists"""
        try:
            # Get artists to check
            if artist_id:
                query = """
                    SELECT * FROM tracked_artists 
                    WHERE user_id = %s AND id = %s AND is_active = 1
                """
                params = (user_id, artist_id)
            else:
                query = """
                    SELECT * FROM tracked_artists 
                    WHERE user_id = %s AND is_active = 1
                """
                params = (user_id,)

            artists = self.db.execute_query(query, params, fetch=True)

            if not artists:
                return {
                    "success": True,
                    "message": "No active artists to check",
                    "new_videos": [],
                }

            new_videos = []
            checked_count = 0

            for artist in artists:
                try:
                    # Search for videos
                    search_result = self.youtube_service.search_artist_videos(
                        artist["artist_name"], 25
                    )

                    if search_result["success"]:
                        for video in search_result["results"]:
                            video_id = video["id"]["videoId"]

                            # Check if we already have this video
                            check_query = """
                                SELECT id FROM downloaded_videos 
                                WHERE user_id = %s AND youtube_video_id = %s
                            """
                            existing = self.db.execute_query(
                                check_query, (user_id, video_id), fetch=True
                            )

                            if not existing:
                                new_videos.append(
                                    {
                                        "video_id": video_id,
                                        "title": video["snippet"]["title"],
                                        "artist_name": artist["artist_name"],
                                        "artist_id": artist["id"],
                                        "auto_download": artist["auto_download"],
                                        "channel": video["snippet"]["channelTitle"],
                                        "published_at": video["snippet"]["publishedAt"],
                                        "thumbnail_url": video["snippet"]["thumbnails"][
                                            "medium"
                                        ]["url"],
                                    }
                                )

                        # Update last_checked
                        update_query = """
                            UPDATE tracked_artists 
                            SET last_checked = CURRENT_TIMESTAMP, videos_found = %s
                            WHERE id = %s
                        """
                        self.db.execute_query(
                            update_query, (len(search_result["results"]), artist["id"])
                        )

                        checked_count += 1

                except Exception as e:
                    logger.warning(
                        f"Error checking artist {artist['artist_name']}: {e}"
                    )
                    continue

            logger.info(
                f"Checked {checked_count} artists for user {user_id}, found {len(new_videos)} new videos"
            )

            return {
                "success": True,
                "message": f"Checked {checked_count} artists, found {len(new_videos)} new videos",
                "new_videos": new_videos,
                "checked_artists": checked_count,
            }

        except Exception as e:
            logger.error(f"Error checking for new videos: {e}")
            return {
                "success": False,
                "error": f"Failed to check for new videos: {str(e)}",
                "new_videos": [],
            }
