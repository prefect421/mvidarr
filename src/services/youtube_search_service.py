"""
YouTube Search Service for discovering music videos
"""

import re
from typing import Dict, List, Optional

import requests

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.youtube_search")


class YouTubeSearchService:
    """Service for searching YouTube videos"""

    def __init__(self):
        self.base_url = "https://www.googleapis.com/youtube/v3"

    @property
    def api_key(self):
        """Get YouTube API key from database settings"""
        try:
            return settings.get("youtube_api_key")
        except Exception as e:
            logger.error(f"Failed to get YouTube API key from settings: {e}")
            return None

    def search_artist_videos(self, artist_name: str, limit: int = 50) -> Dict:
        """Search for music videos by artist name"""
        if not self.api_key:
            logger.warning("YouTube API key not configured, skipping YouTube search")
            return {
                "videos": [],
                "total_results": 0,
                "error": "YouTube API key not configured",
            }

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

            return {
                "videos": videos,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "query": search_query,
                "artist_name": artist_name,
            }

        except requests.RequestException as e:
            logger.error(f"YouTube API request failed: {e}")
            return {
                "videos": [],
                "total_results": 0,
                "error": f"YouTube API request failed: {str(e)}",
            }
        except Exception as e:
            logger.error(f"YouTube search failed for artist {artist_name}: {e}")
            return {
                "videos": [],
                "total_results": 0,
                "error": f"YouTube search failed: {str(e)}",
            }

    def _get_video_details(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed information for multiple videos"""
        if not video_ids or not self.api_key:
            return {}

        try:
            url = f"{self.base_url}/videos"
            params = {
                "part": "contentDetails,statistics,snippet",
                "id": ",".join(video_ids),
                "key": self.api_key,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            video_details = {}

            for video in data.get("items", []):
                video_id = video.get("id")
                content_details = video.get("contentDetails", {})
                statistics = video.get("statistics", {})
                snippet = video.get("snippet", {})

                video_details[video_id] = {
                    "duration": content_details.get("duration"),
                    "view_count": statistics.get("viewCount"),
                    "like_count": statistics.get("likeCount"),
                    "comment_count": statistics.get("commentCount"),
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId"),
                }

            return video_details

        except Exception as e:
            logger.error(f"Failed to get video details: {e}")
            return {}

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
        """Search for a specific video by title and optionally artist"""
        if not self.api_key:
            return {
                "videos": [],
                "total_results": 0,
                "error": "YouTube API key not configured",
            }

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

            return {
                "videos": videos,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "query": search_query,
            }

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
        """Search for artist's channel thumbnail on YouTube"""
        if not self.api_key:
            logger.warning(
                "YouTube API key not configured, skipping YouTube channel search"
            )
            return None

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
                            return thumbnail_url

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
