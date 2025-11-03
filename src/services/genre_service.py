"""
Genre management service for MVidarr
"""

from collections import Counter
from typing import Dict, List

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.genre")


class GenreService:
    """Service for managing video and artist genres"""

    def __init__(self):
        pass

    def get_video_genres(self, video_id: int) -> List[str]:
        """Get genres for a specific video"""
        try:
            with get_db() as db:
                video = db.query(Video).filter(Video.id == video_id).first()
                if video and video.genres:
                    return video.genres if isinstance(video.genres, list) else []
                return []
        except Exception as e:
            logger.error(f"Error getting video genres for video {video_id}: {e}")
            return []

    def set_video_genres(self, video_id: int, genres: List[str]) -> bool:
        """Set genres for a specific video"""
        try:
            with get_db() as db:
                video = db.query(Video).filter(Video.id == video_id).first()
                if video:
                    # Clean and normalize genres
                    cleaned_genres = self._clean_genres(genres)
                    video.genres = cleaned_genres
                    db.commit()

                    # Update artist genres based on video genres
                    self._update_artist_genres(video.artist_id)

                    logger.info(
                        f"Updated genres for video {video_id}: {cleaned_genres}"
                    )
                    return True
                return False
        except Exception as e:
            logger.error(f"Error setting video genres for video {video_id}: {e}")
            return False

    def get_artist_genres(self, artist_id: int) -> List[str]:
        """Get genres for a specific artist"""
        try:
            with get_db() as db:
                artist = db.query(Artist).filter(Artist.id == artist_id).first()
                if artist and artist.genres:
                    return artist.genres if isinstance(artist.genres, list) else []
                return []
        except Exception as e:
            logger.error(f"Error getting artist genres for artist {artist_id}: {e}")
            return []

    def _update_artist_genres(self, artist_id: int) -> bool:
        """Update artist genres based on their videos' genres"""
        try:
            with get_db() as db:
                return self._update_artist_genres_with_session(artist_id, db)
        except Exception as e:
            logger.error(f"Error updating artist genres for artist {artist_id}: {e}")
            return False

    def _update_artist_genres_with_session(self, artist_id: int, db) -> bool:
        """Update artist genres based on their videos' genres using existing session"""
        try:
            # Get all videos for this artist
            videos = db.query(Video).filter(Video.artist_id == artist_id).all()

            # Collect all genres from videos
            all_genres = []
            for video in videos:
                if video.genres:
                    video_genres = (
                        video.genres if isinstance(video.genres, list) else []
                    )
                    all_genres.extend(video_genres)

            # Count genre occurrences and get the most common ones
            if all_genres:
                genre_counts = Counter(all_genres)
                # Get genres that appear in at least 10% of videos or minimum 1 video
                min_count = max(1, len(videos) * 0.1)
                artist_genres = [
                    genre for genre, count in genre_counts.items() if count >= min_count
                ]

                # Sort by frequency
                artist_genres.sort(key=lambda x: genre_counts[x], reverse=True)
            else:
                artist_genres = []

            # Update artist
            artist = db.query(Artist).filter(Artist.id == artist_id).first()
            if artist:
                artist.genres = artist_genres
                logger.info(f"Updated artist {artist_id} genres to: {artist_genres}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error updating artist genres for artist {artist_id}: {e}")
            return False

    def update_all_artist_genres(self) -> Dict[str, int]:
        """Update all artist genres based on their videos"""
        try:
            with get_db() as db:
                artists = db.query(Artist).all()
                updated_count = 0

                for artist in artists:
                    if self._update_artist_genres(artist.id):
                        updated_count += 1

                logger.info(f"Updated genres for {updated_count} artists")
                return {"total_artists": len(artists), "updated_artists": updated_count}
        except Exception as e:
            logger.error(f"Error updating all artist genres: {e}")
            return {"total_artists": 0, "updated_artists": 0}

    def _clean_genres(self, genres: List[str]) -> List[str]:
        """Clean and normalize genre names"""
        if not genres:
            return []

        cleaned = []
        for genre in genres:
            if isinstance(genre, str):
                # Clean up the genre name
                clean_genre = genre.strip().title()
                if clean_genre and clean_genre not in cleaned:
                    cleaned.append(clean_genre)

        return cleaned

    def get_all_genres(self) -> Dict[str, List[str]]:
        """Get all unique genres from videos and artists"""
        try:
            with get_db() as db:
                # Get all video genres
                video_genres = set()
                videos = db.query(Video).filter(Video.genres.isnot(None)).all()
                for video in videos:
                    if video.genres:
                        genres = video.genres if isinstance(video.genres, list) else []
                        video_genres.update(genres)

                # Get all artist genres
                artist_genres = set()
                artists = db.query(Artist).filter(Artist.genres.isnot(None)).all()
                for artist in artists:
                    if artist.genres:
                        genres = (
                            artist.genres if isinstance(artist.genres, list) else []
                        )
                        artist_genres.update(genres)

                return {
                    "video_genres": sorted(list(video_genres)),
                    "artist_genres": sorted(list(artist_genres)),
                    "all_genres": sorted(list(video_genres.union(artist_genres))),
                }
        except Exception as e:
            logger.error(f"Error getting all genres: {e}")
            return {"video_genres": [], "artist_genres": [], "all_genres": []}

    def get_videos_by_genre(self, genre: str, limit: int = 50) -> List[Dict]:
        """Get videos that match a specific genre"""
        try:
            with get_db() as db:
                videos = (
                    db.query(Video)
                    .join(Artist)
                    .filter(Video.genres.contains(f'"{genre}"'))
                    .limit(limit)
                    .all()
                )

                result = []
                for video in videos:
                    result.append(
                        {
                            "id": video.id,
                            "title": video.title,
                            "artist_name": video.artist.name,
                            "artist_id": video.artist_id,
                            "genres": video.genres,
                            "year": video.year,
                            "duration": video.duration,
                            "status": video.status.value if video.status else None,
                        }
                    )

                return result
        except Exception as e:
            logger.error(f"Error getting videos by genre {genre}: {e}")
            return []

    def get_artists_by_genre(self, genre: str, limit: int = 50) -> List[Dict]:
        """Get artists that match a specific genre"""
        try:
            with get_db() as db:
                artists = (
                    db.query(Artist)
                    .filter(Artist.genres.contains(f'"{genre}"'))
                    .limit(limit)
                    .all()
                )

                result = []
                for artist in artists:
                    result.append(
                        {
                            "id": artist.id,
                            "name": artist.name,
                            "genres": artist.genres,
                            "monitored": artist.monitored,
                            "video_count": len(artist.videos) if artist.videos else 0,
                        }
                    )

                return result
        except Exception as e:
            logger.error(f"Error getting artists by genre {genre}: {e}")
            return []

    def suggest_genres_for_video(self, video_id: int) -> List[str]:
        """Suggest genres for a video based on artist and similar videos"""
        try:
            with get_db() as db:
                video = db.query(Video).filter(Video.id == video_id).first()
                if not video:
                    return []

                suggested_genres = set()

                # Get genres from the artist
                if video.artist and video.artist.genres:
                    suggested_genres.update(video.artist.genres)

                # Get genres from other videos by the same artist
                other_videos = (
                    db.query(Video)
                    .filter(
                        Video.artist_id == video.artist_id,
                        Video.id != video_id,
                        Video.genres.isnot(None),
                    )
                    .all()
                )

                for other_video in other_videos:
                    if other_video.genres:
                        suggested_genres.update(other_video.genres)

                return sorted(list(suggested_genres))
        except Exception as e:
            logger.error(f"Error suggesting genres for video {video_id}: {e}")
            return []


# Global instance
genre_service = GenreService()


async def get_genre_service() -> GenreService:
    """
    Get the genre service instance

    Returns:
        GenreService: Configured service instance
    """
    return genre_service
