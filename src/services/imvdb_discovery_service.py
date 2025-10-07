"""
IMVDB Automated Discovery Service for Issue #82
Implements automated video discovery based on artist preferences and patterns.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Setting, User, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.settings_service import settings
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

logger = get_logger("mvidarr.imvdb_discovery")


class IMVDbDiscoveryService:
    """Service for automated video discovery using IMVDB"""

    def __init__(self):
        self.logger = logger
        self.discovery_enabled = True
        self.max_discoveries_per_run = 100
        self.discovery_cooldown_hours = (
            6  # Minimum time between discovery runs for same artist
        )

    @monitor_performance("imvdb_discovery.discover_new_videos")
    def discover_new_videos(
        self, artist_ids: List[int] = None, force: bool = False
    ) -> Dict[str, any]:
        """
        Discover new videos for monitored artists

        Args:
            artist_ids: Specific artist IDs to check (if None, checks all monitored artists)
            force: Force discovery even if recently checked

        Returns:
            Discovery results summary
        """
        if not self._is_discovery_enabled():
            return {"success": False, "message": "Discovery is disabled"}

        with get_db() as session:
            # Get artists to check
            if artist_ids:
                artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
            else:
                artists = self._get_artists_for_discovery(session, force)

            results = {
                "success": True,
                "artists_checked": 0,
                "videos_discovered": 0,
                "new_videos": [],
                "errors": [],
                "discovery_run_at": datetime.utcnow().isoformat(),
            }

            for artist in artists:
                try:
                    artist_result = self._discover_videos_for_artist(artist, session)
                    results["artists_checked"] += 1
                    results["videos_discovered"] += artist_result["videos_found"]
                    results["new_videos"].extend(artist_result["videos"])

                    # Update last discovery timestamp
                    artist.last_discovery = datetime.utcnow()

                except Exception as e:
                    error_msg = f"Discovery failed for artist {artist.name}: {str(e)}"
                    self.logger.error(error_msg)
                    results["errors"].append(error_msg)

                # Respect rate limiting
                if len(results["new_videos"]) >= self.max_discoveries_per_run:
                    break

            session.commit()

            self.logger.info(
                f"Discovery run completed: {results['artists_checked']} artists checked, "
                f"{results['videos_discovered']} new videos discovered"
            )

            return results

    def _get_artists_for_discovery(self, session: Session, force: bool) -> List[Artist]:
        """Get artists that need discovery checking"""
        query = session.query(Artist).filter(
            Artist.monitored == True,
            Artist.imvdb_id.isnot(None),  # Only artists with IMVDB ID
        )

        if not force:
            # Only check artists that haven't been checked recently
            cutoff_time = datetime.utcnow() - timedelta(
                hours=self.discovery_cooldown_hours
            )
            query = query.filter(
                (Artist.last_discovery.is_(None))
                | (Artist.last_discovery < cutoff_time)
            )

        # Prioritize artists with auto_download enabled
        artists = (
            query.order_by(
                desc(Artist.auto_download), Artist.last_discovery.asc().nullsfirst()
            )
            .limit(50)
            .all()
        )  # Limit to prevent overwhelming the system

        return artists

    def _discover_videos_for_artist(
        self, artist: Artist, session: Session
    ) -> Dict[str, any]:
        """Discover new videos for a specific artist"""
        result = {
            "artist_id": artist.id,
            "artist_name": artist.name,
            "videos_found": 0,
            "videos": [],
        }

        # Get existing video IMVDB IDs to avoid duplicates
        existing_imvdb_ids = set()
        existing_videos = (
            session.query(Video.imvdb_id)
            .filter(Video.artist_id == artist.id, Video.imvdb_id.isnot(None))
            .all()
        )

        for video in existing_videos:
            if video.imvdb_id:
                existing_imvdb_ids.add(str(video.imvdb_id))

        # Search for artist's videos on IMVDB
        try:
            imvdb_result = imvdb_service.search_artist_videos(
                artist.name, limit=50  # Get more videos to find new ones
            )

            if not imvdb_result or not imvdb_result.get("videos"):
                self.logger.debug(f"No IMVDB videos found for artist {artist.name}")
                return result

            # Rank videos by quality before processing
            ranked_videos = imvdb_service.rank_videos_by_preferences(
                imvdb_result["videos"],
                user_id=None,  # Could be enhanced to use current user
            )

            # Process discovered videos (prioritizing high-quality ones)
            for video_data in ranked_videos:
                imvdb_id = str(video_data.get("id", ""))

                if not imvdb_id or imvdb_id in existing_imvdb_ids:
                    continue  # Skip if no ID or already exists

                # Only create videos that meet minimum quality threshold
                quality_analysis = video_data.get("quality_analysis", {})
                if (
                    quality_analysis.get("overall_score", 0) < 30
                ):  # Minimum quality threshold
                    self.logger.debug(
                        f"Skipping low-quality video: {video_data.get('song_title', 'Unknown')}"
                    )
                    continue

                # Create new video entry
                try:
                    new_video = self._create_video_from_imvdb(
                        video_data, artist, session
                    )
                    if new_video:
                        result["videos"].append(
                            {
                                "id": new_video.id,
                                "title": new_video.title,
                                "imvdb_id": new_video.imvdb_id,
                                "artist_name": artist.name,
                                "year": new_video.year,
                                "status": new_video.status.value,
                                "quality_analysis": quality_analysis,
                                "preference_score": video_data.get(
                                    "preference_score", 0
                                ),
                            }
                        )
                        result["videos_found"] += 1

                        self.logger.info(
                            f"Discovered high-quality video for {artist.name}: {new_video.title} "
                            f"(quality score: {quality_analysis.get('overall_score', 0):.1f})"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to create video from IMVDB data for {artist.name}: {e}"
                    )
                    continue

        except Exception as e:
            self.logger.error(f"IMVDB search failed for artist {artist.name}: {e}")
            raise

        return result

    def _create_video_from_imvdb(
        self, video_data: Dict, artist: Artist, session: Session
    ) -> Optional[Video]:
        """Create a new Video entry from IMVDB data"""
        try:
            # Extract metadata using the service's existing method
            metadata = imvdb_service.extract_metadata(video_data)

            # Create new video
            video = Video(
                artist_id=artist.id,
                title=metadata.get("title", "Unknown Title"),
                imvdb_id=metadata.get("imvdb_id"),
                year=metadata.get("year"),
                description=None,  # IMVDB doesn't provide descriptions
                thumbnail_url=metadata.get("thumbnail_url"),
                thumbnail_source="imvdb",
                status=(
                    VideoStatus.WANTED
                    if artist.auto_download
                    else VideoStatus.MONITORED
                ),
                imvdb_metadata=metadata.get("raw_metadata"),
                video_metadata={
                    "genre": metadata.get("genre"),
                    "directors": metadata.get("directors"),
                    "producers": metadata.get("producers"),
                    "label": metadata.get("label"),
                    "album": metadata.get("album"),
                },
                source="imvdb_discovery",
                discovered_date=datetime.utcnow(),
            )

            session.add(video)
            session.flush()  # Get the ID

            return video

        except Exception as e:
            self.logger.error(f"Failed to create video from IMVDB data: {e}")
            return None

    def discover_trending_videos(
        self, limit: int = 20, user_id: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Discover trending videos and suggest new artists to monitor

        Args:
            limit: Maximum number of trending videos to discover
            user_id: Optional user ID for personalized quality filtering

        Returns:
            Trending discovery results with quality analysis
        """
        try:
            trending_videos = imvdb_service.get_trending_videos(
                limit=limit * 3
            )  # Get more for quality filtering

            # Apply quality ranking and filtering
            ranked_videos = imvdb_service.rank_videos_by_preferences(
                trending_videos, user_id
            )

            results = {
                "success": True,
                "trending_videos": [],
                "suggested_artists": [],
                "quality_statistics": {},
                "discovery_run_at": datetime.utcnow().isoformat(),
            }

            with get_db() as session:
                # Get existing artist names to identify new ones
                existing_artist_names = set()
                existing_artists = session.query(Artist.name).all()
                for artist in existing_artists:
                    existing_artist_names.add(artist.name.lower())

                suggested_artists = set()
                high_quality_videos = []

                for video in ranked_videos:
                    # Extract artist info
                    artist_name = ""
                    if "artist" in video and isinstance(video["artist"], dict):
                        artist_name = video["artist"].get("name", "")

                    if not artist_name:
                        continue

                    # Only include videos that meet quality threshold
                    if video.get("meets_quality_threshold", False):
                        high_quality_videos.append(video)

                        # Add to trending videos list with quality info
                        results["trending_videos"].append(
                            {
                                "imvdb_id": video.get("id"),
                                "title": video.get("song_title", ""),
                                "artist_name": artist_name,
                                "year": video.get("year"),
                                "genre": video.get("genre"),
                                "directors": video.get("directors", []),
                                "thumbnail_url": self._extract_thumbnail_url(video),
                                "quality_analysis": video.get("quality_analysis", {}),
                                "preference_score": video.get("preference_score", 0),
                            }
                        )

                        # Check if artist is new
                        if artist_name.lower() not in existing_artist_names:
                            suggested_artists.add(artist_name)

                # Limit results
                results["trending_videos"] = results["trending_videos"][:limit]
                results["suggested_artists"] = list(suggested_artists)[:10]

                # Generate quality statistics
                results["quality_statistics"] = imvdb_service.get_quality_statistics(
                    high_quality_videos
                )

                self.logger.info(
                    f"Quality-filtered trending discovery found {len(results['trending_videos'])} videos "
                    f"and {len(results['suggested_artists'])} artist suggestions "
                    f"(from {len(trending_videos)} total videos)"
                )

                return results

        except Exception as e:
            self.logger.error(f"Trending discovery failed: {e}")
            return {
                "success": False,
                "message": f"Trending discovery failed: {str(e)}",
                "trending_videos": [],
                "suggested_artists": [],
                "quality_statistics": {},
            }

    def discover_similar_artists(
        self, artist_id: int, limit: int = 10
    ) -> Dict[str, any]:
        """
        Discover artists similar to a given artist based on genre and metadata

        Args:
            artist_id: ID of the reference artist
            limit: Maximum number of similar artists to find

        Returns:
            Similar artists discovery results
        """
        with get_db() as session:
            artist = session.query(Artist).filter(Artist.id == artist_id).first()
            if not artist:
                return {
                    "success": False,
                    "message": f"Artist with ID {artist_id} not found",
                }

            try:
                # Get artist's videos to analyze genres and metadata
                artist_videos = (
                    session.query(Video)
                    .filter(
                        Video.artist_id == artist_id, Video.video_metadata.isnot(None)
                    )
                    .all()
                )

                # Extract common genres from artist's videos
                genres = set()
                for video in artist_videos:
                    if video.video_metadata and video.video_metadata.get("genre"):
                        genre = video.video_metadata["genre"].lower()
                        genres.add(genre)

                if not genres:
                    # Fallback to searching by artist name for style
                    search_results = imvdb_service.search_artists(artist.name, limit=20)
                else:
                    # Search for artists in similar genres
                    search_results = []
                    for genre in list(genres)[:3]:  # Limit to top 3 genres
                        genre_videos = imvdb_service.search_videos_by_genre(
                            genre, limit=30
                        )
                        for video in genre_videos:
                            if "artist" in video and isinstance(video["artist"], dict):
                                artist_data = video["artist"]
                                if artist_data not in search_results:
                                    search_results.append(artist_data)

                # Filter out existing artists
                existing_names = set()
                existing_artists = session.query(Artist.name).all()
                for existing in existing_artists:
                    existing_names.add(existing.name.lower())

                similar_artists = []
                for artist_data in search_results[: limit * 2]:  # Get extra to filter
                    artist_name = artist_data.get("name", "")
                    if (
                        artist_name
                        and artist_name.lower() not in existing_names
                        and artist_name.lower() != artist.name.lower()
                    ):

                        similar_artists.append(
                            {
                                "imvdb_id": artist_data.get("id"),
                                "name": artist_name,
                                "slug": artist_data.get("slug", ""),
                                "similarity_score": self._calculate_similarity_score(
                                    artist_data, genres
                                ),
                            }
                        )

                # Sort by similarity score
                similar_artists.sort(key=lambda a: a["similarity_score"], reverse=True)

                results = {
                    "success": True,
                    "reference_artist": {
                        "id": artist.id,
                        "name": artist.name,
                        "genres": list(genres),
                    },
                    "similar_artists": similar_artists[:limit],
                    "discovery_run_at": datetime.utcnow().isoformat(),
                }

                self.logger.info(
                    f"Found {len(similar_artists)} similar artists to {artist.name}"
                )

                return results

            except Exception as e:
                self.logger.error(
                    f"Similar artist discovery failed for {artist.name}: {e}"
                )
                return {
                    "success": False,
                    "message": f"Similar artist discovery failed: {str(e)}",
                }

    def get_discovery_statistics(self) -> Dict[str, any]:
        """Get statistics about discovery performance"""
        with get_db() as session:
            stats = {
                "total_monitored_artists": session.query(Artist)
                .filter(Artist.monitored == True)
                .count(),
                "artists_with_imvdb_id": session.query(Artist)
                .filter(Artist.monitored == True, Artist.imvdb_id.isnot(None))
                .count(),
                "recently_discovered_videos": session.query(Video)
                .filter(
                    Video.source == "imvdb_discovery",
                    Video.discovered_date >= datetime.utcnow() - timedelta(days=7),
                )
                .count(),
                "auto_download_artists": session.query(Artist)
                .filter(Artist.monitored == True, Artist.auto_download == True)
                .count(),
                "last_discovery_runs": [],
            }

            # Get recent discovery activity
            recent_artists = (
                session.query(Artist)
                .filter(
                    Artist.last_discovery.isnot(None),
                    Artist.last_discovery >= datetime.utcnow() - timedelta(days=7),
                )
                .order_by(desc(Artist.last_discovery))
                .limit(10)
                .all()
            )

            for artist in recent_artists:
                stats["last_discovery_runs"].append(
                    {
                        "artist_name": artist.name,
                        "last_discovery": artist.last_discovery.isoformat(),
                        "auto_download": artist.auto_download,
                    }
                )

            return stats

    def get_quality_discovery_patterns(self) -> Dict[str, any]:
        """
        Analyze quality patterns in discovered videos

        Returns:
            Analysis of quality patterns in discovery history
        """
        with get_db() as session:
            # Get recently discovered videos
            discovered_videos = (
                session.query(Video)
                .filter(
                    Video.source == "imvdb_discovery",
                    Video.discovered_date >= datetime.utcnow() - timedelta(days=30),
                )
                .all()
            )

            patterns = {
                "total_discovered": len(discovered_videos),
                "quality_distribution": {
                    "high_quality": 0,  # Score >= 70
                    "medium_quality": 0,  # Score 40-70
                    "low_quality": 0,  # Score < 40
                },
                "source_patterns": {
                    "with_metadata": 0,
                    "with_directors": 0,
                    "with_thumbnails": 0,
                    "recent_releases": 0,  # Last 5 years
                },
                "artist_patterns": {},
                "genre_patterns": {},
                "year_patterns": {},
            }

            if not discovered_videos:
                return patterns

            for video in discovered_videos:
                # Simulate quality analysis for stored videos
                if video.imvdb_metadata:
                    try:
                        quality_analysis = imvdb_service.analyze_video_quality(
                            video.imvdb_metadata
                        )
                        score = quality_analysis.get("overall_score", 0)

                        if score >= 70:
                            patterns["quality_distribution"]["high_quality"] += 1
                        elif score >= 40:
                            patterns["quality_distribution"]["medium_quality"] += 1
                        else:
                            patterns["quality_distribution"]["low_quality"] += 1
                    except Exception:
                        patterns["quality_distribution"]["low_quality"] += 1

                # Source pattern analysis
                if video.video_metadata:
                    metadata = video.video_metadata
                    if metadata.get("directors"):
                        patterns["source_patterns"]["with_directors"] += 1
                    if metadata.get("genre"):
                        genre = metadata["genre"]
                        patterns["genre_patterns"][genre] = (
                            patterns["genre_patterns"].get(genre, 0) + 1
                        )

                if video.thumbnail_url:
                    patterns["source_patterns"]["with_thumbnails"] += 1

                if video.year and video.year >= 2019:  # Recent releases
                    patterns["source_patterns"]["recent_releases"] += 1

                    # Year patterns
                    year_key = str(video.year)
                    patterns["year_patterns"][year_key] = (
                        patterns["year_patterns"].get(year_key, 0) + 1
                    )

                # Artist patterns (get artist name)
                artist = (
                    session.query(Artist).filter(Artist.id == video.artist_id).first()
                )
                if artist:
                    patterns["artist_patterns"][artist.name] = (
                        patterns["artist_patterns"].get(artist.name, 0) + 1
                    )

            # Sort patterns by frequency
            patterns["genre_patterns"] = dict(
                sorted(
                    patterns["genre_patterns"].items(), key=lambda x: x[1], reverse=True
                )
            )
            patterns["artist_patterns"] = dict(
                sorted(
                    patterns["artist_patterns"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            )
            patterns["year_patterns"] = dict(sorted(patterns["year_patterns"].items()))

            return patterns

    def _extract_thumbnail_url(self, video_data: Dict) -> Optional[str]:
        """Extract thumbnail URL from IMVDB video data"""
        if "image" in video_data and isinstance(video_data["image"], dict):
            image_data = video_data["image"]
            for size in ["o", "l", "b", "s", "t"]:
                if size in image_data and image_data[size]:
                    return image_data[size]
        return video_data.get("image_url")

    def _calculate_similarity_score(
        self, artist_data: Dict, reference_genres: Set[str]
    ) -> float:
        """Calculate similarity score between artists based on available data"""
        score = 1.0  # Base score

        # This is a simplified similarity calculation
        # In a real implementation, you might use more sophisticated algorithms

        # For now, just give a base score since IMVDB artist search
        # already returns relevant results
        artist_name = artist_data.get("name", "").lower()

        # Boost score for artists with complete profiles
        if artist_data.get("id"):
            score += 0.5
        if artist_data.get("slug"):
            score += 0.3

        return score

    def _is_discovery_enabled(self) -> bool:
        """Check if automated discovery is enabled"""
        return settings.get("imvdb_discovery_enabled", True)


# Global service instance
imvdb_discovery_service = IMVDbDiscoveryService()
