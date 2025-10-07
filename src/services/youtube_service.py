"""
MVidarr - YouTube API Service
Handles YouTube API integration for video search and data retrieval
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


class YouTubeService:
    """YouTube API service for video search and metadata"""

    def __init__(self, settings_service):
        self.settings_service = settings_service
        self.base_url = "https://www.googleapis.com/youtube/v3"

    def get_api_key(self) -> Optional[str]:
        """Get YouTube API key from settings"""
        try:
            # Ensure settings cache is loaded
            self.settings_service.load_cache()
            return self.settings_service.get("youtube_api_key")
        except Exception as e:
            logger.warning(f"Failed to get YouTube API key: {e}")
            return None

    def search_videos(self, query: str, max_results: int = 25) -> Dict[str, Any]:
        """Search for videos using YouTube API"""
        api_key = self.get_api_key()

        if not api_key:
            return {
                "success": False,
                "error": "YouTube API key not configured. Please set it in Settings.",
                "results": [],
            }

        try:
            # Prepare search parameters
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": min(max_results, 50),  # API limit
                "key": api_key,
                "order": "relevance",
                "safeSearch": "none",
                "regionCode": "US",
            }

            # Make API request
            url = f"{self.base_url}/search"
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                if "items" in data:
                    logger.info(
                        f"YouTube search successful: {len(data['items'])} results for '{query}'"
                    )
                    return {
                        "success": True,
                        "results": data["items"],
                        "total": len(data["items"]),
                        "query": query,
                    }
                else:
                    logger.warning(f"YouTube search returned no items for '{query}'")
                    return {"success": True, "results": [], "total": 0, "query": query}

            elif response.status_code == 403:
                error_data = response.json()
                error_message = "YouTube API quota exceeded or invalid API key"

                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]

                logger.error(f"YouTube API access denied: {error_message}")
                return {
                    "success": False,
                    "error": f"YouTube API Error: {error_message}",
                    "results": [],
                }

            elif response.status_code == 400:
                error_data = response.json()
                error_message = "Invalid search query"

                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]

                logger.error(f"YouTube API bad request: {error_message}")
                return {
                    "success": False,
                    "error": f"Search Error: {error_message}",
                    "results": [],
                }

            else:
                logger.error(
                    f"YouTube API request failed: {response.status_code} - {response.text}"
                )
                return {
                    "success": False,
                    "error": f"YouTube API request failed (HTTP {response.status_code})",
                    "results": [],
                }

        except requests.exceptions.Timeout:
            logger.error("YouTube API request timed out")
            return {
                "success": False,
                "error": "YouTube API request timed out. Please try again.",
                "results": [],
            }

        except requests.exceptions.ConnectionError:
            logger.error("YouTube API connection error")
            return {
                "success": False,
                "error": "Unable to connect to YouTube API. Check your internet connection.",
                "results": [],
            }

        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return {
                "success": False,
                "error": f"YouTube API error: {str(e)}",
                "results": [],
            }

    def get_video_details(self, video_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific video"""
        api_key = self.get_api_key()

        if not api_key:
            return {"success": False, "error": "YouTube API key not configured"}

        try:
            params = {
                "part": "snippet,contentDetails,statistics",
                "id": video_id,
                "key": api_key,
            }

            url = f"{self.base_url}/videos"
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                if "items" in data and data["items"]:
                    return {"success": True, "video": data["items"][0]}
                else:
                    return {"success": False, "error": "Video not found"}
            else:
                return {
                    "success": False,
                    "error": f"API request failed (HTTP {response.status_code})",
                }

        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return {"success": False, "error": str(e)}

    def search_artist_videos(
        self, artist_name: str, max_results: int = 25
    ) -> Dict[str, Any]:
        """Search for videos by a specific artist"""
        # Add "official" and "music video" to improve results
        search_query = f"{artist_name} official music video"
        return self.search_videos(search_query, max_results)

    def test_api_connection(self) -> Dict[str, Any]:
        """Test YouTube API connection"""
        api_key = self.get_api_key()

        if not api_key:
            return {"success": False, "message": "YouTube API: No API key configured"}

        try:
            # Test with a simple search
            result = self.search_videos("test", 1)

            if result["success"]:
                return {
                    "success": True,
                    "message": "YouTube API: Connected and working",
                }
            else:
                return {"success": False, "message": f'YouTube API: {result["error"]}'}

        except Exception as e:
            return {
                "success": False,
                "message": f"YouTube API: Connection test failed - {str(e)}",
            }


# Convenience instance
from .settings_service import settings

youtube_service = YouTubeService(settings)


async def get_youtube_service() -> YouTubeService:
    """Get global YouTube service instance"""
    return youtube_service
