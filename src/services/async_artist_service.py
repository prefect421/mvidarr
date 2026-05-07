"""
Async Artist Management Service for FastAPI Migration
Handles tracked artists and their automatic video discovery with async operations
"""

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from src.services.async_base_service import AsyncBaseService, AsyncServiceError


def _validate_sql_identifier(identifier: str) -> bool:
    """
    Validate that a string is a safe SQL identifier (column name).
    Only allows alphanumeric characters and underscores.
    """
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier))


class AsyncArtistService(AsyncBaseService):
    """Async service for managing tracked artists"""

    def __init__(self, youtube_service=None):
        super().__init__("mvidarr.async_artist_service")
        self.youtube_service = youtube_service

    async def add_tracked_artist(
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
            existing = await self._check_existing_artist(user_id, artist_name)
            if existing:
                return {
                    "success": False,
                    "error": f'Artist "{artist_name}" is already being tracked',
                }

            # Test search to validate artist exists (if youtube_service available)
            videos_found = 0
            if self.youtube_service:
                search_result = await self.youtube_service.search_artist_videos(
                    artist_name, 5
                )
                if not search_result["success"]:
                    return {
                        "success": False,
                        "error": f'Could not find videos for "{artist_name}": {search_result["error"]}',
                    }
                videos_found = len(search_result["results"])

            # Create new tracked artist
            artist_data = await self._create_tracked_artist(
                user_id, artist_name, search_terms, auto_download, videos_found
            )

            if artist_data:
                self.logger.info(f"Artist '{artist_name}' added for user {user_id}")
                return {
                    "success": True,
                    "message": f'Successfully added "{artist_name}" to tracked artists',
                    "artist": artist_data,
                }
            else:
                return {"success": False, "error": "Failed to create tracked artist"}

        except Exception as e:
            self.logger.error(f"Error adding tracked artist '{artist_name}': {e}")
            return {"success": False, "error": f"Failed to add artist: {str(e)}"}

    async def _check_existing_artist(self, user_id: int, artist_name: str) -> bool:
        """Check if artist is already being tracked"""
        try:
            query = """
                SELECT id FROM tracked_artists 
                WHERE user_id = :user_id AND LOWER(artist_name) = LOWER(:artist_name)
            """
            result = await self.execute_query(
                query, {"user_id": user_id, "artist_name": artist_name}
            )
            return len(result) > 0
        except Exception as e:
            self.logger.error(f"Error checking existing artist: {e}")
            return False

    async def _create_tracked_artist(
        self,
        user_id: int,
        artist_name: str,
        search_terms: str,
        auto_download: bool,
        videos_found: int,
    ) -> Optional[Dict[str, Any]]:
        """Create a new tracked artist record"""
        try:
            async with self.get_session() as session:
                # Insert new tracked artist
                query = text("""
                    INSERT INTO tracked_artists 
                    (user_id, artist_name, search_terms, auto_download, videos_found) 
                    VALUES (:user_id, :artist_name, :search_terms, :auto_download, :videos_found)
                """)

                await session.execute(
                    query,
                    {
                        "user_id": user_id,
                        "artist_name": artist_name,
                        "search_terms": search_terms,
                        "auto_download": auto_download,
                        "videos_found": videos_found,
                    },
                )

                # Get the newly created artist
                select_query = text("""
                    SELECT * FROM tracked_artists 
                    WHERE user_id = :user_id AND artist_name = :artist_name
                    ORDER BY created_at DESC LIMIT 1
                """)

                result = await session.execute(
                    select_query, {"user_id": user_id, "artist_name": artist_name}
                )

                artist_row = result.fetchone()

                if artist_row:
                    # Convert row to dict
                    columns = result.keys()
                    artist_dict = dict(zip(columns, artist_row))

                    return {
                        "id": artist_dict["id"],
                        "name": artist_dict["artist_name"],
                        "auto_download": artist_dict["auto_download"],
                        "videos_found": artist_dict["videos_found"],
                        "created_at": (
                            artist_dict["created_at"].isoformat()
                            if artist_dict.get("created_at")
                            else None
                        ),
                        "is_active": artist_dict.get("is_active", True),
                    }
                return None

        except Exception as e:
            self.logger.error(f"Error creating tracked artist: {e}")
            raise AsyncServiceError(
                f"Failed to create tracked artist: {str(e)}",
                "AsyncArtistService",
                "create",
            )

    async def get_tracked_artists(
        self, user_id: int, page: int = 1, per_page: int = 20
    ) -> Dict[str, Any]:
        """Get paginated list of tracked artists for a user"""
        try:
            offset = (page - 1) * per_page

            # Get total count
            count_query = (
                "SELECT COUNT(*) as total FROM tracked_artists WHERE user_id = :user_id"
            )
            count_result = await self.execute_query(count_query, {"user_id": user_id})
            total_count = count_result[0]["total"] if count_result else 0

            # Get paginated artists
            query = """
                SELECT 
                    id, artist_name, search_terms, auto_download, videos_found, 
                    is_active, created_at, last_checked
                FROM tracked_artists 
                WHERE user_id = :user_id 
                ORDER BY created_at DESC 
                LIMIT :limit OFFSET :offset
            """

            artists_result = await self.execute_query(
                query, {"user_id": user_id, "limit": per_page, "offset": offset}
            )

            # Format artist data
            artists = []
            for artist in artists_result:
                artists.append(
                    {
                        "id": artist["id"],
                        "name": artist["artist_name"],
                        "search_terms": artist["search_terms"],
                        "auto_download": artist["auto_download"],
                        "videos_found": artist["videos_found"],
                        "is_active": artist["is_active"],
                        "created_at": (
                            artist["created_at"].isoformat()
                            if artist["created_at"]
                            else None
                        ),
                        "last_checked": (
                            artist["last_checked"].isoformat()
                            if artist["last_checked"]
                            else None
                        ),
                    }
                )

            return {
                "success": True,
                "artists": artists,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "pages": (total_count + per_page - 1) // per_page,
                "has_next": page * per_page < total_count,
                "has_prev": page > 1,
            }

        except Exception as e:
            self.logger.error(f"Error getting tracked artists for user {user_id}: {e}")
            return {"success": False, "error": f"Failed to get artists: {str(e)}"}

    async def update_tracked_artist(
        self, user_id: int, artist_id: int, **updates
    ) -> Dict[str, Any]:
        """Update a tracked artist"""
        try:
            # Verify artist belongs to user
            artist = await self._get_tracked_artist_by_id(user_id, artist_id)
            if not artist:
                return {"success": False, "error": "Artist not found"}

            # Build update query
            set_clauses = []
            params = {"artist_id": artist_id, "user_id": user_id}

            allowed_fields = [
                "artist_name",
                "search_terms",
                "auto_download",
                "is_active",
            ]

            for field, value in updates.items():
                if field in allowed_fields and _validate_sql_identifier(field):
                    set_clauses.append(f"{field} = :{field}")
                    params[field] = value

            if not set_clauses:
                return {"success": False, "error": "No valid fields to update"}

            # Add updated timestamp
            set_clauses.append("updated_at = NOW()")

            query = f"""
                UPDATE tracked_artists 
                SET {', '.join(set_clauses)}
                WHERE id = :artist_id AND user_id = :user_id
            """

            async with self.get_session() as session:
                result = await session.execute(text(query), params)

                if result.rowcount > 0:
                    # Get updated artist
                    updated_artist = await self._get_tracked_artist_by_id(
                        user_id, artist_id
                    )

                    self.logger.info(
                        f"Updated tracked artist {artist_id} for user {user_id}"
                    )
                    return {
                        "success": True,
                        "message": "Artist updated successfully",
                        "artist": updated_artist,
                    }
                else:
                    return {"success": False, "error": "No changes made"}

        except Exception as e:
            self.logger.error(f"Error updating tracked artist {artist_id}: {e}")
            return {"success": False, "error": f"Failed to update artist: {str(e)}"}

    async def delete_tracked_artist(
        self, user_id: int, artist_id: int
    ) -> Dict[str, Any]:
        """Delete a tracked artist"""
        try:
            # Verify artist exists and belongs to user
            artist = await self._get_tracked_artist_by_id(user_id, artist_id)
            if not artist:
                return {"success": False, "error": "Artist not found"}

            query = "DELETE FROM tracked_artists WHERE id = :artist_id AND user_id = :user_id"

            async with self.get_session() as session:
                result = await session.execute(
                    text(query), {"artist_id": artist_id, "user_id": user_id}
                )

                if result.rowcount > 0:
                    self.logger.info(
                        f"Deleted tracked artist {artist_id} ({artist['name']}) for user {user_id}"
                    )
                    return {
                        "success": True,
                        "message": f"Successfully removed '{artist['name']}' from tracked artists",
                    }
                else:
                    return {"success": False, "error": "Failed to delete artist"}

        except Exception as e:
            self.logger.error(f"Error deleting tracked artist {artist_id}: {e}")
            return {"success": False, "error": f"Failed to delete artist: {str(e)}"}

    async def _get_tracked_artist_by_id(
        self, user_id: int, artist_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a tracked artist by ID for a specific user"""
        try:
            query = """
                SELECT 
                    id, artist_name, search_terms, auto_download, videos_found, 
                    is_active, created_at, last_checked, updated_at
                FROM tracked_artists 
                WHERE id = :artist_id AND user_id = :user_id
            """

            result = await self.execute_query(
                query, {"artist_id": artist_id, "user_id": user_id}
            )

            if result:
                artist = result[0]
                return {
                    "id": artist["id"],
                    "name": artist["artist_name"],
                    "search_terms": artist["search_terms"],
                    "auto_download": artist["auto_download"],
                    "videos_found": artist["videos_found"],
                    "is_active": artist["is_active"],
                    "created_at": (
                        artist["created_at"].isoformat()
                        if artist["created_at"]
                        else None
                    ),
                    "last_checked": (
                        artist["last_checked"].isoformat()
                        if artist["last_checked"]
                        else None
                    ),
                    "updated_at": (
                        artist["updated_at"].isoformat()
                        if artist.get("updated_at")
                        else None
                    ),
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting tracked artist {artist_id}: {e}")
            return None

    async def search_for_new_videos(
        self, user_id: int, artist_id: int = None
    ) -> Dict[str, Any]:
        """Search for new videos for tracked artists"""
        try:
            if not self.youtube_service:
                return {"success": False, "error": "YouTube service not available"}

            # Get artists to search for
            if artist_id:
                artists_query = """
                    SELECT id, artist_name, search_terms 
                    FROM tracked_artists 
                    WHERE id = :artist_id AND user_id = :user_id AND is_active = 1
                """
                artists_result = await self.execute_query(
                    artists_query, {"artist_id": artist_id, "user_id": user_id}
                )
            else:
                artists_query = """
                    SELECT id, artist_name, search_terms 
                    FROM tracked_artists 
                    WHERE user_id = :user_id AND is_active = 1
                """
                artists_result = await self.execute_query(
                    artists_query, {"user_id": user_id}
                )

            if not artists_result:
                return {"success": False, "error": "No active tracked artists found"}

            total_new_videos = 0
            results = []

            for artist in artists_result:
                try:
                    # Search for videos
                    search_terms = artist["search_terms"] or artist["artist_name"]
                    search_result = await self.youtube_service.search_artist_videos(
                        search_terms, 20
                    )

                    if search_result["success"]:
                        # Process and filter new videos
                        new_videos_count = await self._process_search_results(
                            user_id, artist["id"], search_result["results"]
                        )

                        total_new_videos += new_videos_count

                        results.append(
                            {
                                "artist_id": artist["id"],
                                "artist_name": artist["artist_name"],
                                "new_videos": new_videos_count,
                                "success": True,
                            }
                        )

                        # Update last checked timestamp
                        await self._update_last_checked(artist["id"])

                    else:
                        results.append(
                            {
                                "artist_id": artist["id"],
                                "artist_name": artist["artist_name"],
                                "error": search_result["error"],
                                "success": False,
                            }
                        )

                except Exception as e:
                    self.logger.error(
                        f"Error searching for artist {artist['artist_name']}: {e}"
                    )
                    results.append(
                        {
                            "artist_id": artist["id"],
                            "artist_name": artist["artist_name"],
                            "error": str(e),
                            "success": False,
                        }
                    )

            return {
                "success": True,
                "total_new_videos": total_new_videos,
                "artists_processed": len(results),
                "results": results,
            }

        except Exception as e:
            self.logger.error(f"Error in search_for_new_videos: {e}")
            return {
                "success": False,
                "error": f"Failed to search for new videos: {str(e)}",
            }

    async def _process_search_results(
        self, user_id: int, artist_id: int, search_results: List[Dict]
    ) -> int:
        """Process search results and add new videos to database"""
        try:
            new_videos_count = 0

            for video_data in search_results:
                # Check if video already exists
                existing_query = """
                    SELECT id FROM videos 
                    WHERE youtube_id = :youtube_id AND user_id = :user_id
                """
                existing = await self.execute_query(
                    existing_query,
                    {"youtube_id": video_data.get("id"), "user_id": user_id},
                )

                if not existing:
                    # Add new video (this would need to integrate with video service)
                    # For now, just count it
                    new_videos_count += 1

                    # Note: In full implementation, this would call video service
                    # to properly create video record with all metadata
                    self.logger.debug(
                        f"Found new video: {video_data.get('title', 'Unknown')}"
                    )

            return new_videos_count

        except Exception as e:
            self.logger.error(f"Error processing search results: {e}")
            return 0

    async def _update_last_checked(self, artist_id: int):
        """Update the last_checked timestamp for an artist"""
        try:
            query = (
                "UPDATE tracked_artists SET last_checked = NOW() WHERE id = :artist_id"
            )
            async with self.get_session() as session:
                await session.execute(text(query), {"artist_id": artist_id})
        except Exception as e:
            self.logger.error(
                f"Error updating last_checked for artist {artist_id}: {e}"
            )

    async def get_artist_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics about tracked artists"""
        try:
            stats_query = """
                SELECT 
                    COUNT(*) as total_artists,
                    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_artists,
                    SUM(CASE WHEN auto_download = 1 THEN 1 ELSE 0 END) as auto_download_artists,
                    SUM(videos_found) as total_videos_found
                FROM tracked_artists 
                WHERE user_id = :user_id
            """

            result = await self.execute_query(stats_query, {"user_id": user_id})

            if result:
                stats = result[0]
                return {
                    "success": True,
                    "stats": {
                        "total_artists": stats["total_artists"] or 0,
                        "active_artists": stats["active_artists"] or 0,
                        "auto_download_artists": stats["auto_download_artists"] or 0,
                        "total_videos_found": stats["total_videos_found"] or 0,
                        "inactive_artists": (stats["total_artists"] or 0)
                        - (stats["active_artists"] or 0),
                    },
                }
            else:
                return {
                    "success": True,
                    "stats": {
                        "total_artists": 0,
                        "active_artists": 0,
                        "auto_download_artists": 0,
                        "total_videos_found": 0,
                        "inactive_artists": 0,
                    },
                }

        except Exception as e:
            self.logger.error(f"Error getting artist stats for user {user_id}: {e}")
            return {"success": False, "error": f"Failed to get stats: {str(e)}"}


# Test function for the async artist service
async def test_async_artist_service():
    """Test the async artist service functionality"""
    try:
        from src.database.async_connection import initialize_async_database

        print("🔄 Initializing async database...")
        await initialize_async_database()

        print("🔄 Creating AsyncArtistService...")
        service = AsyncArtistService()

        print("🔄 Testing get_artist_stats...")
        stats = await service.get_artist_stats(user_id=1)
        print(f"Stats result: {stats}")

        if stats["success"]:
            print("✅ AsyncArtistService basic functionality working!")
            return True
        else:
            print("❌ AsyncArtistService stats test failed!")
            return False

    except Exception as e:
        print(f"❌ AsyncArtistService test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    """Run tests if executed directly"""
    import asyncio
    import os
    import sys

    # Add project root to path
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    async def main():
        print("🧪 Testing AsyncArtistService")
        print("=" * 40)

        success = await test_async_artist_service()

        print("=" * 40)
        if success:
            print("🎉 AsyncArtistService tests passed!")
        else:
            print("💥 AsyncArtistService tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
