"""
IMVDb quality analysis and filtering - Advanced search and video quality analysis
"""

from datetime import datetime
from typing import Dict, List, Optional

from src.services.imvdb.imvdb_search import IMVDbSearch
from src.utils.logger import get_logger

logger = get_logger("mvidarr.imvdb_quality")


class IMVDbQuality(IMVDbSearch):
    """Quality analysis and advanced filtering for videos"""

    def advanced_search_videos(self, filters: Dict) -> Dict:
        """
        Advanced video search with multiple filter criteria

        Args:
            filters: Dictionary containing search filters:
                - query: Text search query
                - year_min: Minimum year (int)
                - year_max: Maximum year (int)
                - genre: Genre filter (string)
                - directors: Director names (list or string)
                - artists: Artist names (list or string)
                - limit: Maximum results (default 50)
                - offset: Result offset for pagination (default 0)
                - sort_by: Sort criteria (year, title, artist, relevance)
                - sort_order: asc or desc

        Returns:
            Dictionary with filtered video results and metadata
        """
        # Build base query
        query = filters.get("query", "")

        # Make initial request with broader search
        params = {"q": query, "limit": 200}  # Get more results for filtering
        response = self._make_request("search/videos", params)

        if not response or "results" not in response:
            return {
                "videos": [],
                "total_results": 0,
                "filters_applied": filters,
                "search_method": "advanced_search_no_results",
            }

        videos = response["results"]
        filtered_videos = []

        # Apply filters
        for video in videos:
            if not self._video_matches_filters(video, filters):
                continue

            # Add relevance score
            video["relevance_score"] = self._calculate_video_relevance(video, filters)
            filtered_videos.append(video)

        # Sort results
        sort_by = filters.get("sort_by", "relevance")
        sort_order = filters.get("sort_order", "desc")
        filtered_videos = self._sort_videos(filtered_videos, sort_by, sort_order)

        # Apply pagination
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        paginated_videos = filtered_videos[offset : offset + limit]

        logger.info(
            f"Advanced search found {len(filtered_videos)} videos matching filters "
            f"(showing {len(paginated_videos)} after pagination)"
        )

        return {
            "videos": paginated_videos,
            "total_results": len(filtered_videos),
            "total_before_filters": len(videos),
            "filters_applied": filters,
            "search_method": "advanced_search",
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < len(filtered_videos),
            },
        }

    def _video_matches_filters(self, video: Dict, filters: Dict) -> bool:
        """Check if a video matches the given filter criteria"""

        # Year range filter
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        if year_min or year_max:
            video_year = video.get("year")
            if video_year:
                try:
                    video_year = int(video_year)
                    if year_min and video_year < int(year_min):
                        return False
                    if year_max and video_year > int(year_max):
                        return False
                except (ValueError, TypeError):
                    if (
                        year_min or year_max
                    ):  # If year filters specified but video has no valid year
                        return False

        # Genre filter
        genre_filter = filters.get("genre")
        if genre_filter:
            video_genre = str(video.get("genre", "")).lower()
            if genre_filter.lower() not in video_genre:
                return False

        # Directors filter
        directors_filter = filters.get("directors")
        if directors_filter:
            if isinstance(directors_filter, str):
                directors_filter = [directors_filter]

            video_directors = video.get("directors", [])
            video_director_names = []

            for director in video_directors:
                if isinstance(director, dict):
                    video_director_names.append(director.get("name", "").lower())
                else:
                    video_director_names.append(str(director).lower())

            # Check if any specified director is in the video
            found_director = False
            for director_filter in directors_filter:
                director_filter = director_filter.lower()
                for video_director in video_director_names:
                    if (
                        director_filter in video_director
                        or video_director in director_filter
                    ):
                        found_director = True
                        break
                if found_director:
                    break

            if not found_director:
                return False

        # Artists filter (additional artist filtering beyond the main search)
        artists_filter = filters.get("artists")
        if artists_filter:
            if isinstance(artists_filter, str):
                artists_filter = [artists_filter]

            # Get video artists
            video_artists = []
            if "artist" in video and isinstance(video["artist"], dict):
                video_artists.append(video["artist"].get("name", "").lower())
            elif "artists" in video and isinstance(video["artists"], list):
                for artist in video["artists"]:
                    if isinstance(artist, dict):
                        video_artists.append(artist.get("name", "").lower())
                    else:
                        video_artists.append(str(artist).lower())

            # Check if any specified artist matches
            found_artist = False
            for artist_filter in artists_filter:
                artist_filter = artist_filter.lower()
                for video_artist in video_artists:
                    if artist_filter in video_artist or video_artist in artist_filter:
                        found_artist = True
                        break
                if found_artist:
                    break

            if not found_artist:
                return False

        return True

    def _calculate_video_relevance(self, video: Dict, filters: Dict) -> float:
        """Calculate relevance score for a video based on search criteria"""
        score = 0.0
        query = filters.get("query", "").lower()

        if not query:
            return 1.0  # Default score when no query

        # Title relevance
        title = str(video.get("song_title", "")).lower()
        if query in title:
            score += 10.0
        if title == query:
            score += 5.0

        # Artist relevance
        artist_name = ""
        if "artist" in video and isinstance(video["artist"], dict):
            artist_name = video["artist"].get("name", "").lower()

        if query in artist_name:
            score += 8.0
        if artist_name == query:
            score += 4.0

        # Bonus for complete metadata
        if video.get("year"):
            score += 1.0
        if video.get("directors"):
            score += 0.5
        if video.get("image_url") or video.get("image"):
            score += 0.5

        return score

    def _sort_videos(
        self, videos: List[Dict], sort_by: str, sort_order: str
    ) -> List[Dict]:
        """Sort videos by specified criteria"""
        reverse = sort_order.lower() == "desc"

        if sort_by == "year":
            return sorted(videos, key=lambda v: v.get("year") or 0, reverse=reverse)
        elif sort_by == "title":
            return sorted(
                videos, key=lambda v: v.get("song_title", "").lower(), reverse=reverse
            )
        elif sort_by == "artist":

            def get_artist_name(v):
                if "artist" in v and isinstance(v["artist"], dict):
                    return v["artist"].get("name", "").lower()
                return ""

            return sorted(videos, key=get_artist_name, reverse=reverse)
        elif sort_by == "relevance":
            return sorted(
                videos, key=lambda v: v.get("relevance_score", 0), reverse=reverse
            )
        else:
            # Default to relevance
            return sorted(
                videos, key=lambda v: v.get("relevance_score", 0), reverse=reverse
            )

    def search_videos_by_genre(self, genre: str, limit: int = 50) -> List[Dict]:
        """
        Search for videos by genre

        Args:
            genre: Genre to search for
            limit: Maximum number of results

        Returns:
            List of videos matching the genre
        """
        filters = {"genre": genre, "limit": limit, "sort_by": "relevance"}

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def search_videos_by_year_range(
        self, year_min: int, year_max: int, limit: int = 50
    ) -> List[Dict]:
        """
        Search for videos within a year range

        Args:
            year_min: Minimum year (inclusive)
            year_max: Maximum year (inclusive)
            limit: Maximum number of results

        Returns:
            List of videos from the specified year range
        """
        filters = {
            "year_min": year_min,
            "year_max": year_max,
            "limit": limit,
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def search_videos_by_director(self, director: str, limit: int = 50) -> List[Dict]:
        """
        Search for videos by director

        Args:
            director: Director name to search for
            limit: Maximum number of results

        Returns:
            List of videos by the specified director
        """
        filters = {
            "directors": [director],
            "limit": limit,
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def get_trending_videos(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """
        Get trending/popular videos (simulated with recent high-quality videos)

        Args:
            days: Number of days to look back (currently used for reference)
            limit: Maximum number of results

        Returns:
            List of trending videos
        """
        # Since IMVDb doesn't have a specific trending endpoint,
        # we'll simulate this by getting recent videos with good metadata
        current_year = datetime.now().year
        # Look for videos from recent years with complete metadata

        filters = {
            "year_min": current_year - 2,  # Last 2 years
            "year_max": current_year,
            "limit": limit * 3,  # Get more to filter for quality
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        videos = result["videos"]

        # Filter for videos with good metadata (likely to be popular/well-maintained)
        quality_videos = []
        for video in videos:
            quality_score = 0

            # Videos with directors are often more notable
            if video.get("directors"):
                quality_score += 3

            # Videos with images are more likely to be popular
            if video.get("image_url") or video.get("image"):
                quality_score += 2

            # Videos with genre info
            if video.get("genre"):
                quality_score += 1

            # Videos with complete artist info
            if isinstance(video.get("artist"), dict) and video["artist"].get("name"):
                quality_score += 2

            if quality_score >= 4:  # Minimum quality threshold
                video["quality_score"] = quality_score
                quality_videos.append(video)

        # Sort by quality score and return top results
        quality_videos.sort(key=lambda v: v.get("quality_score", 0), reverse=True)

        logger.info(f"Found {len(quality_videos)} trending/quality videos")
        return quality_videos[:limit]

    def analyze_video_quality(self, video_data: Dict) -> Dict:
        """
        Analyze video quality and source preferences

        Args:
            video_data: IMVDb video metadata

        Returns:
            Dictionary with quality analysis
        """
        quality_analysis = {
            "overall_score": 0.0,
            "metadata_completeness": 0.0,
            "source_quality": 0.0,
            "production_quality": 0.0,
            "factors": [],
        }

        # Metadata completeness score (0-40 points)
        metadata_score = 0
        if video_data.get("song_title"):
            metadata_score += 10
            quality_analysis["factors"].append("Complete title information")

        if video_data.get("year"):
            metadata_score += 10
            quality_analysis["factors"].append("Release year available")

        if video_data.get("genre"):
            metadata_score += 5
            quality_analysis["factors"].append("Genre information")

        if video_data.get("directors"):
            metadata_score += 10
            quality_analysis["factors"].append("Director information")

        if video_data.get("image") or video_data.get("image_url"):
            metadata_score += 5
            quality_analysis["factors"].append("Thumbnail available")

        quality_analysis["metadata_completeness"] = min(metadata_score, 40)

        # Production quality score (0-30 points)
        production_score = 0
        directors = video_data.get("directors", [])
        if directors and len(directors) > 0:
            production_score += 15
            if len(directors) > 1:
                production_score += 5  # Multiple directors often indicate higher budget

        if video_data.get("producers"):
            production_score += 10
            quality_analysis["factors"].append("Producer information available")

        quality_analysis["production_quality"] = min(production_score, 30)

        # Source quality score (0-30 points)
        source_score = 0

        # Year-based quality (newer videos often have better quality)
        year = video_data.get("year")
        if year:
            try:
                year_int = int(year)
                if year_int >= 2020:
                    source_score += 15
                elif year_int >= 2015:
                    source_score += 12
                elif year_int >= 2010:
                    source_score += 8
                elif year_int >= 2005:
                    source_score += 5
                else:
                    source_score += 2
            except (ValueError, TypeError):
                pass

        # Artist popularity indicator (having an IMVDB artist page suggests more popular/quality content)
        if isinstance(video_data.get("artist"), dict) and video_data["artist"].get(
            "id"
        ):
            source_score += 10
            quality_analysis["factors"].append("Artist has dedicated IMVDB profile")

        # Genre-based quality weighting
        genre = video_data.get("genre", "").lower()
        if genre in ["pop", "rock", "hip-hop", "electronic", "r&b"]:
            source_score += 5  # Popular genres often have higher production values

        quality_analysis["source_quality"] = min(source_score, 30)

        # Calculate overall score
        quality_analysis["overall_score"] = (
            quality_analysis["metadata_completeness"]
            + quality_analysis["production_quality"]
            + quality_analysis["source_quality"]
        )

        return quality_analysis

    def get_user_preferences(self, user_id: Optional[int] = None) -> Dict:
        """
        Get user preferences for video quality and sources

        Args:
            user_id: Optional user ID for personalized preferences

        Returns:
            Dictionary with user preferences
        """
        # Default preferences - in a full implementation, these would come from user settings
        default_preferences = {
            "min_quality_score": 50.0,
            "preferred_years": {"min": 2000, "max": 2024},
            "preferred_genres": [
                "pop",
                "rock",
                "hip-hop",
                "electronic",
                "indie",
                "alternative",
            ],
            "require_directors": False,
            "require_thumbnails": True,
            "source_preferences": {
                "high_metadata": 1.0,  # Prefer videos with complete metadata
                "recent_years": 0.8,  # Slight preference for newer videos
                "popular_artists": 0.9,  # Prefer videos from artists with IMVDB profiles
                "complete_production": 0.7,  # Prefer videos with director/producer info
            },
        }

        # In a full implementation, you would query user preferences from database here
        # For now, return defaults
        return default_preferences

    def rank_videos_by_preferences(
        self, videos: List[Dict], user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Rank videos based on user preferences and quality analysis

        Args:
            videos: List of IMVDb video data
            user_id: Optional user ID for personalized ranking

        Returns:
            List of videos ranked by preference score
        """
        preferences = self.get_user_preferences(user_id)
        ranked_videos = []

        for video in videos:
            # Analyze video quality
            quality_analysis = self.analyze_video_quality(video)

            # Calculate preference score
            preference_score = quality_analysis["overall_score"]

            # Apply user preference multipliers
            source_prefs = preferences.get("source_preferences", {})

            # Bonus for high metadata completeness
            if quality_analysis["metadata_completeness"] >= 30:
                preference_score *= source_prefs.get("high_metadata", 1.0)

            # Year preference bonus
            year = video.get("year")
            if year:
                try:
                    year_int = int(year)
                    year_prefs = preferences.get("preferred_years", {})
                    if (
                        year_prefs.get("min", 0)
                        <= year_int
                        <= year_prefs.get("max", 9999)
                    ):
                        preference_score *= source_prefs.get("recent_years", 1.0)
                except (ValueError, TypeError):
                    pass

            # Genre preference bonus
            genre = video.get("genre", "").lower()
            preferred_genres = [
                g.lower() for g in preferences.get("preferred_genres", [])
            ]
            if genre in preferred_genres:
                preference_score *= 1.1

            # Apply minimum quality threshold
            min_quality = preferences.get("min_quality_score", 0)
            if quality_analysis["overall_score"] < min_quality:
                preference_score *= 0.5  # Penalty for low quality

            # Add enhanced video data
            enhanced_video = video.copy()
            enhanced_video.update(
                {
                    "quality_analysis": quality_analysis,
                    "preference_score": preference_score,
                    "meets_quality_threshold": quality_analysis["overall_score"]
                    >= min_quality,
                }
            )

            ranked_videos.append(enhanced_video)

        # Sort by preference score (highest first)
        ranked_videos.sort(key=lambda v: v.get("preference_score", 0), reverse=True)

        logger.info(f"Ranked {len(ranked_videos)} videos by user preferences")
        return ranked_videos

    def get_quality_statistics(self, videos: List[Dict]) -> Dict:
        """
        Get quality statistics for a list of videos

        Args:
            videos: List of videos to analyze

        Returns:
            Dictionary with quality statistics
        """
        if not videos:
            return {"total_videos": 0}

        quality_scores = []
        metadata_scores = []
        production_scores = []
        source_scores = []

        year_distribution = {}
        genre_distribution = {}
        director_count = 0
        thumbnail_count = 0

        for video in videos:
            analysis = self.analyze_video_quality(video)
            quality_scores.append(analysis["overall_score"])
            metadata_scores.append(analysis["metadata_completeness"])
            production_scores.append(analysis["production_quality"])
            source_scores.append(analysis["source_quality"])

            # Year distribution
            year = video.get("year")
            if year:
                try:
                    decade = (int(year) // 10) * 10
                    year_distribution[f"{decade}s"] = (
                        year_distribution.get(f"{decade}s", 0) + 1
                    )
                except (ValueError, TypeError):
                    pass

            # Genre distribution
            genre = video.get("genre", "Unknown").title()
            if genre:
                genre_distribution[genre] = genre_distribution.get(genre, 0) + 1

            # Feature counts
            if video.get("directors"):
                director_count += 1
            if video.get("image") or video.get("image_url"):
                thumbnail_count += 1

        return {
            "total_videos": len(videos),
            "quality_stats": {
                "average_overall": sum(quality_scores) / len(quality_scores),
                "average_metadata": sum(metadata_scores) / len(metadata_scores),
                "average_production": sum(production_scores) / len(production_scores),
                "average_source": sum(source_scores) / len(source_scores),
                "high_quality_count": len([s for s in quality_scores if s >= 70]),
                "medium_quality_count": len(
                    [s for s in quality_scores if 40 <= s < 70]
                ),
                "low_quality_count": len([s for s in quality_scores if s < 40]),
            },
            "feature_stats": {
                "videos_with_directors": director_count,
                "videos_with_thumbnails": thumbnail_count,
                "director_percentage": (director_count / len(videos)) * 100,
                "thumbnail_percentage": (thumbnail_count / len(videos)) * 100,
            },
            "distribution": {
                "by_decade": dict(sorted(year_distribution.items())),
                "by_genre": dict(
                    sorted(genre_distribution.items(), key=lambda x: x[1], reverse=True)
                ),
            },
        }
