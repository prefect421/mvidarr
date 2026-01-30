"""
YouTube Search Service for discovering music videos
"""

import re
from typing import Dict, List, Optional

import requests

from src.services.settings_service import settings
from src.utils.logger import get_logger
from src.utils.youtube_cache import get_youtube_cache
from src.utils.youtube_quota_tracker import track_youtube_api_call

logger = get_logger("mvidarr.services.youtube_search")


class YouTubeSearchService:
    """Service for searching YouTube videos"""

    def __init__(self):
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self._cache = get_youtube_cache()
        self._api_key = None  # Cached API key

    @property
    def api_key(self):
        """Get YouTube API key from database settings (cached)"""
        if self._api_key is None:
            try:
                self._api_key = settings.get("youtube_api_key")
            except Exception as e:
                logger.error(f"Failed to get YouTube API key from settings: {e}")
                return None
        return self._api_key

    def search_artist_videos(self, artist_name: str, limit: int = 50) -> Dict:
        """Search for music videos by artist name (with caching)"""
        if not self.api_key:
            logger.warning("YouTube API key not configured, skipping YouTube search")
            return {
                "videos": [],
                "total_results": 0,
                "error": "YouTube API key not configured",
            }

        # Check cache first
        cache_params = {"artist_name": artist_name, "limit": limit}
        cached_result = self._cache.get("search", cache_params)
        if cached_result is not None:
            logger.info(f"Using cached search results for artist: {artist_name}")
            return cached_result

        try:
            # Search for music videos by artist
            search_query = f"{artist_name} music video"

            url = f"{self.base_url}/search"
            params = {
                "part": "snippet",
                "q": search_query,
                "type": "video",
                "videoCategoryId": "10",  # Music category
                "videoDefinition": "any",
                "order": "relevance",
                "maxResults": min(limit, 50),  # YouTube API limit is 50
                "key": self.api_key,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Track quota usage for search API call
            track_youtube_api_call("search", count=1)

            data = response.json()
            videos = []

            # Get video IDs for detailed info
            video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
            video_details = self._get_video_details(video_ids) if video_ids else {}

            for item in data.get("items", []):
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]
                details = video_details.get(video_id, {})

                # Extract video metadata
                video_info = {
                    "youtube_id": video_id,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel_title": snippet.get("channelTitle"),
                    "channel_id": snippet.get("channelId"),
                    "published_at": snippet.get("publishedAt"),
                    "thumbnail_url": snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url"),
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": self._parse_duration(details.get("duration")),
                    "view_count": details.get("view_count"),
                    "like_count": details.get("like_count"),
                    "tags": details.get("tags", []),
                    "source": "youtube_search",
                    "search_score": self._calculate_relevance_score(
                        snippet.get("title", ""), artist_name
                    ),
                }

                videos.append(video_info)

            # Sort by relevance score
            videos.sort(key=lambda x: x.get("search_score", 0), reverse=True)

            logger.info(f"Found {len(videos)} YouTube videos for artist: {artist_name}")

            result = {
                "videos": videos,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "query": search_query,
                "artist_name": artist_name,
            }

            # Cache the result for 3 hours
            self._cache.set("search", cache_params, result)

            return result

        except requests.RequestException as e:
            # Sanitize error message to remove API key from URL
            error_msg = str(e)
            if self.api_key and self.api_key in error_msg:
                error_msg = error_msg.replace(self.api_key, "***API_KEY***")

            logger.error(f"YouTube API request failed: {error_msg}")
            return {
                "videos": [],
                "total_results": 0,
                "error": f"YouTube API request failed: {error_msg}",
            }
        except Exception as e:
            # Sanitize error message to remove API key
            error_msg = str(e)
            if self.api_key and self.api_key in error_msg:
                error_msg = error_msg.replace(self.api_key, "***API_KEY***")

            logger.error(f"YouTube search failed for artist {artist_name}: {error_msg}")
            return {
                "videos": [],
                "total_results": 0,
                "error": f"YouTube search failed: {error_msg}",
            }

    def _get_video_details(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed information for multiple videos (with caching)"""
        if not video_ids or not self.api_key:
            return {}

        # Check cache for each video
        video_details = {}
        uncached_ids = []

        for video_id in video_ids:
            cache_params = {"video_id": video_id}
            cached_details = self._cache.get("video_details", cache_params)
            if cached_details is not None:
                video_details[video_id] = cached_details
            else:
                uncached_ids.append(video_id)

        # If all videos were cached, return immediately
        if not uncached_ids:
            logger.debug(f"All {len(video_ids)} video details retrieved from cache")
            return video_details

        # Fetch uncached videos from API
        try:
            url = f"{self.base_url}/videos"
            params = {
                "part": "contentDetails,statistics,snippet",
                "id": ",".join(uncached_ids),
                "key": self.api_key,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Track quota usage for video details API call
            track_youtube_api_call("video_details", count=1)

            data = response.json()

            for video in data.get("items", []):
                video_id = video.get("id")
                content_details = video.get("contentDetails", {})
                statistics = video.get("statistics", {})
                snippet = video.get("snippet", {})

                details = {
                    "duration": content_details.get("duration"),
                    "view_count": statistics.get("viewCount"),
                    "like_count": statistics.get("likeCount"),
                    "comment_count": statistics.get("commentCount"),
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId"),
                }

                video_details[video_id] = details

                # Cache individual video details for 24 hours
                cache_params = {"video_id": video_id}
                self._cache.set("video_details", cache_params, details)

            logger.info(
                f"Fetched {len(uncached_ids)} video details from API, "
                f"{len(video_ids) - len(uncached_ids)} from cache"
            )

            return video_details

        except Exception as e:
            logger.error(f"Failed to get video details: {e}")
            return video_details  # Return cached videos even if API call fails

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse YouTube duration string to seconds"""
        if not duration_str:
            return None

        try:
            # YouTube returns duration in ISO 8601 format (PT4M13S)
            match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
            if match:
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                return hours * 3600 + minutes * 60 + seconds
        except:
            pass

        return None

    def _calculate_relevance_score(self, title: str, artist_name: str) -> float:
        """Calculate relevance score based on title and artist name match"""
        if not title or not artist_name:
            return 0.0

        title_lower = title.lower()
        artist_lower = artist_name.lower()

        score = 0.0

        # Exact artist name match
        if artist_lower in title_lower:
            score += 1.0

        # Artist name words match
        artist_words = artist_lower.split()
        for word in artist_words:
            if len(word) > 2 and word in title_lower:
                score += 0.3

        # Music video indicators
        music_indicators = [
            "music video",
            "official video",
            "official music video",
            "mv",
            "clip",
        ]
        for indicator in music_indicators:
            if indicator in title_lower:
                score += 0.5

        # Official channel indicators
        official_indicators = ["official", "vevo"]
        for indicator in official_indicators:
            if indicator in title_lower:
                score += 0.3

        return round(score, 2)

    def search_video_by_title(
        self, title: str, artist_name: str = None, limit: int = 10
    ) -> Dict:
        """Search for a specific video by title and optionally artist (with caching)"""
        if not self.api_key:
            return {
                "videos": [],
                "total_results": 0,
                "error": "YouTube API key not configured",
            }

        # Check cache first
        cache_params = {"title": title, "artist_name": artist_name, "limit": limit}
        cached_result = self._cache.get("search", cache_params)
        if cached_result is not None:
            logger.debug(f"Using cached search results for title: {title}")
            return cached_result

        try:
            # Construct search query
            search_query = title
            if artist_name:
                search_query = f"{artist_name} {title}"

            url = f"{self.base_url}/search"
            params = {
                "part": "snippet",
                "q": search_query,
                "type": "video",
                "videoCategoryId": "10",  # Music category
                "order": "relevance",
                "maxResults": min(limit, 25),
                "key": self.api_key,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Track quota usage for search API call
            track_youtube_api_call("search", count=1)

            data = response.json()
            videos = []

            # Get video IDs for detailed info
            video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
            video_details = self._get_video_details(video_ids) if video_ids else {}

            for item in data.get("items", []):
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]
                details = video_details.get(video_id, {})

                video_info = {
                    "youtube_id": video_id,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel_title": snippet.get("channelTitle"),
                    "channel_id": snippet.get("channelId"),
                    "published_at": snippet.get("publishedAt"),
                    "thumbnail_url": snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url"),
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": self._parse_duration(details.get("duration")),
                    "view_count": details.get("view_count"),
                    "like_count": details.get("like_count"),
                    "tags": details.get("tags", []),
                    "source": "youtube_search",
                    "search_score": self._calculate_title_match_score(
                        snippet.get("title", ""), title, artist_name
                    ),
                }

                videos.append(video_info)

            # Sort by relevance score
            videos.sort(key=lambda x: x.get("search_score", 0), reverse=True)

            result = {
                "videos": videos,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "query": search_query,
            }

            # Cache the result for 3 hours
            self._cache.set("search", cache_params, result)

            return result

        except Exception as e:
            logger.error(f"YouTube title search failed: {e}")
            return {
                "videos": [],
                "total_results": 0,
                "error": f"YouTube search failed: {str(e)}",
            }

    def _calculate_title_match_score(
        self, video_title: str, search_title: str, artist_name: str = None
    ) -> float:
        """Calculate relevance score for title-based search"""
        if not video_title or not search_title:
            return 0.0

        video_lower = video_title.lower()
        search_lower = search_title.lower()

        score = 0.0

        # Exact title match
        if search_lower in video_lower:
            score += 2.0

        # Title words match
        search_words = search_lower.split()
        for word in search_words:
            if len(word) > 2 and word in video_lower:
                score += 0.4

        # Artist name match if provided
        if artist_name:
            artist_lower = artist_name.lower()
            if artist_lower in video_lower:
                score += 1.0

        # Music video indicators
        music_indicators = ["music video", "official video", "official music video"]
        for indicator in music_indicators:
            if indicator in video_lower:
                score += 0.5

        return round(score, 2)

    def search_artist_channel_thumbnail(self, artist_name: str) -> Optional[str]:
        """Search for artist's channel thumbnail on YouTube (with caching - 7 days TTL)"""
        if not self.api_key:
            logger.warning(
                "YouTube API key not configured, skipping YouTube channel search"
            )
            return None

        # Check cache first (thumbnails rarely change, cache for 7 days)
        cache_params = {"artist_name": artist_name}
        cached_thumbnail = self._cache.get("channel", cache_params)
        if cached_thumbnail is not None:
            logger.debug(f"Using cached channel thumbnail for: {artist_name}")
            return cached_thumbnail

        try:
            # Search for channels matching the artist name
            url = f"{self.base_url}/search"
            params = {
                "part": "snippet",
                "q": artist_name,
                "type": "channel",
                "order": "relevance",
                "maxResults": 5,
                "key": self.api_key,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Track quota usage for channel search
            track_youtube_api_call("channel", count=1)

            data = response.json()

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                channel_title = snippet.get("title", "").lower()
                artist_name_lower = artist_name.lower()

                # Check if channel title matches artist name closely
                if artist_name_lower in channel_title or any(
                    word in channel_title
                    for word in artist_name_lower.split()
                    if len(word) > 2
                ):
                    # Get channel thumbnail
                    thumbnails = snippet.get("thumbnails", {})
                    if thumbnails:
                        # Prefer higher resolution: high > medium > default
                        thumbnail_url = (
                            thumbnails.get("high", {}).get("url")
                            or thumbnails.get("medium", {}).get("url")
                            or thumbnails.get("default", {}).get("url")
                        )

                        if thumbnail_url:
                            logger.info(
                                f"Found YouTube channel thumbnail for {artist_name}: {thumbnail_url}"
                            )
                            # Cache the thumbnail for 7 days
                            self._cache.set("channel", cache_params, thumbnail_url)
                            return thumbnail_url

            # Cache the "not found" result for 24 hours to avoid repeated API calls
            self._cache.set("channel", cache_params, None, ttl=24*3600)
            return None

        except requests.RequestException as e:
            logger.error(f"YouTube channel search API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"YouTube channel search failed for artist {artist_name}: {e}")
            return None


# Global instance
youtube_search_service = YouTubeSearchService()


# Standalone function for easier importing
def search_artist_channel_thumbnail(artist_name: str) -> Optional[str]:
    """Search for artist's channel thumbnail on YouTube"""
    return youtube_search_service.search_artist_channel_thumbnail(artist_name)
